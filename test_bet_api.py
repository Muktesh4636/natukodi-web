#!/usr/bin/env python3
"""
Test script for bet placement API
"""
import requests
import json
import sys

BASE_URL = "https://gunduata.online"
test_username = "bet_test_user"
test_password = "testpass123"

def test_bet_api():
    print("=" * 60)
    print("🧪 TESTING BET PLACEMENT API")
    print("=" * 60)
    
    # Step 1: Login
    print("\n🔐 Step 1: Logging in...")
    try:
        login_resp = requests.post(
            f"{BASE_URL}/api/auth/login/",
            json={"username": test_username, "password": test_password},
            headers={"Content-Type": "application/json"},
            timeout=20
        )
        
        if login_resp.status_code != 200:
            print(f"❌ Login failed: {login_resp.status_code}")
            print(f"   Response: {login_resp.text}")
            return False
        
        token = login_resp.json().get("access")
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        print("✅ Login successful")
    except Exception as e:
        print(f"❌ Login error: {e}")
        return False
    
    # Step 2: Get round status
    print("\n📊 Step 2: Getting round status...")
    try:
        round_resp = requests.get(
            f"{BASE_URL}/api/game/round/",
            headers=headers,
            timeout=20
        )
        
        if round_resp.status_code != 200:
            print(f"❌ Failed to get round: {round_resp.status_code}")
            print(f"   Response: {round_resp.text}")
            return False
        
        round_data = round_resp.json()
        print(f"✅ Round ID: {round_data.get('round_id')}")
        print(f"   Status: {round_data.get('status')}")
        print(f"   Timer: {round_data.get('timer')}s")
        print(f"   Dice Result: {round_data.get('dice_result', 'Not rolled yet')}")
    except Exception as e:
        print(f"❌ Round status error: {e}")
        return False
    
    # Step 3: Place bet
    print("\n💰 Step 3: Placing bet...")
    print(f"   Number: 1")
    print(f"   Amount: ₹10.00")
    
    try:
        bet_resp = requests.post(
            f"{BASE_URL}/api/game/bet/",
            json={"number": 1, "chip_amount": 10.00},
            headers=headers,
            timeout=20
        )
        
        print(f"\n📋 Response Status: {bet_resp.status_code}")
        print(f"📋 Response Body:")
        try:
            response_json = bet_resp.json()
            print(json.dumps(response_json, indent=2))
        except:
            print(bet_resp.text)
        
        if bet_resp.status_code == 201:
            print("\n✅ SUCCESS: Bet placed successfully!")
            bet_data = bet_resp.json()
            print(f"   Bet ID: {bet_data.get('bet', {}).get('id', 'N/A')}")
            print(f"   New Wallet Balance: ₹{bet_data.get('wallet_balance', 'N/A')}")
            return True
        elif bet_resp.status_code == 400:
            error_data = bet_resp.json()
            error_msg = error_data.get('error', 'Unknown error')
            print(f"\n⚠️  Betting Failed: {error_msg}")
            if 'timer' in error_msg.lower() or 'closed' in error_msg.lower():
                print("   💡 This is expected if betting window is closed.")
            elif 'balance' in error_msg.lower():
                print("   💡 Insufficient balance - wallet may need funding.")
            return False
        else:
            print(f"\n❌ Unexpected status code: {bet_resp.status_code}")
            return False
    except Exception as e:
        print(f"❌ Bet placement error: {e}")
        return False

if __name__ == "__main__":
    success = test_bet_api()
    print("\n" + "=" * 60)
    sys.exit(0 if success else 1)
