import json
import logging
import time
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import F
from django.utils import timezone
from django.utils.dateparse import parse_datetime
import redis
from django.conf import settings
from game.models import GameRound, Bet, DiceResult, UserDailyTurnover
from game.utils import get_leaderboard_period_date
from accounts.models import Wallet, Transaction, User

logger = logging.getLogger('game.bet_worker')

class Command(BaseCommand):
    help = 'Process bets from Redis Stream (bet_stream) using consumer group and write to Database in batches'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('Starting Bet Queue Worker...'))
        
        # Setup Redis with tiered failover
        from game.utils import get_redis_client
        redis_client = get_redis_client()
        
        if not redis_client:
            self.stdout.write(self.style.ERROR('Redis connection failed on all hosts'))
            return
            
        self.stdout.write(self.style.SUCCESS('✅ Redis connected successfully'))

        STREAM_NAME = "round_events_stream"
        EVENT_GROUP = "event_worker_group"
        BET_STREAM = "bet_stream"
        BET_GROUP = "worker_group"
        CONSUMER_NAME = f"worker_{time.time()}"
        
        # Create groups
        for stream, group in [(STREAM_NAME, EVENT_GROUP), (BET_STREAM, BET_GROUP)]:
            try:
                redis_client.xgroup_create(stream, group, id='0', mkstream=True)
                self.stdout.write(self.style.SUCCESS(f'✅ Created consumer group {group} on {stream}'))
            except redis.exceptions.ResponseError as e:
                if 'BUSYGROUP' not in str(e):
                    self.stdout.write(self.style.WARNING(f'Note: {e}'))

        while True:
            try:
                # 1. ALWAYS process Game Events first
                events = redis_client.xreadgroup(EVENT_GROUP, CONSUMER_NAME, {STREAM_NAME: '>'}, count=5, block=10)
                if events:
                    for stream, messages in events:
                        for message_id, data in messages:
                            event_type = data.get('type')
                            round_id = data.get('round_id')
                            try:
                                from django.db import connections
                                connections.close_all()
                                with transaction.atomic():
                                    if event_type == 'round_start':
                                        start_time_str = data.get('start_time')
                                        durations = json.loads(data.get('durations', '{}'))
                                        start_dt = None
                                        try:
                                            if start_time_str:
                                                start_dt = parse_datetime(start_time_str)
                                        except Exception:
                                            start_dt = None
                                        if start_dt is None:
                                            start_dt = timezone.now()
                                        if timezone.is_naive(start_dt):
                                            start_dt = timezone.make_aware(start_dt)
                                        GameRound.objects.get_or_create(
                                            round_id=round_id,
                                            defaults={
                                                'status': 'BETTING',
                                                'start_time': start_dt,
                                                'betting_close_seconds': durations.get('betting_close_time', 30),
                                                'dice_roll_seconds': durations.get('dice_roll_time', 35),
                                                'dice_result_seconds': durations.get('dice_result_time', 45),
                                                'round_end_seconds': durations.get('round_end_time', 70)
                                            }
                                        )
                                        self.stdout.write(self.style.SUCCESS(f"Created Round {round_id}"))
                                    elif event_type == 'round_result':
                                        result = data.get('result')
                                        dice_values = json.loads(data.get('dice_values', '[]'))
                                        end_time_str = data.get('end_time')
                                        end_dt = None
                                        try:
                                            if end_time_str:
                                                end_dt = parse_datetime(end_time_str)
                                        except Exception:
                                            end_dt = None
                                        if end_dt is None:
                                            end_dt = timezone.now()
                                        if timezone.is_naive(end_dt):
                                            end_dt = timezone.make_aware(end_dt)
                                        round_obj = GameRound.objects.get(round_id=round_id)
                                        round_obj.status = 'RESULT'
                                        round_obj.dice_result = result
                                        round_obj.result_time = end_dt
                                        if len(dice_values) == 6:
                                            for i, val in enumerate(dice_values, 1):
                                                setattr(round_obj, f'dice_{i}', val)
                                        round_obj.save()
                                        DiceResult.objects.update_or_create(round=round_obj, defaults={'result': result})
                                        from game.views import calculate_payouts
                                        calculate_payouts(round_obj, dice_result=result, dice_values=dice_values)
                                        self.stdout.write(self.style.SUCCESS(f"Settled Round {round_id}"))
                                    redis_client.xack(STREAM_NAME, EVENT_GROUP, message_id)
                            except Exception as e:
                                logger.error(f"Event error {event_type} {round_id}: {e}")

                # 2. Process Bets
                messages = redis_client.xreadgroup(BET_GROUP, CONSUMER_NAME, {BET_STREAM: '>'}, count=20, block=10)
                if not messages:
                    # Check for pending (stuck) bets
                    pending = redis_client.xpending(BET_STREAM, BET_GROUP)
                    if pending and pending['pending'] > 0:
                        messages = redis_client.xreadgroup(BET_GROUP, f"{CONSUMER_NAME}_rec", {BET_STREAM: '0'}, count=10, block=1)

                if messages:
                    for stream, msg_list in messages:
                        bets_to_process = []
                        message_ids = []
                        for msg_id, data in msg_list:
                            bets_to_process.append(data)
                            message_ids.append(msg_id)
                        
                        ack_ids = []
                        from django.db import connections
                        connections.close_all()
                        with transaction.atomic():
                            for idx, bet_data in enumerate(bets_to_process):
                                try:
                                    event_type = bet_data.get('type', 'place_bet')
                                    round_id = bet_data['round_id']
                                    try:
                                        if round_id == 'WITHDRAW':
                                            # Special case for withdrawals which don't have a game round
                                            round_obj = None
                                        else:
                                            round_obj = GameRound.objects.get(round_id=round_id)
                                    except GameRound.DoesNotExist:
                                        logger.warning(f"Round {round_id} not found, skipping for now")
                                        continue
                                    
                                    user_id = int(bet_data['user_id'])
                                    
                                    if event_type == 'place_bet':
                                        number = int(bet_data['number'])
                                        chip_amount = Decimal(bet_data['chip_amount'])
                                        
                                        # Update wallet (deduct releases unavaliable_balance when betting)
                                        wallet = Wallet.objects.select_for_update().get(user_id=user_id)
                                        bal_before = wallet.balance
                                        if not wallet.deduct(chip_amount):
                                            logger.warning(f"Insufficient balance for user {user_id}, bet skipped")
                                            ack_ids.append(message_ids[idx])  # ack to avoid infinite retry
                                            continue
                                        
                                        # Create bet record
                                        bet = Bet.objects.create(user_id=user_id, round=round_obj, number=number, chip_amount=chip_amount)
                                        
                                        # Store the DB ID back in Redis for strict removal
                                        redis_client.setex(f"bet_msg_to_id:{message_ids[idx]}", 3600, str(bet.id))

                                        # Update turnover (deduct handles balance and unavaliable_balance)
                                        Wallet.objects.filter(user_id=user_id).update(turnover=F('turnover') + chip_amount)
                                        
                                        # Update daily leaderboard turnover (cached to avoid aggregating Bet on each API call)
                                        period_date = get_leaderboard_period_date(bet.created_at)
                                        udt, created = UserDailyTurnover.objects.get_or_create(
                                            user_id=user_id, period_date=period_date, defaults={'turnover': 0}
                                        )
                                        if created:
                                            udt.turnover = int(chip_amount)
                                            udt.save()
                                        else:
                                            UserDailyTurnover.objects.filter(pk=udt.pk).update(turnover=F('turnover') + int(chip_amount))
                                        
                                        # Transaction log
                                        Transaction.objects.create(
                                            user_id=user_id, transaction_type='BET', amount=chip_amount,
                                            balance_before=bal_before, balance_after=wallet.balance,
                                            description=f"Bet on {number} in round {round_id}"
                                        )
                                    
                                    elif event_type == 'remove_bet':
                                        refund_amount = Decimal(bet_data['refund_amount'])
                                        msg_id_to_remove = bet_data.get('msg_id')
                                        
                                        # Get bet before delete so we can compute leaderboard period_date
                                        bet_id = redis_client.get(f"bet_msg_to_id:{msg_id_to_remove}")
                                        bet_for_period = None
                                        if bet_id:
                                            bet_for_period = Bet.objects.filter(id=int(bet_id)).first()
                                        if not bet_for_period:
                                            number = int(bet_data.get('number', 0))
                                            bet_for_period = Bet.objects.filter(
                                                user_id=user_id,
                                                round=round_obj,
                                                number=number,
                                                chip_amount=refund_amount
                                            ).order_by('-created_at').first()
                                            if bet_for_period:
                                                bet_id = str(bet_for_period.id)
                                        period_date = get_leaderboard_period_date(bet_for_period.created_at) if bet_for_period else None
                                        
                                        # 1. Update DB Wallet atomically (Refund: balance + amount, turnover - amount)
                                        Wallet.objects.filter(user_id=user_id).update(
                                            balance=F('balance') + refund_amount,
                                            turnover=F('turnover') - refund_amount
                                        )
                                        
                                        # 2. Delete the bet record from DB strictly by ID
                                        if bet_id:
                                            Bet.objects.filter(id=int(bet_id)).delete()
                                            redis_client.delete(f"bet_msg_to_id:{msg_id_to_remove}")
                                        
                                        # 3. Update daily leaderboard turnover
                                        if period_date is not None:
                                            UserDailyTurnover.objects.filter(
                                                user_id=user_id, period_date=period_date
                                            ).update(turnover=F('turnover') - int(refund_amount))
                                        
                                        # 4. Transaction log
                                        bal_after = Decimal(redis_client.get(f"user_balance:{user_id}") or 0)
                                        Transaction.objects.create(
                                            user_id=user_id, transaction_type='REFUND', amount=refund_amount,
                                            balance_before=bal_after - refund_amount, balance_after=bal_after,
                                            description=f"Refund for removed bet in round {round_id}"
                                        )

                                    elif event_type == 'approve_withdraw':
                                        withdraw_id = bet_data.get('withdraw_id')
                                        amount = Decimal(bet_data['amount'])
                                        
                                        # 1. Update DB Wallet atomically
                                        # Note: For approve_withdraw, money is already deducted if it came from initiate_withdraw
                                        # but we keep this for backward compatibility or direct approvals
                                        # However, we check if it was already deducted by looking at the transaction log or status
                                        
                                        # 2. Update Withdrawal Request status
                                        WithdrawRequest.objects.filter(id=withdraw_id).update(
                                            status='COMPLETED',
                                            processed_at=timezone.now()
                                        )
                                        
                                        # 3. Transaction log (only if not already created)
                                        if not Transaction.objects.filter(user_id=user_id, description__icontains=f"#{withdraw_id}").exists():
                                            bal_after = Decimal(redis_client.get(f"user_balance:{user_id}") or 0)
                                            Transaction.objects.create(
                                                user_id=user_id, transaction_type='WITHDRAW', amount=amount,
                                                balance_before=bal_after + amount, balance_after=bal_after,
                                                description=f"Withdraw approved and completed #{withdraw_id}"
                                            )

                                    elif event_type == 'initiate_withdraw':
                                        withdraw_id = bet_data.get('withdraw_id')
                                        amount = Decimal(bet_data['amount'])
                                        
                                        # 1. Update DB Wallet atomically (Deduct money immediately)
                                        Wallet.objects.filter(user_id=user_id).update(balance=F('balance') - amount)
                                        
                                        # 2. Transaction log
                                        bal_after = Decimal(redis_client.get(f"user_balance:{user_id}") or 0)
                                        Transaction.objects.create(
                                            user_id=user_id, transaction_type='WITHDRAW', amount=amount,
                                            balance_before=bal_after + amount, balance_after=bal_after,
                                            description=f"Withdrawal initiated and funds locked #{withdraw_id}"
                                        )

                                    elif event_type == 'reject_withdraw_refund':
                                        withdraw_id = bet_data.get('withdraw_id')
                                        amount = Decimal(bet_data['amount'])
                                        note = bet_data.get('note', '')
                                        
                                        # 1. Update DB Wallet atomically (Refund money)
                                        Wallet.objects.filter(user_id=user_id).update(balance=F('balance') + amount)
                                        
                                        # 2. Transaction log
                                        bal_after = Decimal(redis_client.get(f"user_balance:{user_id}") or 0)
                                        description = f"Withdrawal rejected, funds refunded #{withdraw_id}"
                                        if note:
                                            description += f". Note: {note}"
                                            
                                        Transaction.objects.create(
                                            user_id=user_id, transaction_type='REFUND', amount=amount,
                                            balance_before=bal_after - amount, balance_after=bal_after,
                                            description=description
                                        )

                                    ack_ids.append(message_ids[idx])
                                except Exception as e:
                                    logger.error(f"Bet error: {e}")
                        
                        if ack_ids:
                            redis_client.xack(BET_STREAM, BET_GROUP, *ack_ids)
                            self.stdout.write(self.style.SUCCESS(f"Processed {len(ack_ids)} bets"))

                if not events and not messages:
                    time.sleep(0.1)

            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Worker Error: {e}"))
                time.sleep(1)
