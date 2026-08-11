"""Settings must be safe when a deploy forgets to configure them.

These tests re-execute `citemed.settings` under a controlled environment rather
than asserting on the live `django.conf.settings`, because the live object was
built from THIS developer's `.env` (which sets DEBUG=True) and so can never
show what a fresh deploy would get.

`read_env` is stubbed out for the same reason: it would read the repo's own
`.env` back in and mask the very default under test.

Reloading the module is safe here: `django.conf.settings` copied its values at
setup time and does not track the module object, so the running test process is
unaffected. The cleanup reload restores `sys.modules` to a copy built from the
real environment regardless.
"""
import importlib
import os
from unittest import mock

import environ
from django.test import SimpleTestCase


def load_settings(**env_overrides):
    """Execute citemed/settings.py with `env_overrides` as the whole environment."""
    scrubbed = {
        k: v for k, v in os.environ.items()
        if k not in ('DEBUG', 'SECRET_KEY')
    }
    scrubbed.update(env_overrides)
    with mock.patch.dict(os.environ, scrubbed, clear=True), \
         mock.patch.object(environ.Env, 'read_env', lambda *a, **kw: None):
        return importlib.reload(importlib.import_module('citemed.settings'))


class AllowedHostsTests(SimpleTestCase):
    """The container must accept a request addressed to itself (#50).

    Dokku's zero-downtime check probes http://<container-ip>:5000/healthz/, so
    the container's own IP arrives as the Host header. With ALLOWED_HOSTS set to
    the public domain and nothing else, Django answers 400 DisallowedHost — the
    check fails, and a healthy release is rolled back for a reason that has
    nothing to do with its health.
    """
    def setUp(self):
        self.addCleanup(lambda: importlib.reload(importlib.import_module('citemed.settings')))

    def _own_ip(self):
        import socket
        return socket.gethostbyname(socket.gethostname())

    def test_the_containers_own_ip_is_allowed_in_production(self):
        settings_module = load_settings(ALLOWED_HOSTS='support.citemed.com')
        self.assertIn(self._own_ip(), settings_module.ALLOWED_HOSTS)
        # The configured domain must survive, not be replaced.
        self.assertIn('support.citemed.com', settings_module.ALLOWED_HOSTS)

    def test_is_left_alone_in_local_dev(self):
        """DEBUG already relaxes host checking, so there is nothing to add and
        no reason to resolve hostnames on every dev server start."""
        settings_module = load_settings(DEBUG='True', ALLOWED_HOSTS='localhost')
        self.assertEqual(settings_module.ALLOWED_HOSTS, ['localhost'])


class DebugDefaultTests(SimpleTestCase):
    def setUp(self):
        # Leave sys.modules holding a module built from the real environment,
        # whatever this test did to it.
        self.addCleanup(lambda: importlib.reload(importlib.import_module('citemed.settings')))

    def test_debug_is_off_when_the_environment_does_not_set_it(self):
        """A deploy that forgets DEBUG must not get a stack-trace-leaking app."""
        self.assertIs(load_settings().DEBUG, False)

    def test_debug_can_still_be_opted_into(self):
        self.assertIs(load_settings(DEBUG='True').DEBUG, True)

    def test_whitenoise_follows_debug_rather_than_re_reading_the_environment(self):
        """The static-files branch used to read DEBUG a second time with its own
        default, so the two could disagree about what mode we were in."""
        self.assertIs(load_settings()._USE_WHITENOISE, True)
        self.assertIs(load_settings(DEBUG='True')._USE_WHITENOISE, False)
