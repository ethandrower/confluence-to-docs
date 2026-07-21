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
    'daphne',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'channels',
    'rest_framework',
    'django_celery_beat',
    'anymail',
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

ASGI_APPLICATION = 'citemed.asgi.application'

# Channels channel layer: Redis in prod (cross-worker broadcast), in-memory
# locally so dev/tests need no Redis.
if env('REDIS_URL', default=None):
    CHANNEL_LAYERS = {
        'default': {
            'BACKEND': 'channels_redis.core.RedisChannelLayer',
            'CONFIG': {'hosts': [env('REDIS_URL')]},
        }
    }
else:
    CHANNEL_LAYERS = {'default': {'BACKEND': 'channels.layers.InMemoryChannelLayer'}}

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

MEDIA_URL = '/media/'
MEDIA_ROOT = env('MEDIA_ROOT', default=str(BASE_DIR / 'media'))

# ── Storage backends (Django 4.2+ unified STORAGES dict) ────────────────
# Default storage  → filesystem in dev, S3 when AWS_STORAGE_BUCKET_NAME is set.
# Static storage   → plain in dev, WhiteNoise compressed+manifest in prod.
#
# Django 4.2 made STORAGES and the legacy STATICFILES_STORAGE mutually
# exclusive — defining both at once raises ImproperlyConfigured. We always
# set STORAGES (with conditional inner backends) and never set the legacy
# key, so dev + prod, S3 + non-S3 combinations all work without a clash.
_S3_BUCKET = env('AWS_STORAGE_BUCKET_NAME', default='')
_USE_WHITENOISE = not env.bool('DEBUG', default=True)

STORAGES = {
    'default': {
        'BACKEND': (
            'storages.backends.s3boto3.S3Boto3Storage' if _S3_BUCKET
            else 'django.core.files.storage.FileSystemStorage'
        ),
    },
    'staticfiles': {
        'BACKEND': (
            'whitenoise.storage.CompressedManifestStaticFilesStorage' if _USE_WHITENOISE
            else 'django.contrib.staticfiles.storage.StaticFilesStorage'
        ),
    },
}

if _S3_BUCKET:
    # Supports standard AWS S3 and S3-compatible services (R2/MinIO etc.)
    # via AWS_S3_ENDPOINT_URL.
    AWS_ACCESS_KEY_ID = env('AWS_ACCESS_KEY_ID')
    AWS_SECRET_ACCESS_KEY = env('AWS_SECRET_ACCESS_KEY')
    AWS_STORAGE_BUCKET_NAME = _S3_BUCKET
    AWS_S3_REGION_NAME = env('AWS_S3_REGION_NAME', default='us-east-1')
    AWS_S3_ENDPOINT_URL = env('AWS_S3_ENDPOINT_URL', default=None)  # Set for R2/MinIO

    # The citemed-docku bucket has ACLs disabled (bucket-owner-enforced) and
    # Block-Public-Access fully on. Sending any ACL raises
    # AccessControlListNotSupported, so we must NOT set one. Objects are NOT
    # publicly readable via direct S3 URLs (403) — they're served through a
    # CloudFront distribution instead. Set AWS_S3_CUSTOM_DOMAIN to the
    # CloudFront domain so storage URLs (and the <img> srcs the sync writes)
    # point at the CDN rather than the private bucket.
    AWS_DEFAULT_ACL = None
    # Overwrite same-key uploads: an attachment maps to a stable key
    # (confluence/<page>/<file>), so a re-sync should replace it in place
    # rather than pile up suffixed duplicates.
    AWS_S3_FILE_OVERWRITE = True
    AWS_QUERYSTRING_AUTH = env.bool('AWS_QUERYSTRING_AUTH', default=False)
    AWS_S3_CUSTOM_DOMAIN = env('AWS_S3_CUSTOM_DOMAIN', default='') or None
    if AWS_S3_CUSTOM_DOMAIN:
        MEDIA_URL = f'https://{AWS_S3_CUSTOM_DOMAIN}/'
    else:
        MEDIA_URL = env('MEDIA_URL', default=f'https://{_S3_BUCKET}.s3.amazonaws.com/')

# ── Customer file-sharing ──────────────────────────────────────────────
# The dedicated `citemed-fileshare` bucket (same IAM user as doc images).
# Objects are reached only via short-lived presigned URLs. These S3 creds are
# read independently of the *default storage* bucket so file sharing can use
# S3 even when doc images are on the local filesystem (e.g. local dev).
AWS_ACCESS_KEY_ID = globals().get('AWS_ACCESS_KEY_ID') or env('AWS_ACCESS_KEY_ID', default='')
AWS_SECRET_ACCESS_KEY = globals().get('AWS_SECRET_ACCESS_KEY') or env('AWS_SECRET_ACCESS_KEY', default='')
AWS_S3_REGION_NAME = globals().get('AWS_S3_REGION_NAME') or env('AWS_S3_REGION_NAME', default='us-east-1')

FILESHARE_BUCKET = env('FILESHARE_BUCKET', default='') or _S3_BUCKET
FILESHARE_KEY_PREFIX = env('FILESHARE_KEY_PREFIX', default='fileshare')
FILESHARE_MAX_BYTES = env.int('FILESHARE_MAX_BYTES', default=5 * 1024 ** 3)  # 5 GB
FILESHARE_PRESIGN_TTL = env.int('FILESHARE_PRESIGN_TTL', default=3600)
FILESHARE_ALLOWED_EXT = {
    'pdf', 'doc', 'docx', 'xls', 'xlsx', 'csv', 'txt', 'rtf',
    'ris', 'enw', 'nbib', 'xml', 'bib',          # reference-library exports
    'png', 'jpg', 'jpeg', 'gif', 'zip',
}

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
# Per Trinity's docs, ATLASSIAN_JIRA_URL is the base URL for BOTH Jira and
# Confluence (single Atlassian instance) — without it, trinity builds URLs
# like '/wiki/rest/api/content' with no scheme and requests bails.
import os as _os
_os.environ['ATLASSIAN_EMAIL'] = CONFLUENCE_EMAIL
_os.environ['ATLASSIAN_API_TOKEN'] = CONFLUENCE_API_TOKEN
_os.environ['ATLASSIAN_CLOUD_ID'] = ATLASSIAN_CLOUD_ID
_os.environ['ATLASSIAN_JIRA_URL'] = (
    f'https://{CONFLUENCE_DOMAIN}' if CONFLUENCE_DOMAIN else ''
)

# Portal
PORTAL_MAGIC_LINK_EXPIRY_MINUTES = env.int('PORTAL_MAGIC_LINK_EXPIRY_MINUTES', default=60)
FRONTEND_URL = env('FRONTEND_URL', default='http://localhost:5173')

# Which Confluence spaces this portal surfaces. Empty list = all spaces
# (dev default). In production we set DOCS_ALLOWED_SPACES=ECD so only the
# customer-facing Evidence Cloud docs show — internal spaces (Engineering,
# Operations, Collective) stay hidden. Kept separate from each page's
# is_published flag so a future Confluence re-sync can't clobber this intent.
DOCS_ALLOWED_SPACES = env.list('DOCS_ALLOWED_SPACES', default=[])

# Email — Mailgun (via django-anymail) when MAILGUN_ACCESS_KEY is set,
# otherwise console (dev/tests). Anymail gives us provider-agnostic sending,
# the ESP message-id (for delivery-webhook correlation), and signed tracking
# webhooks (delivered/bounced) — see portal/ticket_notify.py + the Mailgun
# webhook. MAILGUN_WEBHOOK_SIGNING_KEY authenticates inbound events.
MAILGUN_ACCESS_KEY = env('MAILGUN_ACCESS_KEY', default='')
MAILGUN_SERVER_NAME = env('MAILGUN_SERVER_NAME', default='')

# Open/click tracking OFF by default (Gmail otherwise shows "loading external
# images" from the tracking pixel; we don't need it). django-mailgun used to
# map X-Mailgun-Track-* headers; Anymail uses these send defaults instead.
ANYMAIL = {
    'MAILGUN_API_KEY': MAILGUN_ACCESS_KEY,
    'MAILGUN_SENDER_DOMAIN': MAILGUN_SERVER_NAME,
    'SEND_DEFAULTS': {'track_opens': False, 'track_clicks': False},
}
# Only set the webhook signing key when provided. Setting it to '' would make
# Anymail verify delivery webhooks against an EMPTY HMAC key (forgeable), and
# real Mailgun events would fail to validate. Leaving it unset lets Anymail fall
# back to the API key. Configure MAILGUN_WEBHOOK_SIGNING_KEY in prod (deploy
# checklist) so genuine events validate against the real signing key.
_mailgun_webhook_key = env('MAILGUN_WEBHOOK_SIGNING_KEY', default='')
if _mailgun_webhook_key:
    ANYMAIL['MAILGUN_WEBHOOK_SIGNING_KEY'] = _mailgun_webhook_key

if MAILGUN_ACCESS_KEY:
    EMAIL_BACKEND = 'anymail.backends.mailgun.EmailBackend'
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

# S1 Jira→portal comment sync: when True, a public Jira comment ingested into a
# ticket is also emailed to the customer via the threaded reply path. Default
# False (ingest-for-visibility only) so we never double-email while JSM is still
# sending its own customer notifications. Flip on once JSM notifications are off.
JIRA_SYNC_EMAIL_CUSTOMER = env.bool('JIRA_SYNC_EMAIL_CUSTOMER', default=False)

# Jira projects whose comments S1 may sync into a customer thread. ONLY
# service-desk (JSM) projects belong here: there `jsdPublic` means
# "shown to the customer". A bug linked to an engineering project (e.g. ECD)
# is deliberately excluded — its comments are dev/bot chatter and would leak.
# Linking itself stays manual (admin pastes the key); this only bounds sync.
JIRA_SYNC_PROJECTS = env.list('JIRA_SYNC_PROJECTS', default=['SUP'])

# Option A — portal creates + links the Jira issue via the API (reliable,
# auto-linked) instead of the fragile email intake. When JIRA_AUTO_CREATE is on
# the portal must NOT also email the JSM intake (would duplicate), so
# notify_ticket_created suppresses that email. Default off. Creates in
# JIRA_TICKET_PROJECT as issue type JIRA_TICKET_ISSUE_TYPE_ID (SUP "Task").
JIRA_AUTO_CREATE = env.bool('JIRA_AUTO_CREATE', default=False)
JIRA_TICKET_PROJECT = env('JIRA_TICKET_PROJECT', default='SUP')
JIRA_TICKET_ISSUE_TYPE_ID = env('JIRA_TICKET_ISSUE_TYPE_ID', default='10103')
# Which ticket categories auto-create a Jira issue. Default 'bug' only (per
# founder: the link is for bug tickets); an empty list means all categories.
JIRA_AUTO_CREATE_CATEGORIES = env.list('JIRA_AUTO_CREATE_CATEGORIES', default=['bug'])

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
