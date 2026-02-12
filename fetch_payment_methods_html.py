#!/usr/bin/env python3
"""
Script to log in to the game admin panel and fetch the payment methods page HTML.
"""
import requests
from bs4 import BeautifulSoup
import sys

# Base URL
BASE_URL = "http://127.0.0.1:8000"
LOGIN_URL = f"{BASE_URL}/game-admin/login/"
PAYMENT_METHODS_URL = f"{BASE_URL}/game-admin/payment-methods/"

def main():
    # Create a session to persist cookies
    session = requests.Session()
    
    print("Step 1: Fetching login page to get CSRF token...")
    try:
        # Get the login page first to retrieve CSRF token
        response = session.get(LOGIN_URL)
        response.raise_for_status()
        
        # Parse the HTML to get CSRF token
        soup = BeautifulSoup(response.text, 'html.parser')
        csrf_token = None
        
        # Try to find CSRF token in various ways
        csrf_input = soup.find('input', {'name': 'csrfmiddlewaretoken'})
        if csrf_input:
            csrf_token = csrf_input.get('value')
        
        # Also check cookies for CSRF token
        csrf_cookie = session.cookies.get('csrftoken')
        
        print(f"CSRF token from input: {csrf_token}")
        print(f"CSRF token from cookie: {csrf_cookie}")
        
        # Prompt for credentials
        print("\nPlease enter your admin credentials:")
        username = input("Username: ").strip()
        password = input("Password: ").strip()
        
        print("\nStep 2: Logging in...")
        
        # Prepare login data
        login_data = {
            'username': username,
            'password': password,
        }
        
        # Add CSRF token if found
        if csrf_token:
            login_data['csrfmiddlewaretoken'] = csrf_token
        
        # Set headers
        headers = {
            'Referer': LOGIN_URL,
        }
        
        if csrf_cookie:
            headers['X-CSRFToken'] = csrf_cookie
        
        # Attempt login
        login_response = session.post(LOGIN_URL, data=login_data, headers=headers, allow_redirects=True)
        
        print(f"Login response status: {login_response.status_code}")
        print(f"Final URL after login: {login_response.url}")
        
        # Check if login was successful
        if 'login' in login_response.url.lower():
            print("\n❌ Login failed. Please check your credentials.")
            print("Response content preview:")
            print(login_response.text[:500])
            sys.exit(1)
        
        print("✅ Login successful!")
        
        print("\nStep 3: Fetching payment methods page...")
        
        # Get the payment methods page
        payment_response = session.get(PAYMENT_METHODS_URL)
        payment_response.raise_for_status()
        
        print(f"Payment methods page status: {payment_response.status_code}")
        print(f"Content length: {len(payment_response.text)} characters")
        
        # Save the HTML to a file
        output_file = "payment_methods_page.html"
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(payment_response.text)
        
        print(f"\n✅ HTML content saved to: {output_file}")
        print("\nHTML Preview (first 1000 characters):")
        print("=" * 80)
        print(payment_response.text[:1000])
        print("=" * 80)
        
        return payment_response.text
        
    except requests.exceptions.ConnectionError:
        print(f"\n❌ Error: Could not connect to {BASE_URL}")
        print("Please make sure the Django server is running on port 8000.")
        sys.exit(1)
    except requests.exceptions.RequestException as e:
        print(f"\n❌ Error: {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n\nOperation cancelled by user.")
        sys.exit(0)

if __name__ == "__main__":
    main()
