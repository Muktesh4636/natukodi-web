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
from django.db.models import Q
import uuid
import re
import logging

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


@api_view(['POST'])
@authentication_classes([])  # Disable authentication for registration
@permission_classes([AllowAny])
@csrf_exempt
def register(request):
    """User registration with OTP verification"""
    try:
        phone_number = request.data.get('phone_number', '').strip()
        otp_code = request.data.get('otp_code', '').strip()
        
        # Normalize OTP code (remove any whitespace, ensure it's a string)
        if otp_code:
            otp_code = str(otp_code).strip().replace(" ", "").replace("-", "")
            logger.info(f"Registration OTP verification: phone={phone_number}, otp_code={otp_code}")
        
        # Verify OTP if provided
        if otp_code:
            from .sms_service import sms_service
            success, message, verified_user = sms_service.verify_otp(phone_number, otp_code, purpose='SIGNUP')
            if not success:
                return Response(
                    {'error': message},
                    status=status.HTTP_400_BAD_REQUEST
                )
            # For SIGNUP, verified_user can be None (user doesn't exist yet)
        
        logger.info(f"Registration attempt for username: {request.data.get('username')}")
        serializer = UserRegistrationSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            logger.info(f"User registered successfully: {user.username} (ID: {user.id})")
            
            # Credit spin balance if provided
            spin_balance = request.data.get('spin_balance')
            if spin_balance:
                try:
                    from decimal import Decimal
                    amount = Decimal(str(spin_balance))
                    if amount > 0:
                        from .models import Wallet, Transaction
                        wallet, _ = Wallet.objects.get_or_create(user=user)
                        balance_before = wallet.balance
                        wallet.balance += amount
                        wallet.save()
                        
                        Transaction.objects.create(
                            user=user,
                            transaction_type='REFERRAL_BONUS', # Use a suitable type or add a new one
                            amount=amount,
                            balance_before=balance_before,
                            balance_after=wallet.balance,
                            description=f"Initial spin reward credited upon registration"
                        )
                        logger.info(f"Credited spin balance ₹{amount} to user {user.username}")
                except Exception as e:
                    logger.error(f"Failed to credit spin balance: {str(e)}")

            refresh = RefreshToken.for_user(user)
            return Response({
                'user': UserSerializer(user).data,
                'refresh': str(refresh),
                'access': str(refresh.access_token),
            }, status=status.HTTP_201_CREATED)
        logger.warning(f"Registration failed for username: {request.data.get('username')} - Errors: {serializer.errors}")
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        logger.exception(f"Error in register: {str(e)}")
        return Response(
            {'error': f'Registration failed: {str(e)}'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@authentication_classes([])  # Disable authentication for login
@permission_classes([AllowAny])
@csrf_exempt
def login(request):
    """User login"""
    try:
        # Safely get request data
        logger.info(f"Request data: {getattr(request, 'data', 'No data attribute')} | Content-Type: {request.content_type}")
        if hasattr(request, 'data'):
            username = request.data.get('username', '').strip()
            password = request.data.get('password', '').strip()
        else:
            # Fallback for non-DRF requests
            username = request.POST.get('username', '').strip()
            password = request.POST.get('password', '').strip()

        logger.info(f"Login attempt for username: {username}")

        if not username or not password:
            logger.warning(f"Login failed: Missing credentials for username: {username}")
            return Response(
                {'error': 'Username and password required'}, 
                status=status.HTTP_400_BAD_REQUEST
            )

        # Authenticate user
        try:
            # Support login with either username or phone number
            user_obj = User.objects.filter(Q(username=username) | Q(phone_number=username)).first()
            if user_obj:
                # Authenticate with the actual username found
                user = authenticate(request=request, username=user_obj.username, password=password)
            else:
                user = None
        except Exception as auth_error:
            logger.exception(f"Authentication error for username {username}: {auth_error}")
            return Response(
                {'error': 'Authentication failed', 'detail': str(auth_error)}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        if not user:
            logger.warning(f"Login failed: Invalid credentials for username: {username}")
            return Response(
                {'error': 'Invalid credentials'}, 
                status=status.HTTP_401_UNAUTHORIZED
            )

        # Check if user is active
        if not user.is_active:
            logger.warning(f"Login failed: Account disabled for user: {user.username} (ID: {user.id})")
            return Response(
                {'error': 'User account is disabled'}, 
                status=status.HTTP_403_FORBIDDEN
            )

        # Generate JWT tokens
        try:
            refresh = RefreshToken.for_user(user)
            access_token = str(refresh.access_token)
            refresh_token = str(refresh)
        except Exception as token_error:
            logger.exception(f"Token generation error for user {user.username}: {token_error}")
            return Response(
                {'error': 'Failed to generate tokens', 'detail': str(token_error)}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        logger.info(f"User logged in successfully: {user.username} (ID: {user.id})")
        # Serialize user data
        try:
            user_data = UserSerializer(user).data
        except Exception as serializer_error:
            logger.exception(f"User serialization error for user {user.username}: {serializer_error}")
            # Return minimal user data if serializer fails
            user_data = {
                'id': user.id,
                'username': user.username,
                'email': getattr(user, 'email', ''),
                'is_staff': getattr(user, 'is_staff', False),
            }

        return Response({
            'user': user_data,
            'refresh': refresh_token,
            'access': access_token,
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
    """Send OTP to phone number for signup or login"""
    try:
        # Get phone_number from request.data (DRF automatically parses JSON)
        phone_number = ''
        purpose = 'SIGNUP'
        
        try:
            # Try to get from request.data (DRF parsed data)
            if hasattr(request, 'data'):
                data = request.data
                if isinstance(data, dict):
                    phone_number = str(data.get('phone_number', '') or '').strip()
                    purpose = str(data.get('purpose', 'SIGNUP') or 'SIGNUP').upper()
                elif hasattr(data, 'get'):
                    phone_number = str(data.get('phone_number', '') or '').strip()
                    purpose = str(data.get('purpose', 'SIGNUP') or 'SIGNUP').upper()
        except Exception as e:
            logger.warning(f"Error reading request.data: {e}")
        
        # Fallback to POST if data is empty
        if not phone_number:
            try:
                if hasattr(request, 'POST'):
                    phone_number = str(request.POST.get('phone_number', '') or '').strip()
                    purpose = str(request.POST.get('purpose', 'SIGNUP') or 'SIGNUP').upper()
            except Exception as e:
                logger.warning(f"Error reading request.POST: {e}")
        
        # Fallback to parsing request.body directly
        if not phone_number:
            try:
                import json
                if hasattr(request, 'body') and request.body:
                    body_data = json.loads(request.body)
                    phone_number = str(body_data.get('phone_number', '') or '').strip()
                    purpose = str(body_data.get('purpose', 'SIGNUP') or 'SIGNUP').upper()
            except Exception as e:
                logger.warning(f"Error parsing request.body: {e}")

        if not purpose:
            purpose = 'SIGNUP'

        logger.info(f"send_otp: phone={phone_number}, purpose={purpose}")

        if not phone_number:
            logger.warning("Phone number is missing in request")
            return Response(
                {'error': 'Phone number is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # For LOGIN purpose, check if user exists
        if purpose == 'LOGIN':
            from .models import User
            user_exists = User.objects.filter(phone_number=phone_number).exists()
            if not user_exists:
                return Response(
                    {'error': 'Invalid phone number'},
                    status=status.HTTP_400_BAD_REQUEST
                )

        # Import SMS service
        from .sms_service import sms_service

        # Send OTP (allow for both SIGNUP and LOGIN)
        success, message, otp_id = sms_service.send_otp(phone_number, purpose=purpose)

        if success:
            return Response({
                'message': message,
                'otp_id': otp_id
            }, status=status.HTTP_200_OK)
        else:
            return Response(
                {'error': message},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    except Exception as e:
        logger.exception(f"Error in send_otp: {str(e)}")
        return Response(
            {'error': f'Internal server error: {str(e)}'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@authentication_classes([])
@permission_classes([AllowAny])
@csrf_exempt
def verify_otp_login(request):
    """Verify OTP and login user"""
    try:
        phone_number = request.data.get('phone_number', '').strip()
        otp_code = request.data.get('otp_code', '').strip()

        if not phone_number or not otp_code:
            return Response(
                {'error': 'Phone number and OTP code are required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Normalize OTP code (remove any whitespace, ensure it's a string)
        otp_code = str(otp_code).strip().replace(" ", "").replace("-", "")
        
        logger.info(f"Login OTP verification: phone={phone_number}, otp_code={otp_code}")

        # Import SMS service
        from .sms_service import sms_service

        # Verify OTP
        success, message, user = sms_service.verify_otp(phone_number, otp_code, purpose='LOGIN')

        if not success:
            return Response(
                {'error': message},
                status=status.HTTP_400_BAD_REQUEST
            )

        if not user:
            return Response(
                {'error': 'User not found'},
                status=status.HTTP_404_NOT_FOUND
            )

        # Check if user is active
        if not user.is_active:
            return Response(
                {'error': 'User account is disabled'},
                status=status.HTTP_403_FORBIDDEN
            )

        # Create JWT tokens
        refresh = RefreshToken.for_user(user)
        refresh_token = str(refresh)
        access_token = str(refresh.access_token)

        # Update last login
        user.last_login = timezone.now()
        user.save(update_fields=['last_login'])

        logger.info(f"OTP login successful for user: {user.username} (ID: {user.id})")

        # Prepare user data for response
        user_data = {
            'id': user.id,
            'username': user.username,
            'email': getattr(user, 'email', ''),
            'phone_number': getattr(user, 'phone_number', ''),
            'is_staff': getattr(user, 'is_staff', False),
        }

        return Response({
            'user': user_data,
            'refresh': refresh_token,
            'access': access_token,
            'message': 'Login successful'
        }, status=status.HTTP_200_OK)

    except Exception as e:
        logger.exception(f"Error in verify_otp_login: {str(e)}")
        return Response(
            {'error': 'Internal server error'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def profile(request):
    """Get or update user profile"""
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


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def wallet(request):
    """Get user wallet"""
    logger.info(f"Wallet balance check for user: {request.user.username} (ID: {request.user.id})")
    wallet, created = Wallet.objects.get_or_create(user=request.user)
    serializer = WalletSerializer(wallet)
    return Response(serializer.data)


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

    # Create deposit request with PENDING status - no wallet credit yet
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
            screenshot=screenshot,
            payment_method=payment_method,
            status='PENDING',
        )
        logger.info(f"Deposit request created: ID {deposit.id} for user {request.user.username}, amount: {amount}")
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
            wallet.balance = balance_before + deposit.amount
            wallet.save()

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
                    referrer_wallet.balance += bonus_amount
                    referrer_wallet.save()
                    
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

    # Check if user has sufficient balance
    wallet, created = Wallet.objects.get_or_create(user=request.user)
    if wallet.balance < amount:
        logger.warning(f"Withdrawal failed for user {request.user.username}: Insufficient balance (Balance: {wallet.balance}, Requested: {amount})")
        return Response({
            'error': f'Insufficient balance. You have ₹{wallet.balance}, but requested ₹{amount}'
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

    # Create withdraw request with PENDING status - no wallet debit yet
    try:
        withdraw = WithdrawRequest.objects.create(
            user=request.user,
            amount=amount,
            withdrawal_method=withdrawal_method,
            withdrawal_details=withdrawal_details,
            status='PENDING',
        )
        logger.info(f"Withdrawal request created: ID {withdraw.id} for user {request.user.username}, amount: {amount}")
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
            {'amount': 1000, 'type': 'MONEY', 'probability': 0},
            {'amount': 500, 'type': 'MONEY', 'probability': 0},
            {'amount': 100, 'type': 'MONEY', 'probability': 0},
            {'amount': 20, 'type': 'MONEY', 'probability': 100},   # TEMP: 100% chance for testing
            {'amount': 10, 'type': 'MONEY', 'probability': 0},
            {'amount': 5, 'type': 'MONEY', 'probability': 0},
            {'amount': 0, 'type': 'TRY_AGAIN', 'probability': 0},
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
            reward_amount=decimal.Decimal(str(selected_reward['amount'])),
            reward_type=selected_reward['type'],
            reward_date=today
        )

        # If it's a money reward, add to wallet
        if selected_reward['type'] == 'MONEY' and selected_reward['amount'] > 0:
            try:
                wallet = user.wallet
                wallet.add(decimal.Decimal(str(selected_reward['amount'])))

                # Create transaction record
                balance_before = wallet.balance - decimal.Decimal(str(selected_reward['amount']))
                Transaction.objects.create(
                    user=user,
                    transaction_type='DEPOSIT',
                    amount=decimal.Decimal(str(selected_reward['amount'])),
                    balance_before=balance_before,
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
    total_earnings = referral_transactions.aggregate(Sum('amount'))['amount__sum'] or decimal.Decimal('0')
    
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
            reward_amount=decimal.Decimal(str(selected_reward['amount'])),
            deposit_amount=recent_deposit.amount
        )
        
        # Add reward to wallet
        try:
            wallet = user.wallet
            balance_before = wallet.balance
            wallet.add(decimal.Decimal(str(selected_reward['amount'])))
            balance_after = wallet.balance
            
            # Create transaction record
            Transaction.objects.create(
                user=user,
                transaction_type='DEPOSIT',
                amount=decimal.Decimal(str(selected_reward['amount'])),
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




