import re
from django.http import HttpResponsePermanentRedirect


_multi_slash_re = re.compile(r"/{2,}")


class NormalizeSlashesMiddleware:
    """
    Redirect paths containing multiple consecutive slashes to a normalized path.

    This prevents hard-to-debug 404s from clients that accidentally build URLs like:
    https://gunduata.club//api/game/settings/
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path or "/"
        normalized = _multi_slash_re.sub("/", path)
        if normalized != path:
            qs = request.META.get("QUERY_STRING", "")
            url = normalized + (("?" + qs) if qs else "")
            return HttpResponsePermanentRedirect(url)
        return self.get_response(request)

