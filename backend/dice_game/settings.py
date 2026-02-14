"""
Django settings for dice_game project.
"""

from pathlib import Path
import os
from datetime import timedelta
from dotenv import load_dotenv

load_dotenv()

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent


# Quick-start development settings - unsuitable for production
SECRET_KEY = os.getenv('SECRET_KEY', 'django-insecure-change-this-in-production')

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = os.getenv('DEBUG', 'False') == 'True'  # Default to False for production

# Security: Only allow specific hosts
ALLOWED_HOSTS_STR = os.getenv('ALLOWED_HOSTS', 'localhost,127.0.0.1,gunduata.online,www.gunduata.online,72.61.254.71,192.168.29.147')
ALLOWED_HOSTS = [host.strip() for host in ALLOWED_HOSTS_STR.split(',') if host.strip()]

# For local development, allow all hosts if DEBUG is True
if DEBUG:
    ALLOWED_HOSTS = ['*']


# Application definition

INSTALLED_APPS = [
    'daphne',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    # Third party
    'rest_framework',
    'rest_framework_simplejwt',
    'corsheaders',
    'channels',
    # Local apps
    'accounts',
    'game',
]

# OCR Settings
# You must install tesseract-ocr on your system for this to work
# macOS: brew install tesseract
# Ubuntu: sudo apt-get install tesseract-ocr
# Windows: Download installer from GitHub
TESSERACT_CMD = os.getenv('TESSERACT_CMD', '/opt/homebrew/bin/tesseract')

MIDDLEWARE = [
    'dice_game.middleware.NormalizePathMiddleware',  # Fix double slashes
    'django.middleware.security.SecurityMiddleware',
    # 'dice_game.cloudflare_middleware.CloudflareOnlyMiddleware',  # SECURITY: Block direct IP access
    # 'dice_game.anonymization_middleware.AnonymizationMiddleware',  # SECURITY: Prevent tracing
    # 'dice_game.vpn_protection_middleware.VPNProtectionMiddleware',  # SECURITY: VPN-resistant protection
    # 'dice_game.firewall_middleware.MultiLayerFirewallMiddleware',  # SECURITY: Multi-layer firewall
    # 'dice_game.api_security_middleware.APISecurityMiddleware',  # SECURITY: API-specific protection
    # 'dice_game.middleware.HideServerInfoMiddleware',  # SECURITY: Hide server info
    'django.contrib.sessions.middleware.SessionMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.common.CommonMiddleware',
    'dice_game.middleware.DisableCSRFMiddleware',  # Disable CSRF for API (after path normalization)
    'django.middleware.csrf.CsrfViewMiddleware',  # Standard CSRF middleware
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

# CSRF Settings
CSRF_TRUSTED_ORIGINS = [
    'https://gunduata.online',
    'http://gunduata.online',
    'https://www.gunduata.online',
    'http://www.gunduata.online',
    'http://72.61.254.71:8080',
    'http://72.61.254.71',
    'http://localhost:8080',
    'http://127.0.0.1:8080',
    'http://192.168.29.147:8080',
    'http://192.168.29.147',
    'http://0.0.0.0:8080',
    'http://0.0.0.0',
]

CSRF_USE_SESSIONS = True
CSRF_COOKIE_HTTPONLY = False

# CSRF Cookie Domain - None means use same domain as request
CSRF_COOKIE_DOMAIN = None

# CSRF Cookie settings (set here so they apply in both DEBUG and production)
CSRF_COOKIE_NAME = 'csrftoken'
CSRF_HEADER_NAME = 'HTTP_X_CSRFTOKEN'
CSRF_COOKIE_AGE = 31449600  # 1 year (same as session)
CSRF_COOKIE_PATH = '/'
# Allow CSRF to work without strict referer checking when behind proxy
CSRF_COOKIE_SAMESITE = 'Lax'
CSRF_COOKIE_SECURE = False
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_HTTPONLY = False
SESSION_COOKIE_HTTPONLY = False

# SECURITY: Production security settings
if not DEBUG:
    # HTTPS/SSL Settings
    SECURE_SSL_REDIRECT = os.getenv('SECURE_SSL_REDIRECT', 'False') == 'True'
    SESSION_COOKIE_SECURE = SECURE_SSL_REDIRECT
    CSRF_COOKIE_SECURE = SECURE_SSL_REDIRECT
    SECURE_BROWSER_XSS_FILTER = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    X_FRAME_OPTIONS = 'DENY'
    
    # HSTS (HTTP Strict Transport Security)
    SECURE_HSTS_SECONDS = 31536000  # 1 year
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    
    # Additional security headers
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    USE_TZ = True
    
    # CSRF settings for proxy setup
    # When behind a proxy, Django needs to trust the X-Forwarded-Proto header
    # CSRF_COOKIE_SECURE will be set based on X-Forwarded-Proto header from proxy
    CSRF_COOKIE_SECURE = SECURE_SSL_REDIRECT
    CSRF_USE_SESSIONS = True  # Use sessions for CSRF token (more robust for some setups)
    CSRF_COOKIE_HTTPONLY = False  # Allow JavaScript to read CSRF token (needed for AJAX)
    # CSRF_TRUSTED_ORIGINS is already set above
    # CSRF_COOKIE_DOMAIN is already set above
    # Note: CSRF_COOKIE_NAME, CSRF_HEADER_NAME, CSRF_COOKIE_AGE, CSRF_COOKIE_PATH are set above
    
    # Session security - Enhanced for anonymity
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    SESSION_COOKIE_SECURE = SECURE_SSL_REDIRECT
    SESSION_COOKIE_AGE = 3600  # 1 hour sessions
    SESSION_SAVE_EVERY_REQUEST = False  # Don't save on every request
    SESSION_EXPIRE_AT_BROWSER_CLOSE = True  # Clear on browser close
    
    # CSRF cookie settings
    # Note: CSRF_COOKIE_HTTPONLY, CSRF_COOKIE_SECURE are set above
    # CSRF_COOKIE_SAMESITE is set above for all environments
    
    # Password reset timeout (in seconds)
    PASSWORD_RESET_TIMEOUT = 3600  # 1 hour
    
    # Logging - Minimize information disclosure
    LOGGING = {
        'version': 1,
        'disable_existing_loggers': False,
        'formatters': {
            'minimal': {
                'format': '%(message)s',
            },
        },
        'handlers': {
            'file': {
                'level': 'ERROR',  # Only log errors, not info/debug
                'class': 'logging.handlers.RotatingFileHandler',
                'filename': BASE_DIR / 'logs' / 'django.log',
                'maxBytes': 10485760,  # 10MB
                'backupCount': 5,
                'formatter': 'minimal',
            },
        },
        'loggers': {
            'django': {
                'handlers': ['file'],
                'level': 'ERROR',
                'propagate': False,
            },
        },
    }
    
    # SECURITY: Hide server information
    SECURE_HIDE_SERVER_INFO = True
    
    # Disable Django admin branding (prevents version disclosure)
    ADMIN_URL = 'admin/'  # Change from default to make it less obvious
    
    # Prevent information disclosure in error pages
    # Note: Setting to 'no-referrer' can break CSRF protection
    # Use 'same-origin' instead to allow CSRF to work while still protecting privacy
    SECURE_REFERRER_POLICY = 'same-origin'  # Allow referrer for same-origin requests (needed for CSRF)
    
    # Minimize error information
    DEBUG_PROPAGATE_EXCEPTIONS = False
    
    # Don't store IP addresses in sessions
    SESSION_SAVE_EVERY_REQUEST = False

ROOT_URLCONF = 'dice_game.urls'

# Custom error handlers
handler404 = 'dice_game.views.custom_404_handler'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'dice_game.wsgi.application'
ASGI_APPLICATION = 'dice_game.asgi.application'


# Database
# Use SQLite for development (no PostgreSQL required)
USE_SQLITE = os.getenv('USE_SQLITE', 'False') == 'True'

if USE_SQLITE:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }
else:
    # PostgreSQL configuration (for production)
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': os.getenv('DB_NAME', 'dice_game'),
            'USER': os.getenv('DB_USER', 'muktesh'),
            'PASSWORD': os.getenv('DB_PASSWORD', 'muktesh123'),
            'HOST': os.getenv('DB_HOST', '72.61.254.74'),
            'PORT': os.getenv('DB_PORT', '6432'),
            'CONN_MAX_AGE': 60,  # Reuse connections for 60 seconds
            'CONN_HEALTH_CHECKS': True,  # Check if connection is alive before using
            'OPTIONS': {
                'connect_timeout': 120,  # Match PgBouncer's server_connect_timeout (120s)
                # Note: statement_timeout removed for PgBouncer compatibility
                # PgBouncer handles timeouts at the pool level
            },
        }
    }


# Password validation - SECURITY: Strong password requirements
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
        'OPTIONS': {
            'min_length': 8,  # Minimum 8 characters
        }
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# Internationalization
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True


# Static files (CSS, JavaScript, Images)
STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [
    BASE_DIR / 'static' / 'react',
    BASE_DIR / 'static' / 'unity',
]
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# React app build directory
REACT_BUILD_DIR = BASE_DIR / 'static' / 'react'

# Default primary key field type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# SMS Settings
SMS_PROVIDER = os.getenv('SMS_PROVIDER', 'MESSAGE_CENTRAL')  # Options: MSG91, TWILIO, TEXTLOCAL, MESSAGE_CENTRAL
SMS_API_KEY = os.getenv('SMS_API_KEY', 'C-8B852AEF1042406')
SMS_SENDER_ID = os.getenv('SMS_SENDER_ID', 'Gundu Ata')
SMS_TEMPLATE_ID = os.getenv('SMS_TEMPLATE_ID', '')
SMS_AUTH_TOKEN = os.getenv('SMS_AUTH_TOKEN', 'eyJhbGciOiJIUzUxMiJ9.eyJzdWIiOiJDLThCODUyQUVGMTA0MjQwNiIsImlhdCI6MTc3MDYyNTY0MSwiZXhwIjoxOTI4MzA1NjQxfQ.vR6ovuKMq1XRAH_Gt4DlOAE65LpgAnWv9DWEqmECWBqgUmUqL0tg28WxM1ZEsb673oO2aONMhezgr7Hmo2N0Jg')
SMS_CUSTOMER_ID = os.getenv('SMS_CUSTOMER_ID', 'C-8B852AEF1042406')

# Twilio settings (if using Twilio)
TWILIO_ACCOUNT_SID = os.getenv('TWILIO_ACCOUNT_SID', '')
TWILIO_AUTH_TOKEN = os.getenv('TWILIO_AUTH_TOKEN', '')

# Textlocal settings (if using Textlocal)
TEXTLOCAL_API_KEY = os.getenv('TEXTLOCAL_API_KEY', '')

# Custom User Model
AUTH_USER_MODEL = 'accounts.User'

# REST Framework - SECURITY: Rate limiting and throttling
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticated',
    ),
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,
    # Rate limiting to prevent abuse
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle'
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon': '1000000/hour',
        'user': '1000000/hour',
        'login': '1000000/minute',
        'bet': '1000000/minute',
        'api': '1000000/hour',
    }
}

# JWT Settings - SECURITY: Shorter token lifetimes
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(hours=1),  # Reduced from 24h to 1h
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': True,
    'ALGORITHM': 'HS256',
    'SIGNING_KEY': SECRET_KEY,
    'AUTH_HEADER_TYPES': ('Bearer',),
    'AUTH_HEADER_NAME': 'HTTP_AUTHORIZATION',
    'USER_ID_FIELD': 'id',
    'USER_ID_CLAIM': 'user_id',
}

# CORS Settings - SECURITY: Restrict to specific origins
CORS_ALLOWED_ORIGINS_STR = os.getenv(
    'CORS_ALLOWED_ORIGINS',
    'https://gunduata.online,https://www.gunduata.online,http://localhost:5173,http://localhost:3000'
)
CORS_ALLOWED_ORIGINS = [
    origin.strip() for origin in CORS_ALLOWED_ORIGINS_STR.split(',') if origin.strip()
]

# Only allow credentials from trusted origins
CORS_ALLOW_CREDENTIALS = True

# CORS Security: Allow all origins for APK compatibility
CORS_ALLOW_ALL_ORIGINS = True

# Redis Configuration
REDIS_HOST = os.getenv('REDIS_HOST', 'localhost')
REDIS_PORT = int(os.getenv('REDIS_PORT', 6379))
REDIS_DB = int(os.getenv('REDIS_DB', 0))
REDIS_PASSWORD = os.getenv('REDIS_PASSWORD', None)

# Redis Connection Pool (for efficient connection reuse)
# IMPORTANT: This is NOT 1 connection per user!
# - Connections are SHARED and REUSED across all users
# - Each operation borrows a connection, uses it, then returns it to the pool
# - Typical ratio: 1 Redis connection can serve 100-1000 concurrent users
# - Pool size should be: (expected concurrent users / 100) + buffer
try:
    import redis
    # Calculate pool size based on expected users
    # Default: 5000 connections (can handle ~500K concurrent users)
    # For 10M users, use Redis Cluster instead (see SCALABILITY_ANALYSIS.md)
    REDIS_POOL_SIZE = int(os.getenv('REDIS_POOL_SIZE', '5000'))
    
    # Create connection pool for Redis
    pool_kwargs = {
        'host': REDIS_HOST,
        'port': REDIS_PORT,
        'db': REDIS_DB,
        'max_connections': REDIS_POOL_SIZE,
        'decode_responses': True,
        'socket_connect_timeout': 5,
        'socket_timeout': 5,
        'retry_on_timeout': True,
    }
    
    # Add password if provided
    if REDIS_PASSWORD:
        pool_kwargs['password'] = REDIS_PASSWORD
    
    REDIS_POOL = redis.ConnectionPool(**pool_kwargs)
    
    # Test Redis connection
    redis_test = redis.Redis(connection_pool=REDIS_POOL)
    redis_test.ping()
    redis_test.close()
    USE_REDIS = True
    USE_REDIS_CHANNELS = True
except Exception as e:
    import logging
    logger = logging.getLogger(__name__)
    logger.warning(f"Redis not available: {e}")
    USE_REDIS = False
    USE_REDIS_CHANNELS = False
    REDIS_POOL = None

# Channels (WebSocket)
# Use Redis channel layer (required for game timer to broadcast to WebSocket consumers)
# In-memory layer only works within same process, but game timer runs separately
if USE_REDIS_CHANNELS:
    # Redis configuration (required for cross-process communication)
    # channels_redis requires URL format for authentication, not separate password key
    if REDIS_PASSWORD:
        # Format: redis://:password@host:port/db
        redis_url = f"redis://:{REDIS_PASSWORD}@{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}"
        channel_config = {
            "hosts": [redis_url],
            "capacity": 5000,  # Increased: Messages per channel (prevents message drops)
            "expiry": 60,  # Increased: Message expiry in seconds (prevents premature expiry)
            "group_expiry": 31536000,  # Group expiry (1 year) - prevents connections from being removed from group
        }
    else:
        channel_config = {
            "hosts": [(REDIS_HOST, REDIS_PORT)],
            "capacity": 5000,  # Increased: Messages per channel (prevents message drops)
            "expiry": 60,  # Increased: Message expiry in seconds (prevents premature expiry)
            "group_expiry": 31536000,  # Group expiry (1 year) - prevents connections from being removed from group
            # CRITICAL: Disable message batching to ensure real-time delivery
            "symmetric_encryption_keys": [os.getenv('CHANNEL_LAYER_SECRET', 'change-this-in-production')],
        }
    
    CHANNEL_LAYERS = {
        'default': {
            'BACKEND': 'channels_redis.core.RedisChannelLayer',
            'CONFIG': channel_config,
        },
    }
else:
    # Fallback to in-memory (only works within same process)
    # Note: Game timer won't be able to broadcast if using this
    CHANNEL_LAYERS = {
        'default': {
            'BACKEND': 'channels.layers.InMemoryChannelLayer',
        },
    }

# Game Settings
GAME_SETTINGS = {
    'BETTING_DURATION': 30,  # seconds (0-30s) - Betting open
    'RESULT_SELECTION_DURATION': 20,  # seconds (31-50s) - Betting closed, waiting for dice roll
    'RESULT_DISPLAY_DURATION': 20,  # seconds (51-70s) - Show dice result
    'TOTAL_ROUND_DURATION': 70,  # seconds (70 seconds total)
     'DICE_ROLL_TIME': 19,  # seconds - Time before dice result when warning is sent   
    'BETTING_CLOSE_TIME': 30,  # seconds - Stop taking bets (0-30s betting open)
    'DICE_RESULT_TIME': 51,  # seconds - Auto-roll dice if not set manually
    'RESULT_ANNOUNCE_TIME': 51,  # seconds - Announce result
    'ROUND_END_TIME': 80,  # seconds - End round and start new one
    'CHIP_VALUES': [10, 20, 50, 100],
    'PAYOUT_RATIOS': {
        1: 6.0,  # If you bet on 1 and it comes, you get 6x
        2: 6.0,
        3: 6.0,
        4: 6.0,
        5: 6.0,
        6: 6.0,
    },
}

# Redis Settings
REDIS_HOST = os.getenv('REDIS_HOST', 'localhost')
REDIS_PORT = int(os.getenv('REDIS_PORT', 6379))
REDIS_DB = int(os.getenv('REDIS_DB', 0))

