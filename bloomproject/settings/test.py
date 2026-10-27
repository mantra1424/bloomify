"""Settings for automated tests: fast and isolated from real services."""
from .dev import *  # noqa: F401,F403

DEBUG = False
SECRET_KEY = 'test-only-key'
PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']
EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'
STORAGES = {
    'default': {'BACKEND': 'django.core.files.storage.InMemoryStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
}
RAZORPAY_KEY_ID = 'rzp_test_key'
RAZORPAY_SECRET_KEY = 'test-razorpay-secret'
