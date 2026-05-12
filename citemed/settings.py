import environ
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env(
    DEBUG=(bool, False),
)
environ.Env.read_env(BASE_DIR / '.env')

SECRET_KEY = env('SECRET_KEY', default='dev-secret-key-change-in-production')
DEBUG = env.bool('DEBUG', default=True)
ALLOWED_HOSTS = env.list('ALLOWED_HOSTS', default=['localhost', '127.0.0.1'])

# Django admin URL path (without leading/trailing slashes). Override in
# production with something unguessable to keep the admin out of bot scans
# of /admin/. Defaults to 'admin' so local dev URLs don't change.
ADMIN_PATH = env('ADMIN_PATH', default='admin').strip('/')

# Behind Dokku's nginx proxy: treat X-Forwarded-Proto as the source of truth
# for whether the connection is HTTPS. Required for SECURE_SSL_REDIRECT and
# secure cookie flags to work correctly.
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

# CSRF: trust the production origin(s) for unsafe requests. Set in env on deploy.
# Example: CSRF_TRUSTED_ORIGINS=https://docs.example.com
CSRF_TRUSTED_ORIGINS = env.list('CSRF_TRUSTED_ORIGINS', default=[])

# Cookie hardening — only enforced when DEBUG is off so local dev (http) still works.
if not DEBUG:
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_SSL_REDIRECT = True
    SECURE_HSTS_SECONDS = 60 * 60 * 24 * 30  # 30 days
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_REFERRER_POLICY = 'same-origin'

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'django_celery_beat',
    'portal',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    # WhiteNoise serves static files in production (must come right after SecurityMiddleware).
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'citemed.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'citemed.wsgi.application'

DATABASES = {
    'default': env.db('DATABASE_URL', default='sqlite:///db.sqlite3')
}

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'

# Pull Vue's built assets into Django's static pipeline so WhiteNoise serves
# them with proper caching headers. Built by `npm run build` inside frontend/.
_FRONTEND_DIST = BASE_DIR / 'frontend' / 'dist'
STATICFILES_DIRS = [_FRONTEND_DIST] if _FRONTEND_DIST.exists() else []

# WhiteNoise: compress + hash filenames in production for cache busting.
# Falls back to plain storage when DEBUG (cleaner error messages during dev).
if not env('DEBUG', default=True):
    STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

MEDIA_URL = '/media/'
MEDIA_ROOT = env('MEDIA_ROOT', default=str(BASE_DIR / 'media'))

# S3 storage — enabled automatically when AWS_STORAGE_BUCKET_NAME is set.
# Supports standard AWS S3 and S3-compatible services (Cloudflare R2 etc.)
# via AWS_S3_ENDPOINT_URL. Falls back to local MEDIA_ROOT in development.
_S3_BUCKET = env('AWS_STORAGE_BUCKET_NAME', default='')
if _S3_BUCKET:
    STORAGES = {
        'default': {'BACKEND': 'storages.backends.s3boto3.S3Boto3Storage'},
        'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
    }
    AWS_ACCESS_KEY_ID = env('AWS_ACCESS_KEY_ID')
    AWS_SECRET_ACCESS_KEY = env('AWS_SECRET_ACCESS_KEY')
    AWS_STORAGE_BUCKET_NAME = _S3_BUCKET
    AWS_S3_REGION_NAME = env('AWS_S3_REGION_NAME', default='us-east-1')
    AWS_S3_ENDPOINT_URL = env('AWS_S3_ENDPOINT_URL', default=None)  # Set for R2/MinIO
    AWS_DEFAULT_ACL = 'public-read'
    AWS_S3_FILE_OVERWRITE = False
    AWS_QUERYSTRING_AUTH = False
    MEDIA_URL = env('MEDIA_URL', default=f'https://{_S3_BUCKET}.s3.amazonaws.com/')

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

SESSION_COOKIE_AGE = 60 * 60 * 24 * 30  # 30 days
SESSION_ENGINE = 'django.contrib.sessions.backends.db'

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.SessionAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.AllowAny',
    ],
}

# Celery
CELERY_BROKER_URL = env('REDIS_URL', default='redis://localhost:6379/0')
CELERY_RESULT_BACKEND = env('REDIS_URL', default='redis://localhost:6379/0')
CELERY_BEAT_SCHEDULER = 'django_celery_beat.schedulers:DatabaseScheduler'
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'

# Confluence
CONFLUENCE_DOMAIN = env('CONFLUENCE_DOMAIN', default='')
CONFLUENCE_EMAIL = env('CONFLUENCE_EMAIL', default='')
CONFLUENCE_API_TOKEN = env('CONFLUENCE_API_TOKEN', default='')
CONFLUENCE_SPACE_KEY = env('CONFLUENCE_SPACE_KEY', default='CITEMED')
ATLASSIAN_CLOUD_ID = env('ATLASSIAN_CLOUD_ID', default='')

# Inject trinity's expected env vars at settings load time so its module-level
# URL constants are populated before any import of trinity.confluence.*
import os as _os
_os.environ['ATLASSIAN_EMAIL'] = CONFLUENCE_EMAIL
_os.environ['ATLASSIAN_API_TOKEN'] = CONFLUENCE_API_TOKEN
_os.environ['ATLASSIAN_CLOUD_ID'] = ATLASSIAN_CLOUD_ID

# Portal
PORTAL_MAGIC_LINK_EXPIRY_MINUTES = env.int('PORTAL_MAGIC_LINK_EXPIRY_MINUTES', default=60)
FRONTEND_URL = env('FRONTEND_URL', default='http://localhost:5173')

# Email — Mailgun when MAILGUN_ACCESS_KEY is set, otherwise console (dev/tests).
# Mirrors the citemed_web pattern so we don't introduce a second mental model.
MAILGUN_ACCESS_KEY = env('MAILGUN_ACCESS_KEY', default='')
MAILGUN_SERVER_NAME = env('MAILGUN_SERVER_NAME', default='')

if MAILGUN_ACCESS_KEY:
    EMAIL_BACKEND = 'django_mailgun.MailgunBackend'
else:
    # SMTP fallback if EMAIL_HOST is set, else console (default for local dev).
    EMAIL_BACKEND = env(
        'EMAIL_BACKEND',
        default='django.core.mail.backends.console.EmailBackend',
    )
    EMAIL_HOST = env('EMAIL_HOST', default='')
    EMAIL_HOST_USER = env('EMAIL_HOST_USER', default='')
    EMAIL_HOST_PASSWORD = env('EMAIL_HOST_PASSWORD', default='')
    EMAIL_PORT = env.int('EMAIL_PORT', default=587)
    EMAIL_USE_TLS = env.bool('EMAIL_USE_TLS', default=True)

DEFAULT_FROM_EMAIL = env('DEFAULT_FROM_EMAIL', default='Support <noreply@example.com>')
SERVER_EMAIL = env('SERVER_EMAIL', default=DEFAULT_FROM_EMAIL)
SUPPORT_EMAIL = env('SUPPORT_EMAIL', default='support@citemed.com')

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'INFO',
    },
    'loggers': {
        'portal': {
            'handlers': ['console'],
            'level': 'DEBUG',
            'propagate': False,
        },
    },
}
