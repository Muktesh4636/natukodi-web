from locust import HttpUser, task, between
import random

class GameUser(HttpUser):
    wait_time = between(1, 3)

    def on_start(self):
        """Login when user starts"""
        # Use a unique user ID for each locust user
        user_id = str(getattr(self, 'user_id', random.randint(1, 464)))

        response = self.client.post("/api/auth/login/", json={
            "username": f"testuser_{user_id}",
            "password": "password123"
        })
        if response.status_code == 200:
            # Extract token from response
            data = response.json()
            if "access" in data:
                self.token = data["access"]
                self.client.headers.update({"Authorization": f"Bearer {self.token}"})
            else:
                print(f"No access token in response: {data}")
        else:
            print(f"Login failed: {response.status_code} - {response.text}")

    @task(3)
    def place_bet(self):
        """Place a bet on a number (1-6)"""
        number = random.randint(1, 6)
        amount = random.choice([10, 50, 100, 500])

        response = self.client.post("/api/game/bet/", json={
            "number": number,
            "chip_amount": amount
        })

        if response.status_code not in [200, 201]:
            print(f"Bet failed: {response.status_code} - {response.text}")

    @task(2)
    def get_wallet_balance(self):
        """Check wallet balance"""
        response = self.client.get("/api/auth/wallet/")
        if response.status_code != 200:
            print(f"Wallet balance failed: {response.status_code} - {response.text}")

    @task(1)
    def get_current_round(self):
        """Get current round status"""
        response = self.client.get("/api/game/round/")
        if response.status_code != 200:
            print(f"Get round failed: {response.status_code} - {response.text}")

    @task(1)
    def get_exposure(self):
        """Get round exposure data"""
        response = self.client.get("/api/game/round/exposure/")
        if response.status_code != 200:
            print(f"Get exposure failed: {response.status_code} - {response.text}")

    @task(1)
    def get_bets(self):
        """Get user's bets"""
        response = self.client.get("/api/game/bets/")
        if response.status_code != 200:
            print(f"Get bets failed: {response.status_code} - {response.text}")

    @task(1)
    def get_settings(self):
        """Get game settings"""
        response = self.client.get("/api/game/settings/")
        if response.status_code != 200:
            print(f"Get settings failed: {response.status_code} - {response.text}")

    @task(1)
    def get_frequency(self):
        """Get dice frequency data"""
        response = self.client.get("/api/game/frequency/")
        if response.status_code != 200:
            print(f"Get frequency failed: {response.status_code} - {response.text}")