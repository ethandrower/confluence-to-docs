"""Tell staff about customer uploads, one message per batch.

Uploads used to email from inside `upload_complete`, once per file. A customer
dragging in a 150-file folder sent 150 emails to every agent and the shared
inbox, and made 150 blocking mail calls on the request path — four at a time,
since uploads run concurrently. The folder-upload feature made that trivially
reachable.

This sweeps everything staff have not been told about yet and sends one message
per (company, audience). The settle window matters: a batch is still arriving
while this runs, so files younger than the window are left for the next pass
rather than split across two emails.
"""
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from portal.models import SharedFile

# How long a file must have been ready before it is worth mentioning. Long
# enough for the rest of its batch to land, short enough that a lone upload is
# still reported promptly.
SETTLE_SECONDS = 90

# A ceiling on one pass, so a pathological backlog can't build an unbounded
# query or an unbounded email. The next run picks up the remainder.
MAX_PER_RUN = 2000


class Command(BaseCommand):
    help = 'Email staff a digest of customer uploads they have not been told about.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Report what would be sent without sending or marking anything.')
        parser.add_argument(
            '--settle', type=int, default=SETTLE_SECONDS,
            help=f'Seconds an upload must have settled before it is sent (default {SETTLE_SECONDS}).')

    def handle(self, *args, **opts):
        from portal import file_notify

        dry = opts['dry_run']
        cutoff = timezone.now() - timedelta(seconds=opts['settle'])

        pending = list(
            SharedFile.objects
            .filter(notified_at__isnull=True,
                    deleted_at__isnull=True,
                    state=SharedFile.STATE_READY,
                    uploaded_at__lte=cutoff)
            .select_related('company', 'bucket', 'bucket__requested_by')
            .order_by('uploaded_at')[:MAX_PER_RUN]
        )
        if not pending:
            self.stdout.write('Nothing to report.')
            return

        # Group by company AND audience. Routing is per-bucket — a request
        # naming a CSM goes to that CSM, everything else to every agent — so
        # collapsing a company's uploads into one email regardless of audience
        # would send a CSM's request files to the whole team, or hide them from
        # the team entirely. Grouping on the resolved recipients keeps who
        # hears about what exactly as it was, and only changes how many
        # messages it takes to say it.
        groups = {}
        for f in pending:
            recipients = file_notify.upload_recipients(f)
            if not recipients:
                continue
            key = (f.company_id, tuple(sorted(r.lower() for r in recipients)))
            groups.setdefault(key, {'company': f.company, 'recipients': recipients, 'files': []})
            groups[key]['files'].append(f)

        sent = 0
        for g in groups.values():
            n = len(g['files'])
            if dry:
                self.stdout.write(
                    f'[dry-run] would email {len(g["recipients"])} recipient(s) about '
                    f'{n} upload(s) from {g["company"].name}')
                continue
            try:
                file_notify.notify_upload_batch(g['company'], g['files'], g['recipients'])
            except Exception as e:
                # One company's bad address must not strand every other
                # company's files as permanently unnotified.
                self.stderr.write(f'Failed to email about {g["company"].name}: {e}')
                continue
            # Marked only after a successful send, so a failure retries next
            # run rather than silently swallowing the notification.
            with transaction.atomic():
                SharedFile.objects.filter(id__in=[f.id for f in g['files']]).update(
                    notified_at=timezone.now())
            sent += 1
            self.stdout.write(f'Emailed {len(g["recipients"])} about {n} upload(s) '
                              f'from {g["company"].name}')

        if dry:
            self.stdout.write(f'[dry-run] {len(groups)} email(s) for {len(pending)} upload(s)')
        else:
            self.stdout.write(f'Sent {sent} email(s) covering {len(pending)} upload(s)')
