# Game Prediction API Documentation

This document describes the API for submitting and managing game predictions in the Gundu Ata application.

## Submit Prediction

Submit a prediction for the current round. This is a "free" guess that users can make after betting has closed but before the result is announced.

- **URL**: `https://gunduata.online/api/game/prediction/`
- **Method**: `POST`
- **Authentication**: Required (JWT Token)
- **CSRF Protection**: Exempt

### Request Body

| Field | Type | Description |
| :--- | :--- | :--- |
| `number` | Integer | The predicted number (1-6). |

**Example Request:**
```json
{
  "number": 6
}
```

### Response

#### Success (201 Created / 200 OK)
Returns the created or updated prediction object.

| Field | Type | Description |
| :--- | :--- | :--- |
| `message` | String | "Prediction submitted successfully" or "Prediction updated" |
| `prediction` | Object | The prediction details. |
| `prediction.id` | Integer | Unique ID of the prediction. |
| `prediction.user` | Object | User details of the person who made the prediction. |
| `prediction.round` | Integer | ID of the game round. |
| `prediction.number` | Integer | The predicted number. |
| `prediction.is_correct`| Boolean | Whether the prediction was correct (updated after result). |
| `prediction.created_at`| String | ISO timestamp of when the prediction was made. |

**Example Response:**
```json
{
  "message": "Prediction submitted successfully",
  "prediction": {
    "id": 456,
    "user": {
      "id": 42,
      "username": "player123",
      "phone_number": "9876543210"
    },
    "round": 123,
    "number": 6,
    "is_correct": false,
    "created_at": "2024-01-15T10:45:30Z"
  }
}
```

### Constraints & Rules

1. **Timing**: Predictions are ONLY allowed after betting has closed and before the result is announced.
   - Specifically: `timer >= BETTING_CLOSE_TIME` and `timer < DICE_RESULT_TIME`.
2. **One Per Round**: Each user can only have one prediction per round. If they submit another one, the existing prediction will be updated.
3. **No Cost**: Predictions do not cost any chips or balance.
4. **Result Update**: The `is_correct` field is automatically updated by the backend when the round result is announced.

### Error Responses

- **400 Bad Request**:
  - `{"number": ["Ensure this value is less than or equal to 6."]}` (Invalid number)
  - `{"error": "Predictions can only be submitted after betting closes"}` (Too early)
  - `{"error": "Result already announced. Predictions closed."}` (Too late)
  - `{"error": "No active round"}`
- **401 Unauthorized**: Missing or invalid authentication token.
- **500 Internal Server Error**: Unexpected server error.

---

## Get Round Predictions

Retrieve all predictions and statistics for a specific round or the current round.

- **URL**: `https://gunduata.online/api/game/round/<round_id>/predictions/`
- **Alternative URL (Current Round)**: `https://gunduata.online/api/game/round/predictions/`
- **Method**: `GET`
- **Authentication**: Required (JWT Token)

### URL Parameters

| Parameter | Type | Description |
| :--- | :--- | :--- |
| `round_id` | String | (Optional) The specific round ID (e.g., `ROUND_2024_001_123`). |

### Response (200 OK)

Returns detailed information about the round, the user's own prediction, all predictions, and statistics.

**Example Response:**
```json
{
  "round": {
    "round_id": "ROUND_2024_001_123",
    "status": "COMPLETED",
    "dice_result": 6
  },
  "user_prediction": {
    "id": 456,
    "user": { ... },
    "round": 123,
    "number": 6,
    "is_correct": true,
    "created_at": "2024-01-15T10:45:30Z"
  },
  "predictions": [
    {
      "id": 456,
      "user": { ... },
      "round": 123,
      "number": 6,
      "is_correct": true,
      "created_at": "2024-01-15T10:45:30Z"
    },
    ...
  ],
  "statistics": {
    "overall": {
      "total_predictions": 50,
      "total_unique_users": 50,
      "total_correct": 12
    },
    "by_number": [
      {
        "number": 1,
        "total_predictions": 8,
        "correct_predictions": 0
      },
      ...
      {
        "number": 6,
        "total_predictions": 12,
        "correct_predictions": 12
      }
    ]
  },
  "count": 50
}
```

### Constraints & Rules

1. **Visibility**: This endpoint provides transparency by showing how many users predicted each number.
2. **Current Round**: If `round_id` is omitted, the API automatically fetches data for the current active or most recent round.
3. **User Specific**: The `user_prediction` field allows the app to easily highlight the current user's choice in the UI.

