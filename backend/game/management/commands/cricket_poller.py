"""
cricket_poller
==============
Polls the external sports API every 2 seconds and stores the full JSON
response in Redis under the key  cricket:live_data  (TTL 30s).
Feeds GET /api/cricket/live/ (same Redis cache).

Default URL: PRE_MATCH event feed (see _DEFAULT_CRICKET_URL below).
Override: set env CRICKET_SOURCE_URL to a full query string URL.

Run via:
    python manage.py cricket_poller

Or as a Docker service (see docker-compose.yml cricket_poller service).
"""

import json
import logging
import os
import time

import requests
from django.core.management.base import BaseCommand
from django.utils import timezone

logger = logging.getLogger('cricket_poller')

# Default: event 42477878, pre-match, OPEN markets only (lightweight payload).
_DEFAULT_CRICKET_URL = (
    'https://sports.indiadafa.com/xapi/rest/events/42477878'
    '?bettable=true'
    '&marketStatus=OPEN'
    '&periodType=PRE_MATCH'
    '&includeMarkets=true'
    '&lightWeightResponse=true'
    '&l=en-GB'
)

SOURCE_URL = (os.environ.get('CRICKET_SOURCE_URL') or _DEFAULT_CRICKET_URL).strip()

REDIS_DATA_KEY = 'cricket:live_data'
REDIS_META_KEY = 'cricket:live_meta'
POLL_INTERVAL  = 2      # seconds between each fetch
REDIS_TTL      = 30     # seconds — data expires if poller dies


class Command(BaseCommand):
    help = 'Polls the external sports API every 2 seconds and caches data in Redis.'

    def handle(self, *args, **options):
        from game.utils import get_redis_client
        rc = get_redis_client()
        if rc is None:
            self.stderr.write('ERROR: Cannot connect to Redis. Exiting.')
            return

        self.stdout.write('Cricket poller started. Polling every 2 seconds...')
        session = requests.Session()
        session.headers.update({
            'Accept': 'application/json',
            'User-Agent': 'Mozilla/5.0 (compatible; GunduAtaPoller/1.0)',
        })

        consecutive_errors = 0

        while True:
            start = time.monotonic()
            try:
                resp = session.get(SOURCE_URL, timeout=5)
                resp.raise_for_status()
                parsed = resp.json()
                from game.cricket_feed import normalize_cricket_event_payload

                data = normalize_cricket_event_payload(parsed)
                if not data or data.get("id") is None:
                    logger.warning(
                        "Cricket API JSON could not be normalized to an event (missing id). "
                        "root_type=%s root_keys=%s",
                        type(parsed).__name__,
                        list(parsed.keys())[:15] if isinstance(parsed, dict) else None,
                    )
                    consecutive_errors += 1
                else:
                    fetched_at = timezone.now().isoformat()
                    rc.set(REDIS_DATA_KEY, json.dumps(data), ex=REDIS_TTL)
                    rc.set(REDIS_META_KEY, json.dumps({
                        'fetched_at': fetched_at,
                        'source_url': SOURCE_URL,
                        'status_code': resp.status_code,
                    }), ex=REDIS_TTL)

                    consecutive_errors = 0
                    logger.debug(f'Fetched cricket data at {fetched_at}')

            except requests.exceptions.Timeout:
                consecutive_errors += 1
                logger.warning(f'Cricket API timeout (consecutive errors: {consecutive_errors})')
            except requests.exceptions.HTTPError as e:
                consecutive_errors += 1
                logger.warning(f'Cricket API HTTP error {e} (consecutive errors: {consecutive_errors})')
            except Exception as e:
                consecutive_errors += 1
                logger.error(f'Cricket poller error: {e}', exc_info=True)

            # Back off slightly if repeated errors (max 10s)
            if consecutive_errors > 5:
                sleep_time = min(POLL_INTERVAL * consecutive_errors, 10)
            else:
                sleep_time = POLL_INTERVAL

            elapsed = time.monotonic() - start
            wait = max(0, sleep_time - elapsed)
            time.sleep(wait)
