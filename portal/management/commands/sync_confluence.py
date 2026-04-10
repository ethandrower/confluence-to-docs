from django.core.management.base import BaseCommand
from django.conf import settings
from portal.confluence.sync import sync_space
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Sync pages from a Confluence space into the portal database'

    def add_arguments(self, parser):
        parser.add_argument('--space', type=str, default=None, help='Confluence space key')
        parser.add_argument('--full', action='store_true', help='Full sync (re-sync all pages)')
        parser.add_argument('--incremental', action='store_true', help='Incremental sync (changed pages only)')

    def handle(self, *args, **options):
        space_key = options['space'] or settings.CONFLUENCE_SPACE_KEY
        full = options['full'] or not options['incremental']

        self.stdout.write(f"Syncing space: {space_key} ({'full' if full else 'incremental'})")

        try:
            result = sync_space(space_key, full=full)
            self.stdout.write(self.style.SUCCESS(
                f"Done — synced: {result['synced']}, skipped: {result['skipped']}, errors: {result['errors']}"
            ))
        except Exception as e:
            self.stderr.write(self.style.ERROR(f"Sync failed: {e}"))
            raise
