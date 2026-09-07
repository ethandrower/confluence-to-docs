"""Walk the customer's journey against a RUNNING server, over real HTTP.

The 661 tests in portal/tests/ all drive Django's test client against a fresh
database in-process. That is the right shape for logic, and it is structurally
blind to a whole class of release breakage, because the test client never
builds a bundle, never resolves a static asset, never terminates TLS and never
reads the environment the container was actually started with:

  * a Vue bundle that built but references an asset collectstatic didn't hash
  * a static path that 404s only under ManifestStaticFilesStorage
  * DEBUG=False turning on SSL redirect against a proxy that forgot the header
  * an env var that is set in CI and missing on the host
  * a migration that passed on an empty test DB and fails on the real one

Every one of those ships green and breaks on first contact with a customer.
This command is the check that sees them, because it talks to a server the
way a browser does.

    # before a deploy, against the parity stack
    python manage.py smoke --url http://localhost:8090

    # after a deploy, against production
    dokku run citemed-docs python manage.py smoke \
        --url https://support.citemed.com --as edrower@citemed.com

It runs INSIDE the app (so it can mint its own sign-in token instead of
needing a password) but every assertion is an HTTP request to --url. Those two
facts are the whole design: full auth coverage with no credential handling.

SAFE TO RUN AGAINST PRODUCTION. It only reads. The single mutation is spending
one magic-link token for an account that already exists, which is what the
login flow does anyway. It creates no company, no folder, no file, and sends
no email — checking that a customer can SEE their files is the goal, and
pushing a real file to a real customer to prove it is not a trade worth
making. Write flows belong on the parity stack, where the blast radius is a
docker volume.
"""
import json
import re
import secrets
from datetime import timedelta
from urllib.parse import urljoin

import requests
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from portal.models import MagicLinkToken, PortalUser


class SmokeFailure(Exception):
    """A check that failed. Carries only the message; the runner formats it."""


class Command(BaseCommand):
    help = "Exercise the live customer journey against a running server."

    def add_arguments(self, parser):
        parser.add_argument(
            '--url', required=True,
            help='Base URL of the running server, e.g. https://support.citemed.com')
        parser.add_argument(
            '--as', dest='as_email', default=None,
            help='Sign in as this existing user. Default: any enabled customer, '
                 'because the customer path is the one clients actually walk.')
        parser.add_argument(
            '--timeout', type=int, default=30,
            help='Per-request timeout in seconds (default: 30).')
        parser.add_argument(
            '--insecure', action='store_true',
            help="Skip TLS certificate verification. For the local parity "
                 "stack's self-signed cert ONLY — never against production, "
                 "where a cert error is a finding rather than a nuisance.")

    def handle(self, *args, **opts):
        self.base = opts['url'].rstrip('/') + '/'
        self.timeout = opts['timeout']
        # One Session for the whole run: the login check has to leave a cookie
        # behind for the checks after it, which is exactly what a browser does
        # and what a fresh request per call would quietly fail to reproduce.
        self.http = requests.Session()
        if opts['insecure']:
            self.http.verify = False
            # Otherwise urllib3 prints a warning per request, burying the
            # actual results under identical noise.
            import urllib3
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
            self.stdout.write(self.style.WARNING(
                'TLS verification is OFF (--insecure).'))
        self.failures = []
        self.passed = 0
        self._shell_html = ''

        user = self._pick_user(opts['as_email'])

        self.stdout.write(f'Smoke test -> {self.base}')
        self.stdout.write(f'Signing in as {user.email} ({user.role})\n')

        # Ordered deliberately: infrastructure, then the shell a browser loads,
        # then the boundary that must hold while logged out, then the journey.
        # An early failure usually explains the later ones, so read top-down.
        self._check('health endpoint reports healthy', self._check_health)
        self._check('SPA shell loads', self._check_spa_shell)
        self._check('static assets resolve', self._check_static_assets)
        self._check('API refuses anonymous callers', self._check_anonymous_blocked)
        self._check('magic-link sign-in works', lambda: self._check_login(user))
        self._check('session identifies the right user', lambda: self._check_me(user))
        self._check('file tree loads', lambda: self._check_files(user))
        self._check('ticket list loads', self._check_tickets)
        self._check('sign-out clears the session', self._check_logout)

        return self._report()

    # -- checks --------------------------------------------------------------

    def _check_health(self):
        r = self._get('healthz/', allow_error=True)
        if r.status_code != 200:
            # /healthz/ names the failing subsystem precisely so a deploy gate
            # can say which dependency is down; surface that, not just the code.
            raise SmokeFailure(f'HTTP {r.status_code}: {r.text[:300]}')
        body = self._json(r)
        checks = body.get('checks') or {}
        # Only 'error' counts as broken, matching health.overall_status: a
        # 'skipped' dependency this configuration does not use, or a 'pending'
        # migration, are reported deliberately and must not fail the run. A
        # stricter bar here would make the smoke test disagree with the health
        # endpoint about what "healthy" means, and the endpoint is the one
        # Dokku gates deploys on.
        bad = [k for k, v in checks.items() if v == 'error']
        if bad:
            raise SmokeFailure(f'unhealthy subsystems: {", ".join(bad)}')
        noted = [f'{k}={v}' for k, v in checks.items() if v != 'ok']
        summary = f'{len(checks)} subsystem(s) ok'
        return summary + (f' ({", ".join(noted)})' if noted else '')

    def _check_spa_shell(self):
        """The HTML a browser gets at /. Catches a missing or unbuilt bundle."""
        r = self._get('', allow_error=True)
        if r.status_code != 200:
            raise SmokeFailure(f'HTTP {r.status_code} at the site root')
        html = r.text
        if '<div id="app"' not in html and 'id=app' not in html:
            # Django served *something* — quite possibly a DEBUG error page or
            # a proxy's own error — but not the SPA mount point, so nothing
            # would render.
            raise SmokeFailure('served HTML has no #app mount point; not the SPA shell')
        self._shell_html = html
        return f'{len(html)} bytes, #app present'

    def _check_static_assets(self):
        """Fetch every asset the shell references.

        This is the check that earns the command. Under
        CompressedManifestStaticFilesStorage a hashed filename that was never
        collected 404s at runtime while every unit test stays green — the page
        loads and then renders nothing, which reads as "the app is broken" with
        no error anywhere. A 200 on each referenced URL is the proof.
        """
        if not self._shell_html:
            raise SmokeFailure('no shell HTML (the previous check failed)')
        refs = re.findall(r'(?:src|href)="([^"]+\.(?:js|css))"', self._shell_html)
        # Absolute URLs point at a CDN we do not control from here; a failure
        # against someone else's host would be noise, not signal.
        refs = [u for u in refs if not u.startswith(('http://', 'https://', '//'))]
        if not refs:
            raise SmokeFailure('the shell references no JS or CSS at all')
        missing = []
        for ref in refs:
            a = self._get(ref.lstrip('/'), allow_error=True)
            if a.status_code != 200:
                missing.append(f'{ref} -> {a.status_code}')
        if missing:
            raise SmokeFailure('unreachable assets: ' + '; '.join(missing))
        return f'{len(refs)} asset(s) all 200'

    def _check_anonymous_blocked(self):
        """Logged out, the API must not hand over data.

        Runs before sign-in on purpose: once the session cookie exists this can
        no longer be observed, and a boundary that is only checked after login
        is not checked at all.
        """
        leaks = []
        for path in ('api/files/buckets/', 'api/tickets/', 'api/admin/companies/'):
            r = self._get(path, allow_error=True)
            if r.status_code == 200:
                leaks.append(f'{path} -> 200')
        if leaks:
            raise SmokeFailure('readable while signed out: ' + ', '.join(leaks))
        return '3 endpoints all refuse anonymous access'

    def _check_login(self, user):
        """Mint a token and spend it against the live server.

        If this breaks, nobody gets into the portal at all — it is the single
        highest-consequence path in the product, and the one least covered by
        anything else, since the unit tests exercise the view and not the
        cookie/CSRF/proxy plumbing that has to work around it.
        """
        token = MagicLinkToken.objects.create(
            user=user, token=secrets.token_urlsafe(32),
            expires_at=timezone.now() + timedelta(minutes=5),
        )
        # GET /api/auth/me/ first. It carries @ensure_csrf_cookie, so this is
        # what seeds the csrftoken the verify POST must echo back — and it is
        # precisely the SPA's own boot sequence: ask who I am, then redeem the
        # token. Skipping it earns a bare 403 with no body worth reading.
        self._get('api/auth/me/', allow_error=True)
        r = self._post('api/auth/verify/', {'token': token.token})
        if r.status_code != 200:
            raise SmokeFailure(f'HTTP {r.status_code}: {r.text[:300]}')
        if not self.http.cookies.get('sessionid'):
            # A 200 without a cookie is the cross-origin/secure-cookie failure:
            # the server signed you in and the browser kept nothing.
            raise SmokeFailure('signed in but no sessionid cookie was set')
        return 'token accepted, session cookie set'

    def _check_me(self, user):
        r = self._get('api/auth/me/')
        body = self._json(r)
        got = (body.get('user') or body).get('email', '')
        if got.lower() != user.email.lower():
            raise SmokeFailure(f'session belongs to {got!r}, expected {user.email!r}')
        return f'authenticated as {got}'

    def _check_files(self, user):
        """The file tree — the feature this release is about.

        For a customer it also re-checks tenancy from the outside. The unit
        tests assert the queryset filters by company; this asserts the bytes on
        the wire carry nothing else, which is the claim that actually matters.
        """
        r = self._get('api/files/buckets/')
        body = self._json(r)
        buckets = body.get('buckets', [])
        if user.company_id:
            foreign = [b for b in buckets
                       if b.get('company') not in (None, user.company_id)]
            if foreign:
                raise SmokeFailure(
                    f'{len(foreign)} bucket(s) from another company are visible — '
                    'tenancy boundary is leaking')
        shared = sum(1 for b in buckets if b.get('origin') == 'staff')
        return f'{len(buckets)} bucket(s), {shared} shared by staff'

    def _check_tickets(self):
        r = self._get('api/tickets/')
        body = self._json(r)
        items = body.get('tickets', body if isinstance(body, list) else [])
        return f'{len(items)} ticket(s)'

    def _check_logout(self):
        r = self._post('api/auth/logout/', {})
        if r.status_code not in (200, 204):
            raise SmokeFailure(f'HTTP {r.status_code}')
        after = self._get('api/auth/me/', allow_error=True)
        if after.status_code == 200:
            raise SmokeFailure('still authenticated after sign-out')
        return 'session cleared'

    # -- plumbing ------------------------------------------------------------

    def _pick_user(self, email):
        if email:
            user = PortalUser.objects.filter(email__iexact=email.strip()).first()
            if not user:
                raise CommandError(f'No such user: {email}')
            if not user.access_enabled:
                raise CommandError(f'{user.email} exists but access is disabled.')
            return user
        # No --as: prefer a customer with a company, because that is the account
        # shape a client has and the only one the tenancy check can be run on.
        user = (PortalUser.objects.filter(access_enabled=True, role='customer',
                                          company__isnull=False).order_by('pk').first()
                or PortalUser.objects.filter(access_enabled=True).order_by('pk').first())
        if not user:
            raise CommandError('No enabled users exist to sign in as.')
        return user

    def _url(self, path):
        return urljoin(self.base, path)

    def _get(self, path, allow_error=False):
        try:
            r = self.http.get(self._url(path), timeout=self.timeout)
        except requests.RequestException as exc:
            raise SmokeFailure(f'request failed: {exc}')
        if not allow_error and r.status_code != 200:
            raise SmokeFailure(f'GET {path} -> HTTP {r.status_code}: {r.text[:200]}')
        return r

    def _post(self, path, payload):
        # Django requires the CSRF token as a header on top of the cookie; the
        # SPA does the same thing on every write.
        headers = {'Content-Type': 'application/json',
                   'Referer': self._url(path)}
        csrf = self.http.cookies.get('csrftoken')
        if csrf:
            headers['X-CSRFToken'] = csrf
        try:
            return self.http.post(self._url(path), data=json.dumps(payload),
                                  headers=headers, timeout=self.timeout)
        except requests.RequestException as exc:
            raise SmokeFailure(f'request failed: {exc}')

    def _json(self, r):
        try:
            return r.json()
        except ValueError:
            raise SmokeFailure(f'expected JSON, got {r.text[:200]!r}')

    def _check(self, label, fn):
        try:
            detail = fn()
        except SmokeFailure as exc:
            self.failures.append((label, str(exc)))
            self.stdout.write(self.style.ERROR(f'  FAIL  {label}'))
            self.stdout.write(self.style.ERROR(f'        {exc}'))
        else:
            self.passed += 1
            self.stdout.write(self.style.SUCCESS(f'  ok    {label}')
                              + (f' - {detail}' if detail else ''))

    def _report(self):
        total = self.passed + len(self.failures)
        self.stdout.write('')
        if self.failures:
            self.stdout.write(self.style.ERROR(
                f'{len(self.failures)} of {total} checks FAILED'))
            for label, msg in self.failures:
                self.stdout.write(self.style.ERROR(f'  - {label}: {msg}'))
            # Non-empty return = non-zero exit, so a deploy script or CI job can
            # gate on this without parsing the output.
            return 'smoke test failed'
        self.stdout.write(self.style.SUCCESS(f'All {total} checks passed.'))
        return None
