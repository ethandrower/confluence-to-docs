"""Hard-delete soft-deleted shared files after a retention window.

Files customers delete are soft-deleted (kept for audit + accidental-deletion
recovery). This command permanently removes the S3 object and the DB row once
they're older than the retention window — the app-side half of the data-
retention policy. Pair it with an S3 lifecycle rule on the bucket (infra).

Schedule daily, e.g.:
    python manage.py purge_deleted_files --days 90
"""
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from portal import file_storage
from portal.models import SharedFile


class Command(BaseCommand):
    help = "Permanently delete soft-deleted shared files (and their S3 objects) older than --days."

    def add_arguments(self, parser):
        parser.add_argument('--days', type=int, default=90,
                            help='Retention window in days (default: 90).')
        parser.add_argument('--dry-run', action='store_true',
                            help='Report what would be purged without deleting.')

    def handle(self, *args, **opts):
        cutoff = timezone.now() - timedelta(days=opts['days'])
        stale = SharedFile.objects.filter(deleted_at__isnull=False, deleted_at__lt=cutoff)
        count = stale.count()
        if opts['dry_run']:
            self.stdout.write(f"[dry-run] {count} soft-deleted file(s) older than {opts['days']}d")
            return

        purged = 0
        for f in stale.iterator():
            if f.storage_key:
                file_storage.delete_object(f.storage_key)  # best-effort; logs on failure
            f.delete()
            purged += 1
        self.stdout.write(self.style.SUCCESS(
            f"Permanently purged {purged} soft-deleted file(s) older than {opts['days']}d."
        ))
