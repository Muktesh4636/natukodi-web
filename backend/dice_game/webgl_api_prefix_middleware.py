"""
WebGL builds hosted under /webgl/ often request APIs with relative paths like "api/game/settings/",
which become /webgl/api/... on the server. Static nginx alias would 404 those; map to /api/... instead.
"""

from django.core.handlers.wsgi import get_script_name


class WebglApiPrefixMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        pi = request.META.get('PATH_INFO', '') or ''
        if pi.startswith('/webgl/api/') or pi == '/webgl/api':
            rest = pi[len('/webgl/api') :].lstrip('/')
            new_pi = '/api/' + rest if rest else '/api/'
            script_name = get_script_name(request.META)
            request.path_info = new_pi
            request.path = '%s/%s' % (script_name.rstrip('/'), new_pi.replace('/', '', 1))
            request.META['PATH_INFO'] = new_pi
            request.resolver_match = None
        return self.get_response(request)
