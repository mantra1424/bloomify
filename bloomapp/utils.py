"""Small helpers for reading untrusted request input safely."""


def parse_int(value, default, min_value=None, max_value=None):
    """Turn form input into an int without crashing; clamp it to a range."""
    try:
        n = int(value)
    except (TypeError, ValueError):
        return default
    if min_value is not None:
        n = max(min_value, n)
    if max_value is not None:
        n = min(max_value, n)
    return n


def parse_float(value, default, min_value=None, max_value=None):
    try:
        n = float(value)
    except (TypeError, ValueError):
        return default
    if n != n:  # NaN
        return default
    if min_value is not None:
        n = max(min_value, n)
    if max_value is not None:
        n = min(max_value, n)
    return n


def back_url(request, default):
    """The page the user came from, if it is on this site; otherwise `default`."""
    from django.utils.http import url_has_allowed_host_and_scheme

    referer = request.META.get('HTTP_REFERER')
    if referer and url_has_allowed_host_and_scheme(
        referer, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return referer
    return default
