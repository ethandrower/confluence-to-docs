"""
Rewrite Confluence inter-page links in already-synced pages.

Walks every published DocPage, rewrites internal Confluence links in its
rendered_html to point at the portal (/docs/<slug>), and unwraps links we
can't resolve. Idempotent — safe to run repeatedly.

Usage:
    python manage.py resolve_internal_links
    python manage.py resolve_internal_links --dry-run
    python manage.py resolve_internal_links --space ECD
"""
from django.conf import settings
from django.core.management.base import BaseCommand

from portal.links import build_link_map, rewrite_internal_links
from portal.models import DocPage


class Command(BaseCommand):
    help = 'Rewrite internal Confluence links in synced pages to portal /docs/ links.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Report what would change without writing to the DB.',
        )
        parser.add_argument(
            '--space', type=str, default=None,
            help='Only process pages in this space key.',
        )

    def handle(self, *args, **options):
        dry = options['dry_run']
        space = options['space']

        # The link map honors DOCS_ALLOWED_SPACES so links to hidden spaces
        # (Engineering/Ops/Collective) are treated as unresolvable and get
        # unwrapped — exactly what we want once those spaces are removed.
        allowed = set(getattr(settings, 'DOCS_ALLOWED_SPACES', []) or [])
        link_map = build_link_map(allowed or None)
        self.stdout.write(
            f'Link map: {len(link_map)} resolvable pages'
            + (f' (allowed spaces: {", ".join(sorted(allowed))})' if allowed else ' (all spaces)')
        )

        pages = DocPage.objects.filter(is_published=True)
        if space:
            pages = pages.filter(space_key=space)

        total_resolved = total_unwrapped = pages_changed = 0
        for page in pages.iterator():
            new_html, stats = rewrite_internal_links(page.rendered_html, link_map)
            if stats['resolved'] or stats['unwrapped']:
                pages_changed += 1
                total_resolved += stats['resolved']
                total_unwrapped += stats['unwrapped']
                if not dry:
                    page.rendered_html = new_html
                    page.save(update_fields=['rendered_html'])
                self.stdout.write(
                    f"  [{page.space_key}] {page.title[:50]}: "
                    f"{stats['resolved']} resolved, {stats['unwrapped']} unwrapped"
                )

        prefix = '[dry-run] ' if dry else ''
        self.stdout.write(self.style.SUCCESS(
            f'{prefix}Done — {pages_changed} pages changed, '
            f'{total_resolved} links resolved, {total_unwrapped} unwrapped.'
        ))
