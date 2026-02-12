# Place Bet API Documentation

**Endpoint:** `https://gunduata.online/api/game/bet/`  
**Method:** `POST`  
**Authentication:** Required (JWT Access Token)

## 📝 Overview
This API allows authenticated users to place bets on dice numbers (1-6) during an active betting window. Each bet deducts the specified amount from the user's wallet balance.

---

## 🔐 Authentication
Include your JWT access token in the Authorization header:
```
Authorization: Bearer <your_access_token>
```

---

## 📦 Request Body

| Field | Type | Required | Description |
| :--- | :--- | :--- | :--- |
| `number` | `integer` | ✅ Yes | Dice number to bet on (1-6) |
| `chip_amount` | `decimal` | ✅ Yes | Amount to bet (e.g., "50.00", "100.00") |

### Example Request:
```json
{
  "number": 3,
  "chip_amount": "50.00"
}
```

---

## ✅ Success Response

**Status Code:** `200 OK`

```json
{
  "id": 5001,
  "user": 10022,
  "round": "RD123456",
  "number": 3,
  "chip_amount": "50.00",
  "payout_amount": null,
  "is_winner": false,
  "created_at": "2026-02-11T10:01:10.123456Z",
  "balance": "450.00"
}
```

### Response Fields:
- `id`: Unique bet ID
- `user`: User ID who placed the bet
- `round`: Round ID for this bet
- `number`: Dice number bet on (1-6)
- `chip_amount`: Amount bet
- `payout_amount`: Payout amount (null until round ends)
- `is_winner`: Whether this bet won (false until round ends)
- `created_at`: Timestamp when bet was placed
- `balance`: User's updated wallet balance after bet

---

## ❌ Error Responses

### 400 Bad Request

#### Invalid Request Data:
```json
{
  "number": ["Ensure this value is less than or equal to 6."],
  "chip_amount": ["A valid number is required."]
}
```

#### Betting Window Closed:
```json
{
  "error": "Betting period has ended. Betting closes at 30 seconds."
}
```

#### Insufficient Balance:
```json
{
  "error": "Insufficient balance"
}
```

#### Round Ended:
```json
{
  "error": "Round has ended. Please refresh to see the new round."
}
```

#### Betting Closed:
```json
{
  "error": "Betting is closed"
}
```

### 401 Unauthorized
```json
{
  "detail": "Authentication credentials were not provided."
}
```

### 404 Not Found
```json
{
  "error": "No active round"
}
```
or
```json
{
  "error": "Wallet not found"
}
```

---

## 🎯 Betting Rules

1. **Betting Window**: Betting is only allowed during the first **30 seconds** of a round (configurable via `BETTING_CLOSE_TIME` setting).

2. **Multiple Bets**: Users can place multiple bets on the same number or different numbers.

3. **Balance Check**: The system automatically checks if the user has sufficient balance before placing the bet.

4. **Automatic Deduction**: Upon successful bet placement, the amount is immediately deducted from the user's wallet.

5. **Round Status**: Betting is only allowed when round status is `BETTING` or `WAITING`.

---

## 💡 Example Usage

### cURL:
```bash
curl -X POST https://gunduata.online/api/game/bet/ \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..." \
  -H "Content-Type: application/json" \
  -d '{
    "number": 4,
    "chip_amount": "100.00"
  }'
```

### Python (requests):
```python
import requests

url = "https://gunduata.online/api/game/bet/"
headers = {
    "Authorization": "Bearer <your_access_token>",
    "Content-Type": "application/json"
}
data = {
    "number": 4,
    "chip_amount": "100.00"
}

response = requests.post(url, json=data, headers=headers)
print(response.json())
```

### JavaScript (fetch):
```javascript
fetch('https://gunduata.online/api/game/bet/', {
  method: 'POST',
  headers: {
    'Authorization': 'Bearer <your_access_token>',
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({
    number: 4,
    chip_amount: "100.00"
  })
})
.then(response => response.json())
.then(data => console.log(data));
```

---

## 🔍 Postman Setup

1. **Method**: `POST`
2. **URL**: `https://gunduata.online/api/game/bet/`
3. **Headers**:
   - `Authorization`: `Bearer <your_access_token>`
   - `Content-Type`: `application/json`
4. **Body** (raw JSON):
   ```json
   {
     "number": 3,
     "chip_amount": "50.00"
   }
   ```

---

## 📊 Notes

- **Chip Amount**: Must be a positive decimal value (e.g., "25.00", "50.00", "100.00")
- **Number Range**: Must be between 1 and 6 (inclusive)
- **Concurrent Bets**: Multiple bets can be placed rapidly; each creates a separate bet record
- **Balance Update**: The response includes the updated balance after the bet is placed
- **Transaction Log**: Each bet creates a `BET` transaction record in the user's transaction history
