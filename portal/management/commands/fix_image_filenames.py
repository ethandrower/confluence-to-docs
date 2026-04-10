"""
Management command to fix DocImage records whose local_path contains '?'
(gitbook-imported Confluence attachments stored with URLs as filenames).

Renames the files on disk, updates local_path in DB, and rewrites the
rendered_html src URLs in the associated DocPage.
"""
import os
from django.core.management.base import BaseCommand
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from portal.models import DocImage
from portal.confluence.sync import _sanitize_attachment_filename


class Command(BaseCommand):
    help = 'Fix DocImage records with URL-as-filename (gitbook imports)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Print what would change without modifying anything',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        fixed = skipped = errors = 0

        broken = DocImage.objects.filter(local_path__contains='?')
        self.stdout.write(f"Found {broken.count()} images with '?' in local_path")

        for img in broken:
            old_path = img.local_path
            page_id = old_path.split('/')[1] if old_path.startswith('confluence/') else None

            # Derive a clean name from the original filename
            safe_name = _sanitize_attachment_filename(img.original_filename)
            if not page_id:
                self.stdout.write(self.style.WARNING(f"  Skipping (unexpected path): {old_path}"))
                skipped += 1
                continue

            new_path = f'confluence/{page_id}/{safe_name}'

            if dry_run:
                self.stdout.write(f"  Would rename: {old_path} → {new_path}")
                fixed += 1
                continue

            try:
                # Read file from old location and re-save under clean name
                if not default_storage.exists(old_path):
                    self.stdout.write(self.style.WARNING(f"  File missing on disk: {old_path}"))
                    skipped += 1
                    continue

                with default_storage.open(old_path, 'rb') as f:
                    content = f.read()

                # Save to new location (storage handles uniqueness suffixes)
                saved_path = default_storage.save(new_path, ContentFile(content))
                new_url = default_storage.url(saved_path)
                old_url = default_storage.url(old_path)

                # Update rendered_html on the page
                page = img.page
                if page and old_url in page.rendered_html:
                    page.rendered_html = page.rendered_html.replace(old_url, new_url)
                    page.save(update_fields=['rendered_html'])

                # Update the DocImage record
                img.local_path = saved_path
                img.save(update_fields=['local_path'])

                # Delete the old file
                default_storage.delete(old_path)

                self.stdout.write(f"  Fixed: {os.path.basename(old_path)!r} → {os.path.basename(saved_path)!r}")
                fixed += 1

            except Exception as e:
                self.stdout.write(self.style.ERROR(f"  Error fixing {old_path}: {e}"))
                errors += 1

        self.stdout.write(
            self.style.SUCCESS(f"\nDone — fixed: {fixed}, skipped: {skipped}, errors: {errors}")
        )
