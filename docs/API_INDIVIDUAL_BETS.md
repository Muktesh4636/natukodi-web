# Round Bets API Documentation (Individual Bet Logs)

**Endpoint:** `https://gunduata.online/api/game/round/bets/`  
**Method:** `GET`  
**Authentication:** Required (User/Admin Token)

## 📝 Overview
This API provides a high-precision, chronological log of every single betting action (chip placement) that occurred during a game round. It is designed for tracking the exact sequence of bets, even if they happen within the same second.

---

## 📦 Individual Bets Log (`individual_bets`)

The `individual_bets` array contains a flat list of every chip placed, ordered by the exact time they reached the server.

### **Field Definitions**
| Field | Type | Description |
| :--- | :--- | :--- |
| `id` | `integer` | Unique identifier for this specific bet action. |
| `user_id` | `integer` | Unique ID of the player who placed the bet. |
| `username` | `string` | Username of the player. |
| **`number`** | `integer` | **The dice number (1-6) the chip was placed on.** |
| **`chip_amount`** | `string` | **The value of the specific chip placed in this action.** |
| **`created_at`** | `string` | **ISO 8601 timestamp with microsecond precision (e.g., `.123456Z`).** |
| `is_winner` | `boolean` | Whether this specific chip was a winning bet. |
| `payout_amount` | `string` | The amount paid out for this chip (if it won). |

---

## 💡 Example Response

```json
{
  "round": {
    "round_id": "RD998877",
    "status": "RESULT"
  },
  "individual_bets": [
    {
      "id": 5001,
      "user_id": 42,
      "username": "player1",
      "number": 1,
      "chip_amount": "50.00",
      "created_at": "2026-02-11T10:01:10.123456Z",
      "is_winner": false,
      "payout_amount": null
    },
    {
      "id": 5002,
      "user_id": 42,
      "username": "player1",
      "number": 1,
      "chip_amount": "100.00",
      "created_at": "2026-02-11T10:01:10.567890Z",
      "is_winner": false,
      "payout_amount": null
    },
    {
      "id": 5003,
      "user_id": 42,
      "username": "player1",
      "number": 3,
      "chip_amount": "25.00",
      "created_at": "2026-02-11T10:01:12.000000Z",
      "is_winner": true,
      "payout_amount": "50.00"
    }
  ],
  "individual_count": 3
}
```

---

## 🎯 Key Features for Integration

1.  **Order Wise Tracking**: The list is strictly ordered by `created_at`. You can see exactly how a player moved their chips (e.g., "Placed 50 on #1, then 100 on #1, then 25 on #3").
2.  **High Precision**: Timestamps include microseconds, allowing you to distinguish between multiple requests sent in the same second.
3.  **User Identification**: Use `user_id` to reliably group actions by player across different rounds.
4.  **Action History**: Unlike the grouped `bets` array, this section shows every individual click/action, not just the final totals.

---

## 🔍 Filtering
You can filter this log using query parameters:
- `?number=1`: Show only bets placed on dice number 1.
- `?limit=50`: Show only the first 50 actions.
- `?round_id=XYZ`: Get logs for a specific past round.
