"""Mint a bearer token for the /api/v1/ integration API.

    manage.py create_api_client "RevenueHub"
    manage.py create_api_client "RevenueHub provisioning" --can-provision

The token is printed ONCE and then only its SHA-256 exists. If it is lost,
revoke the client in the Django admin and mint a new one — there is no recovery
path by design, so a database dump can never be turned back into a credential.
"""
from django.core.management.base import BaseCommand, CommandError

from portal.models import ApiClient


class Command(BaseCommand):
    help = 'Create an API client for /api/v1/ and print its token once.'

    def add_arguments(self, parser):
        parser.add_argument('name', help='Consumer name, e.g. "RevenueHub".')
        parser.add_argument(
            '--can-provision', action='store_true',
            help='Also allow POST to /api/v1/provisioning/ (create companies and '
                 'portal users). Off unless asked for: read access and the ability '
                 'to create customer logins are different grants.')

    def handle(self, *args, **options):
        name = options['name'].strip()
        if not name:
            raise CommandError('name must not be empty.')
        if ApiClient.objects.filter(name=name).exists():
            raise CommandError(
                f'An API client named {name!r} already exists. Pick another name, '
                f'or revoke the existing one in the admin first.')

        client, raw_token = ApiClient.issue(name)
        if options['can_provision']:
            client.can_provision = True
            client.save(update_fields=['can_provision'])

        self.stdout.write(self.style.SUCCESS(f'Created API client {client.name!r}.'))
        if client.can_provision:
            self.stdout.write(self.style.WARNING(
                '  This token CAN provision: it may create companies and portal '
                'users.'))
        self.stdout.write('')
        self.stdout.write('  Token (shown once — copy it now):')
        self.stdout.write(f'    {raw_token}')
        self.stdout.write('')
        self.stdout.write('  Use it as:  Authorization: Bearer <token>')
        self.stdout.write('  Revoke it in the Django admin (Portal → API clients).')
