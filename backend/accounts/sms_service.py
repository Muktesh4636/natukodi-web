import requests
import json
import logging
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

            # For Message Central, they generate their own OTP, so we don't generate one
            # We'll store a placeholder and rely on their verification API
            if self.provider.upper() == 'MESSAGE_CENTRAL':
                # Send SMS via Message Central first (they generate the OTP)
                success, message, verification_id = self._send_via_message_central(sms_number, None)
                if success and verification_id:
                    # Store OTP record with verification_id (use placeholder OTP code)
                    otp_obj = OTP.objects.create(
                        phone_number=clean_number,
                        otp_code='MC-OTP',  # Placeholder - actual OTP is managed by Message Central
                        purpose=purpose,
                        expires_at=expires_at,
                        verification_id=verification_id
                    )
                    logger.info(f"OTP sent successfully to {clean_number} for {purpose} via Message Central. Verification ID: {verification_id}")
                    return True, message, otp_obj.id
                else:
                    logger.error(f"Failed to send OTP to {clean_number} via Message Central: {message}")
                    return False, message, None
            else:
                # For other providers, generate our own OTP
                otp_code = self.generate_otp()
                
                # Save OTP to database (use 10-digit number for consistency)
                otp_obj = OTP.objects.create(
                    phone_number=clean_number,
                    otp_code=otp_code,
                    purpose=purpose,
                    expires_at=expires_at
                )

                # Send SMS via other providers (use SMS number with country code)
                success = self._send_sms_via_provider(sms_number, otp_code)
                message = "OTP sent successfully" if success else "Failed to send SMS"

                if success:
                    logger.info(f"OTP sent successfully to {clean_number} for {purpose}")
                    return True, message, otp_obj.id
                else:
                    # Delete the OTP record if SMS failed
                    otp_obj.delete()
                    logger.error(f"Failed to send OTP to {clean_number}: {message}")
                    return False, message, None

        except Exception as e:
            logger.exception(f"Error sending OTP to {phone_number}: {str(e)}")
            return False, f"Error: {str(e)}", None

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
                if not otp_obj.verification_id:
                    logger.error(f"Message Central OTP record missing verification_id for phone {clean_number}")
                    return False, "OTP verification failed: Missing verification ID. Please request a new OTP.", None
                
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
            logger.info(f"OTP object details: id={otp_obj.id}, created_at={otp_obj.created_at}, expires_at={otp_obj.expires_at}, is_used={otp_obj.is_used}, attempts={otp_obj.attempts}, verification_id={otp_obj.verification_id}")
            
            if stored_otp != provided_otp:
                otp_obj.increment_attempts()
                attempts_left = 10 - otp_obj.attempts
                logger.warning(f"OTP mismatch: stored='{stored_otp}' (type={type(stored_otp).__name__}) vs provided='{provided_otp}' (type={type(provided_otp).__name__}) for phone {clean_number}")
                logger.warning(f"Character comparison: stored_bytes={stored_otp.encode('utf-8')}, provided_bytes={provided_otp.encode('utf-8')}")
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
        Args:
            phone_number: Phone number to clean
            for_sms: If True, add country code for SMS sending. If False, return 10-digit for storage.
        Returns:
            Cleaned phone number (10 digits for storage, or with country code for SMS)
        """
        # Remove spaces, hyphens, etc.
        cleaned = ''.join(filter(str.isdigit, str(phone_number)))

        # If it starts with 91, remove it (assuming Indian numbers)
        if cleaned.startswith('91') and len(cleaned) > 10:
            cleaned = cleaned[2:]
        
        # Ensure we have exactly 10 digits (Indian phone number)
        if len(cleaned) != 10:
            logger.warning(f"Phone number {phone_number} cleaned to {cleaned} has invalid length {len(cleaned)}")
            # Try to extract last 10 digits if longer
            if len(cleaned) > 10:
                cleaned = cleaned[-10:]
            elif len(cleaned) < 10:
                logger.error(f"Phone number {phone_number} has less than 10 digits after cleaning")
                return cleaned  # Return as-is, validation will catch it
        
        # For SMS sending, add country code. For storage/verification, return 10-digit number
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
                # Default to MSG91
                return self._send_via_msg91(phone_number, otp_code)

        except Exception as e:
            logger.exception(f"Error sending SMS via {self.provider}: {str(e)}")
            return False

    def _send_via_msg91(self, phone_number, otp_code):
        """Send SMS via MSG91"""
        if not self.api_key:
            logger.error("MSG91 API key not configured")
            return False

        url = "https://api.msg91.com/api/v5/flow/"
        headers = {
            'authkey': self.api_key,
            'content-type': 'application/json'
        }

        payload = {
            "flow_id": self.template_id or "your_flow_id",
            "sender": self.sender_id,
            "mobiles": phone_number,
            "otp": otp_code
        }

        response = requests.post(url, json=payload, headers=headers, timeout=30)

        if response.status_code == 200:
            result = response.json()
            if result.get('type') == 'success':
                return True

        logger.error(f"MSG91 API error: {response.status_code} - {response.text}")
        return False

    def _send_via_twilio(self, phone_number, otp_code):
        """Send SMS via Twilio"""
        try:
            from twilio.rest import Client
        except ImportError:
            logger.error("Twilio package not installed")
            return False

        account_sid = getattr(settings, 'TWILIO_ACCOUNT_SID', '')
        auth_token = getattr(settings, 'TWILIO_AUTH_TOKEN', '')

        if not all([account_sid, auth_token, self.api_key]):
            logger.error("Twilio credentials not configured")
            return False

        client = Client(account_sid, auth_token)

        message = f"Your GunduAta verification code is: {otp_code}. Valid for 10 minutes."

        try:
            sms = client.messages.create(
                body=message,
                from_=self.api_key,  # Twilio phone number
                to=f"+{phone_number}"
            )
            return True
        except Exception as e:
            logger.error(f"Twilio error: {str(e)}")
            return False

    def _send_via_textlocal(self, phone_number, otp_code):
        """Send SMS via Textlocal"""
        url = "https://api.textlocal.in/send/"
        api_key = getattr(settings, 'TEXTLOCAL_API_KEY', '')

        if not api_key:
            logger.error("Textlocal API key not configured")
            return False

        payload = {
            'apikey': api_key,
            'numbers': phone_number,
            'message': f"Your GunduAta verification code is: {otp_code}. Valid for 10 minutes.",
            'sender': self.sender_id
        }

        response = requests.post(url, data=payload, timeout=30)

        if response.status_code == 200:
            result = response.json()
            if result.get('status') == 'success':
                return True

        logger.error(f"Textlocal API error: {response.status_code} - {response.text}")
        return False

    def _send_via_message_central(self, phone_number, otp_code=None):
        """
        Send SMS via Message Central
        Note: Message Central generates its own OTP, so otp_code parameter is ignored
        """
        if not self.api_key:
            logger.error("Message Central API key not configured")
            return False, "API key not configured", None

        try:
            # Extract country code from phone number (91 for India)
            # Phone number format: 91XXXXXXXXXX (already includes country code from _clean_phone_number)
            country_code = '91'  # India
            if phone_number.startswith('91') and len(phone_number) > 10:
                mobile_number = phone_number[2:]  # Remove country code for mobileNumber param
            else:
                mobile_number = phone_number
            
            # Get auth token and customer ID from settings
            auth_token = getattr(settings, 'SMS_AUTH_TOKEN', '')
            customer_id = getattr(settings, 'SMS_CUSTOMER_ID', self.api_key)
            
            if not auth_token:
                logger.error("Message Central auth token not configured")
                return False, "Auth token not configured", None
            
            # Message Central API endpoint - they generate the OTP themselves
            url = f"https://cpaas.messagecentral.com/verification/v3/send"
            params = {
                'countryCode': country_code,
                'customerId': customer_id,
                'flowType': 'SMS',
                'mobileNumber': mobile_number
            }
            
            headers = {
                'authToken': auth_token
            }

            logger.info(f"Sending OTP via Message Central to {mobile_number} (country: {country_code}) - Message Central will generate the OTP")
            response = requests.post(url, params=params, headers=headers, json={}, timeout=30)
            
            logger.info(f"Message Central response: {response.status_code} - {response.text}")
            
            # Try to parse response regardless of HTTP status code
            try:
                result = response.json()
                # Message Central returns verificationId nested in 'data' object
                data = result.get('data', {})
                verification_id = data.get('verificationId') or data.get('verification_id') or result.get('verificationId') or result.get('verification_id')
                
                # Get response code and message
                response_code = result.get('responseCode') or data.get('responseCode')
                message = result.get('message', '')
                
                # Handle REQUEST_ALREADY_EXISTS (506) - this means OTP was already sent, but we still have verificationId
                if response_code == 506 and message == 'REQUEST_ALREADY_EXISTS' and verification_id:
                    logger.info(f"OTP request already exists for this number. Using existing Verification ID: {verification_id}")
                    return True, "OTP already sent. Please check your phone or wait before requesting again.", verification_id
                
                # Handle success cases
                if response.status_code in [200, 201] and (response_code == 200 or message == 'SUCCESS' or verification_id):
                    if verification_id:
                        logger.info(f"Message Central SMS sent successfully. Verification ID: {verification_id}")
                        return True, "OTP sent successfully", verification_id
                    else:
                        logger.info(f"Message Central SMS sent successfully (no verificationId in response)")
                        return True, "OTP sent successfully", None
                
                # Handle error cases
                if verification_id:
                    # Even if there's an error code, if we have verificationId, consider it success
                    logger.warning(f"Message Central returned error code {response_code} but provided verificationId: {verification_id}")
                    return True, "OTP sent successfully", verification_id
                else:
                    error_msg = f"Message Central API error: {response_code} - {message}"
                    logger.error(error_msg)
                    return False, error_msg, None
                    
            except Exception as e:
                # If response is not JSON or parsing fails
                if response.status_code in [200, 201]:
                    logger.warning(f"Could not parse Message Central response as JSON: {e}, but status is {response.status_code}")
                    return True, "OTP sent successfully", None
                else:
                    error_msg = f"Message Central API error: {response.status_code} - {response.text}"
                    logger.error(error_msg)
                    return False, error_msg, None
                
        except requests.exceptions.RequestException as e:
            error_msg = f"Message Central request failed: {str(e)}"
            logger.exception(error_msg)
            return False, error_msg, None
        except Exception as e:
            error_msg = f"Unexpected error in Message Central: {str(e)}"
            logger.exception(error_msg)
            return False, error_msg, None

    def _verify_via_message_central(self, verification_id, otp_code, phone_number):
        """
        Verify OTP using Message Central's verification API
        Returns: (success: bool, message: str)
        """
        try:
            # Get auth token and customer ID from settings
            auth_token = getattr(settings, 'SMS_AUTH_TOKEN', '')
            customer_id = getattr(settings, 'SMS_CUSTOMER_ID', self.api_key)
            
            if not auth_token:
                logger.error("Message Central auth token not configured")
                return False, "Auth token not configured"
            
            # Message Central verify endpoint
            url = f"https://cpaas.messagecentral.com/verification/v3/validateOtp"
            
            # Extract mobile number (10 digits)
            # phone_number here is already the cleaned 10-digit number from verify_otp
            # We need to use it as-is, but Message Central expects it without country code
            country_code = '91'
            mobile_number = str(phone_number)  # Use the 10-digit number directly
            
            params = {
                'countryCode': country_code,
                'customerId': customer_id,
                'verificationId': verification_id,
                'mobileNumber': mobile_number,
                'code': otp_code
            }
            
            headers = {
                'authToken': auth_token
            }
            
            logger.info(f"Verifying OTP via Message Central: verificationId={verification_id}, mobileNumber={mobile_number}, otp={otp_code}")
            response = requests.get(url, params=params, headers=headers, timeout=30)
            
            logger.info(f"Message Central verify response: {response.status_code} - {response.text}")
            
            try:
                result = response.json()
                response_code = result.get('responseCode')
                message = result.get('message', '')
                
                # Check if the API call was successful (HTTP 200) and responseCode is 200
                # Message Central returns HTTP 200 even for errors, but responseCode indicates actual status
                if response.status_code == 200 and response_code == 200:
                    # Get verification status from data (handle null data)
                    data = result.get('data') or {}
                    verification_status = data.get('verificationStatus') if isinstance(data, dict) else None
                    
                    # Success: responseCode 200 and verificationStatus is VERIFICATION_COMPLETED
                    if verification_status == 'VERIFICATION_COMPLETED' or message.upper() == 'SUCCESS':
                        logger.info(f"Message Central OTP verified successfully")
                        return True, "OTP verified successfully"
                    else:
                        error_msg = f"OTP verification failed: {message or f'Status: {verification_status}'}"
                        logger.warning(f"Message Central verification failed: {error_msg}")
                        return False, error_msg
                else:
                    # API returned an error responseCode (like 702 for WRONG_OTP_PROVIDED)
                    error_msg = f"OTP verification failed: {message or f'Response Code {response_code}'}"
                    logger.warning(f"Message Central verification failed: {error_msg}")
                    return False, error_msg
                    
            except Exception as e:
                # If we can't parse the response, it's an error
                error_msg = f"Message Central verify API error: {response.status_code} - {response.text} - Parse error: {str(e)}"
                logger.error(error_msg)
                return False, error_msg
                    
        except requests.exceptions.RequestException as e:
            error_msg = f"Message Central verify request failed: {str(e)}"
            logger.exception(error_msg)
            return False, error_msg
        except Exception as e:
            error_msg = f"Unexpected error in Message Central verify: {str(e)}"
            logger.exception(error_msg)
            return False, error_msg


# Global SMS service instance
sms_service = SMSService()