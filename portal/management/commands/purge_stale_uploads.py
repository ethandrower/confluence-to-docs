"""Purge abandoned file-share uploads.

`upload-init` creates a SharedFile row in state='uploading' and reserves an S3
key before the browser→S3 PUT. If that PUT fails or the user abandons, the row
(and possibly the S3 object) would linger forever. This command reclaims them.

Schedule it (cron / celery-beat) to run daily, e.g.:
    python manage.py purge_stale_uploads --hours 24
"""
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from portal import file_storage
from portal.models import SharedFile


class Command(BaseCommand):
    help = "Delete abandoned uploads (state='uploading') older than --hours and their S3 objects."

    def add_arguments(self, parser):
        parser.add_argument('--hours', type=int, default=24,
                            help='Age threshold in hours (default: 24).')
        parser.add_argument('--dry-run', action='store_true',
                            help='Report what would be purged without deleting.')

    def handle(self, *args, **opts):
        cutoff = timezone.now() - timedelta(hours=opts['hours'])
        stale = SharedFile.objects.filter(
            state=SharedFile.STATE_UPLOADING, uploaded_at__lt=cutoff,
        )
        count = stale.count()
        if opts['dry_run']:
            self.stdout.write(f"[dry-run] {count} stale upload(s) older than {opts['hours']}h")
            return

        purged = 0
        for f in stale.iterator():
            if f.storage_key:
                file_storage.delete_object(f.storage_key)  # best-effort; logs on failure
            f.delete()
            purged += 1
        self.stdout.write(self.style.SUCCESS(
            f"Purged {purged} stale upload(s) older than {opts['hours']}h."
        ))
