"""
Maintenance mode middleware.

When MAINTENANCE_MODE is enabled (env var or Redis), most requests return 503.
App API calls and APK download are all blocked for the maintenance duration.
Only admin panel and static/media (for maintenance page) remain allowed.

Enable: MAINTENANCE_MODE=1 or set Redis key maintenance_mode=1
Disable: MAINTENANCE_MODE=0 or unset Redis key
"""
import os
import logging
from django.http import HttpResponse
from django.conf import settings

logger = logging.getLogger('django')

# Paths that work during maintenance (admin to turn off; static/media for maintenance page)
# API to check maintenance status must work during maintenance so app can show "Under maintenance"
MAINTENANCE_ALLOWED_PREFIXES = (
    '/api/maintenance/',  # Status check — always reachable so app can show maintenance UI
    '/api/health/',       # Health check — no deps; for load balancer / 502 debugging
    '/api/status/',       # Aggregate DB + Redis + public-route probes — for external monitoring
    '/api/time/',         # Public time endpoint — useful for clients
    '/api/whitelabel/',   # White-label lead capture — public form so leads still work during maintenance
    '/api/game/settings', # Read-only game config (timers, chips, payouts) — app needs this to render UI
    '/static/',
    '/media/',
    '/admin/',  # Franchise / access message (Django admin not exposed here)
    '/game-admin/',  # Admin can access to turn off maintenance
)

# Exact paths allowed during maintenance (none for APK)
MAINTENANCE_ALLOWED_EXACT = frozenset()


def _is_maintenance_allowed(path):
    """Check if this path should bypass maintenance mode."""
    # Normalize: ensure leading slash for prefix checks
    path = path or '/'
    if not path.startswith('/'):
        path = '/' + path

    # Prefix match (covers /apk, /api/download/apk/, /gundu-ata.apk, etc.)
    for prefix in MAINTENANCE_ALLOWED_PREFIXES:
        if path.startswith(prefix) or path == prefix.rstrip('/'):
            return True

    # Exact match for path without leading slash
    path_no_slash = path.strip('/')
    if path_no_slash in MAINTENANCE_ALLOWED_EXACT:
        return True

    return False


# In-process cache for maintenance check (2s) to avoid Redis on every request
_maintenance_cache = None  # (enabled, until, cached_at)
_MAINTENANCE_CACHE_TTL = 2


def _get_maintenance_info():
    """Get (enabled, until_timestamp). Auto-clear if expired. Cached 2s to reduce Redis load."""
    import time
    now = time.time()
    global _maintenance_cache
    if _maintenance_cache is not None:
        enabled, until, cached_at = _maintenance_cache
        if now - cached_at < _MAINTENANCE_CACHE_TTL:
            return enabled, until

    # 1. Environment variable
    env_val = os.getenv('MAINTENANCE_MODE', '').lower()
    if env_val in ('1', 'true', 'yes', 'on'):
        _maintenance_cache = (True, None, now)
        return True, None  # No end time for env-based

    # 2. Redis (runtime toggle) — use pool when available so we don't open new TCP on every cache miss
    try:
        import redis
        r = None
        pool = getattr(settings, 'REDIS_POOL', None)
        if pool:
            r = redis.Redis(connection_pool=pool)
        else:
            host = getattr(settings, 'REDIS_HOST', 'localhost')
            port = int(getattr(settings, 'REDIS_PORT', 6379))
            db = int(getattr(settings, 'REDIS_DB', 0))
            password = getattr(settings, 'REDIS_PASSWORD', None)
            r = redis.Redis(
                host=host,
                port=port,
                db=db,
                password=password,
                socket_timeout=1,
                socket_connect_timeout=1,
                decode_responses=True,
            )
        if r and not r.get('maintenance_mode'):
            _maintenance_cache = (False, None, now)
            return False, None
        if r:
            until_raw = r.get('maintenance_until')
            if until_raw is not None:
                until_raw = until_raw.decode() if isinstance(until_raw, bytes) else str(until_raw)
            until = int(float(until_raw)) if until_raw else None
            now_ts = int(time.time())
            if until and until < now_ts:
                try:
                    r.delete('maintenance_mode')
                    r.delete('maintenance_until')
                except Exception:
                    pass
                _maintenance_cache = (False, None, now)
                return False, None
            _maintenance_cache = (True, until, now)
            return True, until
    except Exception:
        pass
    _maintenance_cache = (False, None, now)
    return False, None


def _is_maintenance_enabled():
    enabled, _ = _get_maintenance_info()
    return enabled


def _maintenance_response(request):
    """Return 503 maintenance page with duration. APK download disabled during maintenance."""
    import time
    _, until = _get_maintenance_info()

    if until:
        until_js = until * 1000  # JS uses milliseconds
        duration_html = '''
        <p class="duration" id="maintenance-duration">We'll be back in <span id="countdown">--</span></p>
        <script>
        (function(){
            var until = ''' + str(until_js) + ''';
            function update(){
                var now = Date.now();
                if (now >= until) { document.getElementById("countdown").textContent = "any moment"; location.reload(); return; }
                var s = Math.floor((until - now) / 1000);
                var m = Math.floor(s / 60);
                var h = Math.floor(m / 60);
                m = m % 60;
                s = s % 60;
                var parts = [];
                if (h) parts.push(h + "h");
                if (m) parts.push(m + "m");
                parts.push(s + "s");
                document.getElementById("countdown").textContent = parts.join(" ");
            }
            update();
            setInterval(update, 1000);
        })();
        </script>'''
    else:
        duration_html = '<p class="duration">We\'re performing scheduled maintenance. Please check back shortly.</p>'

    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>App Under Maintenance - Gundu Ata</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #1e3a5f 0%, #0d1b2a 100%);
            color: #e2e8f0;
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
        }}
        .card {{
            background: rgba(30, 41, 59, 0.9);
            border-radius: 16px;
            padding: 40px;
            max-width: 480px;
            text-align: center;
            box-shadow: 0 25px 50px -12px rgba(0,0,0,0.5);
        }}
        h1 {{ font-size: 1.5rem; margin-bottom: 12px; color: #f8fafc; }}
        p {{ color: #94a3b8; line-height: 1.6; margin-bottom: 24px; }}
        .duration {{ font-size: 1.1rem; color: #fbbf24; font-weight: 600; }}
        #countdown {{ color: #22c55e; }}
        .btn {{
            display: inline-block;
            padding: 14px 28px;
            background: #22c55e;
            color: white;
            text-decoration: none;
            border-radius: 10px;
            font-weight: 600;
            font-size: 1rem;
            transition: background 0.2s;
        }}
        .btn:hover {{ background: #16a34a; }}
        .note {{ font-size: 0.875rem; color: #64748b; margin-top: 20px; }}
    </style>
</head>
<body>
    <div class="card">
        <h1>🔧 App Under Maintenance</h1>
        {duration_html}
        <p class="note">App and downloads will be back after maintenance.</p>
    </div>
</body>
</html>'''
    return HttpResponse(html, status=503, content_type='text/html')


class MaintenanceModeMiddleware:
    """
    When maintenance mode is on, return 503 for most requests.
    App APIs and APK download are blocked for the maintenance duration.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = (request.path or '').strip()
        # Health check must never block on Redis — skip maintenance logic so LB/Cloudflare get fast 200
        if path == '/api/health/' or path == '/api/health':
            return self.get_response(request)

        if not _is_maintenance_enabled():
            return self.get_response(request)

        path = request.path
        # During maintenance, keep read-only game endpoints working so clients can
        # still load state/config. All write operations remain blocked.
        if request.method in ('GET', 'HEAD', 'OPTIONS') and path.startswith('/api/game/'):
            return self.get_response(request)

        if _is_maintenance_allowed(path):
            return self.get_response(request)

        logger.info(f"Maintenance mode: blocking {request.method} {path}")
        return _maintenance_response(request)
