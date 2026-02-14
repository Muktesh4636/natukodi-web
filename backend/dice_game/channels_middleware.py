import os
import django
import logging
import json
import redis
from django.conf import settings

logger = logging.getLogger('game.websocket')

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
    logger.warning(f"Redis connection failed in middleware: {e}")
    redis_client = None

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'dice_game.settings')
django.setup()

from channels.db import database_sync_to_async
from django.contrib.auth.models import AnonymousUser
from rest_framework_simplejwt.tokens import AccessToken
from django.contrib.auth import get_user_model
from urllib.parse import parse_qs

User = get_user_model()

@database_sync_to_async
def get_user_from_db(user_id):
    try:
        return User.objects.get(id=user_id)
    except User.DoesNotExist:
        return AnonymousUser()

async def get_user(user_id):
    """Get user from Redis cache or fallback to DB"""
    if redis_client:
        try:
            cached_user = redis_client.get(f"user_session:{user_id}")
            if cached_user:
                user_data = json.loads(cached_user)
                # Create a mock user object that has the necessary attributes
                class CachedUser:
                    def __init__(self, data):
                        self.id = data['id']
                        self.username = data['username']
                        self.is_staff = data['is_staff']
                        self.is_active = data['is_active']
                        self.is_authenticated = True
                    def __str__(self):
                        return self.username
                
                return CachedUser(user_data)
        except Exception as e:
            logger.warning(f"Error reading user from Redis cache: {e}")

    # Fallback to DB
    user = await get_user_from_db(user_id)
    
    # Cache for next time if it's a real user
    if redis_client and user and not isinstance(user, AnonymousUser):
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

class JWTAuthMiddleware:
    """
    Custom JWT authentication middleware for Channels.
    Supports token in query string: ws://.../?token=...
    """
    def __init__(self, inner):
        self.inner = inner

    async def __call__(self, scope, receive, send):
        # Ensure user is at least AnonymousUser if not set
        if 'user' not in scope:
            scope['user'] = AnonymousUser()
        
        # Get the token from query string
        query_string = scope.get('query_string', b'').decode()
        query_params = parse_qs(query_string)
        token = query_params.get('token', [None])[0]

        # If not in query string, check headers
        if not token:
            headers = dict(scope.get('headers', []))
            auth_header = headers.get(b'authorization', b'').decode()
            if auth_header.startswith('Bearer '):
                token = auth_header.split(' ')[1]

        if token:
            try:
                # Validate the token
                access_token = AccessToken(token)
                user_id = access_token['user_id']
                scope['user'] = await get_user(user_id)
            except Exception as e:
                # Invalid token
                scope['user'] = AnonymousUser()
        return await self.inner(scope, receive, send)
