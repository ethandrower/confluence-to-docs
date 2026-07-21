"""Option A: create + link a Jira issue for open, unlinked portal tickets
(ECD-2246). Gated by settings.JIRA_AUTO_CREATE — a no-op until enabled.
Idempotent (already-linked tickets are skipped); best-effort. Pairs with
sync_jira_comments (S1), which then pulls the issue's public replies back.

    python manage.py provision_jira_issues
    python manage.py provision_jira_issues --ticket 42
"""
from django.core.management.base import BaseCommand

from portal.jira_sync import provision_ticket_issue
from portal.models import Ticket


class Command(BaseCommand):
    help = 'Create + link Jira issues for open, unlinked portal tickets (Option A).'

    def add_arguments(self, parser):
        parser.add_argument('--ticket', type=int, default=None,
                            help='Only provision this ticket number.')

    def handle(self, *args, **opts):
        qs = Ticket.objects.filter(jira_links__isnull=True)
        if opts['ticket'] is not None:
            qs = qs.filter(number=opts['ticket'])
        else:
            qs = qs.exclude(status__in=[Ticket.STATUS_RESOLVED, Ticket.STATUS_CLOSED])

        provisioned = seen = 0
        for ticket in qs:
            seen += 1
            if provision_ticket_issue(ticket):
                provisioned += 1
        self.stdout.write(self.style.SUCCESS(
            f'provision_jira_issues: linked {provisioned} of {seen} ticket(s)'))
