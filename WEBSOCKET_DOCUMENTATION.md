# WebSocket Documentation - Gundu Ata Game

This document describes the WebSocket architecture, connection details, and message formats for the Gundu Ata real-time game engine.

## Connection Details

- **URL:** `wss://gunduata.online/ws/game/`
- **Protocol:** Secure WebSocket (WSS)
- **Authentication:** Not required for game state updates.

## Architecture Overview

1.  **Game Engine (`game_engine_v2.py`)**: A background process that manages the game clock, round transitions, and dice result generation. It publishes state updates to a Redis Pub/Sub channel (`game_room`) every second.
2.  **Redis Pub/Sub**: Acts as the high-speed messaging backbone between the game engine and the web servers.
3.  **Django Channels Consumers (`consumers.py`)**: WebSocket handlers running on the web servers. They subscribe directly to the Redis `game_room` channel and forward every message to connected clients.
4.  **Load Balancing**: Nginx handles SSL termination and distributes WebSocket connections across multiple backend servers.

## Message Flow

### 1. Connection Initiation
Upon successful connection, the server immediately sends an initial state message to sync the client.

- **Type:** `game_state`
- **Purpose:** Provide the current round ID and status so the UI can load immediately.

### 2. Real-time Updates
The server sends updates approximately every 1 second.

- **Round Start (Timer = 1):** Two messages are sent back-to-back:
    1.  `type: "game_start"`
    2.  `type: "timer"`
- **Standard Update (Timer > 1):** One message is sent:
    1.  `type: "timer"`

### 3. Heartbeat
To prevent connection timeouts, the server sends a heartbeat every 20 seconds.

---

## JSON Message Formats

### Initial Connection Message
Sent once immediately after the WebSocket handshake.
```json
{
  "type": "game_state",
  "round_id": "R1771176584",
  "status": "BETTING",
  "timer": 8
}
```

### Standard Timer Update
Sent every second during the round.
```json
{
  "type": "timer",
  "round_id": "R1771176584",
  "timer": 9,
  "status": "BETTING",
  "dice_result": null,
  "is_rolling": false,
  "server_time": 1771176587
}
```

### Round Start Messages (Timer = 1)
Two messages sent sequentially at the beginning of every round.
```json
// Message 1
{
  "type": "game_start",
  "round_id": "R1771176584",
  "timer": 1,
  "status": "BETTING",
  "dice_result": null,
  "is_rolling": false,
  "server_time": 1771176579
}

// Message 2
{
  "type": "timer",
  "round_id": "R1771176584",
  "timer": 1,
  "status": "BETTING",
  "dice_result": null,
  "is_rolling": false,
  "server_time": 1771176579
}
```

### Phase Transitions (Rolling/Result)
When the status changes to `ROLLING` or `RESULT`, the fields update accordingly.
```json
{
  "type": "timer",
  "round_id": "R1771176584",
  "timer": 31,
  "status": "ROLLING",
  "dice_result": null,
  "is_rolling": true,
  "server_time": 1771176610
}
```

### Heartbeat Message
Sent every 20 seconds to keep the connection alive.
```json
{
  "type": "heartbeat",
  "server_time": 1771176620
}
```

## Status Values
- `WAITING`: No active round.
- `BETTING`: Players can place bets (Timer 1-30).
- `ROLLING`: Dice are being rolled (Timer 31-35).
- `RESULT`: Dice result is displayed (Timer 36-45).
