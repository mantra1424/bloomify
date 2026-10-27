"""Local development settings."""
from .base import *  # noqa: F401,F403
from .base import EMAIL_HOST_USER, env_bool

DEBUG = env_bool('DJANGO_DEBUG', True)

if not SECRET_KEY:  # noqa: F405
    SECRET_KEY = 'dev-only-insecure-key'

# Print emails to the terminal unless real SMTP credentials are configured.
if not EMAIL_HOST_USER:
    EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
