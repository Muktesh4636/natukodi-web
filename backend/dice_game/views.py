from django.http import HttpResponse, JsonResponse, FileResponse, StreamingHttpResponse
from django.conf import settings
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework import status
from rest_framework.response import Response
import os
from game.utils import get_game_setting
from .maintenance_middleware import _get_maintenance_info


@api_view(['GET'])
@permission_classes([AllowAny])
def health(request):
    """Minimal health check; no Redis or DB. Use for load balancer / 502 debugging."""
    return JsonResponse({'status': 'ok'}, status=200)


@api_view(['GET'])
@permission_classes([AllowAny])
def time_now(request):
    """Public current server time (UTC + IST) for clients."""
    import time
    from datetime import datetime
    import pytz

    now_utc = datetime.now(pytz.UTC)
    ist = pytz.timezone('Asia/Kolkata')
    now_ist = now_utc.astimezone(ist)
    epoch = int(time.time())

    return JsonResponse(
        {
            'utc': now_utc.isoformat(),
            'ist': now_ist.isoformat(),
            'epoch': epoch,
        },
        status=200,
    )


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

    Backed by GameSettings so admins can update without redeploy:
    - SUPPORT_WHATSAPP_NUMBER  (example: +919876543210)
    - SUPPORT_TELEGRAM        (example: +919876543210)
    """
    whatsapp = get_game_setting('SUPPORT_WHATSAPP_NUMBER', '+919876543210')
    telegram = get_game_setting('SUPPORT_TELEGRAM', '+919876543210')

    return Response({
        'whatsapp_number': str(whatsapp).strip() if whatsapp is not None else '',
        'telegram': str(telegram).strip() if telegram is not None else '',
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
    """Public landing website for gunduata.club (royal 3D landing like http://gunduata.site/)."""
    # Lightweight single response. WebGL is optional; page still looks good without it.
    html = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Gundu Ata - Experience the Royal Dice Game</title>
  <style>
    :root{
      --bg0:#040b12; --bg1:#061725;
      --text:#f1f7fb; --muted:#a7bac9;
      --line:rgba(255,255,255,.12);
      --gold0:#ffd24a; --gold1:#f7b500;
      --rose:#ff4fd8; --cyan:#2de2ff; --violet:#7c3aed;
      --shadow: 0 18px 60px rgba(0,0,0,.45);
    }
    *{box-sizing:border-box}
    body{
      margin:0;
      font-family: ui-sans-serif, -apple-system, BlinkMacSystemFont, \"Segoe UI\", Roboto, \"Helvetica Neue\", Arial;
      background:
        radial-gradient(1100px 650px at 15% 0%, rgba(45,226,255,.22) 0%, rgba(4,11,18,0) 60%),
        radial-gradient(900px 650px at 85% 10%, rgba(255,79,216,.16) 0%, rgba(4,11,18,0) 55%),
        radial-gradient(900px 650px at 50% 120%, rgba(124,58,237,.18) 0%, rgba(4,11,18,0) 55%),
        linear-gradient(180deg, var(--bg0) 0%, var(--bg1) 60%);
      color:var(--text);
      overflow-x:hidden;
    }
    a{color:inherit}
    .bg3d{position:fixed;inset:0;z-index:0;pointer-events:none;opacity:.92}
    .grain{position:fixed;inset:0;z-index:1;pointer-events:none;opacity:.12;
      background-image:url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='120' height='120'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='.9' numOctaves='3' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='120' height='120' filter='url(%23n)' opacity='.35'/%3E%3C/svg%3E\");
      mix-blend-mode:overlay;
    }
    .content{position:relative;z-index:2}
    .container{max-width:1150px;margin:0 auto;padding:26px}

    .nav{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:12px 0}
    .brand{display:flex;align-items:center;gap:12px;font-weight:900;letter-spacing:.4px}
    .logo{width:42px;height:42px;border-radius:14px;display:grid;place-items:center;
      background:linear-gradient(135deg, rgba(255,210,74,.95), rgba(255,79,216,.65));
      box-shadow: 0 14px 40px rgba(247,181,0,.18);
      color:#0a1a26;font-size:18px;
    }
    .navlinks{display:flex;gap:10px;flex-wrap:wrap;justify-content:flex-end}
    .navlinks a{text-decoration:none;border:1px solid var(--line);padding:9px 12px;border-radius:12px;background:rgba(255,255,255,.04)}
    .navlinks a:hover{background:rgba(255,255,255,.07)}

    .pill{display:inline-flex;align-items:center;gap:8px;border:1px solid var(--line);background:rgba(255,255,255,.05);
      padding:8px 12px;border-radius:999px;color:var(--muted);font-weight:800;font-size:12px}
    .pill strong{color:#0a1a26;background:linear-gradient(90deg,var(--gold0),var(--gold1));padding:2px 8px;border-radius:999px}
    .card{border:1px solid var(--line);background:linear-gradient(180deg, rgba(255,255,255,.09), rgba(255,255,255,.03));
      border-radius:20px;padding:18px;backdrop-filter: blur(10px); box-shadow: var(--shadow)}

    .heroWrap{margin-top:8px;display:grid;grid-template-columns:1.15fr .85fr;gap:18px;align-items:stretch}
    h1{font-size:56px;line-height:1.02;margin:12px 0 12px}
    .glow{display:inline-block;background:linear-gradient(90deg,var(--cyan),var(--gold0),var(--rose));
      -webkit-background-clip:text;background-clip:text;color:transparent}
    .sub{color:var(--muted);font-size:16px;line-height:1.6;margin:0 0 14px}
    .cta{display:flex;gap:10px;flex-wrap:wrap;margin-top:12px}
    .btn{display:inline-flex;align-items:center;justify-content:center;gap:10px;text-decoration:none;border-radius:16px;padding:12px 16px;
      font-weight:900;border:1px solid var(--line);background:rgba(255,255,255,.06)}
    .btn.primary{background:linear-gradient(180deg,var(--gold0),var(--gold1));color:#0a1a26;border:none;box-shadow:0 16px 44px rgba(247,181,0,.22)}
    .btn.primary:hover{filter:brightness(1.05)}
    .btn.secondary:hover{background:rgba(255,255,255,.10)}

    .section{margin-top:18px}
    .sectionTitle{display:flex;align-items:center;gap:10px;margin:0 0 10px}
    .sectionTitle h2{margin:0;font-size:20px}
    .dot{width:10px;height:10px;border-radius:50%;background:linear-gradient(90deg,var(--cyan),var(--rose));box-shadow:0 0 18px rgba(45,226,255,.22)}

    .whyGrid{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}
    .tile{border:1px solid var(--line);background:rgba(255,255,255,.04);border-radius:18px;padding:14px}
    .tile b{display:flex;align-items:center;gap:10px;margin-bottom:6px}
    .tile span{color:var(--muted);font-size:13px;line-height:1.5}
    .ico{width:34px;height:34px;border-radius:12px;display:grid;place-items:center;
      background:linear-gradient(135deg, rgba(45,226,255,.25), rgba(255,210,74,.22));
      border:1px solid rgba(255,255,255,.14)}

    .videoFrame{position:relative;overflow:hidden;border-radius:18px;border:1px solid var(--line);
      background:linear-gradient(180deg, rgba(255,255,255,.06), rgba(255,255,255,.02));min-height:320px}
    .videoFrame .label{position:absolute;left:14px;top:14px;z-index:3;background:rgba(0,0,0,.35);border:1px solid rgba(255,255,255,.18);
      padding:8px 10px;border-radius:999px;font-weight:900;font-size:12px;backdrop-filter:blur(8px)}
    .videoFrame .fallback{position:absolute;left:14px;bottom:14px;z-index:3;color:rgba(241,247,251,.8);font-size:12px}
    #gameplay3d{position:absolute;inset:0;width:100%;height:100%}

    .testGrid{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}
    .quote{border:1px solid var(--line);background:rgba(255,255,255,.04);border-radius:18px;padding:14px}
    .stars{color:#ffd24a;letter-spacing:2px;font-weight:900}
    .qText{margin:10px 0;line-height:1.5}
    .who{color:var(--muted);font-size:13px}

    .final{margin-top:18px;display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap}
    .meta{color:var(--muted);font-size:12px}
    .footer{margin:22px 0 8px;color:var(--muted);font-size:12px;display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap}

    @media (prefers-reduced-motion: reduce){ .bg3d{display:none} }
    @media (max-width: 980px){
      .heroWrap{grid-template-columns:1fr}
      h1{font-size:46px}
      .whyGrid,.testGrid{grid-template-columns:1fr}
    }
  </style>
</head>
<body>
  <canvas id="bg3d" class="bg3d"></canvas>
  <div class="grain"></div>
  <div class="content">
    <div class="container">
      <div class="nav">
        <div class="brand">
          <div class="logo">🎲</div>
          <div>
            <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap">
              <div style="font-size:16px">GUNDU ATA</div>
              <div class="pill" style="padding:6px 10px"><strong>Premium</strong> Indian Casino Experience</div>
            </div>
            <div style="color:var(--muted);font-size:12px;margin-top:4px">Roll with Royalty</div>
          </div>
        </div>
        <div class="navlinks">
          <a href="/">Home</a>
          <a href="#gameplay">The Game</a>
          <a href="#winners">Winners</a>
          <a href="/download-apk">Play Now</a>
        </div>
      </div>

      <div class="heroWrap">
        <div class="card">
          <div class="pill">👑 Royal ambience • 🎲 True 3D physics • 💰 Big wins</div>
          <h1><span class="glow">Roll with Royalty</span></h1>
          <p class="sub">
            Step into the most immersive 3D dice game experience. Feel the weight of the cup, hear the rattle of the dice, and claim your fortune.
          </p>
          <div class="cta">
            <a class="btn primary" href="/download-apk">Get the Game</a>
            <a class="btn secondary" href="#gameplay">View Gameplay</a>
          </div>
        </div>

        <div class="card">
          <div class="sectionTitle"><span class="dot"></span><h2>Live Gameplay</h2></div>
          <div id="gameplay" class="videoFrame">
            <div class="label">LIVE GAMEPLAY</div>
            <canvas id="gameplay3d"></canvas>
            <div class="fallback">Your browser does not support WebGL.</div>
          </div>
          <div class="section" style="margin-top:12px">
            <div class="pill">DOWNLOAD NOW • Requires Android 8.0+ • Version 1.0.4</div>
          </div>
        </div>
      </div>

      <div class="section">
        <div class="sectionTitle"><span class="dot"></span><h2>Why Gundu Ata?</h2></div>
        <div class="whyGrid">
          <div class="tile"><b><span class="ico">👑</span> Royal Ambience</b><span>Immerse yourself in a high‑stakes Indian casino environment with stunning visuals.</span></div>
          <div class="tile"><b><span class="ico">🎲</span> True 3D Physics</b><span>Experience realistic dice rolls with smooth animations and responsive controls.</span></div>
          <div class="tile"><b><span class="ico">💰</span> Big Wins</b><span>Join thousands of players winning daily. Your next big jackpot is just a roll away.</span></div>
        </div>
      </div>

      <div id="winners" class="section">
        <div class="sectionTitle"><span class="dot"></span><h2>What Our Players Say</h2></div>
        <div class="testGrid">
          <div class="quote"><div class="stars">★★★★★</div><div class="qText\">\"The graphics are unbelievable! The dice physics are spot on.\"</div><div class="who">Rahul S. • Verified Player</div></div>
          <div class="quote"><div class="stars">★★★★★</div><div class="qText\">\"My go‑to game for relaxation. Smooth UI and exciting wins.\"</div><div class="who">Priya K. • Verified Player</div></div>
          <div class="quote"><div class="stars">★★★★★</div><div class="qText\">\"Best dice game — interface is so smooth and the 3D effects are top‑notch.\"</div><div class="who">Amit V. • Verified Player</div></div>
        </div>
      </div>

      <div class="section card">
        <div class="final">
          <div>
            <div class="pill"><strong>Ready to Win?</strong> Download Gundu Ata now.</div>
            <div class="sub" style="margin:10px 0 0">Download the Android app and start playing live rounds in seconds.</div>
            <div class="meta">Support: <a href="/api/support/contacts/">Contacts</a> • Status: <a href="/api/health/">Health</a> • Admin: <a href="/game-admin/">Panel</a></div>
          </div>
          <div class="cta">
            <a class="btn primary" href="/download-apk">DOWNLOAD NOW</a>
            <a class="btn secondary" href="/api/">API</a>
          </div>
        </div>
      </div>

      <div class="footer">
        <div>© 2026 Gundu Ata Games. All rights reserved.</div>
        <div><a href="/download-apk" style="text-decoration:none">Download</a> • <a href="/api/support/contacts/" style="text-decoration:none">Support</a> • <a href="/game-admin/" style="text-decoration:none">Admin</a></div>
      </div>
    </div>
  </div>

  <script>
  (function(){
    try { if (window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches) return; } catch (e) {}
    function hasWebGL(c){ try { return !!(c && (c.getContext('webgl') || c.getContext('experimental-webgl'))); } catch(e){ return false; } }
    var bg = document.getElementById('bg3d');
    var gp = document.getElementById('gameplay3d');
    if (!hasWebGL(bg) && !hasWebGL(gp)) return;

    var script = document.createElement('script');
    script.src = 'https://unpkg.com/three@0.160.0/build/three.min.js';
    script.async = true;
    script.onload = function(){
      init(bg, {count: 10, gameplay:false});
      init(gp, {count: 5, gameplay:true});
    };
    document.head.appendChild(script);

    function init(canvas, opts){
      if (!canvas) return;
      var THREE = window.THREE; if (!THREE) return;
      var renderer = new THREE.WebGLRenderer({ canvas: canvas, antialias: true, alpha: true, powerPreference: 'high-performance' });
      renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.6));
      renderer.setClearColor(0x000000, 0);
      var scene = new THREE.Scene();
      var camera = new THREE.PerspectiveCamera(45, 1, 0.1, 100);
      camera.position.set(0,0,10);
      scene.add(new THREE.AmbientLight(0xffffff, 0.7));
      var dl = new THREE.DirectionalLight(0xffffff, 1.1); dl.position.set(6,8,6); scene.add(dl);
      scene.fog = new THREE.Fog(0x061725, 7, 18);

      function tex(n, a, b){
        var c=document.createElement('canvas'); c.width=256; c.height=256;
        var ctx=c.getContext('2d');
        var g=ctx.createLinearGradient(0,0,256,256); g.addColorStop(0,a); g.addColorStop(1,b);
        ctx.fillStyle=g; ctx.fillRect(0,0,256,256);
        ctx.strokeStyle='rgba(255,255,255,.18)'; ctx.lineWidth=10; ctx.strokeRect(16,16,224,224);
        ctx.fillStyle='rgba(10,26,38,.92)'; ctx.font='900 120px system-ui, -apple-system, Segoe UI, Roboto, Arial';
        ctx.textAlign='center'; ctx.textBaseline='middle'; ctx.fillText(String(n),128,132);
        ctx.fillStyle='rgba(255,255,255,.10)'; ctx.beginPath(); ctx.arc(70,70,60,0,Math.PI*2); ctx.fill();
        return new THREE.CanvasTexture(c);
      }
      var pal=[['#2de2ff','#7c3aed'],['#ffd24a','#ff4fd8'],['#22c55e','#2de2ff'],['#ff4fd8','#7c3aed'],['#ffd24a','#2de2ff'],['#7c3aed','#ffd24a']];
      function dice(){
        var geo=new THREE.BoxGeometry(1.4,1.4,1.4);
        var mats=[];
        for (var i=1;i<=6;i++){
          var p=pal[i-1];
          mats.push(new THREE.MeshStandardMaterial({ map: tex(i,p[0],p[1]), roughness:.35, metalness:.15 }));
        }
        return new THREE.Mesh(geo,mats);
      }
      var group=new THREE.Group(); scene.add(group);
      var ds=[];
      for (var i=0;i<(opts && opts.count ? opts.count : 7);i++){
        var d=dice();
        d.position.set((Math.random()-0.5)*10,(Math.random()-0.5)*6,(Math.random()-0.5)*6);
        d.rotation.set(Math.random()*Math.PI,Math.random()*Math.PI,Math.random()*Math.PI);
        d.userData={rs:(Math.random()*0.7+0.2)*(Math.random()<0.5?-1:1),rt:(Math.random()*0.6+0.15)*(Math.random()<0.5?-1:1),bob:Math.random()*2+0.5};
        group.add(d); ds.push(d);
      }
      var big=dice();
      big.scale.set((opts && opts.gameplay) ? 2.8 : 2.4, (opts && opts.gameplay) ? 2.8 : 2.4, (opts && opts.gameplay) ? 2.8 : 2.4);
      big.position.set((opts && opts.gameplay) ? 0.0 : 2.4, (opts && opts.gameplay) ? 0.0 : -0.2, 0.0);
      group.add(big);

      function resize(){
        var w=canvas.clientWidth || window.innerWidth || 1;
        var h=canvas.clientHeight || window.innerHeight || 1;
        renderer.setSize(w,h,false);
        camera.aspect=w/h; camera.updateProjectionMatrix();
      }
      resize(); window.addEventListener('resize', resize, {passive:true});
      var t0=performance.now(); var last=0;
      function anim(now){
        if (now-last<33){ requestAnimationFrame(anim); return; }
        last=now; var t=(now-t0)*0.001;
        var drift=(opts && opts.gameplay) ? 0.18 : 0.35;
        camera.position.x=Math.sin(t*0.15)*drift;
        camera.position.y=Math.cos(t*0.12)*(drift*0.75);
        camera.lookAt(0,0,0);
        for (var i=0;i<ds.length;i++){
          var d=ds[i];
          d.rotation.x += 0.006 * d.userData.rs;
          d.rotation.y += 0.007 * d.userData.rt;
          d.position.y += Math.sin(t*0.8 + d.userData.bob) * 0.002;
        }
        big.rotation.x += (opts && opts.gameplay) ? 0.008 : 0.006;
        big.rotation.y += (opts && opts.gameplay) ? 0.010 : 0.0075;
        big.rotation.z += (opts && opts.gameplay) ? 0.006 : 0.004;
        renderer.render(scene,camera);
        requestAnimationFrame(anim);
      }
      requestAnimationFrame(anim);
    }
  })();
  </script>
</body>
</html>"""
    return HttpResponse(html, content_type='text/html', status=200)


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
        '/Users/pradyumna/Gundu_ata_apk-1/out/Sikwin_UnityUpdate_v49_signed.apk',
        '/Users/pradyumna/Gundu_ata_apk-1/out/Sikwin_UnityUpdate_v49.apk',
        '/Users/pradyumna/Gundu_ata_apk-1/kotlin/Sikwin_GunduAta_Final_Clean_signed.apk',
        '/Users/pradyumna/Gundu_ata_apk-1/kotlin/Sikwin_GunduAta_Final_Clean.apk',
        '/Users/pradyumna/Gundu_ata_apk-1/gundu_ata/extracted_8/Gundu Ata.apk',
        # Legacy android_app paths (fallback)
        str(settings.BASE_DIR.parent / 'android_app' / 'Gundu_ata_apk' / 'Gundu Ata 3.apk'),
        str(settings.BASE_DIR.parent / 'android_app' / 'Gundu_ata_apk' / 'Gundu Ata.apk'),
        # Android app build output (if building locally)
        str(settings.BASE_DIR.parent / 'android_app' / 'app' / 'build' / 'outputs' / 'apk' / 'debug' / 'app-debug.apk'),
        # Absolute paths (server locations)
        # Common server locations (domain folder varies by deployment)
        '/var/www/gunduata.club/staticfiles/assets/gundu_ata_latest.apk',
        '/var/www/gunduata.club/staticfiles/apks/gundu_ata_latest.apk',
        '/home/ubuntu/apk_of_ata/backend/staticfiles/assets/gundu_ata_latest.apk',
        '/root/apk_of_ata/backend/staticfiles/assets/gundu_ata_latest.apk',
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
        
        # Set headers to force download
        response['Content-Disposition'] = 'attachment; filename="gundu_ata_latest.apk"'
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






