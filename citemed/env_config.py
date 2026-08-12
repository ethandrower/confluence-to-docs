"""Resolution of security-critical settings, kept out of settings.py so it can
be unit tested (#7).

settings.py is a module with import-time side effects; asserting on the globals
it produces means re-importing it under a scrubbed environment, which is awkward
and only ever shows what the current machine's .env produces. Pure functions
here, tested directly, with settings.py calling them.
"""
import logging

from django.core.exceptions import ImproperlyConfigured
from django.core.management.utils import get_random_secret_key

logger = logging.getLogger(__name__)

#: The value settings.py used to fall back to, published in a public repository
#: for as long as it was the default. Treated as equivalent to "unset", because
#: pasting it from .env.example carries exactly the same exposure as forgetting
#: the variable: sessions signed with a key anyone can read, so anyone can forge
#: a cookie and sign in as any user.
DEV_PLACEHOLDER_KEY = 'dev-secret-key-change-in-production'

_HOWTO = (
    "Set SECRET_KEY in the environment. Generate one with:\n"
    "  python -c 'import secrets; print(secrets.token_urlsafe(64))'\n"
    'On Dokku: dokku config:set <app> SECRET_KEY=...'
)


def resolve_secret_key(raw, debug):
    """The signing key to use, or raise rather than use a known one.

    Configured  -> use it.
    Absent, DEBUG on  -> generate an ephemeral key and warn. A fresh checkout
        still runs `manage.py test` and `runserver`, and the key is random
        rather than a shared known value. Sessions don't survive a restart,
        which is the nudge to configure one properly.
    Absent, DEBUG off -> refuse to boot. This is the whole point: a deploy that
        forgets the variable must fail visibly instead of quietly signing
        sessions with something public.
    """
    key = (raw or '').strip()

    if key and key != DEV_PLACEHOLDER_KEY:
        return key

    if not debug:
        reason = (
            'is set to the placeholder from .env.example' if key
            else 'is not set'
        )
        raise ImproperlyConfigured(
            f'SECRET_KEY {reason}, and DEBUG is off.\n\n'
            'Refusing to start: sessions signed with a publicly-known key can '
            'be forged, which would let anyone sign in as any user.\n\n'
            f'{_HOWTO}'
        )

    logger.warning(
        'SECRET_KEY is not set — generated an ephemeral one for this process. '
        'Sessions will not survive a restart. %s', _HOWTO,
    )
    return get_random_secret_key()
