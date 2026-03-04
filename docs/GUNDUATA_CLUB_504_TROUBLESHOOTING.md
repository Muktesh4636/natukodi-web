# 504 Gateway Timeout – gunduata.club

The 504 "Gateway time-out" page from **Cloudflare** means: **the origin server (gunduata.club) did not respond in time**. So the problem is on the **server that hosts gunduata.club**, not the browser or Cloudflare.

## Request flow for gunduata.club

```
User → Cloudflare (proxy) → Your server (gunduata.club) → Nginx → Django (port 8001)
```

- **Cloudflare** waits for a response from your origin (default often **100 seconds**). If nothing comes back in time → **504**.
- **Nginx** on your server uses `proxy_read_timeout 120s` for `gunduata.club` (see `nginx/gunduata.club.conf`).
- So if Django takes **more than ~100 seconds** (or whatever Cloudflare’s origin timeout is), you get 504.

## What to check on the gunduata.club server

1. **Confirm the app is responding**
   - On the server: `curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8001/api/health/`
   - Should return `200`. If not, the app (e.g. Gunicorn) is down or stuck.

2. **Which URL times out?**
   - **Homepage** `https://gunduata.club/` → Django `serve_react_app` (serves React build or fallback HTML).
   - **Admin** `https://gunduata.club/game-admin/` → login/dashboard (DB + cache).
   - **API** e.g. `https://gunduata.club/api/...` → various views (DB/Redis).
   - Check **Django/Gunicorn logs** on that server around the time of the 504 to see which view was slow or errored.

3. **Increase Cloudflare’s origin timeout (recommended)**
   - In **Cloudflare Dashboard** → your domain (gunduata.club) → **Rules** or **Speed** / **Optimization** (depends on plan).
   - Look for **“Origin connection timeout”** or **“Origin response timeout”** (often 100s).
   - Set it to **120** seconds so it matches Nginx’s `proxy_read_timeout 120s` and gives the origin a bit more time.

4. **Ensure latest backend is deployed on gunduata.club**
   - Caching and query fixes only help if they’re running on the **same host** that serves gunduata.club.
   - Deploy with:  
     `SERVER_PASSWORD='...' ./tools/deploy_leaderboard_route.sh`  
     (or your normal deploy to the gunduata.club origin).

5. **If gunduata.club is behind a load balancer**
   - The machine that **directly** serves `server_name gunduata.club` (or that receives traffic for it) must have the app running and Nginx config with 120s timeouts.
   - Check that this is the same box you’re deploying to and where you run `curl .../api/health/`.

## Quick test from your machine

```bash
# Replace with the actual gunduata.club origin IP if you’re testing direct to origin
curl -v --max-time 15 https://gunduata.club/api/health/
```

- If this succeeds quickly → app is up; 504 may be intermittent (load, slow DB/Redis) or due to Cloudflare timeout.
- If this hangs or fails → the origin (gunduata.club server) is slow or down; debug that server and Nginx/Django logs.

## Summary

- **504 = origin (gunduata.club) too slow or not responding.**
- Fix: make the origin faster (deploy caching/optimizations, fix DB/Redis), and/or **raise Cloudflare’s origin timeout** to 120s so the origin has time to respond.
