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

from portal.models import (
    Bucket, Company, MagicLinkToken, PortalUser, SharedFile,
)

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

        # A staff-owned folder tree, because "for testing staff→customer
        # shares" needs an actual share to look at. Read-only to the customer
        # (origin=staff), and shaped the way CS actually asks for it: a
        # Reference Library with the PDFs kept in their own subfolder, so
        # supporting documents stay separate from the articles themselves.
        library, _ = Bucket.objects.get_or_create(
            company=company, kind=Bucket.KIND_FOLDER, title='Reference Library',
            parent=None, origin=Bucket.ORIGIN_STAFF,
            defaults={'status': 'general',
                      'description': 'Shared with you by CiteMed.'},
        )
        pdfs, _ = Bucket.objects.get_or_create(
            company=company, kind=Bucket.KIND_FOLDER, title='PDFs',
            parent=library, origin=Bucket.ORIGIN_STAFF,
            defaults={'status': 'general'},
        )
        # A link, not an upload: there are no bytes behind it, so seeding one
        # needs no object store and works on any environment.
        SharedFile.objects.get_or_create(
            bucket=pdfs, company=company,
            original_name='EU MDR 2017/745 (EUR-Lex)',
            defaults={
                'item_type': SharedFile.ITEM_LINK,
                'external_url': 'https://eur-lex.europa.eu/eli/reg/2017/745/oj',
                'storage_key': '', 'mime_type': '',
                'state': SharedFile.STATE_READY, 'processed': True,
            },
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
