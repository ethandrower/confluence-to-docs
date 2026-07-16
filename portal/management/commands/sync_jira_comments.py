"""Ingest public Jira comments into their linked portal tickets (S1, ECD-2246).

Read-only against Jira, deduped, so re-running is safe. Only links in a
service-desk project (settings.JIRA_SYNC_PROJECTS) are synced — see jira_sync.

Two ways to run it:
  - Cron (simplest, zero standing infra): every minute via app.json.
  - Loop (near-real-time, founder-approved ~30s): run as a worker process so it
    can poll faster than cron's 1-minute floor.

    python manage.py sync_jira_comments                 # one pass, all tickets
    python manage.py sync_jira_comments --ticket 42      # one pass, one ticket
    python manage.py sync_jira_comments --loop --interval 30   # worker
"""
import time

from django.core.management.base import BaseCommand

from portal.jira_sync import sync_ticket_comments
from portal.models import Ticket


class Command(BaseCommand):
    help = 'Pull public Jira comments into linked portal tickets.'

    def add_arguments(self, parser):
        parser.add_argument('--ticket', type=int, default=None,
                            help='Only sync this ticket number.')
        parser.add_argument('--include-closed', action='store_true',
                            help='Also sync resolved/closed tickets (default: skip).')
        parser.add_argument('--loop', action='store_true',
                            help='Run continuously, sleeping --interval between passes.')
        parser.add_argument('--interval', type=int, default=30,
                            help='Seconds between passes in --loop mode (default: 30).')

    def _run_once(self, opts):
        # Only tickets that actually have a Jira link are worth a fetch.
        qs = Ticket.objects.filter(jira_links__isnull=False).distinct()
        if opts['ticket'] is not None:
            qs = qs.filter(number=opts['ticket'])
        elif not opts['include_closed']:
            qs = qs.exclude(status__in=[Ticket.STATUS_RESOLVED, Ticket.STATUS_CLOSED])

        tickets = total = 0
        for ticket in qs:
            tickets += 1
            total += sync_ticket_comments(ticket)
        return total, tickets

    def handle(self, *args, **opts):
        if not opts['loop']:
            total, tickets = self._run_once(opts)
            self.stdout.write(self.style.SUCCESS(
                f'sync_jira_comments: {total} comment(s) across {tickets} ticket(s)'))
            return

        interval = max(5, opts['interval'])
        self.stdout.write(f'sync_jira_comments: looping every {interval}s (Ctrl-C to stop)')
        while True:
            try:
                self._run_once(opts)
            except Exception as e:  # a bad pass must never kill the worker
                self.stderr.write(f'sync_jira_comments pass failed: {e}')
            time.sleep(interval)
