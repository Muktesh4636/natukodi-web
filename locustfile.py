from locust import HttpUser, task, between
import os
import random
import time

class GameUser(HttpUser):
    wait_time = between(1, 2)
    token = None
    current_status = "WAITING"
    balance = 0
    round_id = None
    _last_round_fetch_ts = 0.0

    def on_start(self):
        """
        Login when user starts (optional).

        Supports two modes:
        - Public-only: don't set LOCUST_USERNAME/LOCUST_PASSWORD and it will only hit public endpoints.
        - Auth mode: set LOCUST_USERNAME/LOCUST_PASSWORD or use test users:
            LOCUST_USER_PREFIX=testuser_  (default)
            LOCUST_USER_COUNT=500         (default)
            LOCUST_PASSWORD=testpassword123 (default)
        """
        self.enable_side_effects = os.getenv("LOCUST_ENABLE_SIDE_EFFECTS", "0").strip().lower() in ("1", "true", "yes", "y")
        self.enable_admin = os.getenv("LOCUST_ENABLE_ADMIN", "0").strip().lower() in ("1", "true", "yes", "y")

        explicit_username = os.getenv("LOCUST_USERNAME")
        explicit_password = os.getenv("LOCUST_PASSWORD")
        use_test_users = os.getenv("LOCUST_USE_TEST_USERS", "0").strip().lower() in ("1", "true", "yes", "y")

        # Public-only mode (default): do not attempt login.
        # Enable auth either by providing explicit credentials, or by setting LOCUST_USE_TEST_USERS=1.
        if explicit_username and explicit_password:
            username = explicit_username
            password = explicit_password
        elif use_test_users:
            prefix = os.getenv("LOCUST_USER_PREFIX", "testuser_")
            user_count = int(os.getenv("LOCUST_USER_COUNT", "500"))
            password = os.getenv("LOCUST_PASSWORD", "testpassword123")
            user_id = random.randint(0, max(1, user_count) - 1)
            username = f"{prefix}{user_id}"
        else:
            return

        with self.client.post("/api/auth/login/", json={
            "username": username,
            "password": password
        }, catch_response=True) as response:
            if response.status_code == 200:
                try:
                    data = response.json()
                except Exception:
                    response.failure("Login returned invalid JSON")
                    return

                self.token = data.get("access")
                self.client.headers.update({"Authorization": f"Bearer {self.token}"})
            elif response.status_code == 401:
                # User not found - run: python scripts/create_test_users.py 500
                # Don't hard-fail the entire user; keep them in public-only mode.
                response.failure(f"Login failed for {username} (401). Wrong password or user doesn't exist.")
                self.token = None
            else:
                response.failure(f"Login failed: {response.status_code}")
                self.token = None

        # Cache wallet balance (best-effort). We do NOT attempt to "refill" via deposit endpoints.
        self.refresh_wallet_balance()
        self.refresh_round_cache(force=True)

    def refresh_round_cache(self, force: bool = False):
        """Fetch current round and cache round_id/status with throttling."""
        now = time.time()
        if not force and (now - self._last_round_fetch_ts) < 2:
            return
        self._last_round_fetch_ts = now

        with self.client.get("/api/game/round/", catch_response=True) as response:
            if response.status_code == 200:
                try:
                    data = response.json()
                except Exception:
                    response.failure("current_round returned invalid JSON")
                    return
                self.current_status = data.get("status", self.current_status)
                self.round_id = data.get("round_id") or data.get("RoundId") or self.round_id
            else:
                # If the site is up, this should be 200; record failures.
                response.failure(f"Failed to get round: {response.status_code}")

    def refresh_wallet_balance(self):
        """Best-effort wallet fetch (auth mode only)."""
        if not self.token:
            return
            
        with self.client.get("/api/auth/wallet/", catch_response=True) as response:
            if response.status_code == 200:
                try:
                    data = response.json()
                except Exception:
                    response.failure("Wallet returned invalid JSON")
                    return

                self.balance = float(data.get("balance", 0))
            else:
                response.failure(f"Wallet check failed: {response.status_code}")

    # ----------------------------
    # Public/readonly API coverage
    # ----------------------------

    @task(2)
    def api_root(self):
        self.client.get("/api/")

    @task(2)
    def loading_time(self):
        self.client.get("/api/loading-time/")

    @task(5)
    def game_settings(self):
        self.client.get("/api/game/settings/")

    @task(3)
    def game_timer_settings(self):
        self.client.get("/api/game/settings/timer/")

    @task(3)
    def game_version(self):
        self.client.get("/api/game/version/")

    @task(5)
    def last_round_results(self):
        self.client.get("/api/game/last-round-results/")

    @task(3)
    def recent_round_results(self):
        self.client.get("/api/game/recent-round-results/")

    @task(6)
    def current_round(self):
        self.refresh_round_cache(force=False)

    # ----------------------------
    # Authenticated readonly APIs
    # ----------------------------

    @task(3)
    def auth_profile(self):
        if not self.token:
            return
        self.client.get("/api/auth/profile/")

    @task(2)
    def auth_referral_data(self):
        if not self.token:
            return
        self.client.get("/api/auth/referral-data/")

    @task(4)
    def auth_wallet(self):
        if not self.token:
            return
        self.refresh_wallet_balance()

    @task(2)
    def auth_transactions(self):
        if not self.token:
            return
        self.client.get("/api/auth/transactions/")

    @task(2)
    def auth_payment_methods(self):
        if not self.token:
            return
        self.client.get("/api/auth/payment-methods/")

    @task(2)
    def auth_bank_details(self):
        if not self.token:
            return
        self.client.get("/api/auth/bank-details/")

    @task(2)
    def auth_daily_reward_history(self):
        if not self.token:
            return
        self.client.get("/api/auth/daily-reward/history/")

    # ----------------------------
    # Game authenticated APIs (mostly readonly)
    # ----------------------------

    @task(4)
    def my_bets(self):
        if not self.token:
            return
        self.client.get("/api/game/bets/")

    @task(4)
    def user_bets_summary(self):
        if not self.token:
            return
        self.client.get("/api/game/user-bets-summary/")

    @task(4)
    def betting_history(self):
        if not self.token:
            return
        self.client.get("/api/game/betting-history/?limit=20")

    @task(4)
    def round_bets_current(self):
        if not self.token:
            return
        self.client.get("/api/game/round/bets/")

    @task(3)
    def round_predictions_current(self):
        if not self.token:
            return
        self.client.get("/api/game/round/predictions/")

    @task(3)
    def exposure_current(self):
        if not self.token:
            return
        self.client.get("/api/game/round/exposure/")

    @task(3)
    def dice_frequency_current(self):
        if not self.token:
            return
        self.client.get("/api/game/frequency/")

    @task(3)
    def winning_results_current(self):
        if not self.token:
            return
        self.client.get("/api/game/winning-results/")

    @task(2)
    def round_specific_endpoints(self):
        if not self.token:
            return
        if not self.round_id:
            self.refresh_round_cache(force=True)
        if not self.round_id:
            return
        rid = self.round_id
        # These require a round_id path param
        self.client.get(f"/api/game/round/{rid}/bets/")
        self.client.get(f"/api/game/round/{rid}/exposure/")
        self.client.get(f"/api/game/round/{rid}/predictions/")
        self.client.get(f"/api/game/user-round-results/{rid}/")
        self.client.get(f"/api/game/winning-results/{rid}/")
        self.client.get(f"/api/game/frequency/{rid}/")

    # ----------------------------
    # Side-effect APIs (disabled by default)
    # ----------------------------

    @task(1)
    def place_bet(self):
        if not self.enable_side_effects or not self.token:
            return
        self.refresh_round_cache(force=False)
        if self.current_status != "BETTING":
            return
        if self.balance < 10:
            self.refresh_wallet_balance()
            return

        number = random.randint(1, 6)
        amount = random.choice([10, 20, 50])
        with self.client.post("/api/game/bet/", json={"number": number, "chip_amount": amount}, catch_response=True) as r:
            # 200/201 success, 400 expected if betting closes or balance race; other codes are failures
            if r.status_code in (200, 201):
                try:
                    data = r.json()
                    self.balance = float(data.get("wallet_balance", self.balance - amount))
                except Exception:
                    pass
                r.success()
            elif r.status_code == 400:
                r.success()
            else:
                r.failure(f"place_bet failed: {r.status_code}")

    @task(1)
    def remove_last_bet(self):
        if not self.enable_side_effects or not self.token:
            return
        self.client.delete("/api/game/bet/last/")

    @task(1)
    def submit_prediction(self):
        if not self.enable_side_effects or not self.token:
            return
        number = random.randint(1, 6)
        self.client.post("/api/game/prediction/", json={"number": number})

    @task(1)
    def daily_reward(self):
        if not self.enable_side_effects or not self.token:
            return
        self.client.post("/api/auth/daily-reward/")

    @task(1)
    def lucky_draw(self):
        if not self.enable_side_effects or not self.token:
            return
        self.client.post("/api/auth/lucky-draw/")

    @task(1)
    def register_fcm_token(self):
        if not self.enable_side_effects or not self.token:
            return
        # Use a random token string; backend should accept idempotently.
        tok = f"locust-{random.randint(1, 10_000_000)}"
        self.client.post("/api/auth/register-fcm-token/", json={"token": tok, "device": "locust"})

    # ----------------------------
    # Admin-only endpoints (optional; will 403 unless admin)
    # ----------------------------

    @task(1)
    def admin_game_stats(self):
        if not self.enable_admin or not self.token:
            return
        self.client.get("/api/game/stats/")

    @task(1)
    def admin_dice_mode(self):
        if not self.enable_admin or not self.token:
            return
        self.client.get("/api/game/dice-mode/")

