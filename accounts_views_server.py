from rest_framework.views import APIView
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

@api_view(['POST'])
@authentication_classes([])
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

        if not redis_client:
            return Response({'error': 'System error: Redis unavailable'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        from .sms_service import sms_service
        clean_phone = sms_service._clean_phone_number(phone_number, for_sms=False)
        
        otp_key = f"otp:{clean_phone}"
        stored_hash = redis_client.get(otp_key)
        
        if not stored_hash:
            return Response({'error': 'OTP expired or not found'}, status=status.HTTP_400_BAD_REQUEST)
        
        provided_hash = hash_otp(otp_code)
        if not constant_time_compare(stored_hash, provided_hash):
            return Response({'error': 'Invalid OTP'}, status=status.HTTP_400_BAD_REQUEST)
        
        if User.objects.filter(username=username).exists():
            return Response({'error': 'Username already taken'}, status=status.HTTP_400_BAD_REQUEST)
        if User.objects.filter(phone_number=clean_phone).exists():
            return Response({'error': 'Phone number already registered'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            with db_transaction.atomic():
                referred_by = None
                if referral_code:
                    referred_by = User.objects.filter(referral_code=referral_code).first()

                user = User.objects.create_user(
                    username=username,
                    password=password,
                    phone_number=clean_phone,
                    referred_by=referred_by
                )
                
                wallet = Wallet.objects.create(user=user, balance=Decimal('0.00'))
                redis_client.delete(otp_key)
                
                # Cache session and balance
                cache_user_session(user, Decimal('0.00'))

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

@api_view(['POST'])
@authentication_classes([])
@permission_classes([AllowAny])
@csrf_exempt
def login(request):
    """Optimized User login with session caching"""
    try:
        username = request.data.get('username', '').strip()
        password = request.data.get('password', '').strip()

        if not username or not password:
            return Response({'error': 'Username and password required'}, status=status.HTTP_400_BAD_REQUEST)

        clean_username = username
        if any(char.isdigit() for char in username):
            digits = ''.join(filter(str.isdigit, username))
            if len(digits) >= 10:
                clean_username = digits[-10:]

        user = User.objects.filter(
            Q(username=username) | 
            Q(phone_number=username) | 
            Q(phone_number=clean_username)
        ).select_related('wallet').first()

        if not user or not user.check_password(password):
            return Response({'error': 'Invalid credentials'}, status=status.HTTP_401_UNAUTHORIZED)

        if not user.is_active:
            return Response({'error': 'User account is disabled'}, status=status.HTTP_403_FORBIDDEN)

        # Cache session and balance
        cache_user_session(user)

        # Update last login asynchronously-ish (minimal hit)
        now = timezone.now()
        if not user.last_login or (now - user.last_login).total_seconds() > 300:
            user.last_login = now
            user.save(update_fields=['last_login'])

        refresh = RefreshToken.for_user(user)
        return Response({
            'user': UserSerializer(user).data,
            'refresh': str(refresh),
            'access': str(refresh.access_token),
        }, status=status.HTTP_200_OK)

    except Exception as e:
        logger.exception(f"Unexpected error during login: {e}")
        return Response({
            'error': 'Internal server error'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['GET'])
@authentication_classes([])
@permission_classes([AllowAny])
@csrf_exempt
def loading_time(request):
    return Response({'loading_time': 3}, status=status.HTTP_200_OK)

@api_view(['POST'])
@authentication_classes([])
@permission_classes([AllowAny])
@csrf_exempt
def send_otp(request):
    try:
        phone_number = request.data.get('phone_number', '').strip()
        if not phone_number:
            return Response({'error': 'Phone number is required'}, status=status.HTTP_400_BAD_REQUEST)
        if not redis_client:
            return Response({'error': 'System error: Redis unavailable'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        from .sms_service import sms_service
        clean_phone = sms_service._clean_phone_number(phone_number, for_sms=False)
        
        rate_key = f"otp_rate:{clean_phone}"
        requests_count = redis_client.incr(rate_key)
        if requests_count == 1:
            redis_client.expire(rate_key, 600)
        if requests_count > 5:
            return Response({'error': 'Too many OTP requests. Please wait 10 minutes.'}, status=status.HTTP_429_TOO_MANY_REQUESTS)

        otp_code = ''.join([str(random.randint(0, 9)) for _ in range(6)])
        otp_key = f"otp:{clean_phone}"
        redis_client.set(otp_key, hash_otp(otp_code), ex=300)
        
        import threading
        thread = threading.Thread(target=sms_service._send_sms_via_provider, args=(sms_service._clean_phone_number(phone_number, for_sms=True), otp_code))
        thread.daemon = True
        thread.start()
        
        return Response({'message': 'OTP sent successfully', 'expires_in': 300}, status=status.HTTP_200_OK)
    except Exception as e:
        logger.exception(f"Error in send_otp: {e}")
        return Response({'error': 'Internal server error'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['POST'])
@authentication_classes([])
@permission_classes([AllowAny])
@csrf_exempt
def verify_otp_login(request):
    try:
        phone_number = request.data.get('phone_number', '').strip()
        otp_code = request.data.get('otp_code', '').strip()
        if not phone_number or not otp_code:
            return Response({'error': 'Phone number and OTP code are required'}, status=status.HTTP_400_BAD_REQUEST)
        if not redis_client:
            return Response({'error': 'System error: Redis unavailable'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        from .sms_service import sms_service
        clean_phone = sms_service._clean_phone_number(phone_number, for_sms=False)
        otp_key = f"otp:{clean_phone}"
        stored_hash = redis_client.get(otp_key)
        if not stored_hash or not constant_time_compare(stored_hash, hash_otp(otp_code)):
            return Response({'error': 'Invalid or expired OTP'}, status=status.HTTP_400_BAD_REQUEST)

        user = User.objects.filter(phone_number=clean_phone).first()
        if not user:
            return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)
        if not user.is_active:
            return Response({'error': 'User account is disabled'}, status=status.HTTP_403_FORBIDDEN)

        redis_client.delete(otp_key)
        cache_user_session(user)
        user.last_login = timezone.now()
        user.save(update_fields=['last_login'])

        refresh = RefreshToken.for_user(user)
        return Response({
            'user': UserSerializer(user).data,
            'refresh': str(refresh),
            'access': str(refresh.access_token),
            'message': 'Login successful'
        }, status=status.HTTP_200_OK)
    except Exception as e:
        logger.exception(f"Error in verify_otp_login: {e}")
        return Response({'error': 'Internal server error'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def profile(request):
    if request.method == 'GET':
        return Response(UserSerializer(request.user, context={'request': request}).data)
    serializer = UserSerializer(request.user, data=request.data, partial=True, context={'request': request})
    if serializer.is_valid():
        serializer.save()
        # Refresh cache on profile update
        cache_user_session(request.user)
        return Response(serializer.data)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
@parser_classes([MultiPartParser, FormParser])
def update_profile_photo(request):
    photo = request.FILES.get('photo')
    if not photo:
        return Response({'error': 'Photo is required'}, status=status.HTTP_400_BAD_REQUEST)
    request.user.profile_photo = photo
    request.user.save()
    return Response(UserSerializer(request.user).data)

class WalletView(APIView):
    permission_classes = [IsAuthenticated]
    def get(self, request, format=None):
        user_id = request.user.id
        if redis_client:
            try:
                balance = redis_client.get(f"user_balance:{user_id}")
                if balance is not None:
                    # Return cached wallet data if available
                    cached_wallet = redis_client.get(f"wallet_data_cache:{user_id}")
                    if cached_wallet:
                        wallet_data = json.loads(cached_wallet)
                        wallet_data['balance'] = balance
                        return Response(wallet_data)
            except: pass

        wallet, _ = Wallet.objects.get_or_create(user=request.user)
        wallet_response = {
            'id': wallet.id,
            'balance': str(wallet.balance),
            'unavaliable_balance': str(wallet.unavaliable_balance),
            'withdrawable_balance': str(wallet.withdrawable_balance),
            'unavailable_balance': str(wallet.unavaliable_balance)
        }
        if redis_client:
            try:
                redis_client.set(f"user_balance:{user_id}", str(wallet.balance), ex=86400)
                redis_client.set(f"wallet_data_cache:{user_id}", json.dumps(wallet_response), ex=10)
            except: pass
        return Response(wallet_response)

class TransactionList(generics.ListAPIView):
    serializer_class = TransactionSerializer
    permission_classes = [IsAuthenticated]
    def get_queryset(self):
        return Transaction.objects.filter(user=self.request.user).order_by('-created_at')

def _parse_amount(value):
    try:
        amount = Decimal(str(value).strip().replace('"', '').replace("'", ''))
        if amount <= 0: raise ValueError()
        return amount.quantize(Decimal('0.01'), rounding='ROUND_HALF_UP')
    except:
        raise ValueError('Invalid amount')

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def initiate_deposit(request):
    try:
        amount = _parse_amount(request.data.get('amount'))
        return Response({'amount': str(amount), 'currency': 'INR', 'payment_link': f"https://pay.example.com/{uuid.uuid4().hex}?amount={amount}"})
    except ValueError as e:
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
@parser_classes([MultiPartParser, FormParser])
def upload_deposit_proof(request):
    screenshot = request.FILES.get('screenshot') or request.FILES.get('file') or request.FILES.get('image')
    if not screenshot: return Response({'error': 'Screenshot required'}, status=400)
    try:
        amount = _parse_amount(request.data.get('amount'))
        pm_id = request.data.get('payment_method_id')
        pm = PaymentMethod.objects.filter(id=pm_id).first() if pm_id else None
        deposit = DepositRequest.objects.create(user=request.user, amount=amount, screenshot=screenshot, payment_method=pm, status='PENDING')
        return Response(DepositRequestSerializer(deposit, context={'request': request}).data, status=201)
    except ValueError as e:
        return Response({'error': str(e)}, status=400)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def my_deposit_requests(request):
    deposits = DepositRequest.objects.filter(user=request.user).order_by('-created_at')
    return Response(DepositRequestSerializer(deposits, many=True, context={'request': request}).data)

@api_view(['GET'])
@permission_classes([IsAdminUser])
def pending_deposit_requests(request):
    deposits = DepositRequest.objects.filter(status='PENDING').select_related('user').order_by('created_at')
    return Response(DepositRequestAdminSerializer(deposits, many=True, context={'request': request}).data)

@api_view(['POST'])
@permission_classes([IsAdminUser])
def approve_deposit_request(request, pk):
    try:
        with db_transaction.atomic():
            deposit = DepositRequest.objects.select_for_update().get(pk=pk, status='PENDING')
            wallet, _ = Wallet.objects.get_or_create(user=deposit.user)
            wallet = Wallet.objects.select_for_update().get(pk=wallet.pk)
            bal_before = wallet.balance
            wallet.add(deposit.amount, is_bonus=True)
            
            Transaction.objects.create(user=deposit.user, transaction_type='DEPOSIT', amount=deposit.amount, balance_before=bal_before, balance_after=wallet.balance, description=f"Deposit #{deposit.id}")
            deposit.status = 'APPROVED'
            deposit.processed_by = request.user
            deposit.processed_at = timezone.now()
            deposit.save()
            
            # Update Redis cache
            cache_user_session(deposit.user, wallet.balance)
            
            return Response(DepositRequestAdminSerializer(deposit, context={'request': request}).data)
    except:
        return Response({'error': 'Failed to approve'}, status=400)

@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def daily_reward(request):
    today = timezone.now().date()
    if request.method == 'GET':
        existing = DailyReward.objects.filter(user=request.user, reward_date=today).first()
        return Response({'claimed': bool(existing), 'reward': {'amount': existing.reward_amount, 'type': existing.reward_type} if existing else None})
    
    if DailyReward.objects.filter(user=request.user, reward_date=today).exists():
        return Response({'error': 'Already claimed'}, status=400)
    
    # Simple random reward
    amount = random.choice([5, 10, 20, 50, 100])
    with db_transaction.atomic():
        reward = DailyReward.objects.create(user=request.user, reward_amount=Decimal(str(amount)), reward_type='MONEY', reward_date=today)
        wallet = request.user.wallet
        bal_before = wallet.balance
        wallet.add(reward.reward_amount)
        Transaction.objects.create(user=request.user, transaction_type='DEPOSIT', amount=reward.reward_amount, balance_before=bal_before, balance_after=wallet.balance, description='Daily Reward')
        cache_user_session(request.user, wallet.balance)
    
    return Response({'reward': {'amount': amount, 'type': 'MONEY'}})

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def referral_data(request):
    from django.db.models import Count, Sum
    user = request.user
    total_referrals = User.objects.filter(referred_by=user).count()
    total_earnings = Transaction.objects.filter(user=user, transaction_type='REFERRAL_BONUS').aggregate(Sum('amount'))['amount__sum'] or 0
    return Response({'referral_code': user.referral_code, 'total_referrals': total_referrals, 'total_earnings': str(total_earnings)})

@api_view(['GET'])
@permission_classes([AllowAny])
def get_payment_methods(request):
    methods = PaymentMethod.objects.filter(is_active=True)
    return Response(PaymentMethodSerializer(methods, many=True, context={'request': request}).data)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
@parser_classes([MultiPartParser, FormParser])
def extract_utr(request):
    if not TESSERACT_AVAILABLE:
        return Response({'success': False, 'error': 'OCR not available'}, status=503)
    screenshot = request.FILES.get('screenshot') or request.FILES.get('file') or request.FILES.get('image')
    if not screenshot: return Response({'error': 'Screenshot required'}, status=400)
    try:
        pytesseract.pytesseract.tesseract_cmd = getattr(settings, 'TESSERACT_CMD', '/usr/bin/tesseract')
        img = Image.open(screenshot).convert('L')
        text = pytesseract.image_to_string(img)
        utr_match = re.search(r'\b\d{12}\b', text)
        utr_number = utr_match.group(0) if utr_match else None
        if not utr_number:
            keyword_match = re.search(r'(?:UTR|Ref|Transaction ID|Ref No)[:\s]+([A-Z0-9]{10,16})', text, re.IGNORECASE)
            utr_number = keyword_match.group(1) if keyword_match else None
        return Response({'success': bool(utr_number), 'utr': utr_number})
    except Exception as e:
        return Response({'success': False, 'error': str(e)}, status=500)

@api_view(['POST'])
@permission_classes([AllowAny])
@parser_classes([MultiPartParser, FormParser])
def process_payment_screenshot(request):
    user_id = request.data.get('user_id')
    amount = request.data.get('amount')
    screenshot = request.FILES.get('screenshot') or request.FILES.get('file') or request.FILES.get('image')
    if not screenshot: return Response({'error': 'Screenshot required'}, status=400)
    try:
        pytesseract.pytesseract.tesseract_cmd = getattr(settings, 'TESSERACT_CMD', '/usr/bin/tesseract')
        img = Image.open(screenshot).convert('L')
        text = pytesseract.image_to_string(img)
        utr_match = re.search(r'\b\d{12}\b', text)
        utr_number = utr_match.group(0) if utr_match else None
        return Response({'success': bool(utr_number), 'user_id': user_id, 'amount': amount, 'utr': utr_number})
    except Exception as e:
        return Response({'success': False, 'error': str(e)}, status=500)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def submit_utr(request):
    amount_raw = request.data.get('amount')
    utr = request.data.get('utr', '').strip()
    if not utr: return Response({'error': 'UTR required'}, status=400)
    try:
        amount = _parse_amount(amount_raw)
        pm_id = request.data.get('payment_method_id')
        pm = PaymentMethod.objects.filter(id=pm_id).first() if pm_id else None
        deposit = DepositRequest.objects.create(user=request.user, amount=amount, payment_reference=utr, payment_method=pm, status='PENDING')
        return Response(DepositRequestSerializer(deposit, context={'request': request}).data, status=201)
    except ValueError as e:
        return Response({'error': str(e)}, status=400)

@api_view(['POST'])
@permission_classes([IsAdminUser])
def reject_deposit_request(request, pk):
    note = request.data.get('note', '')
    try:
        with db_transaction.atomic():
            deposit = DepositRequest.objects.select_for_update().get(pk=pk, status='PENDING')
            deposit.status = 'REJECTED'
            deposit.admin_note = note
            deposit.processed_by = request.user
            deposit.processed_at = timezone.now()
            deposit.save()
            return Response(DepositRequestAdminSerializer(deposit, context={'request': request}).data)
    except:
        return Response({'error': 'Failed to reject'}, status=400)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def initiate_withdraw(request):
    try:
        amount = _parse_amount(request.data.get('amount'))
        bank_detail_id = request.data.get('bank_detail_id')
        bank_detail = get_object_or_404(UserBankDetail, id=bank_detail_id, user=request.user)
        
        with db_transaction.atomic():
            wallet = Wallet.objects.select_for_update().get(user=request.user)
            if wallet.withdrawable_balance < amount:
                return Response({'error': 'Insufficient withdrawable balance'}, status=400)
            
            withdraw = WithdrawRequest.objects.create(user=request.user, amount=amount, bank_detail=bank_detail, status='PENDING')
            wallet.unavaliable_balance += amount
            wallet.balance -= amount
            wallet.save()
            
            # Update Redis cache
            cache_user_session(request.user, wallet.balance)
            
            return Response(WithdrawRequestSerializer(withdraw).data, status=201)
    except ValueError as e:
        return Response({'error': str(e)}, status=400)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def my_withdraw_requests(request):
    withdraws = WithdrawRequest.objects.filter(user=request.user).order_by('-created_at')
    return Response(WithdrawRequestSerializer(withdraws, many=True).data)

@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def my_bank_details(request):
    if request.method == 'GET':
        details = UserBankDetail.objects.filter(user=request.user)
        return Response(UserBankDetailSerializer(details, many=True).data)
    
    serializer = UserBankDetailSerializer(data=request.data)
    if serializer.is_valid():
        serializer.save(user=request.user)
        return Response(serializer.data, status=201)
    return Response(serializer.errors, status=400)

@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def delete_bank_detail(request, pk):
    detail = get_object_or_404(UserBankDetail, id=pk, user=request.user)
    detail.delete()
    return Response(status=204)

@api_view(['GET'])
@permission_classes([IsAdminUser])
def pending_withdraw_requests(request):
    withdraws = WithdrawRequest.objects.filter(status='PENDING').select_related('user', 'bank_detail').order_by('created_at')
    return Response(WithdrawRequestSerializer(withdraws, many=True).data)

@api_view(['POST'])
@permission_classes([IsAdminUser])
def approve_withdraw_request(request, pk):
    try:
        with db_transaction.atomic():
            withdraw = WithdrawRequest.objects.select_for_update().get(pk=pk, status='PENDING')
            wallet = Wallet.objects.select_for_update().get(user=withdraw.user)
            wallet.unavaliable_balance -= withdraw.amount
            wallet.save()
            
            Transaction.objects.create(user=withdraw.user, transaction_type='WITHDRAWAL', amount=withdraw.amount, balance_before=wallet.balance + withdraw.amount, balance_after=wallet.balance, description=f"Withdrawal #{withdraw.id}")
            withdraw.status = 'APPROVED'
            withdraw.processed_by = request.user
            withdraw.processed_at = timezone.now()
            withdraw.save()
            return Response(WithdrawRequestSerializer(withdraw).data)
    except:
        return Response({'error': 'Failed to approve'}, status=400)

@api_view(['POST'])
@permission_classes([IsAdminUser])
def reject_withdraw_request(request, pk):
    note = request.data.get('note', '')
    try:
        with db_transaction.atomic():
            withdraw = WithdrawRequest.objects.select_for_update().get(pk=pk, status='PENDING')
            wallet = Wallet.objects.select_for_update().get(user=withdraw.user)
            wallet.unavaliable_balance -= withdraw.amount
            wallet.balance += withdraw.amount
            wallet.save()
            
            withdraw.status = 'REJECTED'
            withdraw.admin_note = note
            withdraw.processed_by = request.user
            withdraw.processed_at = timezone.now()
            withdraw.save()
            
            # Update Redis cache
            cache_user_session(withdraw.user, wallet.balance)
            
            return Response(WithdrawRequestSerializer(withdraw).data)
    except:
        return Response({'error': 'Failed to reject'}, status=400)

@api_view(['GET', 'DELETE'])
@permission_classes([IsAuthenticated])
def bank_detail_action(request, pk):
    detail = get_object_or_404(UserBankDetail, id=pk, user=request.user)
    if request.method == 'GET':
        return Response(UserBankDetailSerializer(detail).data)
    detail.delete()
    return Response(status=204)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def daily_reward_history(request):
    rewards = DailyReward.objects.filter(user=request.user).order_by('-reward_date')
    return Response([{'amount': r.reward_amount, 'type': r.reward_type, 'date': r.reward_date} for r in rewards])

@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def lucky_draw(request):
    if request.method == 'GET':
        draws = LuckyDraw.objects.filter(user=request.user).order_by('-created_at')[:10]
        return Response([{'amount': d.amount, 'created_at': d.created_at} for d in draws])
    
    # Simple lucky draw logic
    amount = random.choice([0, 0, 0, 10, 20, 50, 100, 500])
    with db_transaction.atomic():
        draw = LuckyDraw.objects.create(user=request.user, amount=Decimal(str(amount)))
        if amount > 0:
            wallet = request.user.wallet
            bal_before = wallet.balance
            wallet.add(draw.amount)
            Transaction.objects.create(user=request.user, transaction_type='DEPOSIT', amount=draw.amount, balance_before=bal_before, balance_after=wallet.balance, description='Lucky Draw Win')
            cache_user_session(request.user, wallet.balance)
    return Response({'amount': amount})
