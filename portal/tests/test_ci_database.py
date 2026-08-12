"""Keep CI honest about which database it is testing.

`settings.py` falls back to SQLite when DATABASE_URL is unset, silently. So if
the workflow's `env:` block is ever restructured and DATABASE_URL goes missing,
the whole suite reverts to SQLite, every test still passes, and the two things
the Postgres job exists to protect stop being checked with no signal at all:

  * the `_is_postgres()` branch in portal/models.py, which then only ever runs
    in production
  * column-length violations, which are a DataError on Postgres and silently
    accepted by SQLite

This turns that silent regression into a red build.
"""
import os
from unittest import skipUnless

from django.db import connection
from django.test import SimpleTestCase


# GitHub Actions sets CI=true on every runner. Skipped elsewhere on purpose:
# local development legitimately runs SQLite, and this assertion is about what
# the pipeline tests, not about what a developer's laptop must install.
@skipUnless(
    os.environ.get('CI') == 'true',
    'asserts the CI database only; local dev runs SQLite by design',
)
class ContinuousIntegrationDatabaseTests(SimpleTestCase):
    def test_ci_tests_against_postgres(self):
        self.assertEqual(
            connection.vendor, 'postgresql',
            'CI must run against Postgres, the engine production runs. '
            'A SQLite run here means DATABASE_URL is no longer reaching the '
            'test step — see .github/workflows/ci.yml.',
        )
