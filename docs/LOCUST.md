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

The locustfile expects test users created by `scripts/create_test_users.py` (e.g. `testuser_0`, `testuser_1`, … with password `testpassword123`). Create them on the target environment before running load tests.
