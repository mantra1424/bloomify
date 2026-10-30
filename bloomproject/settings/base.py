"""
Settings shared by every environment.

Pick an environment with DJANGO_SETTINGS_MODULE:
  bloomproject.settings.dev   – local development (default for manage.py)
  bloomproject.settings.prod  – production (default for wsgi/asgi)
  bloomproject.settings.test  – automated tests
"""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent


def _load_env_file(path):
    """Load KEY=VALUE lines from a local .env file (kept out of git)."""
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, value = line.split('=', 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_env_file(BASE_DIR / '.env')


def env_list(name, default=''):
    return [item.strip() for item in os.environ.get(name, default).split(',') if item.strip()]


def env_bool(name, default=False):
    return os.environ.get(name, str(default)).lower() in ('1', 'true', 'yes')


# The shop's name as customers see it. Change it here to rebrand the whole site.
SITE_BRAND = 'Petal & Stem'

SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY', '')
DEBUG = False
ALLOWED_HOSTS = env_list('DJANGO_ALLOWED_HOSTS', 'localhost,127.0.0.1')

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'axes',
    'bloomapp',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    # Must be last: blocks logins after repeated failures.
    'axes.middleware.AxesMiddleware',
]

ROOT_URLCONF = 'bloomproject.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'bloomapp' / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'bloomapp.context_processors.cart_count',
                'bloomapp.context_processors.site_nav',
            ],
        },
    },
]

WSGI_APPLICATION = 'bloomproject.wsgi.application'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Asia/Kolkata'
USE_I18N = True
USE_TZ = True

# ── Static files (served by WhiteNoise) and uploaded media ───────────────────
STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'bloomapp' / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'
# Let Django serve uploaded files itself (fine for a demo; use S3 storage for real traffic).
SERVE_MEDIA = env_bool('SERVE_MEDIA', False)

STORAGES = {
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
}

# Uploaded images go to S3-compatible storage (AWS S3, Cloudflare R2, …) when a
# bucket is configured; otherwise they stay on the local disk.
AWS_STORAGE_BUCKET_NAME = os.environ.get('AWS_STORAGE_BUCKET_NAME', '')
if AWS_STORAGE_BUCKET_NAME:
    STORAGES['default'] = {'BACKEND': 'storages.backends.s3.S3Storage'}
    AWS_S3_ENDPOINT_URL = os.environ.get('AWS_S3_ENDPOINT_URL') or None
    AWS_S3_CUSTOM_DOMAIN = os.environ.get('AWS_S3_CUSTOM_DOMAIN') or None
    AWS_S3_REGION_NAME = os.environ.get('AWS_S3_REGION_NAME') or None
    AWS_QUERYSTRING_AUTH = False
    AWS_DEFAULT_ACL = None
    AWS_S3_FILE_OVERWRITE = False

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ── Authentication ────────────────────────────────────────────────────────────
AUTH_USER_MODEL = 'bloomapp.User'
LOGIN_URL = 'login'
LOGIN_REDIRECT_URL = 'home'
LOGOUT_REDIRECT_URL = 'home'

AUTHENTICATION_BACKENDS = [
    'axes.backends.AxesStandaloneBackend',
    'django.contrib.auth.backends.ModelBackend',
]

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator', 'OPTIONS': {'min_length': 8}},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# Brute-force protection: 5 failed logins for the same email + IP → locked for 1 hour.
AXES_FAILURE_LIMIT = 5
AXES_COOLOFF_TIME = 1  # hours
AXES_LOCKOUT_PARAMETERS = [['username', 'ip_address']]
AXES_USERNAME_FORM_FIELD = 'email'
AXES_RESET_ON_SUCCESS = True
AXES_LOCKOUT_TEMPLATE = 'bloomapp/auth/locked.html'

# ── Razorpay ──────────────────────────────────────────────────────────────────
RAZORPAY_KEY_ID = os.environ.get('RAZORPAY_KEY_ID', '')
RAZORPAY_SECRET_KEY = os.environ.get('RAZORPAY_SECRET_KEY', '')
# Set in Razorpay Dashboard → Webhooks; used to check webhook calls really come from Razorpay.
RAZORPAY_WEBHOOK_SECRET = os.environ.get('RAZORPAY_WEBHOOK_SECRET', '')

# Unpaid online orders older than this are cancelled and their stock released.
PENDING_PAYMENT_TIMEOUT_MINUTES = 30

SECURE_CROSS_ORIGIN_OPENER_POLICY = 'same-origin-allow-popups'

# ── Email (Gmail SMTP) ────────────────────────────────────────────────────────
SMTP_USER = os.environ.get('BLOOMIFY_EMAIL', '')
SMTP_PASSWORD = os.environ.get('BLOOMIFY_EMAIL_PASS', '')  # Gmail App Password

if SMTP_USER:
    MAILERS = {
        'default': {
            'BACKEND': 'django.core.mail.backends.smtp.EmailBackend',
            'OPTIONS': {
                'host': os.environ.get('EMAIL_HOST', 'smtp.gmail.com'),
                'port': int(os.environ.get('EMAIL_PORT', '587')),
                'username': SMTP_USER,
                'password': SMTP_PASSWORD,
                'use_tls': True,
                'timeout': 10,
            },
        },
    }
else:
    # No SMTP account configured: print emails to the log instead of sending them.
    MAILERS = {'default': {'BACKEND': 'django.core.mail.backends.console.EmailBackend'}}

DEFAULT_FROM_EMAIL = f'{SITE_BRAND} <{SMTP_USER or "noreply@bloomify.local"}>'

# ── Logging: everything to the console (Render/Docker collect stdout) ────────
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'simple': {'format': '{asctime} {levelname} {name}: {message}', 'style': '{'},
    },
    'handlers': {
        'console': {'class': 'logging.StreamHandler', 'formatter': 'simple'},
    },
    'root': {'handlers': ['console'], 'level': 'INFO'},
    'loggers': {
        'django': {'handlers': ['console'], 'level': 'INFO', 'propagate': False},
    },
}
