# Load Balancer Setup - Complete Guide

## ✅ Current Status

### Load Balancer: **CONFIGURED AND RUNNING**
- **Location:** Server 1 (72.61.254.71)
- **Type:** Nginx Load Balancer
- **Port:** 80 (HTTP)
- **Method:** `least_conn` (distributes to server with fewest connections)

### Backend Servers:
- **Server 1:** 72.61.254.71:8001 ✅ Running
- **Server 2:** 72.61.254.74:8001 ⚠️ Needs setup

---

## How 10 Users Connect Now:

```
10 Users
   ↓
Load Balancer (72.61.254.71:80)
   ├──→ ~5 users → Server 1 (72.61.254.71:8001)
   └──→ ~5 users → Server 2 (72.61.254.74:8001) [when ready]
         ↓
         Both → Redis (Server 3)
         Both → Database (Server 4)
```

**Result:** All 10 users see the **SAME game** because:
- Game state is in Redis (Server 3)
- Both servers subscribe to Redis Pub/Sub
- Timer updates broadcast to all users regardless of which server they're on

---

## WebSocket Connection Flow:

**User connects to:** `ws://gunduata.online/ws/game/` or `ws://72.61.254.71/ws/game/`

**Load Balancer:**
1. Receives WebSocket upgrade request
2. Routes to Server 1 or Server 2 (based on connection count)
3. Maintains WebSocket connection (no sticky sessions needed - stateless design)

**Game Updates:**
- Game Engine (Server 1 Leader) → Redis Pub/Sub
- Both Server 1 and Server 2 WebSocket servers subscribe to Redis
- All users receive same timer updates

---

## Next Steps to Complete Setup:

1. **Set up Server 2 web server** (copy backend code and Dockerfile)
2. **Test load balancing** (verify users distribute evenly)
3. **Configure DNS** (point gunduata.online to load balancer IP)

---

## Testing:

```bash
# Test Server 1 directly
curl http://72.61.254.71:8001/health

# Test Server 2 directly (when ready)
curl http://72.61.254.74:8001/health

# Test through Load Balancer
curl http://72.61.254.71/health
```

---

## Configuration Files:

- **Load Balancer Config:** `/etc/nginx/sites-available/load_balancer` on Server 1
- **Backend Servers:** Defined in `upstream backend_servers` block
