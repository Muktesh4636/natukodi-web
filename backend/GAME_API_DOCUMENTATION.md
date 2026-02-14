# Gundu Ata Game API Documentation

This document provides a comprehensive guide to the Game API endpoints for the Gundu Ata application.

## Base URL
`https://gunduata.online/api/game/`

---

## 1. Last Round Results
Returns the results of the most recently completed round, including all 6 dice values.

*   **Endpoint:** `last-round-results/`
*   **Method:** `GET`
*   **Authentication:** None (Public)
*   **Response Format:**
    ```json
    {
      "round_id": "R1770981343",
      "dice_1": 1,
      "dice_2": 5,
      "dice_3": 4,
      "dice_4": 6,
      "dice_5": 2,
      "dice_6": 6,
      "dice_result": "6",
      "timestamp": "2026-02-13T11:30:44.187476+00:00"
    }
    ```

---

## 2. Recent Round Results
Returns a list of the last 3 completed rounds. Useful for displaying a history of recent outcomes.

*   **Endpoint:** `recent-round-results/`
*   **Method:** `GET`
*   **Authentication:** None (Public)
*   **Response Format:**
    ```json
    [
      {
        "round_id": "R1770981343",
        "dice_1": 1,
        "dice_2": 5,
        "dice_3": 4,
        "dice_4": 6,
        "dice_5": 2,
        "dice_6": 6,
        "dice_result": "6",
        "timestamp": "2026-02-13T11:30:44.187476+00:00"
      },
      ...
    ]
    ```

---

## 3. Specific Round Results
Returns detailed information about a specific round by its ID, including winning numbers and multipliers.

*   **Endpoint:** `results/{round_id}/`
*   **Method:** `GET`
*   **Authentication:** None (Public)
*   **Parameters:**
    *   `round_id`: The unique identifier for the round (e.g., `R1770981343`).
*   **Response Format:**
    ```json
    {
      "round_id": "R1770981343",
      "dice_result": "6",
      "round": {
        "round_id": "R1770981343",
        "status": "COMPLETED",
        "dice_result": "6",
        "dice_values": [1, 5, 4, 6, 2, 6],
        "start_time": "2026-02-13T11:15:43.980859+00:00",
        "result_time": "2026-02-13T11:29:43.129031+00:00",
        "end_time": "2026-02-13T11:30:44.187476+00:00"
      },
      "winning_numbers": [
        {
          "number": 6,
          "frequency": 2,
          "payout_multiplier": 2.0
        }
      ]
    }
    ```

---

## 4. Current Round Status
Returns the status of the currently active game round, including the timer.

*   **Endpoint:** `round/`
*   **Method:** `GET`
*   **Authentication:** Required (Bearer Token)
*   **Response Format:**
    ```json
    {
      "round_id": "R1770981343",
      "status": "BETTING",
      "timer": 25,
      "total_bets": 150,
      "total_amount": "1500.00"
    }
    ```

---

## 5. Place a Bet
Allows an authenticated user to place a bet on a specific number for the current round.

*   **Endpoint:** `bet/`
*   **Method:** `POST`
*   **Authentication:** Required (Bearer Token)
*   **Request Body:**
    ```json
    {
      "number": 6,
      "amount": 100
    }
    ```
*   **Response Format:**
    ```json
    {
      "status": "success",
      "message": "Bet placed successfully",
      "bet_id": 45678,
      "new_balance": "900.00"
    }
    ```

---

## 6. Game Settings
Returns the current game configuration, such as durations and payout ratios.

*   **Endpoint:** `settings/`
*   **Method:** `GET`
*   **Authentication:** None (Public)
*   **Response Format:**
    ```json
    {
      "betting_duration": 30,
      "result_display_duration": 20,
      "payout_ratios": {
        "1": 6.0,
        "2": 6.0,
        ...
      }
    }
    ```
