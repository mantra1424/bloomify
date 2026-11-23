"""
Caching for data every visitor reads (menu, home page sections).

`cached()` is cache-aside with protection against a cache stampede (many
requests rebuilding the same key at once when it expires or the cache restarts):

- TTL jitter: each entry lives a slightly random time, so keys don't all expire together.
- Serve stale: an entry keeps its old value for a while after it goes "stale", so
  visitors get slightly old data instead of all hitting the database.
- One rebuild at a time: a short lock means only one request rebuilds a key;
  the others serve the stale copy, or on a cold cache wait briefly for it.
- Warming: `manage.py warm_cache` fills the cache before the app takes traffic.

The cache can fail too: if it is unreachable, pages are built straight from the
database (slower, but the shop stays up) and a warning is logged.

Changing a product, category or review bumps the catalog version (see signals.py),
which makes every cached catalog entry out of date at once.
"""

import logging
import random
import time

from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

VERSION_KEY = 'catalog:version'
LOCK_SECONDS = 10
COLD_WAIT_SECONDS = 2
STALE_GRACE = 10  # an entry lives this many times its TTL so a stale copy is there to serve


class CacheUnavailable(Exception):
    pass


def _call(method, *args, **kwargs):
    """Run one cache operation, turning any connection error into CacheUnavailable."""
    try:
        return getattr(cache, method)(*args, **kwargs)
    except Exception as exc:
        raise CacheUnavailable(exc.__class__.__name__) from exc


def catalog_version():
    version = _call('get', VERSION_KEY)
    if version is None:
        version = int(time.time())  # unique after a cache restart, so old entries are never reused
        _call('add', VERSION_KEY, version, timeout=None)
        version = _call('get', VERSION_KEY, version)
    return version


def invalidate_catalog():
    """Make every cached catalog entry out of date (they rebuild on next use)."""
    try:
        try:
            _call('incr', VERSION_KEY)
        except CacheUnavailable as exc:
            if not isinstance(exc.__cause__, ValueError):  # ValueError: key missing after a restart
                raise
            _call('set', VERSION_KEY, int(time.time()), timeout=None)
    except CacheUnavailable as exc:
        logger.warning('Cache unreachable (%s): could not clear the catalog cache', exc)


def cached(name, build, ttl=None):
    """Return build()'s result, cached under `name` for about `ttl` seconds."""
    ttl = ttl or settings.CATALOG_CACHE_SECONDS
    if ttl <= 0:
        return build()
    try:
        key = f'catalog:{catalog_version()}:{name}'
        entry = _call('get', key)
        now = time.time()
        if entry is not None and entry['fresh_until'] > now:
            return entry['value']

        # Missing or stale. Only the request that wins the lock rebuilds.
        if not _call('add', f'{key}:lock', 1, timeout=LOCK_SECONDS):
            if entry is not None:
                return entry['value']  # someone else is rebuilding: serve the stale copy
            waited = _wait_for(key)  # cold cache: wait briefly for that rebuild instead of piling on
            if waited is not None:
                return waited['value']
    except CacheUnavailable as exc:
        logger.warning('Cache unreachable (%s): building %s from the database', exc, name)
        return build()

    try:
        value = build()
    finally:
        _quietly('delete', f'{key}:lock')
    jittered = ttl * random.uniform(0.9, 1.1)  # noqa: S311 (spreading expiry times, not security)
    _quietly('set', key, {'value': value, 'fresh_until': now + jittered}, timeout=int(ttl * STALE_GRACE))
    return value


def cache_status():
    """For the health check: which cache is in use and whether it answers."""
    backend = 'redis' if 'redis' in settings.CACHES['default']['BACKEND'].lower() else 'memory'
    try:
        _call('set', 'healthz', 1, timeout=5)
        ok = _call('get', 'healthz') == 1
    except CacheUnavailable:
        ok = False
    return {'backend': backend, 'ok': ok}


def _quietly(method, *args, **kwargs):
    try:
        _call(method, *args, **kwargs)
    except CacheUnavailable as exc:
        logger.warning('Cache unreachable (%s) during %s', exc, method)


def _wait_for(key):
    deadline = time.monotonic() + COLD_WAIT_SECONDS
    while time.monotonic() < deadline:
        time.sleep(0.05)
        entry = _call('get', key)
        if entry is not None:
            return entry
    return None
