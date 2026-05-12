"""Shared rate-limiting helpers backed by Django's cache.

We use cache.add + cache.incr (instead of a single cache.incr) so that the
TTL is set on the *first* request in the window and never extended by
subsequent ones. Without this, the window slides forward forever.
"""
from django.core.cache import cache


def client_ip(request):
    """Best-effort client IP, honoring X-Forwarded-For when present."""
    forwarded = request.META.get('HTTP_X_FORWARDED_FOR', '')
    if forwarded:
        return forwarded.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')


def is_rate_limited(scope, key, max_requests, window_seconds):
    """
    Returns True iff `key` (within `scope`) has already hit `max_requests`
    in the current rolling `window_seconds` window. Otherwise increments
    the counter and returns False.

    `scope` is a short string namespace (e.g. 'contact-submit',
    'magic-link-ip') so different endpoints don't share buckets.
    """
    if not key:
        # No identifying info — skip rate limit rather than block everyone.
        return False
    cache_key = f'rl:{scope}:{key}'
    count = cache.get(cache_key, 0)
    if count >= max_requests:
        return True
    # `cache.add` sets the value only if missing — gives us a fresh TTL on
    # the first hit; subsequent hits use `incr` which preserves it.
    if not cache.add(cache_key, 1, window_seconds):
        cache.incr(cache_key)
    return False
