"""Mint a sign-in link for an existing user, without sending any email.

Local testing needs a way in that does not depend on mail being configured.
`seed_share_demo` mints links, but only for the three accounts it creates, and
`create_test_users` only for its own two — so signing in as anybody else (an
owner seeded by migration 0005/0007, say, or a user you just added through the
admin UI) had no route at all when the email backend was the console.

    python manage.py magic_link --email edrower@citemed.com

Prints the URL. Does NOT create the user: a typo should fail loudly rather than
silently mint a login for an account that shouldn't exist. Use `find_user` to
check an address first, or `--list` to see who is available.

On the privilege question: this mints a session for an existing account, and
anyone able to run `manage.py` can already read and rewrite the whole database
— so it grants nothing new. The `verify_magic_link` view logs every redemption
with source IP and user agent either way.
"""
import secrets
from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from portal.models import MagicLinkToken, PortalUser


class Command(BaseCommand):
    help = "Print a sign-in link for an existing PortalUser (no email sent)."

    def add_arguments(self, parser):
        parser.add_argument('--email', help='Address of an existing PortalUser.')
        parser.add_argument('--list', action='store_true',
                            help='List the accounts that can sign in, then exit.')
        parser.add_argument('--hours', type=int, default=12,
                            help='How long the link stays valid (default: 12).')

    def handle(self, *args, **opts):
        if opts['list']:
            self._list()
            return
        if not opts['email']:
            self.stderr.write('Give --email, or --list to see what exists.')
            return

        email = opts['email'].strip()
        user = PortalUser.objects.filter(email__iexact=email).first()
        if not user:
            self.stderr.write(self.style.ERROR(f'No such user: {email}'))
            self._list()
            return
        if not user.access_enabled:
            # Minting anyway would produce a link that mints a session the
            # login view then refuses — a confusing way to learn the account
            # is switched off.
            self.stderr.write(self.style.ERROR(
                f'{user.email} exists but access is disabled; enable it first.'))
            return

        token = MagicLinkToken.objects.create(
            user=user, token=secrets.token_urlsafe(32),
            expires_at=timezone.now() + timedelta(hours=opts['hours']),
        )
        # FRONTEND_URL differs per stack (dev 5174, the parity profile 8090), so
        # the link is built from settings rather than hardcoded — a link that
        # points at the wrong port looks like a broken token.
        frontend = getattr(settings, 'FRONTEND_URL', 'http://localhost:5174').rstrip('/')
        where = user.company.name if user.company_id else 'no company (staff)'
        self.stdout.write(
            f'{user.name or user.email} · {user.role} · {where}\n'
            f'  {frontend}/auth/verify?token={token.token}\n')
        self.stdout.write(self.style.SUCCESS(
            f'Valid for {opts["hours"]}h, single use. Click "Sign in" on the page — '
            'the button is deliberate, so an email scanner cannot spend the token.'))

    def _list(self):
        users = PortalUser.objects.filter(access_enabled=True).order_by('email')
        if not users:
            self.stdout.write('No enabled users.')
            return
        self.stdout.write('Accounts that can sign in:')
        for u in users:
            where = u.company.name if u.company_id else '—'
            self.stdout.write(f'  {u.email:<34} {u.role:<9} {where}')
