"""Custom template filters for number/date formatting."""
from django import template

register = template.Library()


@register.filter
def indian_int(value):
    """Format integer with Indian-style commas (e.g. 12,34,567)."""
    if value is None:
        return '0'
    try:
        n = int(value)
    except (TypeError, ValueError):
        return '0'
    s = str(abs(n))
    if len(s) <= 3:
        return ('-' if n < 0 else '') + s
    groups = [s[-3:]]
    s = s[:-3]
    while s:
        groups.insert(0, s[-2:])
        s = s[:-2]
    result = ','.join(groups)
    return ('-' if n < 0 else '') + result
