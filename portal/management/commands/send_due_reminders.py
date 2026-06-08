"""Email customers a reminder about open document requests that are due soon
or overdue. Throttled to at most once per request per ~day so it can run
daily from cron without spamming.

    python manage.py send_due_reminders --within-days 2
"""
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from portal import file_notify
from portal.models import Bucket


class Command(BaseCommand):
    help = "Email reminders for open requests due within --within-days (or overdue)."

    def add_arguments(self, parser):
        parser.add_argument('--within-days', type=int, default=2,
                            help='Remind when due within this many days (default: 2).')
        parser.add_argument('--dry-run', action='store_true')

    def handle(self, *args, **opts):
        now = timezone.now()
        soon = now + timedelta(days=opts['within_days'])
        # Open/partial requests with a due date, not complete, due within window
        # (includes overdue), not reminded in the last 20h.
        qs = (Bucket.objects.filter(kind=Bucket.KIND_REQUEST, due_at__isnull=False, due_at__lte=soon)
              .exclude(status='complete'))
        sent = 0
        for b in qs.iterator():
            if b.last_reminder_at and (now - b.last_reminder_at) < timedelta(hours=20):
                continue
            overdue = b.due_at < now
            if opts['dry_run']:
                self.stdout.write(f"[dry-run] would remind: {b.company.name} — {b.title} (overdue={overdue})")
                continue
            file_notify.notify_due_reminder(b, overdue=overdue)
            b.last_reminder_at = now
            b.save(update_fields=['last_reminder_at'])
            sent += 1
        if not opts['dry_run']:
            self.stdout.write(self.style.SUCCESS(f"Sent {sent} due-date reminder(s)."))
