import logging

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError

from portal.confluence.sync import sync_space

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Sync pages from Confluence into the portal, scoped to the allowed spaces.'

    def add_arguments(self, parser):
        parser.add_argument('--space', type=str, default=None,
                            help='Confluence space key. Defaults to every space in DOCS_ALLOWED_SPACES.')
        parser.add_argument('--full', action='store_true', help='Full sync (re-sync all pages)')
        parser.add_argument('--incremental', action='store_true', help='Incremental sync (changed pages only)')
        parser.add_argument('--allow-any-space', action='store_true',
                            help='Override the allowlist guard (use with care).')

    def handle(self, *args, **options):
        allowed = set(getattr(settings, 'DOCS_ALLOWED_SPACES', []) or [])
        full = options['full'] or not options['incremental']

        # Decide which spaces to sync.
        if options['space']:
            targets = [options['space']]
        elif allowed:
            targets = sorted(allowed)
        elif settings.CONFLUENCE_SPACE_KEY:
            targets = [settings.CONFLUENCE_SPACE_KEY]
        else:
            raise CommandError(
                'No space to sync: pass --space or set DOCS_ALLOWED_SPACES.'
            )

        # Guard: never sync a space outside the allowlist. This is what keeps a
        # sync from silently re-importing the internal spaces (Engineering /
        # Operations / Collective) we deliberately removed for the audit.
        if allowed and not options['allow_any_space']:
            blocked = [s for s in targets if s not in allowed]
            if blocked:
                raise CommandError(
                    f'Refusing to sync space(s) {blocked} — not in DOCS_ALLOWED_SPACES '
                    f'({sorted(allowed)}). Use --allow-any-space to override.'
                )

        for space_key in targets:
            self.stdout.write(f"Syncing space: {space_key} ({'full' if full else 'incremental'})")
            try:
                result = sync_space(space_key, full=full)
                self.stdout.write(self.style.SUCCESS(
                    f"  synced: {result['synced']}, skipped: {result['skipped']}, errors: {result['errors']}"
                ))
            except Exception as e:
                self.stderr.write(self.style.ERROR(f"  sync failed for {space_key}: {e}"))
                raise

        # Authoritative internal-link pass after all pages are in the DB
        # (a page can only resolve a link once its target page exists).
        self.stdout.write('Resolving internal links...')
        call_command('resolve_internal_links')
