from locust import HttpUser, task, between, events
import random
import logging
import time

# Configuration for the test
TEST_USER_PREFIX = "testuser_"
USER_COUNT = 300 # Match the number of users created in scripts/create_test_users.py
PASSWORD = "testpassword123"

class GunduAtaHighTrafficPlayer(HttpUser):
    # Users wait very little time between actions to simulate high pressure
    wait_time = between(0.5, 1.5)
    token = None
    refresh_token = None
    username = None
    last_login_time = 0
    TOKEN_REFRESH_INTERVAL = 300  # Refresh token every 5 minutes (300 seconds)
    
    def on_start(self):
        """Pick a random test user and log in"""
        # Ensure login completes before starting tasks
        max_retries = 5
        retry_delay = 1.0  # Increased delay between retries
        for attempt in range(max_retries):
            if self.login() and self.token:
                logging.info(f"Successfully logged in as {self.username}")
                return
            if attempt < max_retries - 1:
                time.sleep(retry_delay * (attempt + 1))  # Exponential backoff
        # If login fails after all retries, wait longer before retrying
        logging.warning(f"Login failed after {max_retries} attempts for {self.username}, will retry in tasks")
    
    def setup(self):
        """Setup method called once per user before on_start"""
        # Disable SSL verification warnings if needed (not recommended for production)
        # But useful for testing
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    def login(self):
        """Login and get tokens"""
        user_id = random.randint(0, USER_COUNT - 1)
        self.username = f"testuser_{user_id}"
        
        try:
            # Use absolute URL to avoid any redirect issues
            # Ensure trailing slash is present
            login_url = "/api/auth/login/"
            
            # Make POST request with explicit headers and timeout
            response = self.client.post(
                login_url, 
                json={
                    "username": self.username,
                    "password": PASSWORD
                },
                headers={"Content-Type": "application/json"},
                catch_response=True,
                allow_redirects=True,
                timeout=10,  # 10 second timeout
                name="API: Login"
            )
            
            with response as resp:
                if resp.status_code == 200:
                    try:
                        data = resp.json()
                        # Handle both response formats: {"access": "...", "refresh": "..."} 
                        # and {"user": {...}, "access": "...", "refresh": "..."}
                        self.token = data.get("access")
                        self.refresh_token = data.get("refresh")
                        
                        if not self.token:
                            # Try alternative response format
                            if "user" in data and isinstance(data["user"], dict):
                                # Response has user object, tokens should be at root level
                                logging.warning(f"Login response format: {list(data.keys())}")
                            
                            resp.failure(f"Login succeeded but no access token received for {self.username}. Response keys: {list(data.keys()) if isinstance(data, dict) else 'not a dict'}")
                            return False
                        
                        if not self.refresh_token:
                            logging.warning(f"Login succeeded but no refresh token received for {self.username}")
                            # Don't fail if refresh token is missing, access token is more important
                        
                        self.last_login_time = time.time()
                        resp.success()
                        logging.debug(f"Login successful for {self.username}, token length: {len(self.token) if self.token else 0}")
                        return True
                    except ValueError as e:
                        # JSON parsing error
                        resp.failure(f"Failed to parse login response as JSON: {e}. Response text: {resp.text[:200]}")
                        return False
                    except Exception as e:
                        resp.failure(f"Unexpected error parsing login response: {e}. Response: {resp.text[:200]}")
                        return False
                elif resp.status_code in [301, 302, 303, 307, 308]:
                    # Redirect occurred - this shouldn't happen with HTTPS and trailing slash
                    # But if it does, the redirect should have been followed
                    resp.failure(f"Unexpected redirect (status {resp.status_code}). URL: {login_url}")
                    return False
                else:
                    # If status is not 200, it's a failure
                    resp.failure(f"Failed to login as {self.username}: Status {resp.status_code} - {resp.text[:200]}")
                    self.token = None
                    self.refresh_token = None
                    return False
        except Exception as e:
            logging.error(f"Login exception for {self.username}: {e}")
            self.token = None
            self.refresh_token = None
            return False

    def refresh_auth_token(self):
        """Refresh the access token using refresh token"""
        if not self.refresh_token:
            return self.login()
        
        try:
            with self.client.post("/api/auth/token/refresh/", json={
                "refresh": self.refresh_token
            }, catch_response=True, allow_redirects=False, name="API: Refresh Token") as response:
                if response.status_code == 200:
                    data = response.json()
                    self.token = data.get("access")
                    self.last_login_time = time.time()
                    response.success()
                    return True
                else:
                    # Refresh failed, re-login
                    response.failure(f"Token refresh failed: {response.text}")
                    return self.login()
        except Exception as e:
            logging.error(f"Token refresh error: {e}")
            return self.login()

    def get_auth_headers(self):
        """Get auth headers, refreshing token if needed"""
        # Always ensure we have a valid token
        if not self.token:
            if not self.login():
                return {}
        
        # Refresh token if it's been more than 5 minutes
        if time.time() - self.last_login_time > self.TOKEN_REFRESH_INTERVAL:
            if not self.refresh_auth_token():
                # Refresh failed, try to login again
                if not self.login():
                    return {}
        
        return {"Authorization": f"Bearer {self.token}"} if self.token else {}

    def on_start(self):
        """Pick a random test user and log in"""
        # Ensure login completes before starting tasks
        max_retries = 5
        retry_delay = 1.0  # Increased delay between retries
        for attempt in range(max_retries):
            if self.login() and self.token:
                return
            if attempt < max_retries - 1:
                time.sleep(retry_delay * (attempt + 1))  # Exponential backoff
        # If login fails after all retries, wait longer before retrying
        logging.warning(f"Login failed after {max_retries} attempts for {self.username}, will retry in tasks")

    @task(10)
    def check_game_status(self):
        """Players check the timer very frequently (every second)"""
        # Ensure we have a valid token - refresh if needed
        if not self.token or (time.time() - self.last_login_time > self.TOKEN_REFRESH_INTERVAL):
            if not self.login():
                return
        
        # Double-check token is valid
        if not self.token:
            return
        
        # Ensure token is a string and not None
        token_str = str(self.token).strip()
        if not token_str or token_str == 'None':
            if not self.login():
                return
            token_str = str(self.token).strip()
            if not token_str:
                return
        
        headers = {"Authorization": f"Bearer {token_str}"}
        
        try:
            with self.client.get("/api/game/round/", headers=headers, name="API: Current Round", catch_response=True, timeout=30) as response:
                if response.status_code == 401:
                    # Token expired or invalid, re-login and retry once
                    time.sleep(0.5)  # Small delay before retry to avoid hammering login
                    if self.login() and self.token:
                        token_str = str(self.token).strip()
                        headers = {"Authorization": f"Bearer {token_str}"}
                        retry_response = self.client.get("/api/game/round/", headers=headers, name="API: Current Round", timeout=30)
                        if retry_response.status_code == 200:
                            self.current_round_data = retry_response.json()
                            response.success()
                        else:
                            # If still failing, mark as failure but don't retry again
                            response.failure(f"Failed after re-login: {retry_response.status_code}")
                    else:
                        # Login failed - mark as failure and skip this request
                        response.failure("Re-login failed or no token")
                        return  # Don't continue with this request
                elif response.status_code == 200:
                    try:
                        self.current_round_data = response.json()
                        response.success()
                    except Exception as e:
                        response.failure(f"Failed to parse response: {e}")
                elif response.status_code == 504:
                    # Gateway timeout - mark as failure
                    response.failure(f"Gateway timeout: {response.status_code}")
                else:
                    response.failure(f"Unexpected status: {response.status_code}")
        except Exception as e:
            # Handle any exceptions (timeouts, connection errors, etc.)
            logging.error(f"Error in check_game_status for {self.username}: {e}")
            return

    @task(8)
    def place_aggressive_bets(self):
        """Simulate aggressive betting behavior"""
        # Ensure we have a valid token - refresh if needed
        if not self.token or (time.time() - self.last_login_time > self.TOKEN_REFRESH_INTERVAL):
            if not self.login():
                return
        
        # Double-check token is valid
        if not self.token:
            return
        
        # Check if betting is allowed
        if not hasattr(self, 'current_round_data') or not self.current_round_data:
            return
            
        status = self.current_round_data.get('status')
        timer = self.current_round_data.get('timer', 0)
        
        # Only bet if status is BETTING and timer > 0
        if status != 'BETTING' or timer <= 0:
            return

        # Ensure token is a string and not None
        token_str = str(self.token).strip()
        if not token_str or token_str == 'None':
            if not self.login():
                return
            token_str = str(self.token).strip()
            if not token_str:
                return
        
        headers = {"Authorization": f"Bearer {token_str}"}
        
        # Simulate placing 1-3 chips in one 'action'
        for _ in range(random.randint(1, 3)):
            bet_data = {
                "number": random.randint(1, 6),
                "chip_amount": str(random.choice([10.00, 20.00, 50.00, 100.00]))
            }
            
            try:
                with self.client.post("/api/game/bet/", json=bet_data, headers=headers, name="API: Place Bet", catch_response=True, timeout=30) as response:
                    if response.status_code == 401:
                        # Token expired or invalid, re-login and retry once
                        time.sleep(0.5)  # Small delay before retry to avoid hammering login
                        if self.login() and self.token:
                            token_str = str(self.token).strip()
                            headers = {"Authorization": f"Bearer {token_str}"}
                            retry_response = self.client.post("/api/game/bet/", json=bet_data, headers=headers, name="API: Place Bet", timeout=30)
                            if retry_response.status_code in [200, 201]:
                                response.success()
                            else:
                                # Don't fail on 400 - betting might be closed
                                if retry_response.status_code == 400:
                                    response.success()  # Betting closed is expected
                                else:
                                    response.failure(f"Bet failed after re-login: {retry_response.status_code}")
                        else:
                            # Login failed - mark as failure and skip this bet
                            response.failure("Re-login failed or no token")
                            break  # Don't continue placing more bets in this loop
                    elif response.status_code in [200, 201]:
                        response.success()
                    elif response.status_code == 400:
                        # Betting closed or validation error - this is expected sometimes
                        response.success()
                    elif response.status_code == 504:
                        # Gateway timeout - mark as failure
                        response.failure(f"Gateway timeout: {response.status_code}")
                    else:
                        response.failure(f"Bet failed: {response.status_code}")
            except Exception as e:
                # Handle timeouts and connection errors
                logging.error(f"Error placing bet for {self.username}: {e}")
                break  # Don't continue placing more bets

    @task(2)
    def check_wallet_and_profile(self):
        """Occasionally check balance"""
        # Ensure we have a valid token - refresh if needed
        if not self.token or (time.time() - self.last_login_time > self.TOKEN_REFRESH_INTERVAL):
            if not self.login():
                return
        
        # Double-check token is valid
        if not self.token:
            return
        
        # Ensure token is a string and not None
        token_str = str(self.token).strip()
        if not token_str or token_str == 'None':
            if not self.login():
                return
            token_str = str(self.token).strip()
            if not token_str:
                return
        
        headers = {"Authorization": f"Bearer {token_str}"}
        self.client.get("/api/auth/wallet/", headers=headers, name="API: Wallet")
        self.client.get("/api/auth/profile/", headers=headers, name="API: Profile")

    @task(1)
    def check_exposure_api(self):
        """Simulate checking the exposure list"""
        # Ensure we have a valid token - refresh if needed
        if not self.token or (time.time() - self.last_login_time > self.TOKEN_REFRESH_INTERVAL):
            if not self.login():
                return
        
        # Double-check token is valid
        if not self.token:
            return
        
        # Ensure token is a string and not None
        token_str = str(self.token).strip()
        if not token_str or token_str == 'None':
            if not self.login():
                return
            token_str = str(self.token).strip()
            if not token_str:
                return
        
        headers = {"Authorization": f"Bearer {token_str}"}
        
        try:
            with self.client.get("/api/game/round/exposure/", headers=headers, name="API: Round Exposure", catch_response=True, timeout=30) as response:
                if response.status_code == 401:
                    # Token expired or invalid, re-login and retry once
                    time.sleep(0.5)  # Small delay before retry to avoid hammering login
                    if self.login() and self.token:
                        token_str = str(self.token).strip()
                        headers = {"Authorization": f"Bearer {token_str}"}
                        retry_response = self.client.get("/api/game/round/exposure/", headers=headers, name="API: Round Exposure", timeout=30)
                        if retry_response.status_code == 200:
                            response.success()
                        else:
                            # If still failing, mark as failure but don't retry again
                            response.failure(f"Failed after re-login: {retry_response.status_code}")
                    else:
                        # Login failed - mark as failure and skip this request
                        response.failure("Re-login failed or no token")
                        return  # Don't continue with this request
                elif response.status_code == 200:
                    try:
                        response.json()  # Verify response is valid JSON
                        response.success()
                    except Exception as e:
                        response.failure(f"Failed to parse response: {e}")
                elif response.status_code == 504:
                    # Gateway timeout - mark as failure
                    response.failure(f"Gateway timeout: {response.status_code}")
                else:
                    response.failure(f"Unexpected status: {response.status_code}")
        except Exception as e:
            # Handle any exceptions (timeouts, connection errors, etc.)
            logging.error(f"Error in check_exposure_api for {self.username}: {e}")
            return

@events.init_command_line_parser.add_listener
def _(parser):
    parser.add_argument("--user-prefix", type=str, env_var="LOCUST_USER_PREFIX", default="testuser_")
