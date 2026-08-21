"""Nudge customers who were sent a file or folder and never opened it.

At most TWO reminders per person per push — at 3 days and 7 days after the
send, both measured from the push itself — and then it stays quiet for good.
A third automated email was never going to be the thing that worked; past that
point staff chase it themselves from the per-person status panel on the folder.

Safe to run often; every decision is idempotent and throttled.

    python manage.py send_share_reminders --dry-run
"""
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from portal import file_notify
from portal.models import ShareNotice


class Command(BaseCommand):
    help = "Email up to two reminders to people who haven't opened a shared file or folder."

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true',
                            help='Report what would be sent without sending it.')

    def handle(self, *args, **opts):
        now = timezone.now()
        # Narrow in SQL on the three cheap conditions (unopened, still armed,
        # under the cap) and let due_for_reminder decide the time question —
        # the cadence lives on the model so the command and any future caller
        # cannot disagree about it.
        qs = (ShareNotice.objects
              .filter(first_opened_at__isnull=True, remind=True,
                      reminder_count__lt=ShareNotice.MAX_REMINDERS)
              .select_related('bucket', 'file', 'recipient'))
        sent = 0
        for n in qs.iterator():
            if not n.due_for_reminder(now):
                continue
            # Belt-and-braces against a double run: the cadence alone would
            # re-fire the same nudge if this command were run twice in a day
            # after a threshold passed but before reminder_count was written.
            if n.last_reminder_at and (now - n.last_reminder_at) < timedelta(hours=20):
                continue
            if opts['dry_run']:
                self.stdout.write(
                    f'[dry-run] would remind {n.recipient.email} about '
                    f'"{n.bucket.title}" (nudge {n.reminder_count + 1} of '
                    f'{ShareNotice.MAX_REMINDERS})')
                continue
            try:
                file_notify.notify_share_reminder(n)
            except Exception as e:
                # One bad address must not stop the sweep for everyone else.
                self.stderr.write(f'reminder failed for {n.recipient.email}: {e}')
                continue
            n.reminder_count += 1
            n.last_reminder_at = now
            n.save(update_fields=['reminder_count', 'last_reminder_at'])
            sent += 1
        if not opts['dry_run']:
            self.stdout.write(self.style.SUCCESS(f'Sent {sent} share reminder(s).'))
