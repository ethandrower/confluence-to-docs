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
