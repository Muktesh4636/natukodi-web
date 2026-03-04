#!/usr/bin/env python3
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PatchResult:
    path: str
    changed: bool
    message: str


def insert_block_before_def(text: str, *, def_name: str, block: str, marker: str) -> tuple[str, bool, str]:
    if marker in text:
        return text, False, "already patched"

    lines = text.splitlines(True)
    idx_def = None
    for i, line in enumerate(lines):
        if line.startswith(f"def {def_name}"):
            idx_def = i
            break
    if idx_def is None:
        return text, False, f"could not find def {def_name}"

    idx_insert = idx_def
    while idx_insert > 0 and lines[idx_insert - 1].lstrip().startswith("@"):
        idx_insert -= 1

    out = "".join(lines[:idx_insert] + [block] + lines[idx_insert:])
    return out, True, "patched"


def insert_line_before(text: str, *, contains: str, line_to_insert: str, marker: str) -> tuple[str, bool, str]:
    if marker in text or line_to_insert in text:
        return text, False, "already patched"

    lines = text.splitlines(True)
    idx = None
    for i, line in enumerate(lines):
        if contains in line:
            idx = i
            break
    if idx is None:
        return text, False, f"could not find line containing: {contains}"

    out = "".join(lines[:idx] + [line_to_insert] + lines[idx:])
    return out, True, "patched"


DELETE_LAST_BET_MARKER = "def delete_last_bet(request):"

DELETE_LAST_BET_BLOCK = """

@csrf_exempt
@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def delete_last_bet(request):
    \"\"\"Undo the most recent bet (last wager) for current round.

    The client calls DELETE /api/game/bet/last/. We implement this as an "undo last wager"
    using the most recent BET Transaction for the current round, then refund that amount and
    decrement the corresponding Bet.chip_amount. This matches per-click betting (each wager
    creates a BET Transaction) even though Bet rows are aggregated per number.
    \"\"\"
    logger.info(f"Delete last bet request by user {request.user.username} (ID: {request.user.id})")

    # Get current round (prefer Redis, fallback to DB)
    round_obj = None
    timer = 0

    if redis_client:
        try:
            round_data = redis_client.get("current_round")
            if round_data:
                round_data = json.loads(round_data)
                timer = int(redis_client.get("round_timer") or "0")
                try:
                    round_obj = GameRound.objects.get(round_id=round_data["round_id"])
                except GameRound.DoesNotExist:
                    pass
        except Exception as e:
            logger.error(f"Redis error in delete_last_bet: {e}")

    if not round_obj:
        round_obj = GameRound.objects.order_by("-start_time").first()
        if not round_obj:
            logger.warning(f"Delete last bet failed for user {request.user.username}: No active round")
            return Response({"error": "No active round"}, status=status.HTTP_400_BAD_REQUEST)

    if not redis_client or timer == 0:
        timer = calculate_current_timer(round_obj.start_time)

    betting_close_time = get_game_setting("BETTING_CLOSE_TIME", 30)
    round_end_time = get_game_setting("ROUND_END_TIME", 80)

    is_within_betting_window = timer < betting_close_time
    is_round_active = round_obj.status in ["BETTING", "WAITING"] or (round_obj.status == "RESULT" and timer < betting_close_time)

    elapsed_total = (timezone.now() - round_obj.start_time).total_seconds()
    if elapsed_total >= round_end_time:
        logger.warning(f"Delete last bet failed for user {request.user.username}: Round {round_obj.round_id} has ended")
        return Response({"error": "Round has ended. Please refresh to see the new round."}, status=status.HTTP_400_BAD_REQUEST)

    if not is_within_betting_window or not is_round_active:
        if timer >= betting_close_time:
            return Response(
                {"error": f"Betting period has ended. Betting closes at {betting_close_time} seconds."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response({"error": "Betting is closed"}, status=status.HTTP_400_BAD_REQUEST)

    # Find most recent BET transaction for this round and parse its number
    bet_txn = Transaction.objects.filter(
        user=request.user,
        transaction_type="BET",
        description__contains=f"round {round_obj.round_id}",
    ).order_by("-created_at").first()

    if not bet_txn:
        return Response({"error": "No bet found to remove"}, status=status.HTTP_404_NOT_FOUND)

    import re

    m = re.search(r"Bet on number (\\d+)", bet_txn.description or "")
    if not m:
        return Response({"error": "Could not determine bet number to remove"}, status=status.HTTP_400_BAD_REQUEST)

    number = int(m.group(1))
    refund_amount = bet_txn.amount

    try:
        bet = Bet.objects.get(user=request.user, round=round_obj, number=number)
    except Bet.DoesNotExist:
        return Response({"error": "Bet not found"}, status=status.HTTP_404_NOT_FOUND)

    try:
        with transaction.atomic():
            wallet = request.user.wallet
            balance_before = wallet.balance
            wallet.add(refund_amount)
            balance_after = wallet.balance

            # Decrement bet amount by last wager amount
            bet.chip_amount = max(Decimal("0.00"), bet.chip_amount - refund_amount)
            if bet.chip_amount <= 0:
                bet.delete()
            else:
                bet.save(update_fields=["chip_amount"])

            # total_bets counts wagers (every bet call increments it)
            round_obj.total_bets = max(0, round_obj.total_bets - 1)
            round_obj.total_amount = max(Decimal("0.00"), round_obj.total_amount - refund_amount)
            round_obj.save(update_fields=["total_bets", "total_amount"])

            Transaction.objects.create(
                user=request.user,
                transaction_type="REFUND",
                amount=refund_amount,
                balance_before=balance_before,
                balance_after=balance_after,
                description=f"Undo bet on number {number} in round {round_obj.round_id}",
            )

    except Exception as e:
        logger.exception(f"Unexpected error deleting last bet for user {request.user.username}: {e}")
        return Response({"error": "Internal server error during refund"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    return Response(
        {
            "message": f"Last bet removed (number {number})",
            "refund_amount": str(refund_amount),
            "wallet_balance": str(wallet.balance),
            "round": {
                "round_id": round_obj.round_id,
                "total_bets": round_obj.total_bets,
                "total_amount": str(round_obj.total_amount),
            },
        }
    )

"""


def main() -> int:
    backend = Path("/root/apk_of_ata/backend")
    views_path = backend / "game" / "views.py"
    urls_path = backend / "dice_game" / "urls.py"
    game_urls_path = backend / "game" / "urls.py"

    results: list[PatchResult] = []

    # Patch views
    views_text = views_path.read_text()
    new_views_text, changed, msg = insert_block_before_def(
        views_text,
        def_name="my_bets",
        block=DELETE_LAST_BET_BLOCK,
        marker=DELETE_LAST_BET_MARKER,
    )
    if changed:
        views_path.write_text(new_views_text)
    results.append(PatchResult(str(views_path), changed, msg))

    # Patch dice_game/urls.py (the project uses this file, not include(game.urls))
    urls_text = urls_path.read_text()
    marker = "api/game/bet/last/"
    line_to_insert = '    path("api/game/bet/last/", game_views.delete_last_bet, name="delete_last_bet"),\n'
    new_urls_text, changed, msg = insert_line_before(
        urls_text,
        contains="api/game/bet/<int:number>/",
        line_to_insert=line_to_insert,
        marker=marker,
    )
    if changed:
        urls_path.write_text(new_urls_text)
    results.append(PatchResult(str(urls_path), changed, msg))

    # Patch game/urls.py too (may be used elsewhere)
    game_urls_text = game_urls_path.read_text()
    marker2 = 'path("bet/last/"'
    line_to_insert2 = '    path("bet/last/", views.delete_last_bet, name="delete_last_bet"),\n'
    new_game_urls_text, changed, msg = insert_line_before(
        game_urls_text,
        contains="path('bet/<int:number>/'",
        line_to_insert=line_to_insert2,
        marker=marker2,
    )
    if changed:
        game_urls_path.write_text(new_game_urls_text)
    results.append(PatchResult(str(game_urls_path), changed, msg))

    for r in results:
        print(f"{r.path}: {'CHANGED' if r.changed else 'OK'} - {r.message}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

