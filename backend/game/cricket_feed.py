"""
Normalize cricket/sports API JSON from indiadafa (and similar) into one event dict.

The REST response is usually the event object at the root, but some responses may use
wrappers ({event: {...}}, {data: {...}}) or a single-element list.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


def normalize_cricket_event_payload(obj: Any) -> Optional[Dict[str, Any]]:
    """
    Return a single event dict with at least ``id`` when possible, else None.
    """
    if obj is None:
        return None

    if isinstance(obj, list):
        for item in obj:
            if isinstance(item, dict) and item.get("id") is not None:
                cand = _unwrap_event_dict(item)
                if cand is not None:
                    return cand
        return None

    if isinstance(obj, dict):
        return _unwrap_event_dict(obj)

    return None


def _unwrap_event_dict(d: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    # Common envelopes
    for key in ("event", "data", "result", "payload"):
        inner = d.get(key)
        if isinstance(inner, dict) and inner.get("id") is not None:
            return _unwrap_event_dict(inner)

    # Already looks like an event (Dafa uses GAMEEVENT + markets at root)
    if d.get("id") is not None and (
        d.get("eventType") is not None or d.get("sportCode") is not None or "markets" in d
    ):
        return d

    if d.get("id") is not None:
        return d

    return None


def market_is_open_for_betting(market_obj: Dict[str, Any]) -> bool:
    """True only when the market accepts bets (open book)."""
    st = (market_obj.get("status") or "").strip().lower()
    return st == "open"


def extract_outcome_decimal_odds(outcome_obj: Dict[str, Any]) -> Optional[float]:
    """
    Read decimal odds from a Dafa-style outcome. Tries several shapes used in light/full payloads.
    """
    if not isinstance(outcome_obj, dict):
        return None

    cp = outcome_obj.get("consolidatedPrice")
    if isinstance(cp, dict):
        cur = cp.get("currentPrice")
        if isinstance(cur, dict):
            dec = cur.get("decimal")
            if dec is not None:
                try:
                    return float(dec)
                except (TypeError, ValueError):
                    pass
        dec = cp.get("decimal")
        if dec is not None:
            try:
                return float(dec)
            except (TypeError, ValueError):
                pass

    # Fallbacks seen in some feeds
    for path in (
        ("price", "decimal"),
        ("currentPrice", "decimal"),
        ("odds",),
    ):
        ref: Any = outcome_obj
        try:
            for p in path:
                if isinstance(ref, dict):
                    ref = ref.get(p)
                else:
                    ref = None
                    break
            if ref is not None:
                return float(ref)
        except (TypeError, ValueError):
            continue

    return None
