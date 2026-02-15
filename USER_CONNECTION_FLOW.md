# Where Do 10 Users Go? - Connection Flow Explanation

## Current Architecture (Without Load Balancer)

### **Scenario: 10 Users Join the Game**

---

## **Connection Flow:**

```
10 Users
   ↓
[They connect to Server 1 OR Server 2 directly]
   ↓
Server 1 (72.61.254.71) ← 5 users might connect here
   OR
Server 2 (72.61.254.74) ← 5 users might connect here
   ↓
Both servers connect to:
   ↓
Server 3 (72.62.226.41) - Redis
   ↓
[All users see the SAME game state]
   ↓
When users place bets:
   ↓
Bets → Redis Streams → Workers → Server 4 (Database)
```

---

## **Detailed Breakdown:**

### **1. User Connection (WebSocket)**

**Endpoint:** `ws://[SERVER_IP]:8001/ws/game/`

**Without Load Balancer:**
- Users connect directly to **Server 1** (`72.61.254.71:8001`) OR **Server 2** (`72.61.254.74:8001`)
- Which server they connect to depends on:
  - Which URL they use (if you have different domains)
  - DNS configuration
  - Or they might all connect to the same server if only one is public

**Current Status:**
- **Server 1:** Has Docker web container (port 8001) - but it's restarting
- **Server 2:** Need to check if web server is running

### **2. Game State (All Users See Same Game)**

**Key Point:** Even though users connect to different servers, they ALL see the same game because:

1. **Game Engine** (on Server 1 - Leader) publishes timer to **Redis (Server 3)**
2. **Both Server 1 and Server 2** WebSocket servers subscribe to Redis Pub/Sub
3. **All 10 users** receive the same timer updates regardless of which server they're on

```
User 1-5 (Server 1) ──┐
                       ├──→ Redis Pub/Sub ──→ Same Timer Updates
User 6-10 (Server 2) ──┘
```

### **3. Bet Placement Flow**

When a user places a bet:

```
User (Server 1 or 2)
   ↓
WebSocket receives bet
   ↓
Bet pushed to Redis Stream (Server 3)
   ↓
Worker processes (Server 1 or 2) read from Stream
   ↓
Worker writes to Database (Server 4)
```

**Important:** It doesn't matter which server the user is on - all bets go to the same Redis Stream, and any worker can process them.

---

## **Example: 10 Users Scenario**

### **Distribution (Without Load Balancer):**

**Option A: All on Server 1**
```
10 Users → Server 1 (72.61.254.71:8001)
         → Redis (Server 3)
         → Database (Server 4)
```

**Option B: Split (5 on each)**
```
5 Users → Server 1 (72.61.254.71:8001)
5 Users → Server 2 (72.61.254.74:8001)
         ↓
         Both → Redis (Server 3)
         Both → Database (Server 4)
```

**Result:** All 10 users see the **SAME game** because game state is centralized in Redis.

---

## **With Load Balancer (Recommended for Production):**

```
10 Users
   ↓
Load Balancer (e.g., Nginx/HAProxy)
   ↓
   ├──→ Server 1 (5 users)
   └──→ Server 2 (5 users)
         ↓
         Both → Redis (Server 3)
         Both → Database (Server 4)
```

**Benefits:**
- Automatic distribution
- Failover if one server crashes
- Better performance (load spread)

---

## **Current Status:**

✅ **Server 1:** Web container running (port 8001) - but restarting  
⚠️ **Server 2:** Need to verify web server is running  
✅ **Server 3:** Redis working (all game state here)  
✅ **Server 4:** Database working (all bets stored here)  

---

## **Recommendation:**

For 10 users, **either setup works**, but for production with 3,000+ users:

1. **Set up Load Balancer** to distribute users evenly
2. **Ensure both Server 1 and Server 2** have web servers running
3. **Configure DNS** to point to load balancer

**Current:** Users can connect directly to Server 1 or Server 2, and they'll all see the same game!
