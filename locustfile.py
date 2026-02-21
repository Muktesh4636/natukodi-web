from locust import HttpUser, task, between, events
import random
import json

class GameUser(HttpUser):
    wait_time = between(1, 2)
    token = None
    current_status = "WAITING"
    balance = 0

    def on_start(self):
        """Login when user starts and ensure they have balance"""
        user_id = random.randint(1, 1000)
        username = f"testuser_{user_id}"
        password = "password123"

        # 1. Login or Signup
        with self.client.post("/api/auth/login/", json={
            "username": username,
            "password": password
        }, catch_response=True) as response:
            if response.status_code == 200:
                data = response.json()
                self.token = data.get("access")
                self.client.headers.update({"Authorization": f"Bearer {self.token}"})
            elif response.status_code == 401:
                # Signup if user doesn't exist
                with self.client.post("/api/auth/signup/", json={
                    "username": username,
                    "password": password,
                    "phone_number": f"91000{user_id:05d}",
                    "otp_code": "1234"
                }, catch_response=True) as signup_resp:
                    if signup_resp.status_code in [200, 201]:
                        data = signup_resp.json()
                        self.token = data.get("access")
                        self.client.headers.update({"Authorization": f"Bearer {self.token}"})
                    else:
                        signup_resp.failure(f"Signup failed: {signup_resp.text}")
            else:
                response.failure(f"Login failed: {response.status_code}")

        # 2. Refill balance if it's low (Simulation of a deposit)
        self.check_and_refill_balance()

    def check_and_refill_balance(self):
        """Check balance and refill if below 100"""
        if not self.token:
            return
            
        with self.client.get("/api/auth/wallet/", catch_response=True) as response:
            if response.status_code == 200:
                data = response.json()
                self.balance = float(data.get("balance", 0))
                
                # If balance is low, refill it using the admin-style deposit API
                # Note: This uses the actual deposit API but simulates a successful one
                if self.balance < 100:
                    # We simulate a large deposit to keep the test running
                    # FIXED: Corrected URL from /api/accounts/deposit/ to /api/auth/deposits/upload-proof/
                    # Note: This will still fail if it expects a real file upload, 
                    # but for load testing we should ideally use a dedicated test endpoint.
                    self.client.post("/api/auth/deposits/upload-proof/", data={
                        "amount": 10000,
                        "payment_method_id": 1,
                    })
                    # Note: In a real system, this would need admin approval, 
                    # but for load testing, we just want to ensure the user has funds.
            else:
                response.failure(f"Wallet check failed: {response.status_code}")

    @task(10)
    def check_game_and_bet(self):
        """Smart betting: Only bet if the round is open and user has funds"""
        if not self.token:
            return

        # 1. Check current round status
        with self.client.get("/api/game/round/", catch_response=True) as response:
            if response.status_code == 200:
                data = response.json()
                self.current_status = data.get("status", "WAITING")
                
                # 2. Only place bet if status is BETTING
                if self.current_status == "BETTING":
                    # Refill check every few bets
                    if random.random() < 0.2: 
                        self.check_and_refill_balance()

                    if self.balance < 10:
                        self.check_and_refill_balance()
                        return

                    number = random.randint(1, 6)
                    amount = random.choice([10, 20, 50])
                    
                    with self.client.post("/api/game/bet/", json={
                        "number": number,
                        "chip_amount": amount
                    }, catch_response=True) as bet_resp:
                        if bet_resp.status_code in [200, 201]:
                            data = bet_resp.json()
                            self.balance = float(data.get("wallet_balance", self.balance - amount))
                            bet_resp.success()
                        elif bet_resp.status_code == 400:
                            if "balance" in bet_resp.text.lower():
                                self.check_and_refill_balance()
                                bet_resp.success() # Normal behavior, not a server error
                            elif "closed" in bet_resp.text.lower():
                                bet_resp.success() # Race condition, not a server error
                            else:
                                bet_resp.failure(f"Bet failed: {bet_resp.text}")
            else:
                response.failure(f"Failed to get round status: {response.status_code}")

    @task(1)
    def get_exposure(self):
        """Check exposure"""
        if not self.token:
            return
        self.client.get("/api/game/round/exposure/")

