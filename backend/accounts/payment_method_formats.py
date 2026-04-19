"""
Payment method API response builders — legacy array, payment_details array, and wrapped { data }.
Field names align with common client parsers (aliases documented in get_payment_methods).
"""
from __future__ import annotations

from typing import Any, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from django.http import HttpRequest
    from .models import PaymentMethod, User

# Android package hints for UPI apps (legacy format)
_LEGACY_PACKAGES = {
    'GPAY': 'com.google.android.apps.nbu.paisa.user',
    'PHONEPE': 'com.phonepe.app',
    'PAYTM': 'net.one97.paytm',
    'UPI': '',
    'BANK': '',
    'QR': '',
    'USDT_TRC20': '',
    'USDT_BEP20': '',
}


def _method_type_legacy_slug(method_type: str) -> str:
    return {
        'GPAY': 'gpay',
        'GOOGLE_PAY': 'gpay',
        'PHONEPE': 'phonepe',
        'PAYTM': 'paytm',
        'UPI': 'upi',
        'BANK': 'bank',
        'QR': 'qr',
        'USDT_TRC20': 'usdt_trc20',
        'USDT_BEP20': 'usdt_bep20',
    }.get(method_type, method_type.lower())


def payment_methods_to_legacy_list(methods: List[Any], request: 'HttpRequest') -> List[dict]:
    """Simple array: name, type, upi_id, deep_link, url, package aliases."""
    out: List[dict] = []
    for pm in methods:
        pkg = _LEGACY_PACKAGES.get(pm.method_type, '')
        link = (pm.link or '').strip()
        slug = _method_type_legacy_slug(pm.method_type)
        row = {
            'name': pm.name,
            'title': pm.name,
            'label': pm.name,
            'type': slug,
            'id': slug,
            'app': slug,
            'upi_id': pm.upi_id or '',
            'upi': pm.upi_id or '',
            'vpa': pm.upi_id or '',
            'deep_link': link,
            'url': link,
            'link': link,
            'package': pkg,
            'package_name': pkg,
            'android_package': pkg,
        }
        out.append(row)
    return out


def payment_methods_to_details_list(methods: List[Any], request: 'HttpRequest') -> List[dict]:
    """
    Top-level array: shape depends on ``method_type``.

    - GPAY / PHONEPE / PAYTM / UPI / …: ``id``, ``is_active``, ``method_type``, ``name``,
      ``upi_id``, ``link``.
    - QR: ``id``, ``is_active``, ``method_type``, ``name``, ``qr_image`` (relative ``/media/…`` URL).
    - BANK: ``id``, ``is_active``, ``method_type``, ``name``, ``account_name``, ``bank_name``,
      ``account_number``, ``ifsc_code``.
    - USDT_*: ``usdt_network``, ``usdt_wallet_address``, ``usdt_exchange_rate`` on top of base keys.
    """
    out: List[dict] = []
    for pm in methods:
        mt = pm.method_type
        base = {
            'id': pm.id,
            'is_active': pm.is_active,
            'method_type': mt,
            'name': pm.name,
        }
        if mt == 'QR':
            qr_rel = ''
            if pm.qr_image and getattr(pm.qr_image, 'name', None):
                try:
                    qr_rel = pm.qr_image.url
                except Exception:
                    qr_rel = ''
            row = {**base, 'qr_image': qr_rel}
        elif mt == 'BANK':
            row = {
                **base,
                'account_name': pm.account_name or '',
                'bank_name': pm.bank_name or '',
                'account_number': pm.account_number or '',
                'ifsc_code': pm.ifsc_code or '',
            }
        elif mt in ('USDT_TRC20', 'USDT_BEP20'):
            row = {
                **base,
                'usdt_network': getattr(pm, 'usdt_network', None) or '',
                'usdt_wallet_address': getattr(pm, 'usdt_wallet_address', None) or '',
                'usdt_exchange_rate': getattr(pm, 'usdt_exchange_rate', None),
            }
        else:
            row = {
                **base,
                'upi_id': pm.upi_id or '',
                'link': (pm.link or '').strip(),
            }
        out.append(row)
    return out


def _wallet_balance_display(user: Optional['User']) -> str:
    if not user or not getattr(user, 'is_authenticated', True):
        return '0.00'
    try:
        w = user.wallet
        # balance stored as integer (paise/smallest unit)
        b = (w.balance or 0) / 100.0
        return f'{b:.2f}'
    except Exception:
        return '0.00'


def payment_methods_wrapped_payload(
    methods: List[Any],
    request: 'HttpRequest',
    user: Optional[Any] = None,
) -> dict:
    """
    { "data": { upi_id, balance, payment_methods, payment_details, wallet } }
    Clients may read payment_methods (legacy) and/or payment_details (method_type rows).
    """
    legacy = payment_methods_to_legacy_list(methods, request)
    details = payment_methods_to_details_list(methods, request)
    first_upi = ''
    for pm in methods:
        if pm.upi_id:
            first_upi = pm.upi_id
            break
    balance = _wallet_balance_display(user)
    return {
        'data': {
            'upi_id': first_upi,
            'balance': balance,
            'payment_methods': legacy,
            'payment_details': details,
            'results': details,
            'wallet': {
                'balance': balance,
                'upi_id': first_upi,
            },
        },
    }
