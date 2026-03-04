# Running Locust Load Tests

## Quick start

1. **Install Locust** (if not already installed):
   ```bash
   pip install locust
   ```

2. **Run Locust with web UI** (from the project root):
   ```bash
   locust -f locustfile.py --host=https://gunduata.online
   ```

3. **Open the Locust web UI** in your browser:
   - **Local:** http://localhost:8089
   - **Remote server:** http://YOUR_SERVER_IP:8089 (use `--web-host=0.0.0.0` when running Locust so it listens on all interfaces)

## If you cannot access the web UI

### Running on your own machine
- Open **http://127.0.0.1:8089** or **http://localhost:8089** after starting Locust.
- Ensure nothing else is using port **8089** (e.g. `lsof -i :8089`).

### Running on a remote server / VM
Locust binds to `127.0.0.1` by default, so the web UI is only reachable on that machine. To access from your laptop:

```bash
locust -f locustfile.py --host=https://gunduata.online --web-host=0.0.0.0 --web-port=8089
```

Then open **http://SERVER_IP:8089** in your browser (replace `SERVER_IP` with the server’s IP or hostname).

### Using the run script
From the project root:

```bash
chmod +x scripts/run_locust.sh
./scripts/run_locust.sh
```

This uses `--web-host=0.0.0.0` so the UI is reachable from other machines. Then open **http://localhost:8089** (if running locally) or **http://YOUR_SERVER_IP:8089** (if running on a server).

## Example: start a test from the UI

1. Open http://localhost:8089 (or your server:8089).
2. Set **Number of users** and **Spawn rate** (e.g. 10 users, 2 spawn rate).
3. Click **Start swarming**.

## Headless (no web UI)

```bash
locust -f locustfile.py --host=https://gunduata.online --headless --users 100 --spawn-rate 10 --run-time 2m
```

## Test users

### Option A: Run public-only (no login)
The locustfile will always hit public endpoints (`/api/game/settings/`, `/api/game/last-round-results/`).  
If you do **not** want login/bet traffic, set these to empty (or leave them unset) and run Locust normally.

### Option B: Use a real account (recommended for quick laptop testing)
Set credentials in environment variables so Locust can login and then hit authenticated endpoints (wallet, round, bets, betting):

```bash
export LOCUST_USERNAME="your_username_or_phone"
export LOCUST_PASSWORD="your_password"
locust -f locustfile.py --host=https://gunduata.online
```

### Option C: Use predictable load-test users (recommended for higher scale)
The locustfile can use a pool like `testuser_0..testuser_499` with a shared password.

Defaults:
- `LOCUST_USER_PREFIX=testuser_`
- `LOCUST_USER_COUNT=500`
- `LOCUST_PASSWORD=testpassword123`

Create them on the target DB before running a heavy test:

```bash
python scripts/create_test_users.py 500
```

Then run:

```bash
export LOCUST_USE_TEST_USERS="1"
export LOCUST_USER_PREFIX="testuser_"
export LOCUST_USER_COUNT="500"
export LOCUST_PASSWORD="testpassword123"
locust -f locustfile.py --host=https://gunduata.online
```
