"""Seed a client with people to push files to, for local development.

`create_test_users` makes users with no company, which is enough for auth but
not for anything company-scoped: a share has to go to named members of a
specific client, so testing the push by hand needs a company that actually has
some. This creates one and prints a sign-in link per person.

    python manage.py seed_share_demo

Idempotent — re-run it any time to mint fresh links. Local use only; the
accounts are on a made-up domain so they can never receive real mail.
"""
import secrets
from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from portal.models import Bucket, Company, MagicLinkToken, PortalUser

# .test is reserved by RFC 2606 and can never resolve, so a stray email to one
# of these bounces at the sender rather than reaching a real person.
PEOPLE = [
    ('jane@acme.test', 'Jane Okafor', PortalUser.ROLE_CUSTOMER, True),
    ('raj@acme.test', 'Raj Patel', PortalUser.ROLE_CUSTOMER, True),
    ('ana@citemed.test', 'Ana Silva', PortalUser.ROLE_OWNER, False),
]


class Command(BaseCommand):
    help = 'Seed a demo client with members, for testing staff→customer shares.'

    def add_arguments(self, parser):
        parser.add_argument('--company', default='Acme Devices')

    def handle(self, *args, **opts):
        company, _ = Company.objects.get_or_create(name=opts['company'])
        # The customer file page expects this to exist; get_general_bucket
        # would create it on first load anyway, but seeding it keeps the very
        # first render from being a special case.
        Bucket.objects.get_or_create(
            company=company, kind=Bucket.KIND_GENERAL,
            defaults={'title': 'General uploads', 'status': 'general'},
        )

        frontend = getattr(settings, 'FRONTEND_URL', 'http://localhost:5174').rstrip('/')
        for email, name, role, in_company in PEOPLE:
            user, _ = PortalUser.objects.get_or_create(email=email)
            user.name = name
            user.role = role
            # Staff belong to no company — that is what makes them staff here.
            user.company = company if in_company else None
            user.access_enabled = True
            user.save()
            token = MagicLinkToken.objects.create(
                user=user, token=secrets.token_urlsafe(32),
                expires_at=timezone.now() + timedelta(hours=12),
            )
            where = company.name if in_company else 'CiteMed staff'
            self.stdout.write(
                f'{name} ({where})\n  {frontend}/auth/verify?token={token.token}\n')

        self.stdout.write(self.style.SUCCESS(
            f'Seeded {opts["company"]}. Sign in as Ana to push, as Jane or Raj to receive.'))
