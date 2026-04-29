"""
Shared Cock fight round settlement (COCK1 / COCK2 / DRAW) — used by API and game-admin UI.
"""
from django.db import transaction
from django.utils import timezone

from .models import CockFightSession, CockFightBet, CockFightRoundVideo
from accounts.models import Wallet, Transaction
from .utils import get_redis_client, normalize_cockfight_side, cockfight_side_labels_dict, cockfight_side_display

VALID_WINNERS = ('COCK1', 'COCK2', 'DRAW')


def run_meron_wala_settlement(round_id: int, winner: str):
    """
    Settle an open CockFightSession. ``winner`` must be COCK1, COCK2, or DRAW
    (MERON/WALA accepted as legacy aliases).
    """
    w = normalize_cockfight_side(winner)
    if w not in VALID_WINNERS:
        return {'error': 'winner must be COCK1, COCK2, or DRAW'}, 400

    with transaction.atomic():
        session = CockFightSession.objects.select_for_update().filter(
            video_round_id=round_id, status='OPEN'
        ).first()
        if not session:
            # Legacy rows before video_round existed — settle by session pk
            session = CockFightSession.objects.select_for_update().filter(
                pk=round_id, status='OPEN'
            ).first()
        if not session:
            return {'error': f'Round {round_id} not found'}, 404

        session.status = 'SETTLED'
        session.winner = w
        session.settled_at = timezone.now()
        session.save(update_fields=['status', 'winner', 'settled_at'])

        bets = CockFightBet.objects.select_for_update().filter(session=session, status='PENDING')
        r = get_redis_client()
        for bet in bets:
            if bet.side == w:
                bet.status = 'WON'
                bet.payout_amount = bet.potential_payout
                bet.settled_at = timezone.now()
                bet.save(update_fields=['status', 'payout_amount', 'settled_at'])
                wallet = Wallet.objects.select_for_update().get(user=bet.user)
                balance_before = int(wallet.balance)
                wallet.balance = balance_before + int(bet.potential_payout)
                wallet.save(update_fields=['balance'])
                balance_after = int(wallet.balance)
                Transaction.objects.create(
                    user=bet.user,
                    transaction_type='WIN',
                    amount=int(bet.potential_payout),
                    balance_before=balance_before,
                    balance_after=balance_after,
                    description=f'Cock fight win bet #{bet.pk} — result {w}',
                )
                if r:
                    try:
                        r.set(f'user_balance:{bet.user_id}', str(wallet.balance), ex=86400)
                    except Exception:
                        pass
            else:
                bet.status = 'LOST'
                bet.payout_amount = 0
                bet.settled_at = timezone.now()
                bet.save(update_fields=['status', 'payout_amount', 'settled_at'])

    labels_video = None
    if session.video_round_id:
        labels_video = CockFightRoundVideo.objects.filter(pk=session.video_round_id).only(
            'label_cock1', 'label_cock2'
        ).first()
    sl = cockfight_side_labels_dict(labels_video)
    return {
        'success': True,
        'round_id': session.video_round_id,
        'winner': w,
        'winner_label': cockfight_side_display(w, sl),
    }, 200
