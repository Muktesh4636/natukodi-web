#!/usr/bin/env python3
"""
Automated script to log in to the game admin panel and fetch the payment methods page HTML.
Uses default credentials: admin / admin123
"""
import requests
from bs4 import BeautifulSoup
import sys

# Base URL
BASE_URL = "http://127.0.0.1:8000"
LOGIN_URL = f"{BASE_URL}/game-admin/login/"
PAYMENT_METHODS_URL = f"{BASE_URL}/game-admin/payment-methods/"

# Default credentials
DEFAULT_USERNAME = "admin"
DEFAULT_PASSWORD = "admin123"

def main():
    # Create a session to persist cookies
    session = requests.Session()
    
    print("=" * 80)
    print("AUTOMATED PAYMENT METHODS PAGE FETCHER")
    print("=" * 80)
    print(f"\nUsing credentials: {DEFAULT_USERNAME} / {DEFAULT_PASSWORD}")
    
    print("\nStep 1: Fetching login page to get CSRF token...")
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
        
        print(f"   ✓ CSRF token found: {csrf_token[:20]}..." if csrf_token else "   ✗ No CSRF token in form")
        print(f"   ✓ CSRF cookie found: {csrf_cookie[:20]}..." if csrf_cookie else "   ✗ No CSRF cookie")
        
        print("\nStep 2: Logging in...")
        
        # Prepare login data
        login_data = {
            'username': DEFAULT_USERNAME,
            'password': DEFAULT_PASSWORD,
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
        
        print(f"   Status: {login_response.status_code}")
        print(f"   Final URL: {login_response.url}")
        
        # Check if login was successful
        if 'login' in login_response.url.lower():
            print("\n❌ LOGIN FAILED!")
            print("\nPossible reasons:")
            print("  1. Incorrect credentials (default: admin/admin123)")
            print("  2. Admin user doesn't exist - run: python backend/scripts/create_admin.py")
            print("  3. Server not running - check http://127.0.0.1:8000")
            print("\nResponse preview:")
            print("-" * 80)
            print(login_response.text[:1000])
            print("-" * 80)
            sys.exit(1)
        
        print("   ✓ Login successful!")
        
        print("\nStep 3: Fetching payment methods page...")
        
        # Get the payment methods page
        payment_response = session.get(PAYMENT_METHODS_URL)
        payment_response.raise_for_status()
        
        print(f"   Status: {payment_response.status_code}")
        print(f"   Content length: {len(payment_response.text):,} characters")
        
        # Save the HTML to a file
        output_file = "payment_methods_page.html"
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(payment_response.text)
        
        print(f"\n✅ SUCCESS! HTML content saved to: {output_file}")
        
        # Print a preview
        print("\n" + "=" * 80)
        print("HTML PREVIEW (first 2000 characters):")
        print("=" * 80)
        print(payment_response.text[:2000])
        print("=" * 80)
        print(f"\n📄 Full HTML saved to: {output_file}")
        print(f"📊 Total size: {len(payment_response.text):,} characters")
        print("=" * 80)
        
        return payment_response.text
        
    except requests.exceptions.ConnectionError:
        print(f"\n❌ CONNECTION ERROR!")
        print(f"\nCould not connect to {BASE_URL}")
        print("\nPlease make sure:")
        print("  1. The Django server is running")
        print("  2. It's accessible on http://127.0.0.1:8000")
        print("\nTo start the server, run:")
        print("  cd backend && python manage.py runserver")
        sys.exit(1)
    except requests.exceptions.RequestException as e:
        print(f"\n❌ REQUEST ERROR: {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n\n⚠️  Operation cancelled by user.")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ UNEXPECTED ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
