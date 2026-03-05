# Production server details (reference – do not change servers from automation)

## Load balancer (Nginx / public entry)

- **IP:** 187.77.186.84  
- **Domain:** gunduata.club (also www.gunduata.club; config may mention gunduata.online)  
- **Ports:** 80 / 443  
- **Backends:** app servers on port **8001** (HTTP + WebSocket `/ws/`)
- **Frontend (gunduata.club website):** Nginx serves the repo’s `frontend--2/` directory. Site root on server: `/root/apk_of_ata/frontend--2`. Default page is the file `html` (no extension). Add `apk/` and `videos/` assets as needed; `/api/`, `/admin/`, `/ws/`, `/static/`, `/media/` are proxied to the backend.

## App servers (Docker)

- **Stack:** dice_game_web, dice_game_timer, dice_game_bet_worker (sometimes dice_game_redis)  
- **Port mapping:** host **8001** → container **8080**

| Server   | IP             | Notes |
|----------|----------------|--------|
| Server 1 | 72.61.254.71   | App exposed 8001 → 8080 |
| Server 2 | 72.61.254.74   | App 8001 → 8080; **shared Redis host** (other servers point Redis to this IP). Deploy sets `REDIS_HOST=redis` locally. |
| Server 3 | 72.62.226.41   | App 8001 → 8080. Deploy comment: “dedicated Redis host”; docker-compose defaults still point Redis to 72.61.254.74 unless overridden. |

## Database (Postgres / PgBouncer)

- **Host:** 72.61.255.231  
- **Port:** 6432  
- **DB name:** dice_game  
- **DB user:** muktesh  

## Redis (game state / betting / cache)

- **Host (default for most servers):** 72.61.254.74  
- **Port:** 6379  
- **Password:** Gunduata@123  

## Quick port map

- **Public:** 187.77.186.84:443 → forwards to 72.61.254.71 / 72.61.254.74 / 72.62.226.41:8001  
- **App container:** host :8001 → container :8080  
- **Redis:** 72.61.254.74:6379  
- **DB:** 72.61.255.231:6432  
