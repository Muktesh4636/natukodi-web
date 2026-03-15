# Why Servers Feel Slow & What Was Done

## Main causes of slowness

### 1. **Redis and DB are on different hosts**
- In `docker-compose.yml`, `REDIS_HOST` and `DB_HOST` point to other servers (e.g. `72.61.254.74`, `72.61.255.231`).
- Every Redis/DB call adds network round-trip latency (often 10–50 ms+ per call).
- **What helps:** Run Redis (and if possible Postgres) on the same host as the web app, or in the same region, to cut latency.

### 2. **Redis connections were created per call (fixed)**
- `get_redis_client()` used to create a **new TCP connection** every time it was called.
- It’s used in many places, including `UserSerializer.get_wallet_balance()` — so serializing 20 users could open 20 new connections to Redis per request.
- **Fix applied:** `get_redis_client()` now uses `settings.REDIS_POOL` when available, so connections are reused instead of opening a new one per call.

### 3. **Maintenance middleware and Redis**
- Maintenance mode is checked on almost every request (with a 2s in-process cache).
- On cache miss, the middleware was opening a new Redis connection instead of using the pool.
- **Fix applied:** Middleware now uses `REDIS_POOL` when available.

### 4. **Heavy work in the request path (deposit proof)**
- Payment proof upload used to run Tesseract OCR (up to 3 passes) **before** responding, so the API could take 5–15+ seconds.
- **Fix applied:** Deposit is created and the API responds immediately; OCR runs in a background thread and updates UTR later.

### 5. **Gunicorn and timeouts**
- `docker-compose` uses 9 workers and 120s timeout. If Redis or DB is slow or unreachable, workers can block until timeout.
- Health check and maintenance bypass for `/api/health/` ensure the load balancer/Cloudflare can get a fast 200 from the app even when Redis is slow.

---

## What to check when things feel slow

1. **Redis**
   - From the web server: `redis-cli -h <REDIS_HOST> -a <password> ping`
   - If this is slow or fails, all Redis-dependent requests will be slow.

2. **Database**
   - Run a simple query from the app host to the DB host (e.g. `psql` or app logs). High latency or connection errors will slow every DB call.

3. **Health endpoint**
   - `curl -w '%{time_total}\n' -o /dev/null -s https://gunduata.club/api/health/`
   - Should return in &lt; 1 s. If it’s slow, the problem is on the server/network, not just “heavy” endpoints.

4. **Logs**
   - `docker logs dice_game_web --tail 200` for Redis/DB errors or long-running requests.

5. **Cloudflare / proxy**
   - See `docs/CLOUDFLARE_504.md` for origin timeout and health-check URL so the proxy doesn’t cut off slow responses too early.

---

## Summary of code changes for performance

| Area | Change |
|------|--------|
| `game/utils.py` | `get_redis_client()` uses `REDIS_POOL` when set so callers reuse connections. |
| `dice_game/maintenance_middleware.py` | Uses `REDIS_POOL` for maintenance check instead of opening a new Redis client on cache miss. |
| `accounts/views.py` | Deposit proof API creates the deposit and returns immediately; UTR OCR runs in a background thread. |

These reduce connection churn and move heavy work off the request path so the servers can respond faster under load.
