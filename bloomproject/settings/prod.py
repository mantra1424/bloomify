"""Production settings (Render, Docker)."""
import os

import dj_database_url

from .base import *  # noqa: F401,F403
from .base import ALLOWED_HOSTS, SECRET_KEY, STORAGES, env_list

DEBUG = False

if not SECRET_KEY:
    raise RuntimeError('Set DJANGO_SECRET_KEY in the environment.')

# Render gives each service a public hostname in this variable.
RENDER_HOST = os.environ.get('RENDER_EXTERNAL_HOSTNAME')
if RENDER_HOST:
    ALLOWED_HOSTS = [*ALLOWED_HOSTS, RENDER_HOST]

CSRF_TRUSTED_ORIGINS = env_list('DJANGO_CSRF_TRUSTED_ORIGINS')
if RENDER_HOST:
    CSRF_TRUSTED_ORIGINS.append(f'https://{RENDER_HOST}')

DATABASES = {
    'default': dj_database_url.config(conn_max_age=600, conn_health_checks=True),
}
if not DATABASES['default']:
    raise RuntimeError('Set DATABASE_URL in the environment.')

STORAGES = {
    **STORAGES,
    'staticfiles': {'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage'},
}

# ── HTTPS hardening ───────────────────────────────────────────────────────────
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
SECURE_SSL_REDIRECT = True
SECURE_REDIRECT_EXEMPT = [r'^healthz/?$']
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 60 * 60 * 24 * 30
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = 'same-origin'

# ── Error tracking ────────────────────────────────────────────────────────────
SENTRY_DSN = os.environ.get('SENTRY_DSN')
if SENTRY_DSN:
    import sentry_sdk

    sentry_sdk.init(dsn=SENTRY_DSN, traces_sample_rate=0.1, send_default_pii=False)
