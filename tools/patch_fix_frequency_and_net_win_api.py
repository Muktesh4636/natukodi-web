#!/usr/bin/env python3
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PatchResult:
    path: str
    changed: bool
    message: str


def _find_block(lines: list[str], start_pred, end_pred) -> tuple[int, int] | None:
    start = None
    for i, l in enumerate(lines):
        if start is None and start_pred(l):
            start = i
            continue
        if start is not None and end_pred(l):
            return start, i
    if start is not None:
        return start, len(lines)
    return None


def patch_urls(dice_game_urls: Path) -> PatchResult:
    text = dice_game_urls.read_text()
    if "api/game/frequency/" in text:
        return PatchResult(str(dice_game_urls), False, "frequency route already present")

    lines = text.splitlines(True)
    # Insert near other api/game endpoints; best anchor is winning-results route.
    anchor = "api/game/winning-results/"
    idx = None
    for i, l in enumerate(lines):
        if anchor in l:
            idx = i
            break
    if idx is None:
        # fallback: insert after api/game/results/
        for i, l in enumerate(lines):
            if "path('api/game/results/'" in l or 'path("api/game/results/"' in l:
                idx = i + 1
                break
    if idx is None:
        return PatchResult(str(dice_game_urls), False, "could not find insertion anchor in urls.py")

    # Compatibility endpoint: Unity client calls this for dice frequency.
    insert = "    path('api/game/frequency/', game_views.winning_results, name='winning_frequency'),\n"
    lines.insert(idx, insert)
    dice_game_urls.write_text("".join(lines))
    return PatchResult(str(dice_game_urls), True, "added /api/game/frequency/ -> game_views.winning_results")


def patch_winning_results(views_py: Path) -> PatchResult:
    text = views_py.read_text()
    if "User-specific fields for Unity client compatibility" in text and "user_bets_data" in text:
        return PatchResult(str(views_py), False, "winning_results already patched")

    lines = text.splitlines(True)
    block = _find_block(
        lines,
        start_pred=lambda l: l.startswith("def winning_results("),
        end_pred=lambda l: l.startswith("def ") and not l.startswith("def winning_results("),
    )
    if block is None:
        return PatchResult(str(views_py), False, "could not find winning_results block")

    start, end = block
    sub = lines[start:end]

    # 1) Ensure round dict includes dice_1..dice_6 (Unity RoundInfo expects these fields).
    if "'dice_1':" not in "".join(sub):
        dice_values_line_idx = None
        for i, l in enumerate(sub):
            if "'dice_values':" in l and "dice_values" in l:
                dice_values_line_idx = i
                break
        if dice_values_line_idx is not None:
            indent = sub[dice_values_line_idx].split("'dice_values':")[0]
            insert_lines = [
                f"{indent}'dice_1': round_obj.dice_1,\n",
                f"{indent}'dice_2': round_obj.dice_2,\n",
                f"{indent}'dice_3': round_obj.dice_3,\n",
                f"{indent}'dice_4': round_obj.dice_4,\n",
                f"{indent}'dice_5': round_obj.dice_5,\n",
                f"{indent}'dice_6': round_obj.dice_6,\n",
            ]
            sub[dice_values_line_idx + 1:dice_values_line_idx + 1] = insert_lines

    # 2) Insert user-specific computation block before return Response({ ... })
    return_idx = None
    for i, l in enumerate(sub):
        if "return Response({" in l:
            return_idx = i
            break
    if return_idx is None:
        return PatchResult(str(views_py), False, "could not find return Response({ in winning_results")

    if "user_bets_data" not in "".join(sub):
        indent = sub[return_idx].split("return Response")[0]
        compute_block = [
            f"{indent}# User-specific fields for Unity client compatibility (net win/loss UI)\n",
            f"{indent}try:\n",
            f"{indent}    user_bets = Bet.objects.filter(round=round_obj, user=request.user)\n",
            f"{indent}    user_total_bet_amount = sum(b.chip_amount for b in user_bets)\n",
            f"{indent}    user_total_payout = sum((b.payout_amount or 0) for b in user_bets)\n",
            f"{indent}    user_net_result = user_total_payout - user_total_bet_amount\n",
            f"{indent}    user_winning_bets = [b for b in user_bets if b.is_winner]\n",
            f"{indent}    user_losing_bets = [b for b in user_bets if not b.is_winner]\n",
            f"{indent}    user_bets_data = []\n",
            f"{indent}    for b in user_bets:\n",
            f"{indent}        user_bets_data.append({{\n",
            f"{indent}            'id': b.id,\n",
            f"{indent}            'number': b.number,\n",
            f"{indent}            'chip_amount': str(b.chip_amount),\n",
            f"{indent}            'is_winner': bool(b.is_winner),\n",
            f"{indent}            'payout_amount': str(b.payout_amount or 0),\n",
            f"{indent}        }})\n",
            f"{indent}    # Unity expects net_result as int\n",
            f"{indent}    from decimal import ROUND_HALF_UP\n",
            f"{indent}    try:\n",
            f"{indent}        user_net_result_int = int(user_net_result.to_integral_value(rounding=ROUND_HALF_UP))\n",
            f"{indent}    except Exception:\n",
            f"{indent}        user_net_result_int = int(float(user_net_result)) if user_net_result is not None else 0\n",
            f"{indent}    user_summary = {{\n",
            f"{indent}        'total_bets': len(user_bets_data),\n",
            f"{indent}        'total_bet_amount': str(user_total_bet_amount),\n",
            f"{indent}        'total_payout': str(user_total_payout),\n",
            f"{indent}        'net_result': user_net_result_int,\n",
            f"{indent}        'winning_bets': len(user_winning_bets),\n",
            f"{indent}        'losing_bets': len(user_losing_bets),\n",
            f"{indent}    }}\n",
            f"{indent}    try:\n",
            f"{indent}        wallet_balance = str(request.user.wallet.balance)\n",
            f"{indent}    except Exception:\n",
            f"{indent}        wallet_balance = '0'\n",
            f"{indent}except Exception:\n",
            f"{indent}    user_bets_data = []\n",
            f"{indent}    user_summary = {{'total_bets': 0, 'total_bet_amount': '0', 'total_payout': '0', 'net_result': 0, 'winning_bets': 0, 'losing_bets': 0}}\n",
            f"{indent}    wallet_balance = '0'\n",
            "\n",
        ]
        sub[return_idx:return_idx] = compute_block

    # 3) Insert bets/summary/wallet_balance fields into response dict so Unity can deserialize.
    joined = "".join(sub)
    if "'summary': user_summary" not in joined:
        insert_point = None
        for i, l in enumerate(sub):
            if "'winning_numbers':" in l:
                insert_point = i
                break
        if insert_point is None:
            return PatchResult(str(views_py), False, "could not find winning_numbers key in response dict")
        indent = sub[insert_point].split("'winning_numbers':")[0]
        response_inserts = [
            f"{indent}'bets': user_bets_data,\n",
            f"{indent}'summary': user_summary,\n",
            f"{indent}'wallet_balance': wallet_balance,\n",
        ]
        sub[insert_point:insert_point] = response_inserts

    lines[start:end] = sub
    views_py.write_text("".join(lines))
    return PatchResult(str(views_py), True, "patched winning_results for Unity net-result + dice fields")


def main() -> int:
    backend = Path("/root/apk_of_ata/backend")
    urls = backend / "dice_game" / "urls.py"
    views = backend / "game" / "views.py"

    results = [patch_urls(urls), patch_winning_results(views)]
    for r in results:
        print(f"{r.path}: {'CHANGED' if r.changed else 'OK'} - {r.message}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

