from django.shortcuts import get_object_or_404
from rest_framework import status, generics
from rest_framework.decorators import api_view, permission_classes, parser_classes, authentication_classes
from rest_framework.permissions import AllowAny, IsAuthenticated, IsAdminUser
from rest_framework.response import Response
from django.views.decorators.csrf import csrf_exempt
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from django.contrib.auth import authenticate
from django.db import transaction as db_transaction
from django.utils import timezone
from django.conf import settings
from decimal import Decimal, InvalidOperation
from django.db.models import Q, F
import uuid
import re
import logging
import json

logger = logging.getLogger('accounts')

try:
    import pytesseract
    from PIL import Image
    import io
    TESSERACT_AVAILABLE = True
except ImportError:
    TESSERACT_AVAILABLE = False

from .models import User, Wallet, Transaction, DepositRequest, WithdrawRequest, PaymentMethod, UserBankDetail, DailyReward, LuckyDraw
from .serializers import (
    UserRegistrationSerializer,
    UserSerializer,
    WalletSerializer,
    TransactionSerializer,
    DepositRequestSerializer,
    DepositRequestAdminSerializer,
    WithdrawRequestSerializer,
    PaymentMethodSerializer,
    UserBankDetailSerializer,
)

from game.utils import get_redis_client

# Redis connection with tiered failover
redis_client = get_redis_client()


import hashlib
import hmac
from django.utils.crypto import constant_time_compare

def hash_otp(otp):
    """Hash OTP using SHA256"""
    return hashlib.sha256(str(otp).encode()).hexdigest()

def cache_user_session(user, balance=None):
    """Helper to cache user session and balance in Redis"""
    if not redis_client:
        return
    try:
        if balance is None:
            try:
                balance = user.wallet.balance
            except:
                balance = Decimal('0.00')
        
        pipe = redis_client.pipeline()
        pipe.set(f"user_balance:{user.id}", str(balance), ex=86400) # 24 hours
        
        user_session_data = {
            'id': user.id,
            'username': user.username,
            'is_staff': user.is_staff,
            'is_active': user.is_active,
            'wallet_balance': str(balance)
        }
        pipe.set(f"user_session:{user.id}", json.dumps(user_session_data), ex=86400) # 24 hours
        pipe.execute()
    except Exception as e:
        logger.error(f"Error caching user session: {e}")

def notify_user(user, message):
    """Placeholder notification helper"""
    # In a real system, this would push a notification via WebSocket or a push service
    print(f"[NOTIFY] {user.username}: {message}")


@api_view(['POST'])
@authentication_classes([])  # Disable authentication for registration
@permission_classes([AllowAny])
@csrf_exempt
def register(request):
    """User registration with Redis-based OTP verification"""
    try:
        phone_number = request.data.get('phone_number', '').strip()
        otp_code = request.data.get('otp_code', '').strip()
        username = request.data.get('username', '').strip()
        password = request.data.get('password', '').strip()
        referral_code = request.data.get('referral_code', '').strip()
        
        if not phone_number or not otp_code or not username or not password:
            return Response({'error': 'All fields are required'}, status=status.HTTP_400_BAD_REQUEST)

        # 1. Validate OTP from Redis
        if not redis_client:
            return Response({'error': 'System error: Redis unavailable'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        # Clean phone number (10 digits)
        from .sms_service import sms_service
        clean_phone = sms_service._clean_phone_number(phone_number, for_sms=False)
        
        otp_key = f"otp:{clean_phone}"
        stored_hash = redis_client.get(otp_key)
        
        if not stored_hash:
            return Response({'error': 'OTP expired or not found'}, status=status.HTTP_400_BAD_REQUEST)
        
        # Compare hashes securely
        provided_hash = hash_otp(otp_code)
        if not constant_time_compare(stored_hash, provided_hash):
            return Response({'error': 'Invalid OTP'}, status=status.HTTP_400_BAD_REQUEST)
        
        # 2. Check Uniqueness (rely on DB constraints but check early for better UX)
        if User.objects.filter(username=username).exists():
            return Response({'error': 'Username already taken'}, status=status.HTTP_400_BAD_REQUEST)
        if User.objects.filter(phone_number=clean_phone).exists():
            return Response({'error': 'Phone number already registered'}, status=status.HTTP_400_BAD_REQUEST)

        # 3. Create User and Wallet in a single transaction
        try:
            with db_transaction.atomic():
                # Handle referral
                referred_by = None
                if referral_code:
                    referred_by = User.objects.filter(referral_code=referral_code).first()

                # Create user
                user = User.objects.create_user(
                    username=username,
                    password=password,
                    phone_number=clean_phone,
                    referred_by=referred_by
                )
                
                # Create wallet
                wallet = Wallet.objects.create(user=user, balance=Decimal('0.00'))
                
                # Success - delete OTP from Redis
                redis_client.delete(otp_key)
                
                logger.info(f"User registered successfully: {user.username} (ID: {user.id})")
                
                # 4. Cache balance and session in Redis
                redis_client.set(f"user_balance:{user.id}", "0.00", ex=86400)
                user_session_data = {
                    'id': user.id,
                    'username': user.username,
                    'is_staff': user.is_staff,
                    'is_active': user.is_active,
                    'wallet_balance': "0.00"
                }
                redis_client.set(f"user_session:{user.id}", json.dumps(user_session_data), ex=3600)

                # Generate tokens
                refresh = RefreshToken.for_user(user)
                return Response({
                    'user': UserSerializer(user).data,
                    'refresh': str(refresh),
                    'access': str(refresh.access_token),
                    'message': 'Registration successful'
                }, status=status.HTTP_201_CREATED)

        except Exception as db_err:
            logger.exception(f"Database error during registration: {db_err}")
            return Response({'error': 'Registration failed. Please try again.'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    except Exception as e:
        logger.exception(f"Error in register: {str(e)}")
        return Response({'error': 'Internal server error'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@authentication_classes([])
@permission_classes([AllowAny])
@csrf_exempt
def loading_time(request):
    """API endpoint to get loading time - No authentication required"""
    try:
        # Return only loading time (in seconds)
        loading_time_value = 3  # Default loading time in seconds
        return Response({'loading_time': loading_time_value}, status=status.HTTP_200_OK)
    except Exception as e:
        logger.exception(f"Error in loading_time: {e}")
        return Response({'loading_time': 3}, status=status.HTTP_200_OK)


@api_view(['POST'])
@authentication_classes([])  # Disable authentication for login
@permission_classes([AllowAny])
@csrf_exempt
def login(request):
    """Optimized User login with minimal DB hits and NO Redis dependency"""
    try:
        username = request.data.get('username', '').strip()
        password = request.data.get('password', '').strip()

        if not username or not password:
            return Response({'error': 'Username and password required'}, status=status.HTTP_400_BAD_REQUEST)

        # 1. Clean username if it looks like a phone number
        # This ensures login works even if user enters +91 or spaces
        clean_username = username
        if any(char.isdigit() for char in username):
            # Extract only digits
            digits = ''.join(filter(str.isdigit, username))
            if len(digits) >= 10:
                clean_username = digits[-10:]

        # 2. Single query for User and Wallet (using select_related)
        # Check both original username and cleaned phone number
        user = User.objects.filter(
            Q(username=username) | 
            Q(phone_number=username) | 
            Q(phone_number=clean_username)
        ).select_related('wallet').first()

        if not user or not user.check_password(password):
            return Response({'error': 'Invalid credentials'}, status=status.HTTP_401_UNAUTHORIZED)

        if not user.is_active:
            return Response({'error': 'User account is disabled'}, status=status.HTTP_403_FORBIDDEN)

        # 2. Generate JWT tokens (No DB hit)
        refresh = RefreshToken.for_user(user)
        
        # 3. Sync balance and session to Redis (CRITICAL for high-speed betting)
        if redis_client:
            try:
                # Use the already fetched wallet from select_related
                wallet_balance = user.wallet.balance if hasattr(user, 'wallet') else Decimal('0.00')
                
                # Use a pipeline for faster Redis operations
                pipe = redis_client.pipeline()
                pipe.set(f"user_balance:{user.id}", str(wallet_balance), ex=86400)
                
                user_session_data = {
                    'id': user.id,
                    'username': user.username,
                    'is_staff': user.is_staff,
                    'is_active': user.is_active,
                    'wallet_balance': str(wallet_balance)
                }
                pipe.set(f"user_session:{user.id}", json.dumps(user_session_data), ex=3600)
                pipe.execute()
                
                # Update last login - use update_fields to avoid full model save
                # and only do it if it's been more than 5 minutes to reduce DB load
                now = timezone.now()
                if not user.last_login or (now - user.last_login).total_seconds() > 300:
                    user.last_login = now
                    user.save(update_fields=['last_login'])
            except Exception as re:
                logger.error(f"Redis sync error during login: {re}")

        # 4. Return response with serialized data
        return Response({
            'user': UserSerializer(user).data,
            'refresh': str(refresh),
            'access': str(refresh.access_token),
        }, status=status.HTTP_200_OK)

    except Exception as e:
        logger.exception(f"Unexpected error during login: {e}")
        return Response({
            'error': 'Internal server error',
            'detail': str(e) if settings.DEBUG else 'An error occurred during login'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@authentication_classes([])
@permission_classes([AllowAny])
@csrf_exempt
def send_otp(request):
    """Send OTP to phone number with Redis-based rate limiting and storage"""
    try:
        phone_number = request.data.get('phone_number', '').strip()
        purpose = request.data.get('purpose', 'SIGNUP').upper()

        if not phone_number:
            return Response({'error': 'Phone number is required'}, status=status.HTTP_400_BAD_REQUEST)

        if not redis_client:
            return Response({'error': 'System error: Redis unavailable'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # 1. Clean phone number
        from .sms_service import sms_service
        clean_phone = sms_service._clean_phone_number(phone_number, for_sms=False)
        
        # 2. Rate Limiting: Max 5 requests per 10 minutes
        rate_key = f"otp_rate:{clean_phone}"
        requests_count = redis_client.incr(rate_key)
        if requests_count == 1:
            redis_client.expire(rate_key, 600) # 10 minutes
        
        if requests_count > 5:
            return Response({
                'error': 'Too many OTP requests. Please wait 10 minutes.'
            }, status=status.HTTP_429_TOO_MANY_REQUESTS)

        # 3. Generate secure 6-digit OTP
        import random
        otp_code = ''.join([str(random.randint(0, 9)) for _ in range(6)])
        
        # 4. Store hashed OTP in Redis (5 minutes)
        otp_key = f"otp:{clean_phone}"
        hashed_val = hash_otp(otp_code)
        redis_client.set(otp_key, hashed_val, ex=300)
        
        # 5. Send OTP via SMS provider
        # Note: We pass the generated OTP to the service
        sms_number = sms_service._clean_phone_number(phone_number, for_sms=True)
        
        # We'll use a background thread to avoid blocking the request
        import threading
        thread = threading.Thread(
            target=sms_service._send_sms_via_provider,
            args=(sms_number, otp_code)
        )
        thread.daemon = True
        thread.start()

        logger.info(f"OTP sent to {clean_phone} (Purpose: {purpose})")
        
        return Response({
            'message': 'OTP sent successfully',
            'expires_in': 300
        }, status=status.HTTP_200_OK)

    except Exception as e:
        logger.exception(f"Error in send_otp: {str(e)}")
        return Response({'error': 'Internal server error'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@authentication_classes([])
@permission_classes([AllowAny])
@csrf_exempt
def verify_otp_login(request):
    """Verify Redis-based OTP and login user"""
    try:
        phone_number = request.data.get('phone_number', '').strip()
        otp_code = request.data.get('otp_code', '').strip()

        if not phone_number or not otp_code:
            return Response({'error': 'Phone number and OTP code are required'}, status=status.HTTP_400_BAD_REQUEST)

        if not redis_client:
            return Response({'error': 'System error: Redis unavailable'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # 1. Validate OTP from Redis
        from .sms_service import sms_service
        clean_phone = sms_service._clean_phone_number(phone_number, for_sms=False)
        
        otp_key = f"otp:{clean_phone}"
        stored_hash = redis_client.get(otp_key)
        
        if not stored_hash:
            return Response({'error': 'OTP expired or not found'}, status=status.HTTP_400_BAD_REQUEST)
        
        # Compare hashes securely
        provided_hash = hash_otp(otp_code)
        if not constant_time_compare(stored_hash, provided_hash):
            return Response({'error': 'Invalid OTP'}, status=status.HTTP_400_BAD_REQUEST)

        # 2. Find user
        user = User.objects.filter(phone_number=clean_phone).first()
        if not user:
            return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)

        if not user.is_active:
            return Response({'error': 'User account is disabled'}, status=status.HTTP_403_FORBIDDEN)

        # Success - delete OTP from Redis
        redis_client.delete(otp_key)

        # 3. Create JWT tokens
        refresh = RefreshToken.for_user(user)

        # Update last login
        user.last_login = timezone.now()
        user.save(update_fields=['last_login'])

        logger.info(f"OTP login successful for user: {user.username} (ID: {user.id})")

        # 4. Sync balance and session to Redis
        if redis_client:
            try:
                wallet_obj, _ = Wallet.objects.get_or_create(user=user)
                
                # Use pipeline for faster Redis operations
                pipe = redis_client.pipeline()
                pipe.set(f"user_balance:{user.id}", str(wallet_obj.balance), ex=86400)
                
                user_session_data = {
            'id': user.id,
            'username': user.username,
                    'is_staff': user.is_staff,
                    'is_active': user.is_active,
                    'wallet_balance': str(wallet_obj.balance)
                }
                pipe.set(f"user_session:{user.id}", json.dumps(user_session_data), ex=3600)
                pipe.execute()
            except Exception as re:
                logger.error(f"Redis sync error in verify_otp_login: {re}")

        return Response({
            'user': UserSerializer(user).data,
            'refresh': str(refresh),
            'access': str(refresh.access_token),
            'message': 'Login successful'
        }, status=status.HTTP_200_OK)

    except Exception as e:
        logger.exception(f"Error in verify_otp_login: {str(e)}")
        return Response({'error': 'Internal server error'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def profile(request):
    """Get or update user profile"""
    try:
        if request.method == 'GET':
            logger.info(f"Profile access for user: {request.user.username} (ID: {request.user.id})")
            serializer = UserSerializer(request.user, context={'request': request})
            return Response(serializer.data)
        
        elif request.method == 'POST':
            logger.info(f"Profile update for user: {request.user.username} (ID: {request.user.id})")
            serializer = UserSerializer(request.user, data=request.data, partial=True, context={'request': request})
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        logger.error(f"Error in profile API for user {request.user.id}: {str(e)}", exc_info=True)
        return Response({
            'error': 'An error occurred while processing your request',
            'detail': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@parser_classes([MultiPartParser, FormParser])
def update_profile_photo(request):
    """Update user profile photo"""
    photo = request.FILES.get('photo')
    if not photo:
        return Response({'error': 'Photo is required'}, status=status.HTTP_400_BAD_REQUEST)
    
    request.user.profile_photo = photo
    request.user.save()
    serializer = UserSerializer(request.user)
    return Response(serializer.data)


from rest_framework.views import APIView
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser


class WalletView(APIView):
    """Redis-first Wallet balance check"""
    permission_classes = [IsAuthenticated]

    def get(self, request, format=None):
        user_id = request.user.id
        
        # 1. Try Redis for real-time balance and cached wallet data
        # This avoids hitting the DB for every wallet check
        cache_key = f"wallet_data_cache:{user_id}"
        cached_wallet = None
        if redis_client:
            try:
                cached_wallet = redis_client.get(cache_key)
                if cached_wallet:
                    wallet_data = json.loads(cached_wallet)
                    # Always get the most real-time balance from Redis
                    realtime_balance = redis_client.get(f"user_balance:{user_id}")
                    if realtime_balance is not None:
                        wallet_data['balance'] = realtime_balance
                        # Recalculate withdrawable balance based on realtime balance
                        try:
                            unav = Decimal(wallet_data['unavaliable_balance'])
                            bal = Decimal(realtime_balance)
                            wallet_data['withdrawable_balance'] = str(max(Decimal('0.00'), bal - unav))
                        except: pass
                    return Response(wallet_data)
            except Exception as re:
                logger.error(f"Redis wallet cache fetch error: {re}")

        # 2. Fallback to DB if not in Redis
        wallet, created = Wallet.objects.get_or_create(user=request.user)
        
        balance = None
        if redis_client:
            try:
                balance = redis_client.get(f"user_balance:{user_id}")
            except Exception as re:
                logger.error(f"Redis balance fetch error: {re}")

        if balance is None:
            balance = str(wallet.balance)
            # Sync back to Redis if missing
            if redis_client:
                try:
                    redis_client.set(f"user_balance:{user_id}", balance, ex=86400)
                except: pass

        wallet_response = {
            'id': wallet.id,
            'balance': balance,
            'unavaliable_balance': str(wallet.unavaliable_balance),
            'withdrawable_balance': str(wallet.withdrawable_balance),
            'unavailable_balance': str(wallet.unavaliable_balance)
        }

        # Cache the wallet data (excluding balance which is handled separately) for 5 seconds
        if redis_client:
            try:
                redis_client.set(cache_key, json.dumps(wallet_response), ex=5)
            except: pass

        return Response(wallet_response)


class TransactionList(generics.ListAPIView):
    """List user transactions"""
    serializer_class = TransactionSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        logger.info(f"Transaction history access for user: {self.request.user.username} (ID: {self.request.user.id})")
        return Transaction.objects.filter(user=self.request.user).order_by('-created_at')


def _parse_amount(value):
    """Parse and validate amount value, ensuring it's a valid Decimal with max 2 decimal places"""
    if value is None:
        raise ValueError('Amount is required')
    
    try:
        # Convert to string first to handle various input types
        value_str = str(value).strip()
        
        # Remove surrounding quotes if they exist (common in multipart serialization)
        if (value_str.startswith('"') and value_str.endswith('"')) or \
           (value_str.startswith("'") and value_str.endswith("'")):
            value_str = value_str[1:-1].strip()
            
        if not value_str:
            raise ValueError('Amount cannot be empty')
        
        # Parse as Decimal
        amount = Decimal(value_str)
    except (InvalidOperation, TypeError, ValueError) as e:
        raise ValueError(f'Invalid amount value: {value}. Must be a valid number.')
    
    # Check for special values
    if amount.is_nan() or amount.is_infinite():
        raise ValueError('Amount cannot be NaN or infinite')
    
    if amount <= 0:
        raise ValueError('Amount must be greater than 0')
    
    # Quantize to 2 decimal places, rounding if necessary
    try:
        quantized = amount.quantize(Decimal('0.01'), rounding='ROUND_HALF_UP')
        return quantized
    except InvalidOperation:
        # If quantize fails, try rounding manually
        # This handles cases where the value has too many decimal places
        rounded = round(float(amount), 2)
        return Decimal(str(rounded)).quantize(Decimal('0.01'))


def notify_user(user, message):
    """Placeholder notification helper"""
    print(f"[NOTIFY] {user.username}: {message}")


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def initiate_deposit(request):
    """Generate a payment link for manual deposit"""
    amount_raw = request.data.get('amount')
    try:
        amount = _parse_amount(amount_raw)
    except ValueError as exc:
        return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    if amount < 100:
        return Response({'error': 'Minimum deposit amount is ₹100'}, status=status.HTTP_400_BAD_REQUEST)

    payment_link = f"https://pay.example.com/{uuid.uuid4().hex}?amount={amount}"
    return Response({
        'amount': str(amount),
        'currency': 'INR',
        'payment_link': payment_link,
        'message': 'Complete the payment and upload the receipt.',
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@parser_classes([MultiPartParser, FormParser])
def extract_utr(request):
    """Analyze uploaded screenshot and extract UTR number"""
    if not TESSERACT_AVAILABLE:
        return Response({
            'success': False,
            'error': 'OCR functionality not available. Please install Tesseract OCR: brew install tesseract'
        }, status=status.HTTP_503_SERVICE_UNAVAILABLE)

    screenshot = request.FILES.get('screenshot') or request.FILES.get('file') or request.FILES.get('image')

    if not screenshot:
        return Response({'error': 'Screenshot file is required'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        # Set tesseract path if provided in settings
        tesseract_cmd = getattr(settings, 'TESSERACT_CMD', '/opt/homebrew/bin/tesseract')
        pytesseract.pytesseract.tesseract_cmd = tesseract_cmd
            
        # Open image using Pillow
        img = Image.open(screenshot)
        # Convert to grayscale for better OCR
        img = img.convert('L')
        
        # Perform OCR
        # Note: requires tesseract binary installed on the system
        text = pytesseract.image_to_string(img)
        
        # Extract UTR using regex
        # Common UTR patterns: 12 digits, or starting with specific UPI patterns
        # Look for 12 consecutive digits (most common for UPI UTR)
        utr_match = re.search(r'\b\d{12}\b', text)
        
        # If not found, look for "UTR" or "Ref" keywords nearby
        if not utr_match:
            # Look for 10-16 alphanumeric characters after "UTR" or "Transaction ID"
            keyword_match = re.search(r'(?:UTR|Ref|Transaction ID|Ref No)[:\s]+([A-Z0-9]{10,16})', text, re.IGNORECASE)
            if keyword_match:
                utr_number = keyword_match.group(1)
            else:
                utr_number = None
        else:
            utr_number = utr_match.group(0)

        if not utr_number:
            return Response({
                'success': False,
                'message': 'Could not extract UTR automatically. Please enter it manually.',
                'raw_text': text[:500] if settings.DEBUG else None
            })

        return Response({
            'success': True,
            'utr': utr_number,
            'message': 'UTR extracted successfully'
        })

    except Exception as e:
        return Response({
            'success': False,
            'error': f'Failed to process image: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([AllowAny])
@parser_classes([MultiPartParser, FormParser])
def process_payment_screenshot(request):
    """
    Analyze uploaded screenshot, extract UTR number, and return with user_id and amount.
    Expects: screenshot (file), user_id (string/int), amount (decimal/string)
    """
    user_id = request.data.get('user_id')
    amount = request.data.get('amount')
    screenshot = request.FILES.get('screenshot') or request.FILES.get('file') or request.FILES.get('image')

    if not screenshot:
        return Response({'error': 'Screenshot file is required'}, status=status.HTTP_400_BAD_REQUEST)

    response_data = {
        'success': False,
        'user_id': user_id,
        'amount': amount,
        'utr': None
    }

    if not TESSERACT_AVAILABLE:
        response_data['error'] = 'OCR functionality not available'
        return Response(response_data, status=status.HTTP_503_SERVICE_UNAVAILABLE)

    try:
        # Set tesseract path
        tesseract_cmd = getattr(settings, 'TESSERACT_CMD', '/opt/homebrew/bin/tesseract')
        pytesseract.pytesseract.tesseract_cmd = tesseract_cmd
            
        img = Image.open(screenshot)
        # Convert to grayscale for better OCR
        img = img.convert('L')
        text = pytesseract.image_to_string(img)
        
        # Log extracted text for debugging (limited)
        print(f"Extracted Text: {text[:200]}...")
        
        # Extract UTR using regex
        utr_match = re.search(r'\b\d{12}\b', text)
        if not utr_match:
            keyword_match = re.search(r'(?:UTR|Ref|Transaction ID|Ref No)[:\s]+([A-Z0-9]{10,16})', text, re.IGNORECASE)
            utr_number = keyword_match.group(1) if keyword_match else None
        else:
            utr_number = utr_match.group(0)

        response_data['utr'] = utr_number
        if utr_number:
            response_data['success'] = True
            response_data['message'] = 'UTR extracted successfully'
        else:
            response_data['message'] = 'Could not extract UTR automatically'

        return Response(response_data)

    except Exception as e:
        response_data['error'] = f'Failed to process image: {str(e)}'
        return Response(response_data, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@parser_classes([MultiPartParser, FormParser])
def upload_deposit_proof(request):
    """Create a deposit request with PENDING status - requires admin approval"""
    amount_raw = request.data.get('amount')
    logger.info(f"Deposit proof upload attempt for user {request.user.username} (ID: {request.user.id}), amount: {amount_raw}")
    
    # Try multiple possible field names for the file
    screenshot = request.FILES.get('screenshot') or request.FILES.get('file') or request.FILES.get('image')

    if not screenshot:
        available_files = list(request.FILES.keys()) if hasattr(request, 'FILES') and request.FILES else []
        error_msg = 'Screenshot file is required. '
        logger.warning(f"Deposit proof upload failed for user {request.user.username}: No file received. Available fields: {available_files}")
        if available_files:
            error_msg += f'Received file fields: {available_files}. Please use field name "screenshot".'
        else:
            error_msg += 'No files were received. Make sure to send the request as multipart/form-data.'
        return Response({'error': error_msg, 'received_files': available_files}, status=status.HTTP_400_BAD_REQUEST)

    try:
        amount = _parse_amount(amount_raw)
    except ValueError as exc:
        logger.warning(f"Deposit proof upload failed for user {request.user.username}: Invalid amount {amount_raw} - {exc}")
        return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    if amount < 100:
        logger.warning(f"Deposit proof upload failed for user {request.user.username}: Amount {amount} below minimum ₹100")
        return Response({'error': 'Minimum deposit amount is ₹100'}, status=status.HTTP_400_BAD_REQUEST)

    # Check for existing pending deposit request
    existing_pending = DepositRequest.objects.filter(user=request.user, status='PENDING').exists()
    if existing_pending:
        logger.warning(f"Deposit proof upload failed for user {request.user.username}: Already has a pending request")
        return Response({
            'error': 'You already have a pending deposit request. Please wait for it to be approved or rejected before sending another.'
        }, status=status.HTTP_400_BAD_REQUEST)

    # Create deposit request with PENDING status - no wallet credit yet
    try:
        payment_method_id = request.data.get('payment_method_id')
        payment_method = None
        if payment_method_id:
            try:
                payment_method = PaymentMethod.objects.get(id=payment_method_id)
            except PaymentMethod.DoesNotExist:
                pass

        # Try to extract UTR from screenshot before creating the request
        extracted_utr = None
        if TESSERACT_AVAILABLE:
            try:
                # Set tesseract path - check both common locations
                import os
                tesseract_path = '/usr/bin/tesseract'
                if not os.path.exists(tesseract_path):
                    tesseract_path = getattr(settings, 'TESSERACT_CMD', '/opt/homebrew/bin/tesseract')
                
                pytesseract.pytesseract.tesseract_cmd = tesseract_path
                logger.info(f"Using tesseract at: {tesseract_path}")
                
                # Open image from the uploaded file
                # Reset file pointer to beginning just in case
                screenshot.seek(0)
                img = Image.open(screenshot)
                # Convert to grayscale for better OCR
                img = img.convert('L')
                
                # Use custom config for better digit recognition
                # Try multiple PSM modes if one fails
                text = pytesseract.image_to_string(img, config=r'--oem 3 --psm 6')
                
                # If text is very short, try PSM 11 (sparse text)
                if len(text.strip()) < 20:
                    text += "\n" + pytesseract.image_to_string(img, config=r'--oem 3 --psm 11')
                
                # If still short, try PSM 3 (default)
                if len(text.strip()) < 20:
                    text += "\n" + pytesseract.image_to_string(img, config=r'--oem 3 --psm 3')

                # Clean text: remove extra spaces but keep structure
                clean_text = ' '.join(text.split())
                logger.info(f"OCR Extracted Text (cleaned): {clean_text[:500]}")
                
                # Extract UTR using regex - try multiple patterns
                # 1. Standard 12-digit UTR (most common for IMPS/UPI)
                # Look for 12 digits that might have spaces or dots between them
                utr_match = re.search(r'(?:\b|\D)(\d{12})(?:\b|\D)', clean_text)
                if utr_match:
                    extracted_utr = utr_match.group(1)
                    logger.info(f"Found 12-digit UTR: {extracted_utr}")
                
                # 2. Look for patterns like "UTR: 123456789012" or "Ref No: 123456789012"
                if not extracted_utr:
                    # More flexible regex for keywords
                    keyword_match = re.search(r'(?:UTR|Ref|Transaction|Ref\s*No|TXN)[:\s\-\.]*([A-Z0-9]{10,22})', clean_text, re.IGNORECASE)
                    if keyword_match:
                        extracted_utr = keyword_match.group(1)
                        logger.info(f"Found keyword-based UTR: {extracted_utr}")
                
                # 3. PhonePe specific: T followed by many digits
                if not extracted_utr:
                    phonepe_match = re.search(r'\b(T\d{18,24})\b', clean_text)
                    if phonepe_match:
                        extracted_utr = phonepe_match.group(1)
                        logger.info(f"Found PhonePe ID: {extracted_utr}")

                # 4. Google Pay / GPay specific: often starts with "CIC" or similar or just 12 digits
                if not extracted_utr:
                    gpay_match = re.search(r'\b(\d{4}\s*\d{4}\s*\d{4})\b', clean_text)
                    if gpay_match:
                        extracted_utr = gpay_match.group(1).replace(' ', '')
                        logger.info(f"Found GPay style 12-digit: {extracted_utr}")

                if extracted_utr:
                    logger.info(f"Auto-extracted UTR {extracted_utr} from screenshot for user {request.user.username}")
                else:
                    logger.warning(f"Could not find UTR in extracted text for user {request.user.username}")
            except Exception as ocr_err:
                logger.error(f"Failed to auto-extract UTR for user {request.user.username}: {ocr_err}")
                import traceback
                logger.error(traceback.format_exc())
            finally:
                # Reset file pointer again for saving
                screenshot.seek(0)

        deposit = DepositRequest.objects.create(
            user=request.user,
            amount=amount,
            screenshot=screenshot,
            payment_method=payment_method,
            status='PENDING',
            payment_reference=extracted_utr if extracted_utr else ''
        )
        logger.info(f"Deposit request created: ID {deposit.id} for user {request.user.username}, amount: {amount}, extracted_utr: {extracted_utr}")
    except Exception as e:
        logger.exception(f"Unexpected error creating deposit request for user {request.user.username}: {e}")
        import traceback
        error_details = str(e)
        if hasattr(e, '__class__'):
            error_type = e.__class__.__name__
        else:
            error_type = 'UnknownError'
        
        # Return user-friendly error message
        if 'InvalidOperation' in error_type or 'decimal' in error_details.lower():
            return Response({
                'error': f'Invalid amount value: {amount_raw}. Please provide a valid number with up to 2 decimal places.',
                'details': error_details
            }, status=status.HTTP_400_BAD_REQUEST)
        else:
            return Response({
                'error': 'Failed to create deposit request. Please check your input and try again.',
                'details': error_details
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    notify_user(request.user, f"Your deposit request of ₹{amount} has been submitted and is pending admin approval.")
    serializer = DepositRequestSerializer(deposit, context={'request': request})
    return Response(serializer.data, status=status.HTTP_201_CREATED)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def submit_utr(request):
    """Submit a UTR for a deposit request"""
    amount_raw = request.data.get('amount')
    utr = request.data.get('utr', '').strip()
    
    logger.info(f"UTR submission attempt for user {request.user.username}, amount: {amount_raw}, UTR: {utr}")
    
    if not utr:
        return Response({'error': 'UTR is required'}, status=status.HTTP_400_BAD_REQUEST)
        
    try:
        amount = _parse_amount(amount_raw)
    except ValueError as exc:
        return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    if amount < 100:
        return Response({'error': 'Minimum deposit amount is ₹100'}, status=status.HTTP_400_BAD_REQUEST)

    # Check for existing pending deposit request
    existing_pending = DepositRequest.objects.filter(user=request.user, status='PENDING').exists()
    if existing_pending:
        return Response({
            'error': 'You already have a pending deposit request. Please wait for it to be approved or rejected before sending another.'
        }, status=status.HTTP_400_BAD_REQUEST)

    # Create deposit request with PENDING status and UTR (no screenshot)
    try:
        payment_method_id = request.data.get('payment_method_id')
        payment_method = None
        if payment_method_id:
            try:
                payment_method = PaymentMethod.objects.get(id=payment_method_id)
            except PaymentMethod.DoesNotExist:
                pass

        deposit = DepositRequest.objects.create(
            user=request.user,
            amount=amount,
            payment_reference=utr,
            payment_method=payment_method,
            status='PENDING',
        )
        logger.info(f"Deposit request (UTR) created: ID {deposit.id} for user {request.user.username}, amount: {amount}, UTR: {utr}")
    except Exception as e:
        logger.exception(f"Unexpected error creating deposit request for user {request.user.username}: {e}")
        return Response({'error': 'Failed to create deposit request'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    notify_user(request.user, f"Your deposit request of ₹{amount} with UTR {utr} has been submitted and is pending admin approval.")
    serializer = DepositRequestSerializer(deposit, context={'request': request})
    return Response(serializer.data, status=status.HTTP_201_CREATED)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def my_deposit_requests(request):
    """List the authenticated user's deposit requests"""
    logger.info(f"Fetching deposit requests for user: {request.user.username} (ID: {request.user.id})")
    deposits = DepositRequest.objects.filter(user=request.user).order_by('-created_at')
    serializer = DepositRequestSerializer(deposits, many=True, context={'request': request})
    return Response(serializer.data)


@api_view(['GET'])
@permission_classes([IsAdminUser])
def pending_deposit_requests(request):
    """Admin: list all pending deposit requests"""
    logger.info(f"Admin {request.user.username} fetching all pending deposit requests")
    deposits = DepositRequest.objects.filter(status='PENDING').select_related('user').order_by('created_at')
    serializer = DepositRequestAdminSerializer(deposits, many=True, context={'request': request})
    return Response(serializer.data)


@api_view(['POST'])
@permission_classes([IsAdminUser])
def approve_deposit_request(request, pk):
    """Admin approves a pending deposit request"""
    import logging
    logger = logging.getLogger(__name__)
    import decimal
    note = request.data.get('note', '')
    logger.info(f"Admin {request.user.username} attempting to approve deposit {pk}")
    try:
        with db_transaction.atomic():
            deposit = DepositRequest.objects.select_for_update().get(pk=pk)
            if deposit.status != 'PENDING':
                logger.warning(f"Admin {request.user.username} failed to approve deposit {pk}: Already processed (Status: {deposit.status})")
                return Response({'error': 'Deposit request already processed'}, status=status.HTTP_400_BAD_REQUEST)

            wallet, _ = Wallet.objects.get_or_create(user=deposit.user)
            wallet = Wallet.objects.select_for_update().get(pk=wallet.pk)
            balance_before = wallet.balance
            # Deposit money needs to be rotated 1 time
            wallet.add(deposit.amount, is_bonus=True)
            wallet.save()

            # Update Redis balance (CRITICAL for Redis-First betting)
            if redis_client:
                try:
                    redis_client.set(f"user_balance:{deposit.user.id}", str(wallet.balance), ex=86400)
                except: pass

            Transaction.objects.create(
                user=deposit.user,
                transaction_type='DEPOSIT',
                amount=deposit.amount,
                balance_before=balance_before,
                balance_after=wallet.balance,
                description=f"Manual deposit #{deposit.id}",
            )

            deposit.status = 'APPROVED'
            deposit.admin_note = note
            deposit.processed_by = request.user
            deposit.processed_at = timezone.now()
            deposit.save()
            logger.info(f"Deposit {pk} approved by admin {request.user.username}. User: {deposit.user.username}, Amount: {deposit.amount}")

            # Check for referral bonus
            if deposit.user.referred_by:
                from .referral_logic import calculate_referral_bonus
                bonus_amount = calculate_referral_bonus(deposit.amount)
                
                if bonus_amount > 0:
                    referrer = deposit.user.referred_by
                    referrer_wallet, _ = Wallet.objects.get_or_create(user=referrer)
                    referrer_wallet = Wallet.objects.select_for_update().get(pk=referrer_wallet.pk)
                    
                    ref_balance_before = referrer_wallet.balance
                    # Referral bonus needs to be rotated 1 time
                    referrer_wallet.add(bonus_amount, is_bonus=True)
                    referrer_wallet.save()

                    # Update Redis balance for referrer
                    if redis_client:
                        try:
                            redis_client.set(f"user_balance:{referrer.id}", str(referrer_wallet.balance), ex=86400)
                        except: pass
                    
                    Transaction.objects.create(
                        user=referrer,
                        transaction_type='REFERRAL_BONUS',
                        amount=bonus_amount,
                        balance_before=ref_balance_before,
                        balance_after=referrer_wallet.balance,
                        description=f"Referral bonus from {deposit.user.username}'s deposit of ₹{deposit.amount}",
                    )
                    logger.info(f"Referral bonus of ₹{bonus_amount} granted to {referrer.username} for {deposit.user.username}'s deposit")
                    
                    # Check and award milestone bonus if applicable
                    from .referral_logic import check_and_award_milestone_bonus
                    milestone_awarded = check_and_award_milestone_bonus(referrer)
                    if milestone_awarded:
                        logger.info(f"Milestone bonus awarded to {referrer.username}")
    except DepositRequest.DoesNotExist:
        logger.error(f"Admin {request.user.username} failed to approve deposit {pk}: Not found")
        return Response({'error': 'Deposit request not found'}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        logger.exception(f"Unexpected error approving deposit {pk} by admin {request.user.username}: {e}")
        return Response({'error': 'Internal server error'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    notify_user(deposit.user, f"Your deposit of ₹{deposit.amount} has been approved.")
    serializer = DepositRequestAdminSerializer(deposit, context={'request': request})
    return Response(serializer.data)


@api_view(['POST'])
@permission_classes([IsAdminUser])
def reject_deposit_request(request, pk):
    """Admin rejects a pending deposit request"""
    note = request.data.get('note', '')
    logger.info(f"Admin {request.user.username} attempting to reject deposit {pk}")
    try:
        with db_transaction.atomic():
            deposit = DepositRequest.objects.select_for_update().get(pk=pk)
            if deposit.status != 'PENDING':
                logger.warning(f"Admin {request.user.username} failed to reject deposit {pk}: Already processed (Status: {deposit.status})")
                return Response({'error': 'Deposit request already processed'}, status=status.HTTP_400_BAD_REQUEST)

            deposit.status = 'REJECTED'
            deposit.admin_note = note
            deposit.processed_by = request.user
            deposit.processed_at = timezone.now()
            deposit.save()
            logger.info(f"Deposit {pk} rejected by admin {request.user.username}. User: {deposit.user.username}, Amount: {deposit.amount}, Note: {note}")
    except DepositRequest.DoesNotExist:
        logger.error(f"Admin {request.user.username} failed to reject deposit {pk}: Not found")
        return Response({'error': 'Deposit request not found'}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        logger.exception(f"Unexpected error rejecting deposit {pk} by admin {request.user.username}: {e}")
        return Response({'error': 'Internal server error'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    notify_user(deposit.user, f"Your deposit of ₹{deposit.amount} was rejected. {note}".strip())
    serializer = DepositRequestAdminSerializer(deposit, context={'request': request})
    return Response(serializer.data)


# Withdraw functionality

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def initiate_withdraw(request):
    """Create a withdraw request with PENDING status - requires admin approval"""
    amount_raw = request.data.get('amount')
    withdrawal_method = request.data.get('withdrawal_method', '').strip()
    withdrawal_details = request.data.get('withdrawal_details', '').strip()

    logger.info(f"Withdrawal initiation attempt for user {request.user.username} (ID: {request.user.id}), amount: {amount_raw}, method: {withdrawal_method}")

    if not withdrawal_method:
        logger.warning(f"Withdrawal failed for user {request.user.username}: Missing method")
        return Response({'error': 'Withdrawal method is required'}, status=status.HTTP_400_BAD_REQUEST)

    if not withdrawal_details:
        logger.warning(f"Withdrawal failed for user {request.user.username}: Missing details")
        return Response({'error': 'Withdrawal details are required'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        amount = _parse_amount(amount_raw)
    except ValueError as exc:
        logger.warning(f"Withdrawal failed for user {request.user.username}: Invalid amount {amount_raw} - {exc}")
        return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    if amount < 200:
        logger.warning(f"Withdrawal failed for user {request.user.username}: Amount {amount} below minimum ₹200")
        return Response({'error': 'Minimum withdrawal amount is ₹200'}, status=status.HTTP_400_BAD_REQUEST)

    # Check if user has sufficient withdrawable balance
    wallet, created = Wallet.objects.get_or_create(user=request.user)
    withdrawable = wallet.withdrawable_balance
    
    # Check Redis balance and exposure for real-time validation
    from game.views import redis_client
    if redis_client:
        try:
            redis_balance = float(redis_client.get(f"user_balance:{request.user.id}") or 0)
            # Get current round exposure
            from game.models import GameRound
            current_round = GameRound.objects.filter(status='OPEN').first()
            exposure = 0
            if current_round:
                exposure = float(redis_client.hget(f"round_exposure:{current_round.id}", request.user.id) or 0)
            
            available_realtime = redis_balance - exposure
            if amount > available_realtime:
                logger.warning(f"Withdrawal failed for user {request.user.username}: Insufficient real-time balance (Redis: {redis_balance}, Exposure: {exposure}, Available: {available_realtime}, Requested: {amount})")
                return Response({
                    'error': f'Insufficient available balance. Your current balance is ₹{redis_balance:.2f} and you have ₹{exposure:.2f} in active bets. Available for withdrawal: ₹{max(0, available_realtime):.2f}.'
                }, status=status.HTTP_400_BAD_REQUEST)
        except Exception as re_err:
            logger.error(f"Error checking real-time balance for withdrawal: {re_err}")

    if withdrawable < amount:
        logger.warning(f"Withdrawal failed for user {request.user.username}: Insufficient withdrawable balance (Withdrawable: {withdrawable}, Requested: {amount}, Total Balance: {wallet.balance})")
        return Response({
            'error': f'Insufficient withdrawable balance. You have ₹{withdrawable} available for withdrawal (Total balance: ₹{wallet.balance}). You must rotate deposited/bonus money by betting it at least once.'
        }, status=status.HTTP_400_BAD_REQUEST)

    # Check for existing pending withdraw request
    existing_pending = WithdrawRequest.objects.filter(
        user=request.user,
        status='PENDING'
    ).exists()

    if existing_pending:
        logger.warning(f"Withdrawal failed for user {request.user.username}: Already has a pending request")
        return Response({
            'error': 'You already have a pending withdraw request. Please wait for it to be processed.'
        }, status=status.HTTP_400_BAD_REQUEST)

    # Create withdraw request with PENDING status
    try:
        from game.views import redis_client
        from django.db import transaction
        
        with transaction.atomic():
            withdraw = WithdrawRequest.objects.create(
                user=request.user,
                amount=amount,
                withdrawal_method=withdrawal_method,
                withdrawal_details=withdrawal_details,
                status='PENDING',
            )
            
            # 1️⃣ Deduct from Redis first (atomic)
            if redis_client:
                try:
                    # Deduct from Redis balance immediately
                    redis_client.incrbyfloat(f"user_balance:{request.user.id}", -float(amount))
                    
                    # 2️⃣ Queue withdraw event to worker using Redis Stream
                    withdraw_event = {
                        'type': 'initiate_withdraw',
                        'user_id': str(request.user.id),
                        'withdraw_id': str(withdraw.id),
                        'amount': str(amount),
                        'round_id': 'WITHDRAW',
                        'timestamp': timezone.now().isoformat()
                    }
                    redis_client.xadd('bet_stream', withdraw_event, maxlen=10000)
                    logger.info(f"Withdrawal request created and queued: ID {withdraw.id} for user {request.user.id}, amount: {amount}")
                except Exception as re_err:
                    logger.error(f"Failed to process Redis-First withdrawal initiation for user {request.user.id}: {re_err}")
                    # Fallback: If Redis fails, we still proceed with DB update in worker or here
                    # For now, we allow the transaction to complete and the worker will handle DB
            
        notify_user(request.user, f"Your withdraw request of ₹{amount} has been submitted. Funds have been deducted from your balance and are pending admin approval.")
        
    except Exception as e:
        logger.exception(f"Unexpected error creating withdrawal request for user {request.user.username}: {e}")
        import traceback
        error_details = str(e)
        if hasattr(e, '__class__'):
            error_type = e.__class__.__name__
        else:
            error_type = 'UnknownError'

        # Return user-friendly error message
        if 'InvalidOperation' in error_type or 'decimal' in error_details.lower():
            return Response({
                'error': f'Invalid amount value: {amount_raw}. Please provide a valid number with up to 2 decimal places.',
                'details': error_details
            }, status=status.HTTP_400_BAD_REQUEST)
        else:
            return Response({
                'error': 'Failed to create withdraw request. Please check your input and try again.',
                'details': error_details
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    notify_user(request.user, f"Your withdraw request of ₹{amount} has been submitted and is pending admin approval.")
    serializer = WithdrawRequestSerializer(withdraw, context={'request': request})
    return Response(serializer.data, status=status.HTTP_201_CREATED)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def my_withdraw_requests(request):
    """List the authenticated user's withdraw requests"""
    logger.info(f"Fetching withdrawal requests for user: {request.user.username} (ID: {request.user.id})")
    withdraws = WithdrawRequest.objects.filter(user=request.user).order_by('-created_at')
    serializer = WithdrawRequestSerializer(withdraws, many=True, context={'request': request})
    return Response(serializer.data)


@api_view(['GET'])
@permission_classes([AllowAny])
def get_payment_methods(request):
    """List active payment methods for deposits"""
    logger.info("Fetching active payment methods")
    methods = PaymentMethod.objects.filter(is_active=True)
    serializer = PaymentMethodSerializer(methods, many=True, context={'request': request})
    return Response(serializer.data)


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def my_bank_details(request):
    """Get or create user bank details"""
    if request.method == 'GET':
        logger.info(f"Fetching bank details for user: {request.user.username} (ID: {request.user.id})")
        details = UserBankDetail.objects.filter(user=request.user)
        serializer = UserBankDetailSerializer(details, many=True)
        return Response(serializer.data)
    
    elif request.method == 'POST':
        logger.info(f"Creating bank detail for user: {request.user.username} (ID: {request.user.id})")
        serializer = UserBankDetailSerializer(data=request.data)
        if serializer.is_valid():
            # If setting as default, unset others
            if serializer.validated_data.get('is_default'):
                UserBankDetail.objects.filter(user=request.user).update(is_default=False)
            
            serializer.save(user=request.user)
            logger.info(f"Bank detail created successfully for user: {request.user.username}")
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        logger.warning(f"Bank detail creation failed for user {request.user.username}: {serializer.errors}")
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['DELETE', 'PUT'])
@permission_classes([IsAuthenticated])
def bank_detail_action(request, pk):
    """Update or delete a specific bank detail"""
    detail = get_object_or_404(UserBankDetail, pk=pk, user=request.user)
    
    if request.method == 'DELETE':
        logger.info(f"Deleting bank detail {pk} for user: {request.user.username}")
        detail.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
    
    elif request.method == 'PUT':
        logger.info(f"Updating bank detail {pk} for user: {request.user.username}")
        serializer = UserBankDetailSerializer(detail, data=request.data, partial=True)
        if serializer.is_valid():
            if serializer.validated_data.get('is_default'):
                UserBankDetail.objects.filter(user=request.user).exclude(pk=pk).update(is_default=False)
            serializer.save()
            logger.info(f"Bank detail {pk} updated successfully for user: {request.user.username}")
            return Response(serializer.data)
        logger.warning(f"Bank detail {pk} update failed for user {request.user.username}: {serializer.errors}")
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def daily_reward(request):
    """Get daily reward status and spin the wheel"""
    user = request.user
    today = timezone.now().date()

    if request.method == 'GET':
        # Check if user has already claimed reward today
        existing_reward = DailyReward.objects.filter(
            user=user,
            reward_date=today
        ).first()

        if existing_reward:
            return Response({
                'claimed': True,
                'reward': {
                    'amount': existing_reward.reward_amount,
                    'type': existing_reward.reward_type
                },
                'message': 'Daily reward already claimed today'
            })

        return Response({
            'claimed': False,
            'message': 'Ready to spin for daily reward'
        })

    elif request.method == 'POST':
        # Check if user has already claimed reward today
        existing_reward = DailyReward.objects.filter(
            user=user,
            reward_date=today
        ).first()

        if existing_reward:
            return Response({
                'error': 'Daily reward already claimed today'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Define reward probabilities and amounts
        rewards = [
            {'amount': 1000, 'type': 'MONEY', 'probability': 1},
            {'amount': 500, 'type': 'MONEY', 'probability': 2},
            {'amount': 100, 'type': 'MONEY', 'probability': 5},
            {'amount': 50, 'type': 'MONEY', 'probability': 10},
            {'amount': 30, 'type': 'MONEY', 'probability': 20},
            {'amount': 20, 'type': 'MONEY', 'probability': 30},
            {'amount': 10, 'type': 'MONEY', 'probability': 20},
            {'amount': 5, 'type': 'MONEY', 'probability': 10},
            {'amount': 0, 'type': 'TRY_AGAIN', 'probability': 2},
        ]

        # Calculate total probability
        total_probability = sum(reward['probability'] for reward in rewards)

        # Generate random number
        import random
        random_value = random.randint(1, total_probability)

        # Select reward based on probability
        cumulative_probability = 0
        selected_reward = None

        for reward in rewards:
            cumulative_probability += reward['probability']
            if random_value <= cumulative_probability:
                selected_reward = reward
                break

        if not selected_reward:
            selected_reward = rewards[-1]  # Default to last reward

        # Create the daily reward record
        daily_reward = DailyReward.objects.create(
            user=user,
            reward_amount=Decimal(str(selected_reward['amount'])),
            reward_type=selected_reward['type'],
            reward_date=today
        )

        # If it's a money reward, add to wallet
        if selected_reward['type'] == 'MONEY' and selected_reward['amount'] > 0:
            try:
                reward_amount = Decimal(str(selected_reward['amount']))
                wallet = user.wallet
                
                # 1️⃣ Update DB atomically
                # We use F() expression for safety
                Wallet.objects.filter(pk=wallet.pk).update(balance=F('balance') + reward_amount)
                wallet.refresh_from_db()

                # 2️⃣ Update Redis atomically using INCRBYFLOAT
                if redis_client:
                    try:
                        redis_client.incrbyfloat(f"user_balance:{user.id}", float(reward_amount))
                        logger.info(f"Updated Redis balance for user {user.id} after daily reward: {reward_amount}")
                    except Exception as re_err:
                        logger.error(f"Failed to update Redis balance for user {user.id} after daily reward: {re_err}")

                # 3️⃣ Create transaction record
                Transaction.objects.create(
                    user=user,
                    transaction_type='DEPOSIT',
                    amount=reward_amount,
                    balance_before=wallet.balance - reward_amount,
                    balance_after=wallet.balance,
                    description=f'Daily Reward - ₹{selected_reward["amount"]}'
                )
                logger.info(f"Daily reward ₹{selected_reward['amount']} added to wallet for user: {user.username}")
            except Exception as e:
                logger.error(f"Failed to add daily reward to wallet for user {user.username}: {str(e)}")
                return Response({
                    'error': 'Failed to process reward'
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response({
            'reward': {
                'amount': selected_reward['amount'],
                'type': selected_reward['type']
            },
            'message': f'Congratulations! You won ₹{selected_reward["amount"]}' if selected_reward['type'] == 'MONEY' else 'Better luck next time! Try again tomorrow.'
        })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def daily_reward_history(request):
    """Get user's daily reward history"""
    user = request.user
    rewards = DailyReward.objects.filter(user=user).order_by('-reward_date')[:30]  # Last 30 days

    reward_data = []
    for reward in rewards:
        reward_data.append({
            'date': reward.reward_date,
            'amount': reward.reward_amount,
            'type': reward.reward_type,
            'claimed_at': reward.claimed_at
        })

    return Response({
        'rewards': reward_data
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def referral_data(request):
    """Get referral statistics and milestone information"""
    from django.db.models import Count, Sum, Q
    from .referral_logic import calculate_milestone_bonus, get_next_milestone
    
    user = request.user
    
    # Count total referrals (users who signed up using this user's referral code)
    total_referrals = User.objects.filter(referred_by=user).count()
    
    # Count active referrals (referrals who have made at least one deposit)
    active_referrals = User.objects.filter(
        referred_by=user,
        deposit_requests__status='APPROVED'
    ).distinct().count()
    
    # Calculate total earnings from referral bonuses
    referral_transactions = Transaction.objects.filter(
        user=user,
        transaction_type='REFERRAL_BONUS'
    )
    total_earnings = referral_transactions.aggregate(Sum('amount'))['amount__sum'] or Decimal('0')
    
    # Get current milestone bonus
    current_milestone_bonus = calculate_milestone_bonus(total_referrals)
    
    # Get next milestone info
    next_milestone_info = get_next_milestone(total_referrals)
    
    # Get list of achieved milestones
    milestones = [
        {'count': 3, 'bonus': 500, 'achieved': total_referrals >= 3},
        {'count': 5, 'bonus': 1000, 'achieved': total_referrals >= 5},
        {'count': 10, 'bonus': 2500, 'achieved': total_referrals >= 10},
        {'count': 20, 'bonus': 5000, 'achieved': total_referrals >= 20},
        {'count': 50, 'bonus': 15000, 'achieved': total_referrals >= 50},
        {'count': 100, 'bonus': 50000, 'achieved': total_referrals >= 100},
    ]
    
    # Get recent referral bonuses (last 10)
    recent_bonuses = referral_transactions.order_by('-created_at')[:10].values(
        'amount', 'description', 'created_at'
    )
    
    return Response({
        'referral_code': user.referral_code or '',
        'total_referrals': total_referrals,
        'active_referrals': active_referrals,
        'total_earnings': str(total_earnings),
        'current_milestone_bonus': str(current_milestone_bonus),
        'next_milestone': next_milestone_info,
        'milestones': milestones,
        'recent_bonuses': list(recent_bonuses)
    })


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def lucky_draw(request):
    """Get lucky draw status and spin the wheel based on bank transfer deposits"""
    user = request.user
    
    if request.method == 'GET':
        # Find the most recent approved bank transfer deposit of ₹2000+ that hasn't been used for lucky draw
        recent_deposit = DepositRequest.objects.filter(
            user=user,
            status='APPROVED',
            amount__gte=Decimal('2000.00'),  # Minimum ₹2000 deposit required
            payment_reference__isnull=False  # Bank transfer has UTR/payment reference
        ).exclude(
            lucky_draws__isnull=False  # Exclude deposits that already have lucky draw
        ).order_by('-processed_at').first()
        
        # Check if user has already claimed lucky draw for this deposit
        if recent_deposit:
            existing_lucky_draw = LuckyDraw.objects.filter(
                user=user,
                deposit_request=recent_deposit
            ).first()
            
            if existing_lucky_draw:
                return Response({
                    'claimed': True,
                    'reward': {
                        'amount': existing_lucky_draw.reward_amount,
                    },
                    'deposit_amount': float(existing_lucky_draw.deposit_amount),
                    'message': 'Lucky draw already claimed for this deposit'
                })
            
            return Response({
                'claimed': False,
                'deposit_amount': float(recent_deposit.amount),
                'message': 'Ready to spin for lucky draw'
            })
        
        return Response({
            'claimed': False,
            'deposit_amount': None,
            'message': 'No eligible deposit of ₹2000 or more found. Deposit ₹2000+ to unlock lucky draw!'
        })

    elif request.method == 'POST':
        # Find the most recent approved bank transfer deposit of ₹2000+
        recent_deposit = DepositRequest.objects.filter(
            user=user,
            status='APPROVED',
            amount__gte=Decimal('2000.00'),  # Minimum ₹2000 deposit required
            payment_reference__isnull=False
        ).exclude(
            lucky_draws__isnull=False
        ).order_by('-processed_at').first()
        
        if not recent_deposit:
            return Response({
                'error': 'No eligible deposit of ₹2000 or more found'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Check if already claimed
        existing_lucky_draw = LuckyDraw.objects.filter(
            user=user,
            deposit_request=recent_deposit
        ).first()
        
        if existing_lucky_draw:
            return Response({
                'error': 'Lucky draw already claimed for this deposit'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Define reward amounts: 100, 300, 500, 1000, 5000, 10000
        # Probability distribution (can be adjusted)
        rewards = [
            {'amount': 10000, 'probability': 1},
            {'amount': 5000, 'probability': 2},
            {'amount': 1000, 'probability': 5},
            {'amount': 500, 'probability': 10},
            {'amount': 300, 'probability': 20},
            {'amount': 100, 'probability': 62},  # Higher probability for smaller amounts
        ]
        
        # Calculate total probability
        total_probability = sum(reward['probability'] for reward in rewards)
        
        # Generate random number
        import random
        random_value = random.randint(1, total_probability)
        
        # Select reward based on probability
        cumulative_probability = 0
        selected_reward = None
        
        for reward in rewards:
            cumulative_probability += reward['probability']
            if random_value <= cumulative_probability:
                selected_reward = reward
                break
        
        if not selected_reward:
            selected_reward = rewards[-1]  # Default to last reward
        
        # Create the lucky draw record
        lucky_draw = LuckyDraw.objects.create(
            user=user,
            deposit_request=recent_deposit,
            reward_amount=Decimal(str(selected_reward['amount'])),
            deposit_amount=recent_deposit.amount
        )
        
        # Add reward to wallet
        try:
            wallet = user.wallet
            balance_before = wallet.balance
            wallet.add(Decimal(str(selected_reward['amount'])))
            balance_after = wallet.balance
            
            # Create transaction record
            Transaction.objects.create(
                user=user,
                transaction_type='DEPOSIT',
                amount=Decimal(str(selected_reward['amount'])),
                balance_before=balance_before,
                balance_after=balance_after,
                description=f'Lucky Draw Reward - ₹{selected_reward["amount"]} (from ₹{recent_deposit.amount} deposit)'
            )
            logger.info(f"Lucky draw reward ₹{selected_reward['amount']} added to wallet for user: {user.username}")
        except Exception as e:
            logger.error(f"Failed to add lucky draw reward to wallet for user {user.username}: {str(e)}")
            return Response({
                'error': 'Failed to process reward'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        return Response({
            'lucky_draw': {
                'amount': selected_reward['amount'],
            },
            'message': f'Congratulations! You won ₹{selected_reward["amount"]}'
        })
