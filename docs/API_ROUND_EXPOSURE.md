# Round Exposure API Documentation

**Endpoint:** `https://gunduata.online/api/game/round/exposure/`  
**Method:** `GET`  
**Authentication:** Required (User/Admin Token)

## 📝 Overview
This API provides the "exposure amount" for a game round. Exposure amount is the total sum of all chips placed by a player during that specific round. This endpoint requires an authentication token.

---

## 🔍 Query Parameters
| Parameter | Type | Description |
| :--- | :--- | :--- |
| `round_id` | `string` | (Optional) Specific Round ID. If omitted, returns exposure for the **current/latest** round. |
| `user_id` | `integer` | (Optional) Filter exposure for a specific player ID. If omitted, returns exposure for all participating players. |

---

## 📦 Response Structure

### **Field Definitions**
| Field | Type | Description |
| :--- | :--- | :--- |
| `round_id` | `string` | Unique identifier for the round. |
| `status` | `string` | Current status of the round (`BETTING`, `CLOSED`, `RESULT`, `ENDED`). |
| `exposure` | `array` | List of player exposure objects. |

### **Exposure Object Fields**
| Field | Type | Description |
| :--- | :--- | :--- |
| `player_id` | `integer` | Unique ID of the player. |
| `username` | `string` | Username of the player. |
| `exposure_amount` | `string` | **Total amount bet by this player in this round.** |

---

## 💡 Example Responses

### **1. Request for a Specific User**
`GET /api/game/round/exposure/?user_id=42`

```json
{
  "round_id": "RD123456",
  "status": "BETTING",
  "exposure": [
    {
      "player_id": 42,
      "username": "player1",
      "exposure_amount": "1500.00"
    }
  ]
}
```

### **2. Request for All Users (Admin/Global View)**
`GET /api/game/round/exposure/`

```json
{
  "round_id": "RD123456",
  "status": "BETTING",
  "exposure": [
    {
      "player_id": 42,
      "username": "player1",
      "exposure_amount": "1500.00"
    },
    {
      "player_id": 45,
      "username": "player2",
      "exposure_amount": "750.00"
    }
  ]
}
```

---

## 🎯 Key Features
1.  **Secure Access**: Requires a valid `Authorization: Bearer <token>` header.
2.  **Flexible Filtering**: Use `user_id` to fetch data for a particular player.
3.  **Real-time Ready**: Can be called during the `BETTING` phase to track live risk.
4.  **House Risk Tracking**: Summing the `exposure_amount` values gives the total house risk for the round.

---

## 🔍 Usage Examples
- `https://gunduata.online/api/game/round/exposure/` (All players, current round)
- `https://gunduata.online/api/game/round/exposure/?user_id=42` (Specific player, current round)
- `https://gunduata.online/api/game/round/RD123456/exposure/?user_id=42` (Specific player, specific round)
