"""Normalize HTTP_HOST before ALLOWED_HOSTS validation (trailing dot, first forwarded host)."""


class NormalizeHostMiddleware:
    """Strip trailing '.' from Host; avoids DisallowedHost when DNS/clients send FQDN form."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        meta = request.META
        host = meta.get('HTTP_HOST')
        if host:
            host = host.strip()
            if host.endswith('.'):
                meta['HTTP_HOST'] = host[:-1].strip()
        # Some proxies append port oddly; Django handles Host:port — only normalize forwarded chain.
        xfwd = meta.get('HTTP_X_FORWARDED_HOST')
        if xfwd:
            first = xfwd.split(',')[0].strip()
            if first.endswith('.'):
                first = first[:-1].strip()
            if first != xfwd:
                meta['HTTP_X_FORWARDED_HOST'] = first
        return self.get_response(request)
