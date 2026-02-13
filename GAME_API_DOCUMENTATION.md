# Gundu Ata Game API Documentation

This document provides a comprehensive guide to the game-related APIs for Gundu Ata.

## Base URL
`https://gunduata.online`

## Authentication
All game APIs require a JWT Bearer Token.
**Header:** `Authorization: Bearer <your_access_token>`

---

## 1. Game Status & Timer
### **Get Current Round Status**
Returns the current state of the game (Timer, Round ID, Status).
*   **Endpoint:** `GET /api/game/round/`
*   **Response Fields:**
    *   `round_id`: Unique ID of the current round.
    *   `timer`: Current seconds remaining in the phase.
    *   `status`: `BETTING`, `CLOSED`, or `RESULT`.
    *   `dice_result`: The winning number (only if status is `RESULT`).

---

## 2. Betting APIs
### **Place a Bet**
Place a new bet on a number (1-6) for the current active round.
*   **Endpoint:** `POST /api/game/bet/`
*   **Request Body:**
    ```json
    {
      "number": 3,
      "chip_amount": 50.00
    }
    ```
*   **Response:** `201 Created` with bet details and updated wallet balance.

### **View Last Bet**
View the details of your most recent bet in the current round.
*   **Endpoint:** `GET /api/game/bet/last/`

### **Delete/Refund Last Bet**
Remove your most recent bet and get a refund (only allowed during `BETTING` phase).
*   **Endpoint:** `DELETE /api/game/bet/last/`

### **View All My Current Bets**
List all bets you have placed in the current active round.
*   **Endpoint:** `GET /api/game/bets/current/`

---

## 3. Results & History
### **Last Round Results**
Get the winning numbers and aggregate statistics for the most recently completed round.
*   **Endpoint:** `GET /api/game/winning-results/`
*   **Note:** Individual winning bets are hidden for privacy.

### **Specific Round Result**
Get the dice result for a specific round ID.
*   **Endpoint:** `GET /api/game/results/<round_id>/`

### **Recent Winning History**
Get a list of winning numbers from the last 20-50 rounds.
*   **Endpoint:** `GET /api/game/last-round-results/`

---

## 4. Game Analytics
### **Total Bet Exposure**
See the total amount of money placed on each number (1-6) by all users in the current round.
*   **Endpoint:** `GET /api/game/round/exposure/`
*   **Response Example:**
    ```json
    {
      "1": 500.00,
      "2": 1250.00,
      "3": 0.00,
      ...
    }
    ```

---

## 5. Account & Wallet
### **Get Wallet Balance**
*   **Endpoint:** `GET /api/auth/wallet/`

### **Get User Profile**
*   **Endpoint:** `GET /api/auth/profile/`

---

## 6. Real-time Updates (WebSockets)
For instant timer updates and results without polling, connect to:
*   **WebSocket URL:** `wss://gunduata.online/ws/game/`
