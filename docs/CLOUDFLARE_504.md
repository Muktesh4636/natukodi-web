# Fixing 504 Gateway Timeout (Cloudflare)

If you see **504 Gateway time-out** for gunduata.club, Cloudflare is not getting a response from your origin server in time.

## Code-side fixes (already applied)

- **`/api/health/`** never touches Redis or DB — use this for health checks.
- Maintenance middleware skips Redis for `/api/health/` so it always returns quickly.
- Redis timeouts are reduced (connect 1–2s) so a slow Redis does not hang the app.
- Dashboard and dashboard-data have try/except so Redis/DB errors don’t crash the worker.

## Cloudflare settings

1. **Increase origin timeout**
   - Dashboard → **Rules** → **Configuration Rules** (or **Settings** → **Network**).
   - Find **Origin Server Connection** / **Origin Response Timeout**.
   - Set to **120** seconds (or higher) so slow dashboard/DB requests can finish.

2. **Use a health check**
   - If you use **Load Balancing** or **Health Checks**, set the URL to:  
     `https://gunduata.club/api/health/`
   - That endpoint is fast and does not depend on Redis/DB.

3. **Check the origin**
   - On the server: `curl -I http://127.0.0.1:8000/api/health/`  
     (replace 8000 with your app port)
   - Should return `200 OK` quickly. If it hangs, the problem is on the server (app/Redis/DB).

## Server-side checks

- Restart the app after deploy: `docker compose restart web` (or your web service).
- Ensure Redis is up: `redis-cli -h <host> ping`.
- Check app logs: `docker logs dice_game_web --tail 100`.
