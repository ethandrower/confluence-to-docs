"""Create portal tickets from customer-raised JSM requests.

Matches each unlinked Jira request's reporter email against the PortalUser
allowlist; a hit means a real onboarded customer and tells us their company.
Gated by settings.JIRA_INGEST — a no-op until enabled.

    python manage.py ingest_jira_requests --dry-run   # log only, writes nothing
    python manage.py ingest_jira_requests
"""
from django.core.management.base import BaseCommand

from portal.jira_ingest import ingest_requests


class Command(BaseCommand):
    help = 'Create portal tickets from customer-raised Jira service-desk requests.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Report what would be ingested without creating anything.')

    def handle(self, *args, **opts):
        dry = opts['dry_run']
        n = ingest_requests(dry_run=dry)
        prefix = 'would ingest' if dry else 'ingested'
        self.stdout.write(self.style.SUCCESS(
            f'ingest_jira_requests: {prefix} {n} request(s)'))
