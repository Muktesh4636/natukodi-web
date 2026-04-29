import re

from django.http import HttpResponse, JsonResponse, FileResponse, StreamingHttpResponse
from django.conf import settings
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework import status
from rest_framework.response import Response
import os
from urllib.parse import quote
from game.utils import get_game_setting
from .maintenance_middleware import _get_maintenance_info
from accounts.models import FranchiseBalance


@api_view(['GET'])
@permission_classes([AllowAny])
def health(request):
    """Minimal health check; no Redis or DB. Use for load balancer / 502 debugging."""
    return JsonResponse({'status': 'ok'}, status=200)


@api_view(['GET'])
@permission_classes([AllowAny])
@never_cache
def api_status(request):
    """
    Deep health: PostgreSQL, Redis, and in-process GET probes to public API routes.

    Returns 200 with ok=true only if every check passes; otherwise 503 with details.
    Use for monitoring (e.g. UptimeRobot) — point one monitor at /api/status/.
    Does not exercise authenticated routes (login, wallet, etc.).
    """
    import time
    from django.db import connection
    from django.test import Client

    checked_at = time.time()
    checks = {}
    routes = {}
    all_ok = True

    db_start = time.perf_counter()
    try:
        connection.ensure_connection()
        checks['database'] = {'ok': True, 'ms': round((time.perf_counter() - db_start) * 1000, 2)}
    except Exception as e:
        checks['database'] = {'ok': False, 'error': str(e)}
        all_ok = False

    redis_start = time.perf_counter()
    try:
        from game.utils import get_redis_client

        r = get_redis_client()
        if r:
            r.ping()
            checks['redis'] = {'ok': True, 'ms': round((time.perf_counter() - redis_start) * 1000, 2)}
        else:
            checks['redis'] = {'ok': False, 'error': 'client unavailable'}
            all_ok = False
    except Exception as e:
        checks['redis'] = {'ok': False, 'error': str(e)}
        all_ok = False

    # Synthetic GETs: full middleware + URL resolution (same process as production).
    # Only paths that bypass maintenance mode — otherwise this endpoint would 503 whenever
    # maintenance is on even if DB/Redis are fine.
    client = Client()
    # (path, acceptable HTTP status codes)
    probe_paths = [
        ('/api/health/', (200,)),
        ('/api/maintenance/status/', (200,)),
        ('/api/time/', (200,)),
        ('/api/game/version/', (200,)),
    ]

    for path, acceptable in probe_paths:
        try:
            resp = client.get(path)
            code = resp.status_code
            ok = code in acceptable
            routes[path] = {'ok': ok, 'status_code': code}
            if not ok:
                all_ok = False
        except Exception as e:
            routes[path] = {'ok': False, 'error': str(e)}
            all_ok = False

    issues = []
    if not checks.get('database', {}).get('ok'):
        issues.append(f"database: {checks.get('database', {}).get('error', 'failed')}")
    if not checks.get('redis', {}).get('ok'):
        issues.append(f"redis: {checks.get('redis', {}).get('error', 'failed')}")
    for path, info in routes.items():
        if not info.get('ok'):
            err = info.get('error')
            code = info.get('status_code')
            if err:
                issues.append(f"{path}: {err}")
            else:
                issues.append(f"{path}: HTTP {code}")

    from datetime import datetime, timezone

    checked_iso = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
    n_infra = 2  # database + redis
    n_routes = len(routes)
    total = n_infra + n_routes
    passed = sum(1 for c in (checks.get('database'), checks.get('redis')) if c and c.get('ok'))
    passed += sum(1 for r in routes.values() if r.get('ok'))

    body = {
        'ok': all_ok,
        'checked_at': checked_at,
        'checked_at_iso': checked_iso,
        'summary': {
            'total': total,
            'passed': passed,
            'failed': total - passed,
        },
        'issues': issues,
        'checks': checks,
        'routes': routes,
    }
    status_http = 200 if all_ok else 503
    return JsonResponse(body, status=status_http)


@never_cache
def django_admin_disabled_message(request):
    """
    Django's /admin/ (database UI) is not offered at this URL.
    No redirect — same response for /admin/, /admin/login/, etc.
    """
    html = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Take Franchise — Gundu Ata</title>
  <style>
    * { box-sizing: border-box; }
    html, body { height: 100%; margin: 0; }
    body {
      font-family: system-ui, sans-serif;
      background: #000000;
      color: #FFEB3B;
      display: flex;
      align-items: center;
      justify-content: center;
      min-height: 100vh;
      padding: 1rem;
      text-align: center;
    }
    p {
      font-size: clamp(1.125rem, 4vw, 1.5rem);
      font-weight: 700;
      line-height: 1.5;
      margin: 0;
      max-width: 36rem;
    }
    a.back {
      display: inline-block;
      margin-top: 1.75rem;
      font-size: clamp(1rem, 3vw, 1.125rem);
      font-weight: 600;
      color: #FFEB3B;
      text-decoration: underline;
    }
    a.back:hover { opacity: 0.9; }
  </style>
</head>
<body>
  <div>
    <p>Take franchise</p>
    <a class="back" href="/">← Back to Game</a>
  </div>
</body>
</html>"""
    return HttpResponse(html, content_type='text/html; charset=utf-8', status=200)


def _get_round_start_info():
    """Return current round start data: round_id, start_time_ist (IST with ms)."""
    import json
    from game.utils import get_redis_client
    from game.models import GameRound
    from django.utils import timezone as dj_tz
    import pytz

    start_dt = None
    round_id = None
    redis_client = get_redis_client()
    if redis_client:
        try:
            state_json = redis_client.get('current_game_state')
            if state_json:
                state = json.loads(state_json)
                round_id = state.get('round_id')
                start_str = state.get('start_time')
                if start_str and round_id:
                    from datetime import datetime
                    start_dt = datetime.fromisoformat(start_str.replace('Z', '+00:00'))
                    if start_dt.tzinfo is None:
                        start_dt = dj_tz.make_aware(start_dt)
        except Exception:
            pass
    if start_dt is None:
        round_obj = GameRound.objects.order_by('-start_time').first()
        if round_obj:
            round_id = round_obj.round_id
            start_dt = round_obj.start_time
    if not start_dt or not round_id:
        return {'round_id': None, 'start_time_ist': None}

    ist_tz = pytz.timezone('Asia/Kolkata')
    if start_dt.tzinfo is None:
        start_dt = dj_tz.make_aware(start_dt)
    start_ist = start_dt.astimezone(ist_tz)
    # IST string with milliseconds, no timezone suffix (e.g. 2026-03-20T12:10:00.123)
    ms = int(start_ist.microsecond / 1000)
    start_time_ist = start_ist.strftime('%Y-%m-%dT%H:%M:%S.') + f'{ms:03d}'
    return {'round_id': round_id, 'start_time_ist': start_time_ist}


@api_view(['GET'])
@permission_classes([AllowAny])
def time_now(request):
    """Public current server time in IST + current round start time (same as round/start-time/)."""
    import time
    from datetime import datetime
    import pytz

    # Use epoch so we get true UTC even if server TZ is set to IST or wrong
    now_utc = datetime.fromtimestamp(time.time(), tz=pytz.UTC)
    ist_tz = pytz.timezone('Asia/Kolkata')
    now_ist = now_utc.astimezone(ist_tz)
    ms = int(now_ist.microsecond / 1000)
    ist_str = now_ist.strftime('%Y-%m-%dT%H:%M:%S.') + f'{ms:03d}'

    round_start = _get_round_start_info()
    return JsonResponse({
        'ist': ist_str,
        'round_started': round_start,
    }, status=200)


def api_root(request):
    """API root endpoint that lists available API endpoints"""
    base_url = request.build_absolute_uri('/')
    api_data = {
        'name': 'Gundu ata API',
        'version': '1.0',
        'description': 'REST API for Gundu ata application',
        'endpoints': {
            'auth': {
                'base_url': f'{base_url}api/auth/',
                'endpoints': {
                    'register': f'{base_url}api/auth/register/',
                    'login': f'{base_url}api/auth/login/',
                    'profile': f'{base_url}api/auth/profile/',
                    'wallet': f'{base_url}api/auth/wallet/',
                    'transactions': f'{base_url}api/auth/transactions/',
                }
            },
            'game': {
                'base_url': f'{base_url}api/game/',
                'endpoints': {
                    'round': f'{base_url}api/game/round/',
                    'bet': f'{base_url}api/game/bet/',
                    'bets': f'{base_url}api/game/bets/',
                }
            }
        },
        'admin': {
            'game_admin': f'{base_url}game-admin/dashboard/',
        }
    }
    return JsonResponse(api_data, json_dumps_params={'indent': 2})


@api_view(['GET'])
@permission_classes([AllowAny])
def support_contacts(request):
    """
    Public support contacts for Help Center (APK can read, admin panel edits).

    Query params (optional):
    - package or package_name: APK applicationId (e.g. com.franchise1.app).
      When provided, returns help numbers for that franchise if configured; else global defaults.

    Global defaults (GameSettings):
    - SUPPORT_WHATSAPP_NUMBER, SUPPORT_TELEGRAM, SUPPORT_FACEBOOK, SUPPORT_INSTAGRAM
    """
    package = (request.GET.get('package') or request.GET.get('package_name') or '').strip()
    whatsapp = get_game_setting('SUPPORT_WHATSAPP_NUMBER', '')
    telegram = get_game_setting('SUPPORT_TELEGRAM', '')
    facebook = get_game_setting('SUPPORT_FACEBOOK', '')
    instagram = get_game_setting('SUPPORT_INSTAGRAM', '')

    if package:
        try:
            fb = FranchiseBalance.objects.filter(package_name=package).first()
            if fb:
                whatsapp = fb.help_whatsapp_number or whatsapp
                telegram = fb.help_telegram or telegram
                facebook = fb.help_facebook or facebook
                instagram = fb.help_instagram or instagram
        except Exception:
            pass

    return Response({
        'whatsapp_number': str(whatsapp).strip() if whatsapp else '',
        'telegram': str(telegram).strip() if telegram else '',
        'facebook': str(facebook).strip() if facebook else '',
        'instagram': str(instagram).strip() if instagram else '',
    })


@api_view(['GET'])
@permission_classes([AllowAny])
def maintenance_status(request):
    """
    Public API: returns whether app maintenance is on or off.
    Three fields only: maintenance, remaining_hours, remaining_minutes (for countdown display).
    """
    import time
    from dice_game.maintenance_middleware import _get_maintenance_info
    enabled, until = _get_maintenance_info()
    remaining_hours = 0
    remaining_minutes = 0
    if enabled and until is not None:
        now = int(time.time())
        secs = max(0, until - now)
        remaining_hours = secs // 3600
        remaining_minutes = (secs % 3600) // 60
    return Response({
        'maintenance': enabled,
        'remaining_hours': remaining_hours,
        'remaining_minutes': remaining_minutes,
    })


def _normalize_phone_number(raw: str) -> str:
    if raw is None:
        return ''
    s = str(raw).strip()
    if not s:
        return ''
    keep_plus = s.startswith('+')
    digits = ''.join(ch for ch in s if ch.isdigit())
    if not digits:
        return ''
    return f"+{digits}" if keep_plus else digits


@csrf_exempt
@api_view(['POST', 'OPTIONS'])
@permission_classes([AllowAny])
def white_label_lead(request):
    """
    White-label lead capture. Public API; works during maintenance.
    Body (JSON or form): name (required), phone_number (required), message (optional).
    """
    if request.method == 'OPTIONS':
        return Response(status=status.HTTP_200_OK)
    name = (request.data.get('name') or '').strip()
    phone_number = _normalize_phone_number(request.data.get('phone_number'))
    message = (request.data.get('message') or '').strip()

    if not name:
        return Response({'error': 'name is required'}, status=status.HTTP_400_BAD_REQUEST)
    if not phone_number:
        return Response({'error': 'phone_number is required'}, status=status.HTTP_400_BAD_REQUEST)

    # Best-effort client metadata
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR', '')
    ip = x_forwarded_for.split(',')[0].strip() if x_forwarded_for else request.META.get('REMOTE_ADDR', None)
    ua = (request.META.get('HTTP_USER_AGENT') or '').strip()

    try:
        from game.models import WhiteLabelLead
    except ImportError:
        return Response({'error': 'Service not configured'}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

    WhiteLabelLead.objects.create(
        name=name[:100],
        phone_number=phone_number[:30],
        message=message,
        ip_address=ip if ip else None,
        user_agent=ua,
    )

    return Response({'status': 'ok'}, status=status.HTTP_201_CREATED)


def root_status(request):
    """Simple landing page so / shows helpful links instead of 404."""
    admin_url = request.build_absolute_uri('/admin/')
    dashboard_url = request.build_absolute_uri('/game-admin/dashboard/')
    api_url = request.build_absolute_uri('/api/')

    html = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="utf-8">
        <title>Gundu ata Backend</title>
        <style>
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
                background: #f5f7fb;
                color: #1f2933;
                margin: 0;
                padding: 40px 20px;
            }}
            .container {{
                max-width: 720px;
                margin: 0 auto;
                background: #fff;
                border-radius: 12px;
                box-shadow: 0 10px 30px rgba(15, 23, 42, 0.08);
                padding: 32px 40px;
            }}
            h1 {{
                margin-top: 0;
                font-size: 32px;
            }}
            p {{
                line-height: 1.6;
            }}
            a.button {{
                display: inline-block;
                margin: 12px 12px 0 0;
                padding: 12px 18px;
                border-radius: 8px;
                background: #6366f1;
                color: #fff;
                text-decoration: none;
                font-weight: 600;
            }}
            .links {{
                margin-top: 24px;
            }}
            code {{
                background: #eef2ff;
                padding: 3px 6px;
                border-radius: 4px;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>Gundu ata Backend</h1>
            <p>
                The Django backend is running. Use the links below to access the admin
                panel, custom game dashboard, or REST API.
            </p>
            <div class="links">
                <a class="button" href="{dashboard_url}">Game Admin Dashboard</a>
                <a class="button" href="{api_url}">API Root</a>
            </div>
            <p style="margin-top:24px;">
                Frontend (React/Vite) runs separately on <code>npm run dev</code> (default <code>http://localhost:5173</code>).
            </p>
        </div>
    </body>
    </html>
    """
    return HttpResponse(html)


_COCKFIGHT_HOOK_SNIPPET = '<script defer src="/cockfight-video-hook.js"></script>'


@never_cache
def cockfight_video_hook_js(request):
    """
    Tiny client for SPAs: polls latest admin cockfight upload and drives <video> on #cockfight.
    Injected into index.html by serve_react_app.
    """
    js = r"""
(function () {
    var INFO_URL = '/api/game/meron-wala/info/';
    var POLL_MS = 12000;
    var IS_MOBILE = /android|iphone|ipad|ipod|mobile|phone/i.test(navigator.userAgent || '');
    var PRE_BUFFER_SECS = IS_MOBILE ? 15 : 60;

    /* ── hls.js loader ─────────────────────────────────────────────────────────
     * Inject hls.js from CDN once, then use it for all HLS playback.
     * Falls back to native HLS on Safari (which supports it natively).
     * ────────────────────────────────────────────────────────────────────────── */
    var _hlsJsReady = false;
    var _hlsJsCallbacks = [];
    function loadHlsJs(cb) {
        if (typeof Hls !== 'undefined') { cb(); return; }
        if (_hlsJsCallbacks.length > 0) { _hlsJsCallbacks.push(cb); return; }
        _hlsJsCallbacks.push(cb);
        var s = document.createElement('script');
        s.src = 'https://cdn.jsdelivr.net/npm/hls.js@1.5.7/dist/hls.min.js';
        s.onload = function () {
            _hlsJsReady = true;
            _hlsJsCallbacks.forEach(function (fn) { try { fn(); } catch (e) {} });
            _hlsJsCallbacks = [];
        };
        s.onerror = function () {
            _hlsJsCallbacks.forEach(function (fn) { try { fn(true); } catch (e) {} });
            _hlsJsCallbacks = [];
        };
        document.head.appendChild(s);
    }

    /* Active Hls instances keyed by video element (WeakMap equivalent via array). */
    var _hlsInstances = [];
    var lastUrl = '';
    var dockTimer = null;
    var pendingStartTimer = null;
    var wallClockSyncTimer = null;
    var liveEdgeStartMs = null;
    var lastPollStreamKey = '';
    var lastAppliedSyncKey = '';
    var pendingStreamKey = '';
    /* Offset so Date.now()+skew tracks server clock (pseudo-live; same moment for all users). */
    var clockSkewMs = 0;

    function effectiveNowMs() {
        return Date.now() + clockSkewMs;
    }

    function hashIsCockfight() {
        return /cockfight/i.test(location.hash || '');
    }

    function targetVideos() {
        var sel = (
            'video[data-cockfight-stream],video[data-cockfight-latest],' +
            '[data-game="cockfight"] video,[data-tab="cockfight"] video'
        );
        var marked = document.querySelectorAll(sel);
        if (marked.length) return Array.prototype.slice.call(marked);
        var root = document.getElementById('cockfight');
        if (root) return Array.prototype.slice.call(root.querySelectorAll('video'));
        if (!hashIsCockfight()) return [];
        var one = document.querySelector('#root video, main video, [role="main"] video');
        return one ? [one] : [];
    }

    function mimeForUrl(u) {
        var path = (u || '').split('?')[0].split('#')[0].toLowerCase();
        if (path.endsWith('.webm')) return 'video/webm';
        if (path.endsWith('.mov')) return 'video/quicktime';
        if (path.endsWith('.mkv')) return 'video/x-matroska';
        if (path.endsWith('.m4v') || path.endsWith('.mp4')) return 'video/mp4';
        return 'video/mp4';
    }

    function clearScheduleTimers() {
        if (pendingStartTimer) {
            clearTimeout(pendingStartTimer);
            pendingStartTimer = null;
        }
        if (wallClockSyncTimer) {
            clearInterval(wallClockSyncTimer);
            wallClockSyncTimer = null;
        }
    }

    function detachCockfightVideos() {
        clearScheduleTimers();
        stopBackgroundPreload();
        destroyAllHls();
        lastUrl = '';
        lastPollStreamKey = '';
        lastAppliedSyncKey = '';
        pendingStreamKey = '';
        liveEdgeStartMs = null;
        targetVideos().forEach(function (v) {
            try {
                v.removeAttribute('src');
                while (v.firstChild) v.removeChild(v.firstChild);
                v.pause();
                v.load();
            } catch (e1) {}
        });
    }

    function attachSourceAndMeta(v, url) {
        v.removeAttribute('src');
        while (v.firstChild) v.removeChild(v.firstChild);
        var srcEl = document.createElement('source');
        srcEl.src = url;
        srcEl.type = mimeForUrl(url.split('#')[0]);
        v.appendChild(srcEl);
        v.muted = true;
        v.setAttribute('playsinline', '');
        v.setAttribute('webkit-playsinline', '');
        v.playsInline = true;
        v.setAttribute('preload', 'auto');
        v.setAttribute('controls', '');
        try {
            v.setAttribute('controlsList', 'nodownload');
        } catch (e0) {}
        v.load();
    }

    function videoBaseUrl(v) {
        /* Return the base URL (without fragment) of the currently loaded source. */
        try {
            var src = v.currentSrc || '';
            return src.split('#')[0].split('?token=')[0];
        } catch (e) { return ''; }
    }

    function softSyncPosition(v, startWallMs) {
        /* Adjust currentTime toward live position without reloading. */
        var target = (effectiveNowMs() - startWallMs) / 1000;
        if (target < 0) target = 0;
        if (v.duration && !isNaN(v.duration)) {
            if (target >= v.duration) {
                v.pause();
                return;
            }
            target = Math.min(target, v.duration - 0.05);
        }
        if (Math.abs(v.currentTime - target) > 1) {
            v.currentTime = target;
        }
        if (v.paused) {
            var p = v.play();
            if (p && typeof p.catch === 'function') p.catch(function () {});
        }
    }

    /* No start time (legacy): play from beginning immediately */
    function destroyHlsForVideo(v) {
        for (var i = _hlsInstances.length - 1; i >= 0; i--) {
            if (_hlsInstances[i].el === v) {
                try { _hlsInstances[i].hls.destroy(); } catch (e) {}
                _hlsInstances.splice(i, 1);
            }
        }
    }

    function destroyAllHls() {
        _hlsInstances.forEach(function (x) { try { x.hls.destroy(); } catch (e) {} });
        _hlsInstances = [];
    }

    /*
     * setupHlsPlayer: attach hls.js to a <video> element.
     * Handles seeking to the correct live position after the manifest is parsed.
     */
    function setupHlsPlayer(v, hlsUrl, startWallMs, onReady) {
        destroyHlsForVideo(v);
        v.removeAttribute('src');
        while (v.firstChild) v.removeChild(v.firstChild);
        v.muted = true;
        v.setAttribute('playsinline', '');
        v.setAttribute('webkit-playsinline', '');
        v.setAttribute('controls', '');
        try { v.setAttribute('controlsList', 'nodownload'); } catch (e) {}

        /* Safari supports HLS natively — don't load hls.js */
        if (!Hls.isSupported() && v.canPlayType('application/vnd.apple.mpegurl')) {
            v.src = hlsUrl;
            v.load();
            v.addEventListener('loadedmetadata', function onM() {
                v.removeEventListener('loadedmetadata', onM);
                if (onReady) onReady(v);
            });
            return;
        }

        var hls = new Hls({
            maxBufferLength: 60,          /* Buffer exactly 60s (1 min) ahead — no more */
            maxMaxBufferLength: 60,       /* Hard cap at 60s regardless of network speed */
            startLevel: -1,               /* Auto-select starting quality */
            abrEwmaDefaultEstimate: IS_MOBILE ? 500000 : 2000000,  /* Initial bandwidth guess */
            enableWorker: true,
            lowLatencyMode: false,
        });
        _hlsInstances.push({ el: v, hls: hls });

        hls.loadSource(hlsUrl);
        hls.attachMedia(v);

        hls.on(Hls.Events.MANIFEST_PARSED, function () {
            if (onReady) onReady(v);
        });

        hls.on(Hls.Events.ERROR, function (event, data) {
            if (data.fatal) {
                if (data.type === Hls.ErrorTypes.NETWORK_ERROR) {
                    hls.startLoad();  /* retry on network error */
                } else {
                    hls.destroy();
                }
            }
        });
    }

    /*
     * Pseudo-live HLS playback — same position for every viewer.
     * startWallMs is null for videos with no schedule (play from 0).
     */
    function applyHlsSynced(hlsUrl, startWallMs, streamKey) {
        lastUrl = hlsUrl;
        liveEdgeStartMs = startWallMs;
        clearScheduleTimers();
        if (streamKey) lastAppliedSyncKey = streamKey;

        var list = targetVideos();
        if (!list.length) return;

        loadHlsJs(function (err) {
            if (err || typeof Hls === 'undefined') return;   /* hls.js CDN unreachable */
            list.forEach(function (v) {
                try {
                    setupHlsPlayer(v, hlsUrl, startWallMs, function (v2) {
                        if (startWallMs !== null) {
                            waitForBuffer(v2, startWallMs);
                        } else {
                            doPlay(v2, 0);
                        }
                        startWallClockSync(v2, startWallMs);
                    });
                } catch (e) {}
            });
        });

        try {
            window.dispatchEvent(new CustomEvent('kokoroko:cockfight-video', {
                detail: { hls_url: hlsUrl, start: startWallMs ? new Date(startWallMs).toISOString() : null }
            }));
        } catch (e) {}
    }

    function doPlay(v, startWallMs) {
        if (startWallMs) {
            var liveEl = (effectiveNowMs() - startWallMs) / 1000;
            if (liveEl < 0) liveEl = 0;
            if (v.duration && !isNaN(v.duration)) liveEl = Math.min(liveEl, v.duration - 0.05);
            v.currentTime = liveEl;
        }
        var p = v.play();
        if (p && typeof p.catch === 'function') {
            p.catch(function () { showTapToPlay(v, startWallMs); });
        }
    }

    function showTapToPlay(v, startWallMs) {
        try {
            if (document.getElementById('cf-tap-play')) return;
            var btn = document.createElement('div');
            btn.id = 'cf-tap-play';
            btn.style.cssText = 'position:absolute;inset:0;display:flex;align-items:center;justify-content:center;background:rgba(0,0,0,0.45);cursor:pointer;z-index:20;';
            btn.innerHTML = '<div style="width:64px;height:64px;border-radius:50%;background:rgba(255,255,255,.9);display:flex;align-items:center;justify-content:center;">' +
                '<svg width="28" height="28" viewBox="0 0 24 24" fill="#111"><polygon points="5,3 19,12 5,21"/></svg></div>';
            var par = v.parentElement || document.body;
            if (getComputedStyle(par).position === 'static') par.style.position = 'relative';
            par.appendChild(btn);
            btn.addEventListener('click', function () {
                try { par.removeChild(btn); } catch (e) {}
                doPlay(v, startWallMs);
            }, { once: true });
        } catch (e) {}
    }

    function waitForBuffer(v, startWallMs) {
        /* Always wait exactly 10 seconds before starting playback.
         * During those 10s the browser downloads segments silently so
         * the video starts smoothly with no buffering stutter.
         * After 10s, play from the exact live position (join_time + 10s - start). */
        var WAIT_MS = 10000;   /* fixed 10-second pre-load wait for all devices */
        var waited = 0;
        v.pause();
        var bufTimer = setInterval(function () {
            waited += 500;
            if (waited < WAIT_MS) return;   /* always wait the full 10 seconds */
            clearInterval(bufTimer);
            doPlay(v, startWallMs);
        }, 500);
    }

    function startWallClockSync(v, startWallMs) {
        if (wallClockSyncTimer) clearInterval(wallClockSyncTimer);
        wallClockSyncTimer = setInterval(function () {
            if (liveEdgeStartMs == null || !v.duration) return;
            var target = (effectiveNowMs() - liveEdgeStartMs) / 1000;
            if (target >= v.duration) {
                clearInterval(wallClockSyncTimer);
                wallClockSyncTimer = null;
                return;
            }
            /* Only seek if badly out of sync (> 10s) — seeks drop buffered data and stall playback. */
            var drift = Math.abs(v.currentTime - target);
            if (drift > 10) {
                v.currentTime = Math.min(target, v.duration - 0.05);
            }
        }, 15000); /* check every 15s */
    }

    var _bgPreloadEl = null;
    var _bgPreloadUrl = '';

    function startBackgroundPreload(url) {
        /* Create (or reuse) a hidden <video> that downloads the full file into
         * the browser HTTP cache before start time.  The element is invisible,
         * muted, and never plays — its only job is to pull bytes from the server
         * so they land in cache.  When the real <video> requests the same URL it
         * gets served from cache immediately with no network round-trip. */
        if (_bgPreloadUrl === url && _bgPreloadEl) return;  /* already running */
        stopBackgroundPreload();
        try {
            var el = document.createElement('video');
            el.style.cssText = 'position:fixed;width:1px;height:1px;top:-9999px;left:-9999px;opacity:0;pointer-events:none;';
            el.muted = true;
            el.preload = 'auto';
            el.setAttribute('playsinline', '');
            el.setAttribute('webkit-playsinline', '');
            var src = document.createElement('source');
            src.src = url;
            src.type = mimeForUrl(url.split('#')[0]);
            el.appendChild(src);
            document.body.appendChild(el);
            el.load();   /* kick off download immediately */
            _bgPreloadEl = el;
            _bgPreloadUrl = url;
        } catch (e) {}
    }

    function stopBackgroundPreload() {
        try {
            if (_bgPreloadEl) {
                /* Destroy attached hls.js instance if present */
                if (_bgPreloadEl._bgHls) {
                    try { _bgPreloadEl._bgHls.destroy(); } catch (e) {}
                    _bgPreloadEl._bgHls = null;
                }
                _bgPreloadEl.pause();
                _bgPreloadEl.removeAttribute('src');
                while (_bgPreloadEl.firstChild) _bgPreloadEl.removeChild(_bgPreloadEl.firstChild);
                _bgPreloadEl.load();
                if (_bgPreloadEl.parentElement) _bgPreloadEl.parentElement.removeChild(_bgPreloadEl);
            }
        } catch (e) {}
        _bgPreloadEl = null;
        _bgPreloadUrl = '';
    }

    function handleLatestVideo(lv) {
        /* API drops hls_url after broadcast ends; stop player. */
        if (!lv || !lv.hls_url) {
            if (lastUrl && (!lv || lv.requires_authentication === false)) {
                detachCockfightVideos();
            }
            return;
        }

        var hlsUrl = lv.hls_url;
        var schedIso = lv.start || '';
        var streamKey = hlsUrl + '|' + schedIso;

        if (streamKey !== lastPollStreamKey) {
            clearScheduleTimers();
            lastPollStreamKey = streamKey;
            lastAppliedSyncKey = '';
            pendingStreamKey = '';
        }

        var startMs = schedIso ? Date.parse(schedIso) : NaN;
        var hasSchedule = schedIso && !isNaN(startMs);

        if (!hasSchedule) {
            clearScheduleTimers();
            applyHlsSynced(hlsUrl, null);
            return;
        }

        var now = effectiveNowMs();
        if (now < startMs) {
            if (pendingStartTimer && pendingStreamKey === streamKey) return;
            clearScheduleTimers();
            pendingStreamKey = streamKey;
            lastUrl = hlsUrl;

            /* ── Background HLS pre-load before start time ──────────────────────
             * Attach hls.js to a hidden element so it starts downloading the
             * same .ts segments the real player will use — all served from
             * cache when start time hits.
             * ─────────────────────────────────────────────────────────────────── */
            loadHlsJs(function (err) {
                if (err || typeof Hls === 'undefined') return;
                if (_bgPreloadEl) stopBackgroundPreload();
                try {
                    var el = document.createElement('video');
                    el.style.cssText = 'position:fixed;width:1px;height:1px;top:-9999px;left:-9999px;opacity:0;pointer-events:none;';
                    el.muted = true;
                    el.setAttribute('playsinline', '');
                    document.body.appendChild(el);
                    var bgHls = new Hls({ maxBufferLength: 60, maxMaxBufferLength: 60, enableWorker: true });
                    bgHls.loadSource(hlsUrl);
                    bgHls.attachMedia(el);
                    _bgPreloadEl = el;
                    _bgPreloadUrl = hlsUrl;
                    el._bgHls = bgHls;
                } catch (e) {}
            });

            pendingStartTimer = setTimeout(function () {
                pendingStartTimer = null;
                pendingStreamKey = '';
                stopBackgroundPreload();
                applyHlsSynced(hlsUrl, startMs, streamKey);
            }, Math.max(0, startMs - effectiveNowMs()) + 100);
            return;
        }

        if (lastAppliedSyncKey === streamKey && targetVideos().length) return;
        applyHlsSynced(hlsUrl, startMs, streamKey);
    }

    function authFetchHeaders() {
        var headers = {};
        try {
            var keys = ['access', 'access_token', 'token', 'jwt'];
            for (var i = 0; i < keys.length; i++) {
                var t = localStorage.getItem(keys[i]) || sessionStorage.getItem(keys[i]);
                if (t && typeof t === 'string' && t.length > 8) {
                    headers['Authorization'] = 'Bearer ' + t.replace(/^Bearer\s+/i, '');
                    break;
                }
            }
        } catch (e) {}
        return headers;
    }

    function poll() {
        fetch(INFO_URL, {
            credentials: 'same-origin',
            cache: 'no-store',
            headers: authFetchHeaders(),
        })
            .then(function (r) { return r.json(); })
            .then(function (d) {
                var lv = d && d.latest_round_video;
                try {
                    if (lv && lv.server_time) {
                        var srv = Date.parse(lv.server_time);
                        if (!isNaN(srv)) clockSkewMs = srv - Date.now();
                    }
                } catch (eSk) {}
                handleLatestVideo(lv);
            })
            .catch(function () {});
    }

    function scheduleRedock() {
        if (!lastUrl) return;
        clearTimeout(dockTimer);
        dockTimer = setTimeout(function () {
            /* If same video is playing at roughly the right position, skip full reload — just resync. */
            if (liveEdgeStartMs != null && lastAppliedSyncKey) {
                var vids = targetVideos();
                var urlBase = lastUrl.split('?token=')[0];
                var allOk = vids.length > 0 && vids.every(function (v) {
                    return videoBaseUrl(v) === urlBase && v.readyState >= 2 && !v.paused;
                });
                if (allOk) {
                    vids.forEach(function (v) { softSyncPosition(v, liveEdgeStartMs); });
                    return;
                }
            }
            lastAppliedSyncKey = '';
            poll();
        }, 500);
    }

    try {
        var mo = new MutationObserver(scheduleRedock);
        mo.observe(document.documentElement, { childList: true, subtree: true });
    } catch (e) {}

    poll();
    setInterval(poll, POLL_MS);
    window.addEventListener('hashchange', poll);
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', poll);
    }
    window.__pollCockfightLatestVideo = poll;
})();
"""
    resp = HttpResponse(js, content_type='application/javascript; charset=utf-8')
    resp['Cache-Control'] = 'no-store, max-age=0'
    return resp


@never_cache
def serve_react_app(request, path=''):
    """Serve React app - serves index.html for all routes except API/admin/download. Never crash to avoid 502."""
    try:
        request_path = (request.path or '').strip('/')
        download_paths = ['apk', 'download-apk', 'app.apk', 'gundu-ata.apk', 'download.apk']
        if request_path in download_paths or (request_path or '').endswith('.apk') or request_path.startswith('download/apk') or request_path.startswith('apk/download'):
            return HttpResponse("This endpoint should be handled by download_apk view. If you see this, there's a URL routing issue.", status=404)

        react_build_dir = getattr(settings, 'REACT_BUILD_DIR', None)
        if react_build_dir is not None:
            react_build_dir = os.path.normpath(str(react_build_dir))

        if not react_build_dir or not os.path.exists(react_build_dir):
            # Return 200 with minimal page so root never 5xx (avoids 502 from proxy)
            return HttpResponse("""
            <!DOCTYPE html>
            <html><head><meta charset="utf-8"><title>Gundu Ata</title></head>
            <body style="font-family:sans-serif;padding:40px;text-align:center;">
            <h1>Gundu Ata</h1>
            <p>App is running. <a href="/api/">API</a> | <a href="/game-admin/">Admin</a></p>
            </body></html>
            """, content_type='text/html', status=200)

        request_path = (request.path or '').lstrip('/')
        if request_path and '.' in request_path:
            base_real = os.path.realpath(react_build_dir)
            file_path = os.path.realpath(os.path.normpath(os.path.join(react_build_dir, request_path)))
            if not file_path.startswith(base_real):
                file_path = os.path.join(react_build_dir, 'assets', os.path.basename(request_path))
                file_path = os.path.realpath(file_path) if os.path.exists(file_path) else None
            if file_path and os.path.exists(file_path) and os.path.isfile(file_path) and file_path.startswith(base_real):
                content_type = 'application/octet-stream'
                if file_path.endswith('.js'):
                    content_type = 'application/javascript'
                elif file_path.endswith('.css'):
                    content_type = 'text/css'
                elif file_path.endswith('.png'):
                    content_type = 'image/png'
                elif file_path.endswith(('.jpg', '.jpeg')):
                    content_type = 'image/jpeg'
                elif file_path.endswith('.svg'):
                    content_type = 'image/svg+xml'
                return FileResponse(open(file_path, 'rb'), content_type=content_type)

        index_path = os.path.join(react_build_dir, 'index.html')
        if os.path.exists(index_path):
            with open(index_path, 'r', encoding='utf-8') as f:
                content = f.read()
            if _COCKFIGHT_HOOK_SNIPPET not in content:
                m = re.search(r'</body>', content, flags=re.IGNORECASE)
                if m:
                    content = content[: m.start()] + _COCKFIGHT_HOOK_SNIPPET + content[m.start() :]
                else:
                    content = content + _COCKFIGHT_HOOK_SNIPPET
            return HttpResponse(content, content_type='text/html')
        return HttpResponse("React app index.html not found", status=404)
    except Exception as e:
        import logging
        logging.getLogger('django').exception("serve_react_app error")
        return HttpResponse(
            f"<html><body><h1>Error</h1><p>Something went wrong.</p></body></html>",
            content_type='text/html',
            status=500
        )


@never_cache
def home(request):
    """Root URL: serve the React build (same as SPA catch-all), not a separate marketing page."""
    return serve_react_app(request, path='')


@never_cache
def root_maintenance(request):
    """Homepage disabled for browser frontend: show maintenance page (503)."""
    import time
    enabled, until = _get_maintenance_info()
    now = int(time.time())

    # If maintenance is not enabled, still show a generic maintenance page on root as requested.
    remaining_seconds = max(0, (int(until) - now)) if until else 0
    remaining_hours = remaining_seconds // 3600
    remaining_minutes = (remaining_seconds % 3600) // 60

    countdown_html = ""
    if until:
        until_js = int(until) * 1000
        countdown_html = f"""
        <p class="duration" id="maintenance-duration">We'll be back in <span id="countdown">--</span></p>
        <script>
        (function(){{
            var until = {until_js};
            function update(){{
                var now = Date.now();
                if (now >= until) {{ document.getElementById("countdown").textContent = "any moment"; return; }}
                var s = Math.floor((until - now) / 1000);
                var m = Math.floor(s / 60);
                var h = Math.floor(m / 60);
                m = m % 60;
                document.getElementById("countdown").textContent = (h>0 ? (h + "h ") : "") + m + "m";
            }}
            update();
            setInterval(update, 1000);
        }})();
        </script>
        """
    else:
        countdown_html = f"""
        <p class="duration">Website is temporarily unavailable.</p>
        <p class="duration" style="opacity:0.9">Please use the Android app or try again later.</p>
        """

    html = f"""<!DOCTYPE html>
    <html lang="en">
    <head>
      <meta charset="utf-8" />
      <meta name="viewport" content="width=device-width, initial-scale=1" />
      <title>Gundu Ata - Maintenance</title>
      <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Arial, sans-serif; margin:0; background:#0f172a; color:#e2e8f0; }}
        .wrap {{ max-width: 720px; margin: 0 auto; padding: 56px 20px; text-align:center; }}
        h1 {{ font-size: 34px; margin: 0 0 10px; }}
        .duration {{ font-size: 16px; margin: 10px 0; color:#cbd5e1; }}
        .card {{ margin-top: 24px; padding: 18px; border-radius: 14px; background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.12); }}
        a {{ color: #93c5fd; }}
        .small {{ font-size: 13px; opacity: 0.8; }}
      </style>
    </head>
    <body>
      <div class="wrap">
        <h1>Under Maintenance</h1>
        {countdown_html}
        <div class="card">
          <div class="small">Status: {"ON" if enabled else "OFF"}{"" if not until else f" • Remaining ~ {remaining_hours}h {remaining_minutes}m"}</div>
          <div class="small" style="margin-top:8px">Admin: <a href="/game-admin/">/game-admin/</a> • API: <a href="/api/">/api/</a></div>
        </div>
      </div>
    </body>
    </html>"""
    return HttpResponse(html, content_type='text/html', status=503)


# Filename shown in the browser download dialog (RFC 5987 filename* for UTF-8 / spaces).
APK_DOWNLOAD_DISPLAY_NAME = "Gundu ata.apk"


@never_cache
def download_apk(request):
    """Serve the latest APK file for download"""
    import logging
    logger = logging.getLogger('django')
    
    # Log that this view was called
    logger.info(f"DOWNLOAD_APK VIEW CALLED - Path: {request.path}, Method: {request.method}")
    print(f"DOWNLOAD_APK VIEW CALLED - Path: {request.path}, Method: {request.method}")
    
    # Try multiple possible locations (check both string and Path objects)
    possible_paths = [
        # STATIC_ROOT paths
        str(settings.STATIC_ROOT / 'assets' / 'gundu_ata_latest.apk'),
        str(settings.STATIC_ROOT / 'apks' / 'gundu_ata_latest.apk'),
        # BASE_DIR paths
        str(settings.BASE_DIR / 'staticfiles' / 'assets' / 'gundu_ata_latest.apk'),
        str(settings.BASE_DIR / 'staticfiles' / 'apks' / 'gundu_ata_latest.apk'),
        str(settings.BASE_DIR / 'static' / 'apks' / 'gundu_ata_latest.apk'),
        str(settings.BASE_DIR / 'static' / 'assets' / 'gundu_ata_latest.apk'),
        # Gundu_ata_apk-1 (primary source for present)
        # Legacy android_app paths (fallback)
        str(settings.BASE_DIR.parent / 'android_app' / 'Gundu_ata_apk' / 'Gundu Ata 3.apk'),
        str(settings.BASE_DIR.parent / 'android_app' / 'Gundu_ata_apk' / 'Gundu Ata.apk'),
        # Android app build output (if building locally)
        str(settings.BASE_DIR.parent / 'android_app' / 'app' / 'build' / 'outputs' / 'apk' / 'debug' / 'app-debug.apk'),
    ]
    
    apk_path = None
    for path in possible_paths:
        if os.path.exists(path):
            apk_path = path
            logger.info(f"APK found at: {apk_path}")
            print(f"APK found at: {apk_path}")
            break
    
    if not apk_path:
        error_msg = f"APK file not found in any of these locations:\n" + "\n".join([f"  - {p}" for p in possible_paths])
        logger.error(error_msg)
        print(error_msg)
        return HttpResponse(f"APK file not found. Please contact support.\n\nChecked locations:\n{error_msg}", status=404, content_type='text/plain')
    
    try:
        file_size = os.path.getsize(apk_path)
        logger.info(f"Serving APK file: {apk_path} ({file_size} bytes)")
        
        # Use StreamingHttpResponse for large files (better performance)
        def file_iterator(file_path, chunk_size=8192):
            with open(file_path, 'rb') as f:
                while True:
                    chunk = f.read(chunk_size)
                    if not chunk:
                        break
                    yield chunk
        
        response = StreamingHttpResponse(
            file_iterator(apk_path),
            content_type='application/vnd.android.package-archive'
        )
        
        # Set headers to force download (display name; on-disk file may still be gundu_ata_latest.apk)
        fn = APK_DOWNLOAD_DISPLAY_NAME
        response['Content-Disposition'] = (
            f'attachment; filename="{fn}"; filename*=UTF-8\'\'{quote(fn)}'
        )
        response['Content-Length'] = str(file_size)
        response['Content-Type'] = 'application/vnd.android.package-archive'
        response['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response['Pragma'] = 'no-cache'
        response['Expires'] = '0'
        response['X-Content-Type-Options'] = 'nosniff'
        
        return response
    except Exception as e:
        logger.error(f"Error serving APK file: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return HttpResponse(f"Error serving APK file: {str(e)}", status=500, content_type='text/plain')


def custom_404_handler(request, exception):
    """Custom 404 handler that returns JSON for API requests"""
    if request.path.startswith('/api/'):
        return JsonResponse({
            'error': 'Not Found',
            'detail': f'The requested resource "{request.path}" was not found on this server.',
            'path': request.path
        }, status=404)
    # For non-API requests, return the default HTML 404
    from django.views.defaults import page_not_found
    return page_not_found(request, exception)


# ---------------------------------------------------------------------------
# Cricket live events — background poller (every 3 seconds, file-based cache)
# ---------------------------------------------------------------------------
import threading as _threading
import time as _time
import json as _json
import os as _os

_CRICKET_SOURCE_URL = (
    'https://sports.indiadafa.com/xapi/rest/events'
    '?allBettableEvents=true&bettable=true&includeHiddenOutcomes=true'
    '&includeLiveEvents=true&includeMarkets=true&lightWeightResponse=true'
    '&liveAboutToStart=true&liveExcludeLongTermSuspended=true'
    '&liveMarketStatus=OPEN,SUSPENDED&marketFilter=GAME&marketStatus=OPEN'
    '&sortMarketsByPriceDifference=true&sportGroups=REGULAR'
    '&periodType=IN_RUNNING&eventPathIds=215&liveOnly=true'
    '&marketTypeIds=22,24,25,76,622,130069,130079,130081,145136,145142,'
    '145145,10112523,20670747,20670748,40671455,40671613'
    '&periodTypeIds=257,258&excludeLongTermSuspended=true'
    '&excludeMarketByOpponent=false&maxMarketsPerMarketType=5'
    '&maxMarketPerEvent=50&l=en-GB'
)
_CRICKET_CACHE_FILE = '/tmp/cricket_live_cache.json'
_CRICKET_BY_EVENT_CACHE_FILE = '/tmp/cricket_live_by_event.json'
_cricket_poller_started = False
_cricket_poller_lock = _threading.Lock()


def _parse_all_markets_for_event(ev):
    """Return a rich dict for a single raw event with ALL markets and their outcomes."""
    opponents_map = {}
    for opp in (ev.get('opponents') or []):
        opponents_map[opp.get('id')] = opp.get('description', '')
    scores_data = ev.get('scores') or {}
    score_list = scores_data.get('score') or []
    scores = []
    for s in score_list:
        opp_id = s.get('opponentId')
        scores.append({
            'team': opponents_map.get(opp_id, str(opp_id)),
            'score': s.get('formattedPoints', ''),
            'batting': s.get('serving', False),
        })
    clock = ev.get('clock') or {}
    all_markets = []
    for mkt in (ev.get('markets') or []):
        outcomes = []
        for oc in (mkt.get('outcomes') or []):
            price = (oc.get('consolidatedPrice') or {}).get('currentPrice') or {}
            outcomes.append({
                'name': oc.get('description', ''),
                'decimal': price.get('decimal'),
                'price_format': price.get('format'),
                'status': oc.get('status', ''),
            })
        all_markets.append({
            'market_id': mkt.get('id'),
            'market_name': mkt.get('description', ''),
            'market_status': mkt.get('status', ''),
            'outcomes': outcomes,
        })
    return {
        'event_id': ev.get('id'),
        'match_name': ev.get('description', ''),
        'current_innings': ev.get('currentPeriod', ''),
        'clock_status': clock.get('status', ''),
        'scores': scores,
        'all_markets': all_markets,
    }


def _parse_cricket_events(raw_events):
    events = []
    for ev in (raw_events if isinstance(raw_events, list) else []):
        opponents_map = {}
        for opp in (ev.get('opponents') or []):
            opponents_map[opp.get('id')] = opp.get('description', '')
        scores_data = ev.get('scores') or {}
        score_list = scores_data.get('score') or []
        scores = []
        for s in score_list:
            opp_id = s.get('opponentId')
            scores.append({
                'team': opponents_map.get(opp_id, str(opp_id)),
                'score': s.get('formattedPoints', ''),
                'batting': s.get('serving', False),
            })
        clock = ev.get('clock') or {}
        match_odds = []
        for mkt in (ev.get('markets') or []):
            if mkt.get('description', '').strip().lower() == 'head to head':
                for oc in (mkt.get('outcomes') or []):
                    price = (oc.get('consolidatedPrice') or {}).get('currentPrice') or {}
                    match_odds.append({
                        'team': oc.get('description', ''),
                        'decimal': price.get('decimal'),
                        'price_format': price.get('format'),
                    })
                break
        events.append({
            'event_id': ev.get('id'),
            'match_name': ev.get('description', ''),
            'current_innings': ev.get('currentPeriod', ''),
            'clock_status': clock.get('status', ''),
            'scores': scores,
            'match_odds': match_odds,
        })
    return events


def _cricket_poller():
    import requests as _req
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'en-GB,en;q=0.9',
        'Referer': 'https://sports.indiadafa.com/',
        'Origin': 'https://sports.indiadafa.com',
    }
    while True:
        try:
            resp = _req.get(_CRICKET_SOURCE_URL, timeout=8, headers=headers)
            resp.raise_for_status()
            raw = resp.json()
            parsed = _parse_cricket_events(raw)
            # Write list cache (used by /api/cricket/live-events/)
            payload = _json.dumps({
                'count': len(parsed),
                'events': parsed,
                'last_updated': _time.time(),
            })
            tmp = _CRICKET_CACHE_FILE + '.tmp'
            with open(tmp, 'w') as f:
                f.write(payload)
            _os.replace(tmp, _CRICKET_CACHE_FILE)
            # Write per-event indexed cache with ALL markets (used by /api/cricket/live-odds/)
            raw_list = raw if isinstance(raw, list) else []
            ts = _time.time()
            by_event = {
                str(ev.get('id')): _parse_all_markets_for_event(ev)
                for ev in raw_list
                if ev.get('id') is not None
            }
            by_event_payload = {'last_updated': ts, 'events': by_event}
            tmp2 = _CRICKET_BY_EVENT_CACHE_FILE + '.tmp'
            with open(tmp2, 'w') as f:
                f.write(_json.dumps(by_event_payload))
            _os.replace(tmp2, _CRICKET_BY_EVENT_CACHE_FILE)
        except Exception:
            pass
        _time.sleep(3)


def _ensure_cricket_poller():
    global _cricket_poller_started
    if _cricket_poller_started:
        return
    with _cricket_poller_lock:
        if _cricket_poller_started:
            return
        _cricket_poller_started = True
        t = _threading.Thread(target=_cricket_poller, daemon=True)
        t.start()


@api_view(['GET'])
@permission_classes([AllowAny])
def live_cricket_events(request):
    """
    Live cricket events — updated every 3 seconds from indiadafa sports feed.
    GET /api/cricket/live-events/
    """
    _ensure_cricket_poller()
    try:
        with open(_CRICKET_CACHE_FILE, 'r') as f:
            data = _json.load(f)
        # Sort: matches with odds first, no odds at the bottom
        events = data.get('events', [])
        events.sort(key=lambda e: 0 if e.get('match_odds') else 1)
        data['events'] = events
        return Response(data)
    except Exception:
        return Response({
            'count': 0,
            'events': [],
            'message': 'Please come back after some time',
        })


# ---------------------------------------------------------------------------
# Cricket pre-match events — background poller (every 10 seconds, file-based)
# ---------------------------------------------------------------------------
_CRICKET_PRE_SOURCE_URL = 'https://sports.indiadafa.com/xapi/rest/events?hash=968a9178b351ab653bf703fb26c08427&l=en-GB'
_CRICKET_PRE_CACHE_FILE = '/tmp/cricket_pre_cache.json'
_cricket_pre_poller_started = False
_cricket_pre_poller_lock = _threading.Lock()


def _cricket_pre_poller():
    import requests as _req
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'en-GB,en;q=0.9',
        'Referer': 'https://sports.indiadafa.com/',
        'Origin': 'https://sports.indiadafa.com',
    }
    while True:
        try:
            resp = _req.get(_CRICKET_PRE_SOURCE_URL, timeout=10, headers=headers)
            resp.raise_for_status()
            raw = resp.json()
            parsed = _parse_cricket_events(raw)
            payload = _json.dumps({
                'count': len(parsed),
                'events': parsed,
                'last_updated': _time.time(),
            })
            tmp = _CRICKET_PRE_CACHE_FILE + '.tmp'
            with open(tmp, 'w') as f:
                f.write(payload)
            _os.replace(tmp, _CRICKET_PRE_CACHE_FILE)
        except Exception:
            pass
        _time.sleep(10)


def _ensure_cricket_pre_poller():
    global _cricket_pre_poller_started
    if _cricket_pre_poller_started:
        return
    with _cricket_pre_poller_lock:
        if _cricket_pre_poller_started:
            return
        _cricket_pre_poller_started = True
        t = _threading.Thread(target=_cricket_pre_poller, daemon=True)
        t.start()


@api_view(['GET'])
@permission_classes([AllowAny])
def cricket_live_odds_single_match(request):
    """
    Live odds for a single match.
    GET /api/cricket/live-odds/<event_id>/
    Returns event_id, match_name, match_odds for the requested event from the live cache.
    """
    event_id = request.query_params.get('event_id') or request.GET.get('event_id')
    if not event_id:
        return Response({'error': 'event_id query parameter is required.'}, status=400)
    try:
        event_id = int(event_id)
    except (ValueError, TypeError):
        return Response({'error': 'event_id must be an integer.'}, status=400)

    _ensure_cricket_poller()
    try:
        with open(_CRICKET_BY_EVENT_CACHE_FILE, 'r') as f:
            cache = _json.load(f)
        by_event = cache.get('events', cache)  # backwards-compat if old cache exists
        match = by_event.get(str(event_id))
        if match is None:
            return Response({'error': 'Match not found.'}, status=404)
        return Response({
            'event_id': match['event_id'],
            'match_name': match.get('match_name', ''),
            'current_innings': match.get('current_innings'),
            'clock_status': match.get('clock_status'),
            'scores': match.get('scores'),
            'all_markets': match.get('all_markets', []),
            'last_updated': cache.get('last_updated'),
            'poll_interval_seconds': 3,
        })
    except Exception:
        return Response({'error': 'Please come back after some time.'}, status=503)


@api_view(['GET'])
@permission_classes([AllowAny])
def cricket_pre_events(request):
    """
    Pre-match cricket events — updated every 10 seconds from indiadafa sports feed.
    GET /api/cricket/pre-events/
    """
    _ensure_cricket_pre_poller()
    try:
        with open(_CRICKET_PRE_CACHE_FILE, 'r') as f:
            data = _json.load(f)
        events = data.get('events', [])
        # Filter out virtual/simulated matches
        events = [
            e for e in events
            if '(virtual)' not in e.get('match_name', '').lower()
            and ' srl' not in e.get('match_name', '').lower()
            and not e.get('match_name', '').lower().endswith(' srl')
        ]
        # Only return event_id, match_name, match_odds
        events = [
            {
                'event_id': e['event_id'],
                'match_name': e['match_name'],
                'match_odds': e['match_odds'],
            }
            for e in events
        ]
        events.sort(key=lambda e: 0 if e.get('match_odds') else 1)
        data['events'] = events
        data['count'] = len(events)
        return Response(data)
    except Exception:
        return Response({
            'count': 0,
            'events': [],
            'message': 'Please come back after some time',
        })


# ---------------------------------------------------------------------------
# Cricket pre-match odds for a single event — on-demand with 30s file cache
# ---------------------------------------------------------------------------
_CRICKET_PREEVENT_CACHE_DIR = '/tmp/cricket_preevent_cache'
_CRICKET_PREEVENT_CACHE_TTL = 15  # seconds


def _preevent_cache_path(event_id):
    return _os.path.join(_CRICKET_PREEVENT_CACHE_DIR, f'{event_id}.json')


def _fetch_preevent_odds(event_id):
    import requests as _req
    url = (
        f'https://sports.indiadafa.com/xapi/rest/events/{event_id}'
        '?bettable=true&marketStatus=OPEN&periodType=PRE_MATCH'
        '&includeMarkets=true&lightWeightResponse=true&l=en-GB'
    )
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'en-GB,en;q=0.9',
        'Referer': 'https://sports.indiadafa.com/',
        'Origin': 'https://sports.indiadafa.com',
    }
    resp = _req.get(url, timeout=10, headers=headers)
    resp.raise_for_status()
    ev = resp.json()

    all_markets = []
    for mkt in (ev.get('markets') or []):
        outcomes = []
        for oc in (mkt.get('outcomes') or []):
            price = (oc.get('consolidatedPrice') or {}).get('currentPrice') or {}
            outcomes.append({
                'name': oc.get('description', ''),
                'decimal': price.get('decimal'),
                'price_format': price.get('format'),
                'status': oc.get('status', ''),
            })
        all_markets.append({
            'market_id': mkt.get('id'),
            'market_name': mkt.get('description', ''),
            'market_status': mkt.get('status', ''),
            'outcomes': outcomes,
        })

    return {
        'event_id': ev.get('id'),
        'match_name': ev.get('description', ''),
        'event_date': ev.get('eventDate'),
        'current_innings': ev.get('currentPeriod', ''),
        'all_markets': all_markets,
        'total_markets': len(all_markets),
        'last_updated': _time.time(),
        'cache_ttl_seconds': _CRICKET_PREEVENT_CACHE_TTL,
    }


@api_view(['GET'])
@permission_classes([AllowAny])
def cricket_preevent_odds(request):
    """
    Pre-match odds for a single event — fetched on demand, cached 30 seconds per event.
    GET /api/cricket/preevent-odds/?event_id=<event_id>
    """
    event_id = request.query_params.get('event_id') or request.GET.get('event_id')
    if not event_id:
        return Response({'error': 'event_id query parameter is required.'}, status=400)
    try:
        event_id = int(event_id)
    except (ValueError, TypeError):
        return Response({'error': 'event_id must be an integer.'}, status=400)

    _os.makedirs(_CRICKET_PREEVENT_CACHE_DIR, exist_ok=True)
    cache_file = _preevent_cache_path(event_id)

    # Serve from cache if still fresh
    try:
        mtime = _os.path.getmtime(cache_file)
        if _time.time() - mtime < _CRICKET_PREEVENT_CACHE_TTL:
            with open(cache_file, 'r') as f:
                return Response(_json.load(f))
    except (OSError, ValueError):
        pass

    # Fetch fresh data from upstream
    try:
        data = _fetch_preevent_odds(event_id)
        tmp = cache_file + '.tmp'
        with open(tmp, 'w') as f:
            f.write(_json.dumps(data))
        _os.replace(tmp, cache_file)
        return Response(data)
    except Exception as exc:
        if '404' in str(exc):
            return Response({'error': 'Match not found.'}, status=404)
        return Response({'error': 'Please come back after some time.'}, status=503)
