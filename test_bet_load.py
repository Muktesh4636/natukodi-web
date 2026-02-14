#!/usr/bin/env python3
"""
Load test script for bet placement API with 100 concurrent users
Usage: locust -f test_bet_load.py --host=https://gunduata.online --users 100 --spawn-rate 10
"""

from locust import HttpUser, task, between, events
import random
import logging
import time

# Configuration
TEST_USER_PREFIX = "testuser_"
USER_COUNT = 300  # Ensure you have at least 100 test users
PASSWORD = "testpassword123"

class BetPlacingUser(HttpUser):
    """Simulates a user that focuses on placing bets"""
    wait_time = between(1, 3)  # Wait 1-3 seconds between actions
    token = None
    username = None
    current_round_data = None
    
    def on_start(self):
        """Login when user starts"""
        self.login()
    
    def login(self):
        """Login and get auth token"""
        user_id = random.randint(0, USER_COUNT - 1)
        self.username = f"{TEST_USER_PREFIX}{user_id}"
        
        try:
            response = self.client.post(
                "/api/auth/login/",
                json={"username": self.username, "password": PASSWORD},
                headers={"Content-Type": "application/json"},
                timeout=10,
                name="Login"
            )
            
            if response.status_code == 200:
                data = response.json()
                self.token = data.get("access")
                if self.token:
                    logging.info(f"✅ Logged in as {self.username}")
                    return True
            else:
                logging.warning(f"❌ Login failed for {self.username}: {response.status_code}")
                return False
        except Exception as e:
            logging.error(f"Login error for {self.username}: {e}")
            return False
    
    def get_auth_headers(self):
        """Get authentication headers"""
        if not self.token:
            if not self.login():
                return {}
        return {"Authorization": f"Bearer {self.token}"}
    
    @task(5)
    def check_round_status(self):
        """Check current round status before betting"""
        headers = self.get_auth_headers()
        if not headers:
            return
        
        try:
            with self.client.get(
                "/api/game/round/",
                headers=headers,
                name="Get Round Status",
                catch_response=True,
                timeout=15
            ) as response:
                if response.status_code == 200:
                    self.current_round_data = response.json()
                    response.success()
                elif response.status_code == 401:
                    # Token expired, re-login
                    if self.login():
                        headers = self.get_auth_headers()
                        retry = self.client.get("/api/game/round/", headers=headers, timeout=15)
                        if retry.status_code == 200:
                            self.current_round_data = retry.json()
                            response.success()
                        else:
                            response.failure(f"Retry failed: {retry.status_code}")
                    else:
                        response.failure("Re-login failed")
                else:
                    response.failure(f"Status: {response.status_code}")
        except Exception as e:
            logging.error(f"Error checking round status: {e}")
    
    @task(10)
    def place_bet(self):
        """Place a bet on a random number"""
        headers = self.get_auth_headers()
        if not headers:
            return
        
        # Check if we have round data and betting is open
        if not self.current_round_data:
            # Try to get round status first
            try:
                round_resp = self.client.get("/api/game/round/", headers=headers, timeout=10)
                if round_resp.status_code == 200:
                    self.current_round_data = round_resp.json()
                else:
                    return  # Can't get round status, skip betting
            except:
                return
        
        # Check if betting window is open
        timer = self.current_round_data.get('timer', 999)
        status = self.current_round_data.get('status', '')
        
        # Only bet if timer < 30 seconds and status is BETTING
        if timer >= 30 or status != 'BETTING':
            return  # Betting window closed, skip this attempt
        
        # Prepare bet data
        bet_number = random.randint(1, 6)
        bet_amount = random.choice([10.00, 20.00, 50.00, 100.00])
        
        bet_data = {
            "number": bet_number,
            "chip_amount": bet_amount
        }
        
        try:
            with self.client.post(
                "/api/game/bet/",
                json=bet_data,
                headers=headers,
                name="Place Bet",
                catch_response=True,
                timeout=15
            ) as response:
                if response.status_code == 201:
                    # Bet placed successfully
                    response.success()
                    logging.debug(f"✅ {self.username} placed bet: ₹{bet_amount} on {bet_number}")
                elif response.status_code == 400:
                    # Betting closed or validation error - this is expected sometimes
                    error_data = response.json()
                    error_msg = error_data.get('error', 'Unknown error')
                    if 'timer' in error_msg.lower() or 'closed' in error_msg.lower():
                        # Betting window closed - this is normal, don't count as failure
                        response.success()
                    elif 'balance' in error_msg.lower():
                        # Insufficient balance - mark as failure
                        response.failure(f"Insufficient balance: {error_msg}")
                    else:
                        response.failure(f"Bet failed: {error_msg}")
                elif response.status_code == 401:
                    # Token expired, re-login and retry
                    if self.login():
                        headers = self.get_auth_headers()
                        retry = self.client.post("/api/game/bet/", json=bet_data, headers=headers, timeout=15)
                        if retry.status_code == 201:
                            response.success()
                        else:
                            response.failure(f"Retry failed: {retry.status_code}")
                    else:
                        response.failure("Re-login failed")
                else:
                    response.failure(f"Unexpected status: {response.status_code}")
        except Exception as e:
            logging.error(f"Error placing bet for {self.username}: {e}")
