from django.shortcuts import get_object_or_404
from rest_framework.views import APIView
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
from django.db.models import Sum
import uuid
import re
import logging
import json
import random

logger = logging.getLogger('accounts')

try:
    import pytesseract
    from PIL import Image
    import io
    TESSERACT_AVAILABLE = True
except ImportError:
    TESSERACT_AVAILABLE = False

from .models import User, Wallet, Transaction, DepositRequest, WithdrawRequest, PaymentMethod, UserBankDetail, DailyReward, LuckyDraw, RewardProbability
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

redis_client = get_redis_client()

import hashlib
from django.utils.crypto import constant_time_compare

def hash_otp(otp):
    return hashlib.sha256(str(otp).encode()).hexdigest()

def cache_user_session(user, balance=None):
    if not redis_client: return
    try:
        if balance is None:
            try: balance = user.wallet.balance
            except: balance = Decimal('0.00')
        pipe = redis_client.pipeline()
        pipe.set(f"user_balance:{user.id}", str(balance), ex=86400)
        user_session_data = {'id': user.id, 'username': user.username, 'is_staff': user.is_staff, 'is_active': user.is_active, 'wallet_balance': str(balance)}
        pipe.set(f"user_session:{user.id}", json.dumps(user_session_data), ex=86400)
        pipe.execute()
    except Exception as e: logger.error(f"Error caching user session: {e}")

def notify_user(user, message):
    print(f"[NOTIFY] {user.username}: {message}")

@api_view(['POST'])
@authentication_classes([])
@permission_classes([AllowAny])
@csrf_exempt
def register(request):
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
        if not constant_time_compare(stored_hash, hash_otp(otp_code)):
            return Response({'error': 'Invalid OTP'}, status=status.HTTP_400_BAD_REQUEST)
        if User.objects.filter(username=username).exists():
            return Response({'error': 'Username already taken'}, status=status.HTTP_400_BAD_REQUEST)
        if User.objects.filter(phone_number=clean_phone).exists():
            return Response({'error': 'Phone number already registered'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            with db_transaction.atomic():
                referred_by = User.objects.filter(referral_code=referral_code).first() if referral_code else None
                user = User.objects.create_user(username=username, password=password, phone_number=clean_phone, referred_by=referred_by)
                wallet = Wallet.objects.create(user=user, balance=Decimal('0.00'))
                redis_client.delete(otp_key)
                redis_client.set(f"user_balance:{user.id}", "0.00", ex=3600)
                user_session_data = {'id': user.id, 'username': user.username, 'is_staff': user.is_staff, 'is_active': user.is_active, 'wallet_balance': "0.00"}
                redis_client.set(f"user_session:{user.id}", json.dumps(user_session_data), ex=3600)
                refresh = RefreshToken.for_user(user)
                return Response({'user': UserSerializer(user).data, 'refresh': str(refresh), 'access': str(refresh.access_token), 'message': 'Registration successful'}, status=status.HTTP_201_CREATED)
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
    return Response({'loading_time': 3}, status=status.HTTP_200_OK)

@api_view(['POST'])
@authentication_classes([])
@permission_classes([AllowAny])
@csrf_exempt
def login(request):
    try:
        username = request.data.get('username', '').strip()
        password = request.data.get('password', '').strip()
        if not username or not password:
            return Response({'error': 'Username and password required'}, status=status.HTTP_400_BAD_REQUEST)
        clean_username = username
        if any(char.isdigit() for char in username):
            digits = ''.join(filter(str.isdigit, username))
            if len(digits) >= 10: clean_username = digits[-10:]
        user = User.objects.filter(Q(username=username) | Q(phone_number=username) | Q(phone_number=clean_username)).select_related('wallet').first()
        if not user or not user.check_password(password):
            return Response({'error': 'Invalid credentials'}, status=status.HTTP_401_UNAUTHORIZED)
        if not user.is_active:
            return Response({'error': 'User account is disabled'}, status=status.HTTP_403_FORBIDDEN)
        refresh = RefreshToken.for_user(user)
        if redis_client:
            try:
                wallet_balance = user.wallet.balance if hasattr(user, 'wallet') else Decimal('0.00')
                pipe = redis_client.pipeline()
                pipe.set(f"user_balance:{user.id}", str(wallet_balance), ex=3600)
                user_session_data = {'id': user.id, 'username': user.username, 'is_staff': user.is_staff, 'is_active': user.is_active, 'wallet_balance': str(wallet_balance)}
                pipe.set(f"user_session:{user.id}", json.dumps(user_session_data), ex=3600)
                pipe.execute()
                now = timezone.now()
                if not user.last_login or (now - user.last_login).total_seconds() > 300:
                    user.last_login = now
                    user.save(update_fields=['last_login'])
            except Exception as re: logger.error(f"Redis sync error during login: {re}")
        return Response({'user': UserSerializer(user).data, 'refresh': str(refresh), 'access': str(refresh.access_token)}, status=status.HTTP_200_OK)
    except Exception as e:
        logger.exception(f"Unexpected error during login: {e}")
        return Response({'error': 'Internal server error'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['POST'])
@authentication_classes([])
@permission_classes([AllowAny])
@csrf_exempt
def send_otp(request):
    try:
        phone_number = request.data.get('phone_number', '').strip()
        if not phone_number: return Response({'error': 'Phone number is required'}, status=status.HTTP_400_BAD_REQUEST)
        if not redis_client: return Response({'error': 'System error: Redis unavailable'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        from .sms_service import sms_service
        clean_phone = sms_service._clean_phone_number(phone_number, for_sms=False)
        rate_key = f"otp_rate:{clean_phone}"
        requests_count = redis_client.incr(rate_key)
        if requests_count == 1: redis_client.expire(rate_key, 600)
        if requests_count > 5: return Response({'error': 'Too many OTP requests. Please wait 10 minutes.'}, status=status.HTTP_429_TOO_MANY_REQUESTS)
        otp_code = ''.join([str(random.randint(0, 9)) for _ in range(6)])
        otp_key = f"otp:{clean_phone}"
        redis_client.set(otp_key, hash_otp(otp_code), ex=300)
        sms_number = sms_service._clean_phone_number(phone_number, for_sms=True)
        import threading
        threading.Thread(target=sms_service._send_sms_via_provider, args=(sms_number, otp_code)).start()
        return Response({'message': 'OTP sent successfully', 'expires_in': 300}, status=status.HTTP_200_OK)
    except Exception as e:
        logger.exception(f"Error in send_otp: {str(e)}")
        return Response({'error': 'Internal server error'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['POST'])
@authentication_classes([])
@permission_classes([AllowAny])
@csrf_exempt
def verify_otp_login(request):
    try:
        phone_number = request.data.get('phone_number', '').strip()
        otp_code = request.data.get('otp_code', '').strip()
        if not phone_number or not otp_code: return Response({'error': 'Phone number and OTP required'}, status=status.HTTP_400_BAD_REQUEST)
        if not redis_client: return Response({'error': 'System error: Redis unavailable'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        from .sms_service import sms_service
        clean_phone = sms_service._clean_phone_number(phone_number, for_sms=False)
        otp_key = f"otp:{clean_phone}"
        stored_hash = redis_client.get(otp_key)
        if not stored_hash or not constant_time_compare(stored_hash, hash_otp(otp_code)):
            return Response({'error': 'Invalid or expired OTP'}, status=status.HTTP_400_BAD_REQUEST)
        user = User.objects.filter(phone_number=clean_phone).first()
        if not user: return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)
        if not user.is_active: return Response({'error': 'User disabled'}, status=status.HTTP_403_FORBIDDEN)
        redis_client.delete(otp_key)
        refresh = RefreshToken.for_user(user)
        user.last_login = timezone.now()
        user.save(update_fields=['last_login'])
        if redis_client:
            wallet_obj, _ = Wallet.objects.get_or_create(user=user)
            pipe = redis_client.pipeline()
            pipe.set(f"user_balance:{user.id}", str(wallet_obj.balance), ex=3600)
            user_session_data = {'id': user.id, 'username': user.username, 'is_staff': user.is_staff, 'is_active': user.is_active, 'wallet_balance': str(wallet_obj.balance)}
            pipe.set(f"user_session:{user.id}", json.dumps(user_session_data), ex=3600)
            pipe.execute()
        return Response({'user': UserSerializer(user).data, 'refresh': str(refresh), 'access': str(refresh.access_token), 'message': 'Login successful'}, status=status.HTTP_200_OK)
    except Exception as e:
        logger.exception(f"Error in verify_otp_login: {str(e)}")
        return Response({'error': 'Internal server error'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def profile(request):
    if request.method == 'GET': return Response(UserSerializer(request.user, context={'request': request}).data)
    serializer = UserSerializer(request.user, data=request.data, partial=True, context={'request': request})
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
@parser_classes([MultiPartParser, FormParser])
def update_profile_photo(request):
    photo = request.FILES.get('photo')
    if not photo: return Response({'error': 'Photo required'}, status=status.HTTP_400_BAD_REQUEST)
    request.user.profile_photo = photo
    request.user.save()
    return Response(UserSerializer(request.user).data)

class WalletView(APIView):
    permission_classes = [IsAuthenticated]
    def get(self, request, format=None):
        user_id = request.user.id
        if redis_client:
            try:
                cached_wallet = redis_client.get(f"wallet_data_cache:{user_id}")
                if cached_wallet:
                    wallet_data = json.loads(cached_wallet)
                    realtime_balance = redis_client.get(f"user_balance:{user_id}")
                    if realtime_balance:
                        wallet_data['balance'] = realtime_balance
                        wallet_data['withdrawable_balance'] = str(max(Decimal('0.00'), Decimal(realtime_balance) - Decimal(wallet_data['unavaliable_balance'])))
                    return Response(wallet_data)
            except: pass
        wallet, _ = Wallet.objects.get_or_create(user=request.user)
        balance = redis_client.get(f"user_balance:{user_id}") if redis_client else str(wallet.balance)
        if balance is None: balance = str(wallet.balance)
        wallet_response = {'id': wallet.id, 'balance': balance, 'unavaliable_balance': str(wallet.unavaliable_balance), 'withdrawable_balance': str(wallet.withdrawable_balance), 'unavailable_balance': str(wallet.unavaliable_balance)}
        if redis_client: redis_client.set(f"wallet_data_cache:{user_id}", json.dumps(wallet_response), ex=5)
        return Response(wallet_response)

class TransactionList(generics.ListAPIView):
    serializer_class = TransactionSerializer
    permission_classes = [IsAuthenticated]
    def get_queryset(self): return Transaction.objects.filter(user=self.request.user).order_by('-created_at')

def _parse_amount(value):
    try:
        amount = Decimal(str(value).strip(' "\''))
        if amount <= 0 or amount.is_nan(): raise ValueError()
        return amount.quantize(Decimal('0.01'), rounding='ROUND_HALF_UP')
    except: raise ValueError(f'Invalid amount: {value}')

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def initiate_deposit(request):
    try: amount = _parse_amount(request.data.get('amount'))
    except ValueError as e: return Response({'error': str(e)}, status=400)
    return Response({'amount': str(amount), 'currency': 'INR', 'payment_link': f"https://pay.example.com/{uuid.uuid4().hex}?amount={amount}"})

@api_view(['POST'])
@permission_classes([IsAuthenticated])
@parser_classes([MultiPartParser, FormParser])
def extract_utr(request):
    if not TESSERACT_AVAILABLE: return Response({'error': 'OCR unavailable'}, status=503)
    screenshot = request.FILES.get('screenshot') or request.FILES.get('file')
    if not screenshot: return Response({'error': 'File required'}, status=400)
    try:
        pytesseract.pytesseract.tesseract_cmd = getattr(settings, 'TESSERACT_CMD', '/usr/bin/tesseract')
        text = pytesseract.image_to_string(Image.open(screenshot).convert('L'))
        match = re.search(r'\b\d{12}\b', text) or re.search(r'(?:UTR|Ref)[:\s]+([A-Z0-9]{10,16})', text, re.I)
        utr = match.group(0) if match else None
        return Response({'success': bool(utr), 'utr': utr})
    except Exception as e: return Response({'error': str(e)}, status=500)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def upload_deposit_proof(request):
    try:
        amount = _parse_amount(request.data.get('amount'))
        screenshot = request.FILES.get('screenshot')
        if not screenshot: return Response({'error': 'Screenshot required'}, status=400)
        pm_id = request.data.get('payment_method_id')
        pm = PaymentMethod.objects.filter(id=pm_id).first() if pm_id else None
        deposit = DepositRequest.objects.create(user=request.user, amount=amount, screenshot=screenshot, payment_method=pm, status='PENDING')
        return Response(DepositRequestSerializer(deposit, context={'request': request}).data, status=201)
    except Exception as e: return Response({'error': str(e)}, status=400)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def submit_utr(request):
    try:
        amount = _parse_amount(request.data.get('amount'))
        utr = request.data.get('utr', '').strip()
        if not utr: return Response({'error': 'UTR required'}, status=400)
        pm_id = request.data.get('payment_method_id')
        pm = PaymentMethod.objects.filter(id=pm_id).first() if pm_id else None
        deposit = DepositRequest.objects.create(user=request.user, amount=amount, payment_reference=utr, payment_method=pm, status='PENDING')
        return Response(DepositRequestSerializer(deposit, context={'request': request}).data, status=201)
    except Exception as e: return Response({'error': str(e)}, status=400)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def my_deposit_requests(request):
    return Response(DepositRequestSerializer(DepositRequest.objects.filter(user=request.user).order_by('-created_at'), many=True, context={'request': request}).data)

@api_view(['GET', 'POST'])
@permission_classes([IsAdminUser])
def reward_probability_settings(request):
    if request.method == 'GET':
        rtype = request.query_params.get('type')
        uid = request.query_params.get('user_id')
        if not rtype: return Response({'error': 'Type required'}, status=400)
        setting = RewardProbability.objects.filter(reward_type=rtype, user_id=uid).first() if uid else RewardProbability.objects.filter(reward_type=rtype, user__isnull=True).first()
        if not setting: return Response({'reward_type': rtype, 'probabilities': {}, 'scope': 'default'})
        return Response({'reward_type': setting.reward_type, 'probabilities': setting.probabilities, 'scope': 'user' if setting.user else 'global', 'user_id': setting.user.id if setting.user else None})
    rtype, uid, probs = request.data.get('type'), request.data.get('user_id'), request.data.get('probabilities')
    if not rtype or probs is None: return Response({'error': 'Type and probs required'}, status=400)
    user = get_object_or_404(User, id=uid) if uid else None
    setting, _ = RewardProbability.objects.update_or_create(reward_type=rtype, user=user, defaults={'probabilities': probs})
    return Response({'message': 'Updated', 'reward_type': setting.reward_type, 'probabilities': setting.probabilities, 'scope': 'user' if setting.user else 'global'})

@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def daily_reward(request):
    user, today = request.user, timezone.now().date()
    if request.method == 'GET':
        existing = DailyReward.objects.filter(user=user, reward_date=today).first()
        return Response({'claimed': bool(existing), 'reward': {'amount': existing.reward_amount, 'type': existing.reward_type} if existing else None})
    if DailyReward.objects.filter(user=user, reward_date=today).exists(): return Response({'error': 'Already claimed'}, status=400)
    setting = RewardProbability.objects.filter(reward_type='DAILY_REWARD', user=user).first() or RewardProbability.objects.filter(reward_type='DAILY_REWARD', user__isnull=True).first()
    if setting and setting.probabilities:
        rewards = [{'amount': float(k), 'type': 'MONEY' if float(k) > 0 else 'TRY_AGAIN', 'probability': float(v)} for k, v in setting.probabilities.items()]
    else: rewards = [{'amount': 10, 'type': 'MONEY', 'probability': 50}, {'amount': 0, 'type': 'TRY_AGAIN', 'probability': 50}]
    total = sum(r['probability'] for r in rewards)
    rand, cum, selected = random.uniform(0, total), 0, rewards[-1]
    for r in rewards:
        cum += r['probability']
        if rand <= cum:
            selected = r
            break
    daily = DailyReward.objects.create(user=user, reward_amount=Decimal(str(selected['amount'])), reward_type=selected['type'], reward_date=today)
    if selected['type'] == 'MONEY' and selected['amount'] > 0:
        user.wallet.add(Decimal(str(selected['amount'])))
        Transaction.objects.create(user=user, transaction_type='DEPOSIT', amount=Decimal(str(selected['amount'])), balance_before=user.wallet.balance-Decimal(str(selected['amount'])), balance_after=user.wallet.balance, description=f'Daily Reward ₹{selected["amount"]}')
    return Response({'reward': selected, 'message': f'Won ₹{selected["amount"]}' if selected['amount'] > 0 else 'Try again tomorrow'})

@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def lucky_draw(request):
    user = request.user
    if request.method == 'GET':
        dep = DepositRequest.objects.filter(user=user, status='APPROVED', amount__gte=2000, payment_reference__isnull=False).exclude(lucky_draws__isnull=False).first()
        return Response({'claimed': False, 'deposit_amount': float(dep.amount) if dep else None})
    dep = DepositRequest.objects.filter(user=user, status='APPROVED', amount__gte=2000, payment_reference__isnull=False).exclude(lucky_draws__isnull=False).first()
    if not dep: return Response({'error': 'No eligible deposit'}, status=400)
    setting = RewardProbability.objects.filter(reward_type='MEGA_SPIN', user=user).first() or RewardProbability.objects.filter(reward_type='MEGA_SPIN', user__isnull=True).first()
    if setting and setting.probabilities:
        rewards = [{'amount': float(k), 'probability': float(v)} for k, v in setting.probabilities.items()]
    else: rewards = [{'amount': 100, 'probability': 100}]
    total = sum(r['probability'] for r in rewards)
    rand, cum, selected = random.uniform(0, total), 0, rewards[-1]
    for r in rewards:
        cum += r['probability']
        if rand <= cum:
            selected = r
            break
    LuckyDraw.objects.create(user=user, deposit_request=dep, reward_amount=Decimal(str(selected['amount'])), deposit_amount=dep.amount)
    user.wallet.add(Decimal(str(selected['amount'])))
    Transaction.objects.create(user=user, transaction_type='DEPOSIT', amount=Decimal(str(selected['amount'])), balance_before=user.wallet.balance-Decimal(str(selected['amount'])), balance_after=user.wallet.balance, description=f'Lucky Draw ₹{selected["amount"]}')
    return Response({'lucky_draw': selected})

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def referral_data(request):
    user = request.user
    referrals = User.objects.filter(referred_by=user)
    referral_count = referrals.count()
    
    # Get total referral bonus earned
    total_bonus = Transaction.objects.filter(
        user=user, 
        transaction_type__in=['REFERRAL_BONUS', 'MILESTONE_BONUS']
    ).aggregate(total=Sum('amount'))['total'] or 0
    
    return Response({
        'referral_code': user.referral_code,
        'referral_count': referral_count,
        'total_bonus': float(total_bonus),
        'referral_link': f"https://gunduata.online/register?ref={user.referral_code}"
    })

@api_view(['POST'])
@permission_classes([IsAuthenticated])
@parser_classes([MultiPartParser, FormParser])
def process_payment_screenshot(request):
    screenshot = request.FILES.get('screenshot')
    if not screenshot:
        return Response({'error': 'Screenshot required'}, status=status.HTTP_400_BAD_REQUEST)
    
    # For now, just return success. OCR can be added later if needed.
    return Response({
        'message': 'Screenshot uploaded successfully',
        'status': 'success'
    })

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def pending_deposit_requests(request):
    deposits = DepositRequest.objects.filter(user=request.user, status='PENDING').order_by('-created_at')
    return Response(DepositRequestSerializer(deposits, many=True, context={'request': request}).data)


@api_view(['POST'])
@permission_classes([IsAdminUser])
def approve_deposit_request(request, pk):
    """Admin approves a pending deposit request"""
    note = request.data.get('note', '')
    try:
        with db_transaction.atomic():
            deposit = DepositRequest.objects.select_for_update().get(pk=pk)
            if deposit.status != 'PENDING':
                return Response({'error': 'Deposit request already processed'}, status=400)

            wallet, _ = Wallet.objects.get_or_create(user=deposit.user)
            wallet = Wallet.objects.select_for_update().get(pk=wallet.pk)
            balance_before = wallet.balance
            wallet.add(deposit.amount, is_bonus=True)
            wallet.save()

            if redis_client:
                try:
                    redis_client.set(f"user_balance:{deposit.user.id}", str(wallet.balance), ex=3600)
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
            
            # Referral logic...
            if deposit.user.referred_by:
                from .referral_logic import calculate_referral_bonus, check_and_award_milestone_bonus
                bonus = calculate_referral_bonus(deposit.amount)
                if bonus > 0:
                    referrer = deposit.user.referred_by
                    ref_wallet, _ = Wallet.objects.get_or_create(user=referrer)
                    ref_wallet = Wallet.objects.select_for_update().get(pk=ref_wallet.pk)
                    ref_bal_before = ref_wallet.balance
                    ref_wallet.add(bonus, is_bonus=True)
                    ref_wallet.save()
                    if redis_client:
                        try: redis_client.set(f"user_balance:{referrer.id}", str(ref_wallet.balance), ex=3600)
                        except: pass
                    Transaction.objects.create(user=referrer, transaction_type='REFERRAL_BONUS', amount=bonus, balance_before=ref_bal_before, balance_after=ref_wallet.balance, description=f"Referral bonus from {deposit.user.username}")
                    check_and_award_milestone_bonus(referrer)

        return Response({'message': 'Approved'})
    except Exception as e:
        return Response({'error': str(e)}, status=500)

@api_view(['POST'])
@permission_classes([IsAdminUser])
def reject_deposit_request(request, pk):
    """Admin rejects a pending deposit request"""
    note = request.data.get('note', '')
    try:
        deposit = DepositRequest.objects.get(pk=pk)
        if deposit.status != 'PENDING':
            return Response({'error': 'Already processed'}, status=400)
        deposit.status = 'REJECTED'
        deposit.admin_note = note
        deposit.processed_by = request.user
        deposit.processed_at = timezone.now()
        deposit.save()
        return Response({'message': 'Rejected'})
    except Exception as e:
        return Response({'error': str(e)}, status=500)
