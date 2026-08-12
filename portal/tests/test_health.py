"""The /healthz/ endpoint Dokku gates deploys on (#50).

The probes must genuinely exercise each dependency — a check that only proves
"Django imported a settings module" would pass while the app returned 500 on
every request, which is exactly the hole this endpoint closes.

The response must also stay boring: it is public and unauthenticated, so it
gets to say which subsystem is unhealthy and nothing else.
"""
from unittest import mock
from unittest import skipUnless

from django.db import connections
from django.db.migrations.executor import MigrationExecutor
from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.urls import Resolver404, resolve, reverse

from portal import health


class DatabaseProbeTests(TestCase):
    def test_reports_ok_against_a_live_connection(self):
        self.assertEqual(health.check_database(), health.OK)

    def test_reports_error_when_the_query_fails(self):
        """A connection object that exists but cannot serve a query is the
        failure mode a naive `connections['default']` check misses.

        The log assertion is load-bearing: the response deliberately withholds
        the reason, so if we don't log it, it exists nowhere.
        """
        with mock.patch.object(
            connections['default'], 'cursor', side_effect=OSError('connection reset')
        ), self.assertLogs('portal.health', level='ERROR'):
            self.assertEqual(health.check_database(), health.ERROR)


#: Where `docker-compose.yml` publishes redis. Deliberately not 6379, so the
#: probe is exercised against a real server without assuming the developer has
#: one running system-wide.
LIVE_REDIS_URL = 'redis://127.0.0.1:6380/0'


def redis_is_running(url=LIVE_REDIS_URL):
    import redis
    try:
        return bool(redis.Redis.from_url(url, socket_connect_timeout=1).ping())
    except Exception:
        return False


class RedisProbeTests(SimpleTestCase):
    @override_settings(REDIS_URL='')
    def test_is_skipped_when_no_redis_is_configured(self):
        """Local dev runs the in-memory channel layer on purpose. An absent
        optional dependency is not an outage, so it must not fail the deploy."""
        self.assertEqual(health.check_redis(), health.SKIPPED)

    @override_settings(REDIS_URL='redis://127.0.0.1:1/0')
    def test_reports_error_when_redis_is_configured_but_unreachable(self):
        with self.assertLogs('portal.health', level='ERROR'):
            self.assertEqual(health.check_redis(), health.ERROR)

    @skipUnless(redis_is_running(), f'no redis listening on {LIVE_REDIS_URL}')
    @override_settings(REDIS_URL=LIVE_REDIS_URL)
    def test_reports_ok_against_a_live_server(self):
        """`docker run -p 6380:6379 redis:7-alpine` to exercise this locally.

        Proves the probe actually completes a round-trip, rather than reporting
        ok for any URL that merely parses.
        """
        self.assertEqual(health.check_redis(), health.OK)


class MigrationProbeTests(TestCase):
    def test_reports_ok_when_every_migration_is_applied(self):
        self.assertEqual(health.check_migrations(), health.OK)

    def test_reports_pending_when_a_migration_is_unapplied(self):
        """PENDING, not ERROR. `release: manage.py migrate` runs before the new
        container is ever probed, so this is informational — and an unapplied
        migration is not customers being unable to use the site, which is the
        only thing that should wake someone up."""
        with mock.patch.object(
            MigrationExecutor, 'migration_plan',
            return_value=[('portal', '0001_initial')],
        ), self.assertLogs('portal.health', level='WARNING') as logged:
            self.assertEqual(health.check_migrations(), health.PENDING)
        self.assertIn('unapplied', ' '.join(logged.output))


class OverallStatusTests(SimpleTestCase):
    def test_is_ok_when_probes_pass(self):
        self.assertEqual(
            health.overall_status({'database': health.OK, 'redis': health.OK}),
            health.STATUS_OK,
        )

    def test_ignores_skipped_probes(self):
        self.assertEqual(
            health.overall_status({'database': health.OK, 'redis': health.SKIPPED}),
            health.STATUS_OK,
        )

    def test_ignores_pending_probes(self):
        """PENDING is surfaced but must not degrade the endpoint — this function
        is what decides whether a human gets paged."""
        self.assertEqual(
            health.overall_status({'database': health.OK, 'migrations': health.PENDING}),
            health.STATUS_OK,
        )

    def test_is_degraded_when_any_probe_errors(self):
        self.assertEqual(
            health.overall_status({'database': health.OK, 'redis': health.ERROR}),
            health.STATUS_DEGRADED,
        )


class HealthzViewTests(TestCase):
    url = '/healthz/'

    def test_returns_200_and_ok_when_every_dependency_is_healthy(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['status'], health.STATUS_OK)

    def test_returns_503_when_a_dependency_is_unreachable(self):
        """The point of the endpoint: a broken release must fail to promote
        rather than going live green."""
        with mock.patch.object(health, 'check_database', return_value=health.ERROR):
            response = self.client.get(self.url)
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()['status'], health.STATUS_DEGRADED)
        self.assertEqual(response.json()['checks']['database'], health.ERROR)

    def test_needs_no_authentication(self):
        """Dokku's checker has no session, and neither does an uptime monitor."""
        self.assertEqual(self.client.get(self.url).status_code, 200)

    def test_names_every_dependency_it_probed(self):
        checks = self.client.get(self.url).json()['checks']
        self.assertEqual(set(checks), {'database', 'redis', 'migrations'})

    def test_gives_an_attacker_nothing_beyond_status(self):
        """No version strings, no settings, no counts, no exception text — it is
        a public endpoint."""
        payload = self.client.get(self.url).json()
        self.assertEqual(set(payload), {'status', 'checks'})
        self.assertTrue(
            all(v in (health.OK, health.ERROR, health.SKIPPED, health.PENDING)
                for v in payload['checks'].values()),
            f'probe values must be a fixed vocabulary, got {payload["checks"]}',
        )

    def test_does_not_leak_the_underlying_error_when_a_probe_fails(self):
        with mock.patch.object(
            connections['default'], 'cursor',
            side_effect=OSError('could not connect to 10.0.0.5:5432 as citemed_prod'),
        ), self.assertLogs('portal.health', level='ERROR'):
            body = self.client.get(self.url).content.decode()
        self.assertNotIn('10.0.0.5', body)
        self.assertNotIn('citemed_prod', body)

    def test_rejects_a_post(self):
        """Read-only: nothing about health is mutable.

        Asserted as "refused", not as a specific code, because the two differ by
        client. Django's test client skips CSRF, so `require_GET` answers 405;
        a real browser or curl is rejected at 403 by CsrfViewMiddleware first.
        Both are correct — pinning 405 would assert something production never
        does. The endpoint is deliberately NOT csrf_exempt: PR #40 removed every
        one of those and there is a sweep test keeping them gone.
        """
        self.assertEqual(self.client.post(self.url).status_code, 405)

        enforcing = Client(enforce_csrf_checks=True)
        self.assertEqual(enforcing.post(self.url).status_code, 403)

    def test_is_never_cached(self):
        """A cached 200 would mask an ongoing outage from the monitor."""
        self.assertIn('no-store', self.client.get(self.url)['Cache-Control'])


class HealthzReachabilityTests(SimpleTestCase):
    """Production settings must not make the endpoint unreachable to the very
    checker it exists for. Both of these are silent killers: the app is healthy,
    the probe says otherwise, and the release is rolled back for no reason."""

    def test_is_not_bounced_to_https_by_the_ssl_redirect(self):
        """SECURE_SSL_REDIRECT is on in production. Dokku probes over plain HTTP
        inside the container network, so without an exemption a perfectly
        healthy app answers the check with a 301."""
        from django.http import HttpResponse
        from django.middleware.security import SecurityMiddleware
        from django.test import RequestFactory

        with override_settings(SECURE_SSL_REDIRECT=True):
            middleware = SecurityMiddleware(lambda request: HttpResponse('ok'))
            response = middleware(RequestFactory().get('/healthz/'))
            self.assertEqual(response.status_code, 200)

            # Guard against a lazy fix that exempts everything.
            other = middleware(RequestFactory().get('/api/tickets/'))
            self.assertEqual(other.status_code, 301)


class HealthzRoutingTests(SimpleTestCase):
    def test_is_not_swallowed_by_the_spa_catch_all(self):
        """The catch-all serves index.html for anything it doesn't exclude, so a
        misordered urlconf would hand Dokku a 200 full of HTML for a dead app."""
        self.assertEqual(resolve('/healthz/').func, health_view())

    def test_reverses_by_name(self):
        self.assertEqual(reverse('healthz'), '/healthz/')


def health_view():
    from portal.views import health as health_views
    return health_views.healthz


class PagerSemanticsTests(TestCase):
    """One endpoint serves two consumers: Dokku's deploy gate and an external
    uptime monitor that can only see a status code. What returns 503 therefore
    decides what wakes a human at 2am, and it must be "customers cannot use the
    site" — nothing weaker."""
    url = '/healthz/'

    def test_a_pending_migration_does_not_page_anyone(self):
        with mock.patch.object(
            MigrationExecutor, 'migration_plan',
            return_value=[('portal', '0001_initial')],
        ), self.assertLogs('portal.health', level='WARNING'):
            response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['checks']['migrations'], health.PENDING)

    def test_a_pending_migration_is_still_reported_so_it_is_not_invisible(self):
        with mock.patch.object(
            MigrationExecutor, 'migration_plan',
            return_value=[('portal', '0001_initial')],
        ), self.assertLogs('portal.health', level='WARNING'):
            body = self.client.get(self.url).json()
        self.assertNotEqual(body['checks']['migrations'], health.OK)

    def test_an_unreachable_database_still_pages(self):
        """The case that genuinely means nobody can use the site."""
        with mock.patch.object(health, 'check_database', return_value=health.ERROR):
            self.assertEqual(self.client.get(self.url).status_code, 503)

    def test_an_unreachable_redis_still_pages(self):
        """Channels and the rate limiter both depend on it."""
        with mock.patch.object(health, 'check_redis', return_value=health.ERROR):
            self.assertEqual(self.client.get(self.url).status_code, 503)
