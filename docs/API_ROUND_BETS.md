# Round Bets API Documentation

**Endpoint:** `https://gunduata.online/api/game/round/bets/`  
**Method:** `GET`  
**Authentication:** Required (User/Admin Token)

## 📝 Overview
This API provides detailed information about all bets placed in a specific game round. It includes grouped summaries per player/number, individual bet logs with precise timestamps, and overall round statistics.

---

## 🔍 Query Parameters
| Parameter | Type | Description |
| :--- | :--- | :--- |
| `round_id` | `string` | (Optional) Specific Round ID. If omitted, returns the **current/latest** round. |
| `number` | `integer` | (Optional) Filter bets by a specific dice number (1-6). |
| `limit` | `integer` | (Optional) Limit the number of individual bets returned (Default: 1000). |
| `user_id` | `integer` | (Optional) Filter by User ID (**Admin only**). |

---

## 📦 Response Structure

### 1. `round` Object
Contains metadata about the game round.
- `round_id`: Unique identifier for the round.
- `status`: Current status (`BETTING`, `CLOSED`, `RESULT`, `ENDED`).
- `dice_result`: Final winning numbers (if available).
- `start_time`: ISO timestamp when the round started.

### 2. `bets` Array (Grouped Summary)
Summarizes bets per player and per number.
- `username`: Name of the player.
- `number`: The dice number (1-6) they bet on.
- `amount`: Total amount bet on this specific number.
- `total_player_bet`: Total amount this player has bet across **all** numbers in this round.
- `chip_breakdown`: Object showing counts of each chip denomination (e.g., `{"50": 2, "100": 1}`).
- `chip_summary`: Human-readable string of chips (e.g., `"2x50, 1x100"`), sorted by chip value.
- **`last_chip_amount`**: The value of the **most recent chip** placed by this user on this specific number.
- `last_bet_time`: ISO timestamp of the most recent bet on this number.

### 3. `individual_bets` Array (Chronological Log)
A flat list of every single chip placed, ordered by time (oldest first).
- `id`: Unique Bet ID.
- `user_id`: Unique User ID of the player.
- `username`: Player name.
- `number`: Dice number.
- `chip_amount`: Value of that specific chip (the amount for that specific bet action).
- `created_at`: **Precise timestamp** of the bet.
- `is_winner`: Boolean indicating if this specific bet won.

### 4. `statistics` Object
Round-wide data for analytics.
- `overall`: Total bets, total amount, unique players, total winners, and total payout.
- `by_number`: Breakdown of total bets and amounts for each number (1-6).

---

## 💡 Example Response
```json
{
  "round": {
    "round_id": "RD123456",
    "status": "BETTING",
    "dice_result": null,
    "start_time": "2026-02-11T10:00:00.000Z"
  },
  "bets": [
    {
      "username": "player1",
      "number": 1,
      "amount": "175.00",
      "total_player_bet": "445.00",
      "chip_breakdown": {"25": 1, "50": 1, "100": 1},
      "chip_summary": "1x25, 1x50, 1x100",
      "last_chip_amount": "25.00",
      "last_bet_time": "2026-02-11T10:02:45.123Z"
    }
  ],
  "individual_bets": [
    {
      "id": 5001,
      "user_id": 42,
      "username": "player1",
      "number": 1,
      "chip_amount": "100.00",
      "created_at": "2026-02-11T10:01:10.000Z",
      "is_winner": false
    },
    {
      "id": 5005,
      "user_id": 42,
      "username": "player1",
      "number": 1,
      "chip_amount": "50.00",
      "created_at": "2026-02-11T10:02:15.000Z",
      "is_winner": false
    },
    {
      "id": 5010,
      "user_id": 42,
      "username": "player1",
      "number": 1,
      "chip_amount": "25.00",
      "created_at": "2026-02-11T10:02:45.123Z",
      "is_winner": false
    }
  ],
  "statistics": {
    "overall": {
      "total_bets": 23,
      "total_amount": "1500.00",
      "total_unique_players": 5
    },
    "by_number": [...]
  },
  "count": 1,
  "individual_count": 3
}
```
