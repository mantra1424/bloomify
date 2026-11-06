"""Local development settings."""

from .base import *  # noqa: F401,F403
from .base import env_bool

DEBUG = env_bool('DJANGO_DEBUG', True)

if not SECRET_KEY:  # noqa: F405
    SECRET_KEY = 'dev-only-insecure-key'

PWA_ENABLED = env_bool('PWA_ENABLED', False)  # dev static names aren't hashed, so caching them would go stale
