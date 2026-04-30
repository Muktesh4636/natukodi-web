"""Parse PUBLIC_SITE_URL from env for centralized domain / origin configuration."""

from __future__ import annotations

from urllib.parse import urlparse


def parse_public_site_url(raw: str) -> dict[str, str] | None:
    """
    Normalize a public site URL from env.

    Accepts ``https://example.com``, ``example.com`` (https assumed), or ``http://127.0.0.1:8000``.

    Returns dict with ``origin`` (scheme://netloc, no path), ``hostname`` (for ALLOWED_HOSTS),
    and ``url`` (same as origin — canonical base). Returns None if unset or invalid.
    """
    raw = (raw or '').strip()
    if not raw:
        return None
    if not raw.startswith(('http://', 'https://')):
        raw = 'https://' + raw
    parsed = urlparse(raw)
    if not parsed.netloc:
        return None
    hostname = parsed.hostname
    if not hostname:
        return None
    scheme = (parsed.scheme or 'https').lower()
    netloc = parsed.netloc.lower()
    origin = f'{scheme}://{netloc}'.rstrip('/')
    return {
        'origin': origin,
        'hostname': hostname.lower(),
        'url': origin,
    }
