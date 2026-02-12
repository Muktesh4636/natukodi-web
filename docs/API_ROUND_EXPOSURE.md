# Round Exposure API Documentation

**Endpoint:** `https://gunduata.online/api/game/round/exposure/`  
**Method:** `GET`  
**Authentication:** Required (User/Admin Token)

## 📝 Overview
This API provides the "exposure amount" for a game round. Exposure amount is the total sum of all chips placed by a player during that specific round. This endpoint requires an authentication token.

**Privacy Note:** 
- **Regular users** will only see their own exposure data.
- **Admin users** can see all players' exposure data.

---

## 🔍 Query Parameters
| Parameter | Type | Description |
| :--- | :--- | :--- |
| `round_id` | `string` | (Optional) Specific Round ID. If omitted, returns exposure for the **current/latest** round. |
| `user_id` | `integer` | (Optional) Filter exposure for a specific player ID. **Admin only** - Regular users cannot use this parameter and will receive a 403 Forbidden error. |

---

## 📦 Response Structure

### **Top-Level Fields**
| Field | Type | Description |
| :--- | :--- | :--- |
| `round` | `object` | Complete round information (see Round Object below). |
| `exposure` | `array` | List of player exposure objects. |
| `statistics` | `object` | Overall round statistics (see Statistics Object below). |

### **Round Object Fields**
| Field | Type | Description |
| :--- | :--- | :--- |
| `round_id` | `string` | Unique identifier for the round. |
| `status` | `string` | Current status of the round (`BETTING`, `CLOSED`, `RESULT`, `ENDED`). |
| `dice_result` | `string` | Comma-separated winning numbers (e.g., "1,3,5"). |
| `dice_1` through `dice_6` | `integer` | Individual dice values (1-6). |
| `start_time` | `string` | ISO timestamp when the round started. |
| `betting_close_time` | `string` | ISO timestamp when betting closed (null if not closed yet). |
| `result_time` | `string` | ISO timestamp when results were announced (null if not announced yet). |
| `end_time` | `string` | ISO timestamp when the round ended (null if not ended yet). |

### **Exposure Object Fields**
| Field | Type | Description |
| :--- | :--- | :--- |
| `player_id` | `integer` | Unique ID of the player. |
| `username` | `string` | Username of the player. |
| `exposure_amount` | `string` | **Total amount bet by this player in this round.** |
| `bet_count` | `integer` | **Number of individual bets placed by this player.** |

### **Statistics Object Fields**
| Field | Type | Description |
| :--- | :--- | :--- |
| `total_exposure` | `string` | Total exposure amount across all players. |
| `total_bets` | `integer` | Total number of individual bets placed. |
| `total_amount` | `string` | Total amount bet across all players. |
| `total_unique_players` | `integer` | Number of unique players who placed bets. |

---

## 💡 Example Responses

### **1. Request for a Specific User**
`GET /api/game/round/exposure/?user_id=42`

```json
{
  "round": {
    "round_id": "RD123456",
    "status": "CLOSED",
    "dice_result": "1,3,5",
    "dice_1": 1,
    "dice_2": 3,
    "dice_3": 5,
    "dice_4": 2,
    "dice_5": 4,
    "dice_6": 6,
    "start_time": "2026-02-11T10:00:00.000Z",
    "betting_close_time": "2026-02-11T10:00:30.000Z",
    "result_time": "2026-02-11T10:00:51.000Z",
    "end_time": "2026-02-11T10:01:10.000Z"
  },
  "exposure": [
    {
      "player_id": 42,
      "username": "player1",
      "exposure_amount": "1500.00",
      "bet_count": 15
    }
  ],
  "statistics": {
    "total_exposure": "1500.00",
    "total_bets": 15,
    "total_amount": "1500.00",
    "total_unique_players": 1
  }
}
```

### **2. Request for Regular User (Own Data Only)**
`GET /api/game/round/exposure/`

**Note:** Regular users will automatically see only their own exposure data.

### **3. Request for All Users (Admin/Global View)**
`GET /api/game/round/exposure/` (with admin token)

```json
{
  "round": {
    "round_id": "RD123456",
    "status": "CLOSED",
    "dice_result": "1,3,5",
    "dice_1": 1,
    "dice_2": 3,
    "dice_3": 5,
    "dice_4": 2,
    "dice_5": 4,
    "dice_6": 6,
    "start_time": "2026-02-11T10:00:00.000Z",
    "betting_close_time": "2026-02-11T10:00:30.000Z",
    "result_time": "2026-02-11T10:00:51.000Z",
    "end_time": "2026-02-11T10:01:10.000Z"
  },
  "exposure": [
    {
      "player_id": 42,
      "username": "player1",
      "exposure_amount": "1500.00",
      "bet_count": 15
    },
    {
      "player_id": 45,
      "username": "player2",
      "exposure_amount": "750.00",
      "bet_count": 8
    }
  ],
  "statistics": {
    "total_exposure": "2250.00",
    "total_bets": 23,
    "total_amount": "2250.00",
    "total_unique_players": 2
  }
}
```

---

## 🎯 Key Features
1.  **Secure Access**: Requires a valid `Authorization: Bearer <token>` header.
2.  **Privacy Protection**: Regular users only see their own exposure data. Admins can see all players.
3.  **Flexible Filtering**: Admins can use `user_id` parameter to fetch data for a particular player.
4.  **Real-time Ready**: Can be called during the `BETTING` phase to track live risk.
5.  **House Risk Tracking**: Admins can sum the `exposure_amount` values to get the total house risk for the round.

---

## 🔍 Usage Examples
- `https://gunduata.online/api/game/round/exposure/` (All players, current round)
- `https://gunduata.online/api/game/round/exposure/?user_id=42` (Specific player, current round)
- `https://gunduata.online/api/game/round/RD123456/exposure/?user_id=42` (Specific player, specific round)
