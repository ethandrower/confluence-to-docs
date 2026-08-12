"""Dependency probes behind /healthz/ (#50).

Each probe genuinely exercises its dependency — a query rather than a
connection object, a round-trip rather than an import. Dokku promotes a release
only if this passes, so a probe that can't fail is worse than no probe: it
turns "is the app healthy" into "did Python start".

Probes never raise. They return one of OK / ERROR / SKIPPED and log the real
reason, because the caller is a public endpoint that must not echo internals
back to whoever asked.

SKIPPED is for dependencies that are legitimately absent in the current
configuration (Redis in local dev), as distinct from present-but-broken. It
does not fail the deploy; ERROR does.
"""
import logging

from django.conf import settings
from django.db import connections
from django.db.migrations.executor import MigrationExecutor

logger = logging.getLogger(__name__)

OK = 'ok'
ERROR = 'error'
SKIPPED = 'skipped'
#: Reported, but does not fail the endpoint. See overall_status.
PENDING = 'pending'

STATUS_OK = 'ok'
STATUS_DEGRADED = 'degraded'

#: Keep the probe well under Dokku's own healthcheck timeout: a probe that
#: hangs is reported as a hung app, which is the correct outcome but should be
#: reached quickly rather than by the checker giving up on us.
REDIS_TIMEOUT_SECONDS = 2


def check_database():
    """Serve an actual query. `connections['default']` alone would report
    healthy while the server refused every statement."""
    try:
        with connections['default'].cursor() as cursor:
            cursor.execute('SELECT 1')
            cursor.fetchone()
    except Exception:
        logger.exception('healthz: database probe failed')
        return ERROR
    return OK


def check_redis():
    """PING the server Channels and the rate limiter depend on.

    Unconfigured Redis is SKIPPED, not ERROR: local dev runs the in-memory
    channel layer by design, and reporting 503 for a dependency nobody asked
    for would train people to ignore this endpoint.
    """
    url = getattr(settings, 'REDIS_URL', '')
    if not url:
        return SKIPPED
    try:
        import redis

        client = redis.Redis.from_url(
            url,
            socket_connect_timeout=REDIS_TIMEOUT_SECONDS,
            socket_timeout=REDIS_TIMEOUT_SECONDS,
        )
        try:
            if not client.ping():
                logger.error('healthz: redis PING returned falsey')
                return ERROR
        finally:
            client.close()
    except Exception:
        logger.exception('healthz: redis probe failed')
        return ERROR
    return OK


def check_migrations():
    """Report a release whose code has shipped ahead of its schema.

    PENDING rather than ERROR, deliberately. `release: manage.py migrate` in the
    Procfile runs before the new container is ever probed, so pending migrations
    should not happen at deploy time — and if they do occur later, the site is
    still serving customers. Returning ERROR here would make the external uptime
    monitor page a human at 2am for something that is not an outage, and a pager
    that cries wolf gets muted.

    Still surfaced, so it isn't invisible: it shows in the body and is logged.
    """
    try:
        executor = MigrationExecutor(connections['default'])
        plan = executor.migration_plan(executor.loader.graph.leaf_nodes())
    except Exception:
        # Couldn't determine it. Whatever is wrong is almost certainly the
        # database, which check_database reports on with the severity it
        # deserves — so don't page twice for one fault.
        logger.exception('healthz: migration probe failed')
        return PENDING
    if plan:
        logger.warning('healthz: %d unapplied migration(s)', len(plan))
        return PENDING
    return OK


def run_checks():
    """Every probe runs even if an earlier one failed — one request should
    report the whole picture rather than only the first thing to break."""
    return {
        'database': check_database(),
        'redis': check_redis(),
        'migrations': check_migrations(),
    }


def overall_status(checks):
    """Only ERROR degrades the endpoint.

    This function decides what wakes someone up, because the external monitor
    can see nothing but the status code. So the bar for a non-200 is "customers
    cannot use the site" — an unreachable database or Redis. SKIPPED (a
    dependency this configuration doesn't use) and PENDING (surfaced, not
    serious) are both reported without failing.
    """
    return STATUS_DEGRADED if ERROR in checks.values() else STATUS_OK
