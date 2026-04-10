import secrets
from datetime import timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone


class Command(BaseCommand):
    help = 'Create test portal users for browser automation testing'

    def handle(self, *args, **options):
        from portal.models import PortalUser, MagicLinkToken

        customer, _ = PortalUser.objects.get_or_create(
            email='test-customer@citemed-test.com',
            defaults={'is_jsm_customer': True, 'name': 'Test Customer'}
        )
        non_customer, _ = PortalUser.objects.get_or_create(
            email='test-noncustomer@citemed-test.com',
            defaults={'is_jsm_customer': False, 'name': 'Test Non-Customer'}
        )

        for user in [customer, non_customer]:
            token = MagicLinkToken.objects.create(
                user=user,
                token=secrets.token_urlsafe(32),
                expires_at=timezone.now() + timedelta(hours=1)
            )
            self.stdout.write(f'{user.email}: http://localhost:5173/auth/verify?token={token.token}')
