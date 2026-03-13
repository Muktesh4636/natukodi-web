"""
Smart Dice Engine
=================
Decides whether to force a win, force a loss, or roll pure random
for every round, based on each bettor's current journey state.

Rules (evaluated in strict priority order):
  1. PROTECTED numbers  — any number with total bets >= PROTECT_THRESHOLD
                          must NOT appear twice in the dice (max once).
  2. FORCED WIN         — if a bettor needs a win (floor hit, drought, time
                          target reached + WIN/BIG_WIN day), force their
                          number to appear twice — but only if budget allows.
  3. PURE RANDOM        — everything else.

The engine is fully async-compatible (works with redis.asyncio) and also
exposes a sync wrapper used by the Django management command.
"""

import json
import logging
import random
from collections import Counter

logger = logging.getLogger('smart_dice_engine')

# ── Config ────────────────────────────────────────────────────────────────────
PROTECT_THRESHOLD = 2000   # Any number with total bets >= this must not win
MAX_FORCED_WIN_NUMBERS = 2  # Max different numbers we force to win in one round
DROUGHT_ROUNDS_WARN = 5     # Rounds without win — start watching
DROUGHT_ROUNDS_FORCE = 8    # Rounds without win — must force win now
FLOOR_URGENCY_HIGH = 1.2    # balance < floor * 1.2 → high urgency
BIG_WIN_MULTIPLIER = 3      # Force the number to appear 3 times on BIG_WIN days


# ── Redis Key Helpers ─────────────────────────────────────────────────────────

def _ps_key(user_id):
    """Player state key in Redis."""
    return f"player_state:{user_id}"


def _nb_key(round_id):
    """Per-number bet totals key (HASH: number -> total amount)."""
    return f"round:{round_id}:number_bets"


def _nu_key(round_id, number):
    """Set of user_ids who bet on `number` in this round."""
    return f"round:{round_id}:number:{number}:users"


# ── Player State Helpers ──────────────────────────────────────────────────────

def _default_state():
    return {
        'day_type': 'WIN',
        'floor_balance': 0,
        'emergency_floor': 0,
        'target_min': 0,
        'target_max': 0,
        'budget_remaining': 0,
        'rounds_since_last_win': 0,
        'time_target_reached': False,
        'active_day': 1,
        'is_flagged': False,
        'current_balance': 0,
    }


def _load_state(raw):
    if not raw:
        return _default_state()
    try:
        s = json.loads(raw)
        d = _default_state()
        d.update(s)
        return d
    except Exception:
        return _default_state()


def _calculate_priority(state, balance):
    """
    Returns an integer priority score for forcing a win.
    Higher = more urgent.
    """
    active_day = state.get('active_day', 0)
    if active_day > 30:
        return 0  # Pure random after 30 active days

    if state.get('is_flagged'):
        return 0
    if state.get('budget_remaining', 0) <= 0:
        return 0

    day_type = state.get('day_type', 'WIN')
    if day_type in ('LOSS', 'RANDOM'):
        return 0  # No forced wins on LOSS or post-journey days

    score = 0
    floor = state.get('floor_balance', 0)
    emergency = state.get('emergency_floor', 0)

    # Balance-based urgency
    if balance <= emergency:
        score += 200
    elif balance <= floor:
        score += 100
    elif balance <= floor * FLOOR_URGENCY_HIGH:
        score += 50

    # Drought-based urgency
    drought = state.get('rounds_since_last_win', 0)
    if drought >= DROUGHT_ROUNDS_FORCE:
        score += 80
    elif drought >= DROUGHT_ROUNDS_WARN:
        score += 40

    # Day-type bonus
    if day_type == 'BIG_WIN':
        score += 60
    elif day_type == 'WIN':
        score += 20
    elif day_type == 'BREAK_EVEN':
        score += 5  # Only save from floor on break-even days

    # Time-target bonus: only award main win after time target reached
    if not state.get('time_target_reached', False) and score < 100:
        score = 0  # Withhold non-emergency wins until time target met

    return score


# ── Dice Building ─────────────────────────────────────────────────────────────

def _build_dice(win_numbers, protected_numbers, big_win_numbers=None):
    """
    Build a list of 6 dice values.

    win_numbers       — these numbers MUST appear exactly twice (or 3x if BIG_WIN)
    protected_numbers — these numbers must appear at most once
    big_win_numbers   — subset of win_numbers that should appear 3 times
    """
    big_win_numbers = big_win_numbers or set()
    dice = []

    # Place forced wins
    for num in win_numbers:
        appearances = 3 if num in big_win_numbers else 2
        dice.extend([num] * appearances)

    # Fill remaining slots randomly — respecting constraints
    slots_left = 6 - len(dice)
    if slots_left < 0:
        # Too many forced numbers — trim to 6 (keep wins, truncate randomly)
        dice = dice[:6]
        slots_left = 0

    for _ in range(slots_left):
        attempts = 0
        while attempts < 50:
            n = random.randint(1, 6)
            current_count = dice.count(n)

            # Never let a protected number reach 2 appearances
            if n in protected_numbers and current_count >= 1:
                attempts += 1
                continue

            # Win numbers: cap at their target (3 for big_win, 2 otherwise)
            if n in win_numbers:
                cap = 3 if n in big_win_numbers else 2
                if current_count >= cap:
                    attempts += 1
                    continue

            # Never let any other number exceed 3 appearances
            if current_count >= 3:
                attempts += 1
                continue

            dice.append(n)
            break
        else:
            # Fallback: pick any number that doesn't break constraints
            for fallback in range(1, 7):
                if fallback in protected_numbers and dice.count(fallback) >= 1:
                    continue
                if fallback in win_numbers:
                    cap = 3 if fallback in big_win_numbers else 2
                    if dice.count(fallback) >= cap:
                        continue
                dice.append(fallback)
                break
            else:
                dice.append(random.randint(1, 6))

    random.shuffle(dice)
    return dice[:6]


def _pure_random_dice(protected_numbers):
    """Pure random dice respecting protected numbers (appear max once)."""
    return _build_dice(win_numbers=set(), protected_numbers=protected_numbers)


def _determine_result(dice):
    """Return comma-separated winning numbers (appear 2+ times), or '0'."""
    counts = Counter(dice)
    winners = sorted([num for num, cnt in counts.items() if cnt >= 2])
    return ','.join(map(str, winners)) if winners else '0'


# ── Sync Engine (for Django management command / worker) ──────────────────────

def generate_smart_dice_sync(redis_client, round_id):
    """
    Synchronous version — used by start_game_timer.py and worker_v2.py.
    Returns (dice_values: list[int], result: str).
    """
    try:
        # 1. Per-number bet totals
        number_bets_raw = redis_client.hgetall(_nb_key(round_id)) or {}
        number_bets = {int(k): float(v) for k, v in number_bets_raw.items()}

        # 2. Protected numbers (total bets >= threshold)
        protected = {n for n, amt in number_bets.items() if amt >= PROTECT_THRESHOLD}

        # 3. Evaluate each bettor
        candidates = []  # (priority, number, user_id, state)

        for number in range(1, 7):
            if number in protected:
                continue
            users_raw = redis_client.smembers(_nu_key(round_id, number)) or set()
            for uid_raw in users_raw:
                try:
                    user_id = int(uid_raw)
                except (ValueError, TypeError):
                    continue
                state_raw = redis_client.get(_ps_key(user_id))
                state = _load_state(state_raw)

                if state.get('is_flagged'):
                    continue

                balance = state.get('current_balance', 0)
                priority = _calculate_priority(state, balance)
                if priority > 0:
                    candidates.append((priority, number, user_id, state))

        # 4. Sort by priority, pick top candidates (different numbers)
        candidates.sort(key=lambda x: -x[0])
        win_numbers = []
        big_win_numbers = set()
        seen_users = set()

        for priority, number, user_id, state in candidates:
            if number in win_numbers:
                continue
            if user_id in seen_users:
                continue
            if len(win_numbers) >= MAX_FORCED_WIN_NUMBERS:
                break
            win_numbers.append(number)
            seen_users.add(user_id)
            if state.get('day_type') == 'BIG_WIN':
                big_win_numbers.add(number)

        # 5. Build dice
        if win_numbers:
            dice = _build_dice(
                win_numbers=set(win_numbers),
                protected_numbers=protected,
                big_win_numbers=big_win_numbers,
            )
        else:
            dice = _pure_random_dice(protected)

        result = _determine_result(dice)
        logger.info(
            f"SmartDice round={round_id} protected={protected} "
            f"win_numbers={win_numbers} dice={dice} result={result}"
        )
        return dice, result

    except Exception as exc:
        logger.error(f"SmartDice error round={round_id}: {exc}", exc_info=True)
        # Fallback to pure random
        dice = [random.randint(1, 6) for _ in range(6)]
        return dice, _determine_result(dice)


# ── Async Engine (for game_engine_v3.py) ─────────────────────────────────────

async def generate_smart_dice_async(redis_client, round_id):
    """
    Asynchronous version — used by game_engine_v3.py.
    Returns (dice_values: list[int], result: str).
    """
    try:
        # 1. Per-number bet totals
        number_bets_raw = await redis_client.hgetall(_nb_key(round_id)) or {}
        number_bets = {int(k): float(v) for k, v in number_bets_raw.items()}

        # 2. Protected numbers
        protected = {n for n, amt in number_bets.items() if amt >= PROTECT_THRESHOLD}

        # 3. Evaluate each bettor
        candidates = []

        for number in range(1, 7):
            if number in protected:
                continue
            users_raw = await redis_client.smembers(_nu_key(round_id, number)) or set()
            for uid_raw in users_raw:
                try:
                    user_id = int(uid_raw)
                except (ValueError, TypeError):
                    continue
                state_raw = await redis_client.get(_ps_key(user_id))
                state = _load_state(state_raw)

                if state.get('is_flagged'):
                    continue

                balance = state.get('current_balance', 0)
                priority = _calculate_priority(state, balance)
                if priority > 0:
                    candidates.append((priority, number, user_id, state))

        # 4. Pick top candidates
        candidates.sort(key=lambda x: -x[0])
        win_numbers = []
        big_win_numbers = set()
        seen_users = set()

        for priority, number, user_id, state in candidates:
            if number in win_numbers:
                continue
            if user_id in seen_users:
                continue
            if len(win_numbers) >= MAX_FORCED_WIN_NUMBERS:
                break
            win_numbers.append(number)
            seen_users.add(user_id)
            if state.get('day_type') == 'BIG_WIN':
                big_win_numbers.add(number)

        # 5. Build dice
        if win_numbers:
            dice = _build_dice(
                win_numbers=set(win_numbers),
                protected_numbers=protected,
                big_win_numbers=big_win_numbers,
            )
        else:
            dice = _pure_random_dice(protected)

        result = _determine_result(dice)
        logger.info(
            f"SmartDice(async) round={round_id} protected={protected} "
            f"win_numbers={win_numbers} dice={dice} result={result}"
        )
        return dice, result

    except Exception as exc:
        logger.error(f"SmartDice(async) error round={round_id}: {exc}", exc_info=True)
        dice = [random.randint(1, 6) for _ in range(6)]
        return dice, _determine_result(dice)


# ── Player State Writer (called by worker after settlement) ───────────────────

def update_player_state_sync(redis_client, user_id, won, win_amount, current_balance):
    """
    Called by worker_v2.py after each round is settled for a user.
    Updates the Redis player_state with new balance and streak counters.
    """
    key = _ps_key(user_id)
    state_raw = redis_client.get(key)
    state = _load_state(state_raw)

    state['current_balance'] = int(current_balance)

    if won:
        state['rounds_since_last_win'] = 0
        # Deduct from budget
        state['budget_remaining'] = max(
            0, int(state.get('budget_remaining', 0)) - int(win_amount)
        )
    else:
        state['rounds_since_last_win'] = int(state.get('rounds_since_last_win', 0)) + 1

    redis_client.set(key, json.dumps(state), ex=86400)


async def update_player_state_async(redis_client, user_id, won, win_amount, current_balance):
    """Async version of update_player_state_sync."""
    key = _ps_key(user_id)
    state_raw = await redis_client.get(key)
    state = _load_state(state_raw)

    state['current_balance'] = int(current_balance)

    if won:
        state['rounds_since_last_win'] = 0
        state['budget_remaining'] = max(
            0, int(state.get('budget_remaining', 0)) - int(win_amount)
        )
    else:
        state['rounds_since_last_win'] = int(state.get('rounds_since_last_win', 0)) + 1

    await redis_client.set(key, json.dumps(state), ex=86400)
