import requests
import json
import logging
import threading
from django.conf import settings
from django.utils import timezone
from .models import OTP
import random
import string

logger = logging.getLogger(__name__)


class SMSService:
    """SMS service for sending OTP messages"""

    def __init__(self):
        self.provider = getattr(settings, 'SMS_PROVIDER', 'MSG91')  # Default to MSG91 for Indian market
        self.api_key = getattr(settings, 'SMS_API_KEY', '')
        self.sender_id = getattr(settings, 'SMS_SENDER_ID', 'GUNDAT')
        self.template_id = getattr(settings, 'SMS_TEMPLATE_ID', '')

    def generate_otp(self, length=4):
        """Generate a random OTP code"""
        return ''.join(random.choices(string.digits, k=length))

    def send_otp(self, phone_number, purpose='LOGIN'):
        """
        Send OTP to phone number
        Returns: (success: bool, message: str, otp_id: int or None)
        """
        try:
            # Clean phone number for storage (10 digits without country code)
            clean_number = self._clean_phone_number(phone_number, for_sms=False)
            # Clean phone number for SMS (with country code)
            sms_number = self._clean_phone_number(phone_number, for_sms=True)

            # Set expiration (10 minutes from now)
            expires_at = timezone.now() + timezone.timedelta(minutes=10)

            # For Message Central, they generate their own OTP
            if self.provider.upper() == 'MESSAGE_CENTRAL':
                # Create the OTP record first with a temporary verification_id
                otp_obj = OTP.objects.create(
                    phone_number=clean_number,
                    otp_code='PENDING',  # Placeholder
                    purpose=purpose,
                    expires_at=expires_at,
                    verification_id='PENDING'
                )

                # Start a background thread to call the SMS API
                thread = threading.Thread(
                    target=self._send_otp_background,
                    args=(sms_number, otp_obj.id, purpose)
                )
                thread.daemon = True
                thread.start()

                logger.info(f"OTP process started in background for {clean_number}")
                return True, "OTP is being sent", otp_obj.id
            else:
                # For other providers, generate our own OTP
                otp_code = self.generate_otp()
                
                # Save OTP to database
                otp_obj = OTP.objects.create(
                    phone_number=clean_number,
                    otp_code=otp_code,
                    purpose=purpose,
                    expires_at=expires_at
                )

                # Start a background thread to call the SMS API
                thread = threading.Thread(
                    target=self._send_otp_background,
                    args=(sms_number, otp_obj.id, purpose, otp_code)
                )
                thread.daemon = True
                thread.start()

                logger.info(f"OTP process started in background for {clean_number}")
                return True, "OTP is being sent", otp_obj.id

        except Exception as e:
            logger.exception(f"Error initiating OTP send to {phone_number}: {str(e)}")
            return False, f"Error: {str(e)}", None

    def _send_otp_background(self, sms_number, otp_record_id, purpose, otp_code=None):
        """Background task to call the SMS provider API"""
        try:
            # Re-fetch the OTP object in this thread
            otp_obj = OTP.objects.get(id=otp_record_id)
            
            if self.provider.upper() == 'MESSAGE_CENTRAL':
                success, message, verification_id = self._send_via_message_central(sms_number, None)
                if success and verification_id:
                    otp_obj.verification_id = verification_id
                    otp_obj.otp_code = 'MC-OTP'
                    otp_obj.save()
                    logger.info(f"Background OTP sent via Message Central to {sms_number}. ID: {verification_id}")
                else:
                    logger.error(f"Background OTP failed via Message Central for {sms_number}: {message}")
                    # We don't delete the record so we can track the failure if needed
            else:
                success = self._send_sms_via_provider(sms_number, otp_code)
                if success:
                    logger.info(f"Background OTP sent to {sms_number}")
                else:
                    logger.error(f"Background OTP failed for {sms_number}")
                    otp_obj.delete()

        except Exception as e:
            logger.error(f"Critical error in background OTP thread: {str(e)}")

    def verify_otp(self, phone_number, otp_code, purpose='LOGIN'):
        """
        Verify OTP code
        Returns: (success: bool, message: str, user: User or None)
        """
        try:
            # Clean phone number for verification (10 digits without country code)
            clean_number = self._clean_phone_number(phone_number, for_sms=False)
            
            # Clean and normalize OTP code (remove whitespace, convert to string)
            otp_code_clean = str(otp_code).strip() if otp_code else ""

            # Find the latest unused OTP for this number and purpose
            otp_obj = OTP.objects.filter(
                phone_number=clean_number,
                purpose=purpose,
                is_used=False
            ).order_by('-created_at').first()

            if not otp_obj:
                logger.warning(f"No valid OTP found for phone {clean_number}, purpose {purpose}")
                return False, "No valid OTP found", None

            if otp_obj.is_expired():
                logger.warning(f"OTP expired for phone {clean_number}")
                return False, "OTP has expired", None

            if not otp_obj.can_verify():
                if otp_obj.attempts >= 10:
                    return False, "Too many failed attempts. Please wait 5 minutes before trying again.", None
                return False, "OTP cannot be verified at this time", None

            # If using Message Central, always verify via their API
            if self.provider.upper() == 'MESSAGE_CENTRAL':
                if not otp_obj.verification_id or otp_obj.verification_id == 'PENDING':
                    # Wait a few seconds if it's still pending (the background thread might be slow)
                    import time
                    for _ in range(3):
                        otp_obj.refresh_from_db()
                        if otp_obj.verification_id != 'PENDING':
                            break
                        time.sleep(1)
                    
                    if not otp_obj.verification_id or otp_obj.verification_id == 'PENDING':
                        logger.error(f"Message Central OTP record missing verification_id for phone {clean_number}")
                        return False, "OTP is still being sent. Please wait a moment and try again.", None
                
                logger.info(f"Verifying OTP via Message Central API for phone {clean_number}")
                success, message = self._verify_via_message_central(otp_obj.verification_id, otp_code_clean, clean_number)
                if success:
                    # Mark OTP as used
                    otp_obj.is_used = True
                    otp_obj.save()
                    # Find user
                    from .models import User
                    user = User.objects.filter(phone_number=clean_number).first()
                    if user:
                        logger.info(f"OTP verified successfully for user {user.username}")
                        return True, "OTP verified successfully", user
                    elif purpose == 'SIGNUP':
                        logger.info(f"OTP verified successfully for signup with phone {clean_number}")
                        return True, "OTP verified successfully", None
                    else:
                        return False, "User not found", None
                else:
                    otp_obj.increment_attempts()
                    attempts_left = 10 - otp_obj.attempts
                    if attempts_left > 0:
                        return False, f"{message}. {attempts_left} attempts remaining", None
                    else:
                        return False, f"{message}. Too many failed attempts. Please wait 5 minutes.", None

            # Fallback: Compare OTP codes directly (for other providers)
            stored_otp = str(otp_obj.otp_code).strip()
            provided_otp = otp_code_clean
            
            # Debug logging
            logger.info(f"OTP verification attempt: phone={clean_number} (original={phone_number}), stored_otp='{stored_otp}' (len={len(stored_otp)}), provided_otp='{provided_otp}' (len={len(provided_otp)}), purpose={purpose}")
            
            if stored_otp != provided_otp:
                otp_obj.increment_attempts()
                attempts_left = 10 - otp_obj.attempts
                if attempts_left > 0:
                    return False, f"Invalid OTP. {attempts_left} attempts remaining", None
                else:
                    return False, "Invalid OTP. Too many failed attempts. Please wait 5 minutes.", None

            # Mark OTP as used
            otp_obj.is_used = True
            otp_obj.save()

            # Find user with this phone number
            from .models import User
            user = User.objects.filter(phone_number=clean_number).first()

            if user:
                logger.info(f"OTP verified successfully for user {user.username}")
                return True, "OTP verified successfully", user
            elif purpose == 'SIGNUP':
                # For SIGNUP, it's okay if user doesn't exist yet
                logger.info(f"OTP verified successfully for signup with phone {clean_number}")
                return True, "OTP verified successfully", None
            else:
                logger.warning(f"OTP verified but no user found for phone {clean_number}")
                return False, "User not found", None

        except Exception as e:
            logger.exception(f"Error verifying OTP for {phone_number}: {str(e)}")
            return False, f"Error: {str(e)}", None

    def _clean_phone_number(self, phone_number, for_sms=False):
        """
        Clean phone number by removing country code, spaces, etc.
        """
        # Remove spaces, hyphens, etc.
        cleaned = ''.join(filter(str.isdigit, str(phone_number)))

        # If it starts with 91, remove it (assuming Indian numbers)
        if cleaned.startswith('91') and len(cleaned) > 10:
            cleaned = cleaned[2:]
        
        # Ensure we have exactly 10 digits
        if len(cleaned) != 10:
            if len(cleaned) > 10:
                cleaned = cleaned[-10:]
        
        # For SMS sending, add country code
        if for_sms and not cleaned.startswith('91') and len(cleaned) == 10:
            return f'91{cleaned}'
        
        return cleaned

    def _send_sms_via_provider(self, phone_number, otp_code):
        """Send SMS via configured provider"""
        try:
            if self.provider.upper() == 'MSG91':
                return self._send_via_msg91(phone_number, otp_code)
            elif self.provider.upper() == 'TWILIO':
                return self._send_via_twilio(phone_number, otp_code)
            elif self.provider.upper() == 'TEXTLOCAL':
                return self._send_via_textlocal(phone_number, otp_code)
            elif self.provider.upper() == 'MESSAGE_CENTRAL':
                return self._send_via_message_central(phone_number, otp_code)
            else:
                return self._send_via_msg91(phone_number, otp_code)
        except Exception as e:
            logger.exception(f"Error sending SMS via {self.provider}: {str(e)}")
            return False

    def _send_via_msg91(self, phone_number, otp_code):
        """Send SMS via MSG91"""
        if not self.api_key:
            return False
        url = "https://api.msg91.com/api/v5/flow/"
        headers = {'authkey': self.api_key, 'content-type': 'application/json'}
        payload = {
            "flow_id": self.template_id or "your_flow_id",
            "sender": self.sender_id,
            "mobiles": phone_number,
            "otp": otp_code
        }
        response = requests.post(url, json=payload, headers=headers, timeout=30)
        return response.status_code == 200 and response.json().get('type') == 'success'

    def _send_via_twilio(self, phone_number, otp_code):
        """Send SMS via Twilio"""
        try:
            from twilio.rest import Client
            account_sid = getattr(settings, 'TWILIO_ACCOUNT_SID', '')
            auth_token = getattr(settings, 'TWILIO_AUTH_TOKEN', '')
            client = Client(account_sid, auth_token)
            client.messages.create(
                body=f"Your GunduAta verification code is: {otp_code}",
                from_=self.api_key,
                to=f"+{phone_number}"
            )
            return True
        except Exception:
            return False

    def _send_via_textlocal(self, phone_number, otp_code):
        """Send SMS via Textlocal"""
        url = "https://api.textlocal.in/send/"
        api_key = getattr(settings, 'TEXTLOCAL_API_KEY', '')
        payload = {
            'apikey': api_key,
            'numbers': phone_number,
            'message': f"Your GunduAta verification code is: {otp_code}",
            'sender': self.sender_id
        }
        response = requests.post(url, data=payload, timeout=30)
        return response.status_code == 200 and response.json().get('status') == 'success'

    def _send_via_message_central(self, phone_number, otp_code=None):
        """Send SMS via Message Central"""
        if not self.api_key:
            return False, "API key not configured", None
        try:
            country_code = '91'
            mobile_number = phone_number[2:] if phone_number.startswith('91') else phone_number
            auth_token = getattr(settings, 'SMS_AUTH_TOKEN', '')
            customer_id = getattr(settings, 'SMS_CUSTOMER_ID', self.api_key)
            url = f"https://cpaas.messagecentral.com/verification/v3/send"
            params = {'countryCode': country_code, 'customerId': customer_id, 'flowType': 'SMS', 'mobileNumber': mobile_number}
            headers = {'authToken': auth_token}
            response = requests.post(url, params=params, headers=headers, json={}, timeout=30)
            result = response.json()
            data = result.get('data', {})
            verification_id = data.get('verificationId') or result.get('verificationId')
            return True, "OTP sent successfully", verification_id
        except Exception as e:
            return False, str(e), None

    def _verify_via_message_central(self, verification_id, otp_code, phone_number):
        """Verify OTP using Message Central"""
        try:
            auth_token = getattr(settings, 'SMS_AUTH_TOKEN', '')
            customer_id = getattr(settings, 'SMS_CUSTOMER_ID', self.api_key)
            url = f"https://cpaas.messagecentral.com/verification/v3/validateOtp"
            params = {
                'countryCode': '91',
                'customerId': customer_id,
                'verificationId': verification_id,
                'mobileNumber': phone_number,
                'code': otp_code
            }
            headers = {'authToken': auth_token}
            response = requests.get(url, params=params, headers=headers, timeout=30)
            result = response.json()
            if result.get('responseCode') == 200:
                return True, "OTP verified successfully"
            return False, result.get('message', 'Verification failed')
        except Exception as e:
            return False, str(e)


# Global SMS service instance
sms_service = SMSService()
