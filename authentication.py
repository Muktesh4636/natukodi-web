import json
import logging
import redis
from django.conf import settings
from django.contrib.auth import get_user_model
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken, AuthenticationFailed

logger = logging.getLogger('game.auth')
User = get_user_model()

# Setup Redis connection
try:
    if hasattr(settings, 'REDIS_POOL') and settings.REDIS_POOL:
        redis_client = redis.Redis(connection_pool=settings.REDIS_POOL)
    else:
        redis_client = redis.Redis(
            host=getattr(settings, 'REDIS_HOST', 'localhost'),
            port=getattr(settings, 'REDIS_PORT', 6379),
            db=getattr(settings, 'REDIS_DB', 0),
            password=getattr(settings, 'REDIS_PASSWORD', None),
            decode_responses=True
        )
except Exception as e:
    logger.warning(f"Redis connection failed in auth: {e}")
    redis_client = None

class CachedJWTAuthentication(JWTAuthentication):
    """
    Custom JWT Authentication that caches user objects in Redis 
    to avoid database hits on every API request.
    """
    def get_user(self, validated_token):
        user_id = validated_token.get(settings.SIMPLE_JWT.get('USER_ID_CLAIM', 'user_id'))
        if not user_id:
            raise InvalidToken('Token contained no recognizable user identification')

        # 1. Try to get user from Redis cache
        if redis_client:
            try:
                cache_key = f"user_session:{user_id}"
                cached_user = redis_client.get(cache_key)
                if cached_user:
                    user_data = json.loads(cached_user)
                    
                    # Create a minimal user object that DRF can use
                    # We use the real model class but don't save it
                    user = User(
                        id=user_data['id'],
                        username=user_data['username'],
                        is_staff=user_data['is_staff'],
                        is_active=user_data['is_active']
                    )
                    # Mark as authenticated for DRF
                    user._is_authenticated = True
                    return user
            except Exception as e:
                logger.warning(f"Error reading user from Redis cache: {e}")

        # 2. Fallback to Database
        try:
            user = User.objects.get(**{settings.SIMPLE_JWT.get('USER_ID_FIELD', 'id'): user_id})
        except User.DoesNotExist:
            raise AuthenticationFailed('User not found', code='user_not_found')

        if not user.is_active:
            raise AuthenticationFailed('User is inactive', code='user_inactive')

        # 3. Cache the user for next time
        if redis_client:
            try:
                user_session_data = {
                    'id': user.id,
                    'username': user.username,
                    'is_staff': user.is_staff,
                    'is_active': user.is_active
                }
                redis_client.set(f"user_session:{user.id}", json.dumps(user_session_data), ex=3600)
            except Exception:
                pass

        return user
