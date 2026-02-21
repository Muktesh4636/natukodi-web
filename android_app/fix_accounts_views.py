import os

with open('accounts_views_server_full.py', 'r') as f:
    lines = f.readlines()

new_lines = []
for line in lines:
    # 1. Fix referral_data path error
    if "path('api/auth/referral-data/', accounts_views.referral_data, name='referral_data')," in line:
        # This is in urls.py, not views.py. We need to make sure referral_data is in views.py.
        pass
    
    # 2. Fix the missing approve_deposit_request error
    # We will add the missing functions at the end of the file
    new_lines.append(line)

# Add missing functions if they are truly missing
views_content = "".join(new_lines)

# Add RewardProbability model to imports if not there
if 'RewardProbability' not in views_content:
    views_content = views_content.replace(
        'from .models import User, Wallet, Transaction, DepositRequest, WithdrawRequest, PaymentMethod, UserBankDetail, DailyReward, LuckyDraw',
        'from .models import User, Wallet, Transaction, DepositRequest, WithdrawRequest, PaymentMethod, UserBankDetail, DailyReward, LuckyDraw, RewardProbability'
    )

# Add missing admin views to accounts/views.py if they were expected there
if 'def approve_deposit_request' not in views_content:
    views_content += """

@api_view(['POST'])
@permission_classes([IsAdminUser])
def approve_deposit_request(request, pk):
    \"\"\"Admin approves a pending deposit request\"\"\"
    note = request.data.get('note', '')
    try:
        with db_transaction.atomic():
            deposit = DepositRequest.objects.select_for_update().get(pk=pk)
            if deposit.status != 'PENDING':
                return Response({'error': 'Deposit request already processed'}, status=400)

            wallet, _ = Wallet.objects.get_or_create(user=deposit.user)
            wallet = Wallet.objects.select_for_update().get(pk=wallet.pk)
            balance_before = wallet.balance
            wallet.add(deposit.amount, is_bonus=True)
            wallet.save()

            if redis_client:
                try:
                    redis_client.set(f"user_balance:{deposit.user.id}", str(wallet.balance), ex=3600)
                except: pass

            Transaction.objects.create(
                user=deposit.user,
                transaction_type='DEPOSIT',
                amount=deposit.amount,
                balance_before=balance_before,
                balance_after=wallet.balance,
                description=f"Manual deposit #{deposit.id}",
            )

            deposit.status = 'APPROVED'
            deposit.admin_note = note
            deposit.processed_by = request.user
            deposit.processed_at = timezone.now()
            deposit.save()
            
            # Referral logic...
            if deposit.user.referred_by:
                from .referral_logic import calculate_referral_bonus, check_and_award_milestone_bonus
                bonus = calculate_referral_bonus(deposit.amount)
                if bonus > 0:
                    referrer = deposit.user.referred_by
                    ref_wallet, _ = Wallet.objects.get_or_create(user=referrer)
                    ref_wallet = Wallet.objects.select_for_update().get(pk=ref_wallet.pk)
                    ref_bal_before = ref_wallet.balance
                    ref_wallet.add(bonus, is_bonus=True)
                    ref_wallet.save()
                    if redis_client:
                        try: redis_client.set(f"user_balance:{referrer.id}", str(ref_wallet.balance), ex=3600)
                        except: pass
                    Transaction.objects.create(user=referrer, transaction_type='REFERRAL_BONUS', amount=bonus, balance_before=ref_bal_before, balance_after=ref_wallet.balance, description=f"Referral bonus from {deposit.user.username}")
                    check_and_award_milestone_bonus(referrer)

        return Response({'message': 'Approved'})
    except Exception as e:
        return Response({'error': str(e)}, status=500)

@api_view(['POST'])
@permission_classes([IsAdminUser])
def reject_deposit_request(request, pk):
    \"\"\"Admin rejects a pending deposit request\"\"\"
    note = request.data.get('note', '')
    try:
        deposit = DepositRequest.objects.get(pk=pk)
        if deposit.status != 'PENDING':
            return Response({'error': 'Already processed'}, status=400)
        deposit.status = 'REJECTED'
        deposit.admin_note = note
        deposit.processed_by = request.user
        deposit.processed_at = timezone.now()
        deposit.save()
        return Response({'message': 'Rejected'})
    except Exception as e:
        return Response({'error': str(e)}, status=500)
"""

with open('accounts_views_fixed.py', 'w') as f:
    f.write(views_content)
