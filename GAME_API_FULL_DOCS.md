# Gundu Ata Game API - Full Endpoint Documentation

This document provides the full URLs and exact JSON request/response formats for all game-related AP

**Base URL:** `https://gunduata.online`  
**Auth Header:** `Authorization: Bearer <your_access_token>`

---

## 1. Game Status & Timer
### **Get Current Round Status**
*   **URL:** `GET https://gunduata.online/api/game/round/`
*   **Response JSON:**
    ```json
    {
      "round_id": "R1770910659",
      "timer": 25,
      "status": "BETTING",
      "dice_result": null,
      "server_time": "2026-02-12T16:50:00Z"
    }
    ```

---

## 2. Betting APIs
### **Place a New Bet**
*   **URL:** `POST https://gunduata.online/api/game/bet/`
*   **Request JSON:**
    ```json
    {
      "number": 1,
      "chip_amount": 100.00
    }
    ```
*   **Response JSON (Success):**
    ```json
    {
      "id": 54321,
      "round": "R1770910659",
      "number": 1,
      "chip_amount": "100.00",
      "wallet_balance": "950.00",
      "message": "Bet placed successfully"
    }
    ```

### **View Last Bet**
*   **URL:** `GET https://gunduata.online/api/game/bet/last/`
*   **Response JSON:**
    ```json
    {
      "id": 54321,
      "number": 1,
      "chip_amount": "100.00",
      "created_at": "2026-02-12T16:51:00Z"
    }
    ```

### **Delete/Refund Last Bet**
*   **URL:** `DELETE https://gunduata.online/api/game/bet/last/`
*   **Response JSON:**
    ```json
    {
      "message": "Last bet removed and ₹100.00 refunded to wallet",
      "refunded_amount": "100.00",
      "new_balance": "1050.00"
    }
    ```

### **View All My Current Round Bets**
*   **URL:** `GET https://gunduata.online/api/game/bets/current/`
*   **Response JSON:**
    ```json
    [
      { "number": 1, "chip_amount": "100.00" },
      { "number": 5, "chip_amount": "50.00" }
    ]
    ```

---

## 3. Results & History
### **Last Round Winning Results**
*   **URL:** `GET https://gunduata.online/api/game/winning-results/`
*   **Response JSON:**
    ```json
    {
      "round_id": "R1770910600",
      "dice_result": 6,
      "winning_numbers": [
        { "number": 6, "frequency": 2, "payout_multiplier": 2.0 }
      ],
      "winning_bets": [],
      "statistics": {
        "total_bets": 150,
        "total_bet_amount": "15000.00",
        "total_payouts": "8000.00"
      }
    }
    ```

### **Recent Winning History (Last 20 Rounds)**
*   **URL:** `GET https://gunduata.online/api/game/last-round-results/`
*   **Response JSON:**
    ```json
    [
      { "round_id": "R1770910600", "dice_result": 6 },
      { "round_id": "R1770910550", "dice_result": 2 },
      { "round_id": "R1770910500", "dice_result": 4 }
    ]
    ```

---

## 4. Game Analytics
### **Total Bet Exposure (Admin/Public)**
*   **URL:** `GET https://gunduata.online/api/game/round/exposure/`
*   **Response JSON:**
    ```json
    {
      "1": "500.00",
      "2": "1250.00",
      "3": "0.00",
      "4": "2100.00",
      "5": "75.00",
      "6": "300.00",
      "total": "4225.00"
    }
    ```

---

## 5. Account & Wallet
### **Get Wallet Balance**
*   **URL:** `GET https://gunduata.online/api/auth/wallet/`
*   **Response JSON:**
    ```json
    {
      "balance": "1050.00",
      "currency": "INR"
    }
    ```

---

## 6. Real-time Updates
### **WebSocket Connection**
*   **URL:** `wss://gunduata.online/ws/game/`
*   **Message Received (Every Second):**
    ```json
    {
      "type": "timer_update",
      "timer": 15,
      "status": "BETTING",
      "round_id": "R1770910659"
    }
    ```
