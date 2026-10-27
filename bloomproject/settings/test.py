"""Settings for automated tests: fast and isolated from real services."""

import os

from .dev import *  # noqa: F401,F403

DEBUG = False
SECRET_KEY = 'test-only-key'
PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']
MAILERS = {'default': {'BACKEND': 'django.core.mail.backends.locmem.EmailBackend'}}
STORAGES = {
    'default': {'BACKEND': 'django.core.files.storage.InMemoryStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
}
RAZORPAY_KEY_ID = 'rzp_test_key'
RAZORPAY_SECRET_KEY = 'test-razorpay-secret'
RAZORPAY_WEBHOOK_SECRET = 'test-webhook-secret'
AXES_ENABLED = False  # turned on per-test where needed
# Tests don't serve static files, so skip WhiteNoise (it warns when staticfiles/ hasn't been collected).
MIDDLEWARE = [m for m in MIDDLEWARE if 'whitenoise' not in m]  # noqa: F405

# CI runs the suite against PostgreSQL (like production) by setting DATABASE_URL.
if os.environ.get('DATABASE_URL'):
    import dj_database_url

    DATABASES = {'default': dj_database_url.config()}
