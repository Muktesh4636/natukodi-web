# Exposure Reset Rule

## Description
Ensures that game exposure data (chips on the board) is always reset to zero once a game round ends.

## Requirements
- The game engine (`backend/game_engine_v2.py`) MUST explicitly delete exposure-related Redis keys at the end of every round.
- Exposure keys to be cleared:
  - `round:{round_id}:total_exposure`
  - `round:{round_id}:user_exposure`
  - `round:{round_id}:bet_count`
- This reset must occur before the next round starts to prevent chip data from leaking into new rounds.

## Implementation Detail
In the `run()` loop of the game engine, after the round timer finishes and the `game_end` state is published, the Redis `delete` commands must be executed for the current `round_id`.
