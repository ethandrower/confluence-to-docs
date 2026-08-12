"""A deploy must never sign sessions with a key anyone can read (#7).

The old default was the literal string 'dev-secret-key-change-in-production',
committed to a public repository. Any deploy that forgot to set SECRET_KEY
signed session cookies with it, so anyone could forge a cookie and sign in as
any user. Production sets the variable explicitly, so it was never exposed —
the risk is the next environment that forgets.

`resolve_secret_key` is a pure function so this is testable directly, rather
than by re-importing settings and asserting on a global.
"""
from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase

from citemed.env_config import DEV_PLACEHOLDER_KEY, resolve_secret_key


class ConfiguredKeyTests(SimpleTestCase):
    def test_uses_the_key_from_the_environment(self):
        self.assertEqual(resolve_secret_key('a-real-key', debug=False), 'a-real-key')

    def test_uses_it_in_debug_too(self):
        self.assertEqual(resolve_secret_key('a-real-key', debug=True), 'a-real-key')


class MissingKeyInProductionTests(SimpleTestCase):
    def test_refuses_to_boot(self):
        """Loudly, so a misconfigured deploy fails instead of running on a
        publicly-known signing key."""
        with self.assertRaises(ImproperlyConfigured):
            resolve_secret_key('', debug=False)

    def test_says_what_to_do_about_it(self):
        """The person hitting this is mid-deploy and needs the fix, not a
        stack trace to interpret."""
        with self.assertRaises(ImproperlyConfigured) as caught:
            resolve_secret_key(None, debug=False)
        message = str(caught.exception)
        self.assertIn('SECRET_KEY', message)
        self.assertIn('secrets.token_urlsafe', message)

    def test_refuses_the_dev_placeholder_even_when_set_explicitly(self):
        """Pasting the placeholder from .env.example is the same exposure as
        forgetting the variable, so it cannot be a way around the check."""
        with self.assertRaises(ImproperlyConfigured):
            resolve_secret_key(DEV_PLACEHOLDER_KEY, debug=False)


class MissingKeyInDevelopmentTests(SimpleTestCase):
    def generate(self):
        """Every call warns by design; captured so it doesn't spray the test
        output. The warning itself is asserted below."""
        with self.assertLogs('citemed.env_config', level='WARNING'):
            return resolve_secret_key('', debug=True)

    def test_generates_a_key_so_a_fresh_checkout_still_runs(self):
        generated = self.generate()
        self.assertTrue(generated)
        self.assertNotEqual(generated, DEV_PLACEHOLDER_KEY)

    def test_generates_a_different_key_each_time(self):
        """Ephemeral by design: sessions don't survive a restart, which is the
        nudge to set a real key, and the key is never a shared known value."""
        self.assertNotEqual(self.generate(), self.generate())

    def test_generates_a_key_long_enough_for_django_not_to_warn(self):
        """check --deploy flags keys under 50 characters (security.W009)."""
        self.assertGreaterEqual(len(self.generate()), 50)

    def test_warns_so_it_is_not_mistaken_for_a_working_configuration(self):
        with self.assertLogs('citemed.env_config', level='WARNING') as logged:
            resolve_secret_key('', debug=True)
        self.assertIn('SECRET_KEY', ' '.join(logged.output))
