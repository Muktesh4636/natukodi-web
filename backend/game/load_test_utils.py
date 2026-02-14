import threading
import time
import random
import requests
import json
import logging
from django.conf import settings
from django.contrib.auth import get_user_model
from accounts.models import Wallet
from game.models import GameRound
from rest_framework_simplejwt.tokens import RefreshToken
from decimal import Decimal
from django.utils import timezone
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger('game.load_test')
User = get_user_model()

class LoadTester:
    def __init__(self, base_url):
        self.base_url = base_url.rstrip('/')
        self.results = {
            'total_requests': 0,
            'success_count': 0,
            'failure_count': 0,
            'response_times': [],
            'errors': [],
            'is_running': False,
            'start_time': None,
            'end_time': None
        }
        self.lock = threading.Lock()
        self.executor = None

    def _get_token_for_user(self, user):
        refresh = RefreshToken.for_user(user)
        return str(refresh.access_token)

    def _simulate_user_session(self, user_id, bets_count, chip_amount):
        try:
            user = User.objects.get(id=user_id)
            token = self._get_token_for_user(user)
            headers = {
                'Authorization': f'Bearer {token}',
                'Content-Type': 'application/json'
            }

            for _ in range(bets_count):
                if not self.results['is_running']:
                    break
                
                # The user wants "every second", so we aim for 1 bet/sec per user
                loop_start = time.time()
                
                number = random.randint(1, 6)
                payload = {
                    'number': number,
                    'chip_amount': float(chip_amount)
                }

                req_start = time.time()
                try:
                    response = requests.post(
                        f"{self.base_url}/game/bet/",
                        json=payload,
                        headers=headers,
                        timeout=5
                    )
                    duration = time.time() - req_start
                    
                    with self.lock:
                        self.results['total_requests'] += 1
                        self.results['response_times'].append(duration)
                        if response.status_code == 201:
                            self.results['success_count'] += 1
                        else:
                            self.results['failure_count'] += 1
                            if len(self.results['errors']) < 100: # Limit error list size
                                self.results['errors'].append(f"U:{user.username} S:{response.status_code} E:{response.text[:50]}")
                except Exception as e:
                    with self.lock:
                        self.results['total_requests'] += 1
                        self.results['failure_count'] += 1
                        if len(self.results['errors']) < 100:
                            self.results['errors'].append(str(e))
                
                # Aim for 1 second total per loop iteration
                elapsed = time.time() - loop_start
                sleep_time = max(0.01, 1.0 - elapsed)
                time.sleep(sleep_time)

        except Exception as e:
            logger.error(f"Error in simulated session for user {user_id}: {e}")

    def run_simulation(self, user_count, bets_per_user, chip_amount=10):
        with self.lock:
            if self.results['is_running']:
                return self.results
            
            self.results = {
                'total_requests': 0,
                'success_count': 0,
                'failure_count': 0,
                'response_times': [],
                'errors': [],
                'is_running': True,
                'start_time': timezone.now(),
                'end_time': None
            }

        # Get candidates for simulation
        # Using a larger pool to ensure we find enough users with balance or can fund them
        test_users = User.objects.filter(is_staff=False).order_by('?')[:user_count]
        
        # Funding users in bulk if needed (optimization: only fund if balance is low)
        # For simplicity, we fund them here.
        user_ids = [u.id for u in test_users]
        wallets = Wallet.objects.filter(user_id__in=user_ids)
        wallet_map = {w.user_id: w for w in wallets}
        
        to_update = []
        for user in test_users:
            wallet = wallet_map.get(user.id)
            if not wallet:
                wallet = Wallet(user=user, balance=0)
                wallet.save()
            
            required_balance = chip_amount * bets_per_user
            if wallet.balance < required_balance:
                wallet.balance += required_balance * 2
                to_update.append(wallet)
        
        if to_update:
            Wallet.objects.bulk_update(to_update, ['balance'])

        # Using ThreadPoolExecutor for managing 300+ threads efficiently
        self.executor = ThreadPoolExecutor(max_workers=user_count)
        
        if not isinstance(chip_amount, Decimal):
            chip_amount = Decimal(str(chip_amount))

        for user in test_users:
            self.executor.submit(self._simulate_user_session, user.id, bets_per_user, chip_amount)

        def wait_and_finish():
            self.executor.shutdown(wait=True)
            with self.lock:
                self.results['is_running'] = False
                self.results['end_time'] = timezone.now()

        threading.Thread(target=wait_and_finish).start()
        
        return self.results

    def get_status(self):
        with self.lock:
            data = self.results.copy()
            # Summarize response times to avoid sending huge lists
            if data['response_times']:
                data['avg_response_time'] = sum(data['response_times']) / len(data['response_times'])
                data['max_response_time'] = max(data['response_times'])
                # Clear response_times list for the summary
                del data['response_times']
            else:
                data['avg_response_time'] = 0
                data['max_response_time'] = 0
                if 'response_times' in data: del data['response_times']
            
            # Limit errors to last 20
            data['recent_errors'] = data['errors'][-20:]
            del data['errors']
            
            return data

# Global instance
load_tester = LoadTester(base_url="http://127.0.0.1:8000")
