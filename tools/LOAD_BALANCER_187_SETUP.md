# Load balancer 187.77.186.84 (gunduata.club)

**DNS:** gunduata.club → **187.77.186.84** (orange cloud in Cloudflare)

**Flow:** User → Cloudflare → **187.77.186.84** (LB) → backends (71, 74, 41)

## On the load balancer (187.77.186.84)

1. **Nginx must proxy to these backends (port 8001):**
   - 72.61.254.71:8001
   - 72.61.254.74:8001
   - 72.62.226.41:8001

2. **Use the config in the repo:**  
   Copy `nginx/load_balancer.conf` to the LB server and enable it:
   ```bash
   # From your machine (or copy the file to 187.77.186.84)
   scp nginx/load_balancer.conf root@187.77.186.84:/etc/nginx/sites-available/gunduata_lb.conf
   # On 187.77.186.84:
   ln -sf /etc/nginx/sites-available/gunduata_lb.conf /etc/nginx/sites-enabled/
   nginx -t && systemctl reload nginx
   ```

3. **Timeouts:** Config uses **120s** for HTTP so Cloudflare doesn’t get 504. If your LB uses something else, set `proxy_read_timeout` (and connect/send) to at least **120s**.

4. **SSL:** If Cloudflare uses “Flexible” or “Full”, the LB can listen on **80 only** and proxy HTTP to the backends. If the LB must speak HTTPS to Cloudflare, add a `listen 443 ssl` server block and your cert paths.

## Backends (71, 74, 41)

- Deploy code with: `bash tools/deploy_leaderboard_route.sh`
- At least one backend must have the app **Up** (not Restarting). If 74 and 41 are unhealthy, the LB will still work if 71 is up.

## Quick test

```bash
curl -s -o /dev/null -w "%{http_code}" --connect-timeout 10 https://gunduata.club/
# Expect 200 or 301/302, not 504.
```
