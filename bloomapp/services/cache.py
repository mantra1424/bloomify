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

Changing a product, category or review bumps the catalog version (see signals.py),
which makes every cached catalog entry out of date at once.
"""

import random
import time

from django.conf import settings
from django.core.cache import cache

VERSION_KEY = 'catalog:version'
LOCK_SECONDS = 10
COLD_WAIT_SECONDS = 2
STALE_GRACE = 10  # an entry lives this many times its TTL so a stale copy is there to serve


def catalog_version():
    version = cache.get(VERSION_KEY)
    if version is None:
        version = int(time.time())  # unique after a cache restart, so old entries are never reused
        cache.add(VERSION_KEY, version, timeout=None)
        version = cache.get(VERSION_KEY, version)
    return version


def invalidate_catalog():
    """Make every cached catalog entry out of date (they rebuild on next use)."""
    try:
        cache.incr(VERSION_KEY)
    except ValueError:  # key missing (cache restarted): any new version will do
        cache.set(VERSION_KEY, int(time.time()), timeout=None)


def cached(name, build, ttl=None):
    """Return build()'s result, cached under `name` for about `ttl` seconds."""
    ttl = ttl or settings.CATALOG_CACHE_SECONDS
    if ttl <= 0:
        return build()
    key = f'catalog:{catalog_version()}:{name}'
    entry = cache.get(key)
    now = time.time()

    if entry is not None and entry['fresh_until'] > now:
        return entry['value']

    # Missing or stale. Only the request that wins the lock rebuilds.
    if not cache.add(f'{key}:lock', 1, timeout=LOCK_SECONDS):
        if entry is not None:
            return entry['value']  # someone else is rebuilding: serve the stale copy
        waited = _wait_for(key)  # cold cache: wait briefly for that rebuild instead of piling on
        if waited is not None:
            return waited['value']

    try:
        value = build()
        jittered = ttl * random.uniform(0.9, 1.1)  # noqa: S311 (spreading expiry times, not security)
        cache.set(key, {'value': value, 'fresh_until': now + jittered}, timeout=int(ttl * STALE_GRACE))
    finally:
        cache.delete(f'{key}:lock')
    return value


def _wait_for(key):
    deadline = time.monotonic() + COLD_WAIT_SECONDS
    while time.monotonic() < deadline:
        time.sleep(0.05)
        entry = cache.get(key)
        if entry is not None:
            return entry
    return None
