"""S1: ingest PUBLIC Jira comments into a ticket's portal thread (ECD-2246).

The portal is the system of record for customer comms, but staff sometimes
reply from inside Jira — those replies were previously lost to the customer.
This pulls each linked issue's public comments in and appends them as staff
messages (under the "CiteMed Support" facade), so the conversation stays whole
regardless of where the reply was typed.

Read-only against Jira; best-effort; deduped by Jira comment id so a comment is
ingested at most once. Two safety gates so engineering chatter never reaches a
customer: (1) only links in a service-desk project (settings.JIRA_SYNC_PROJECTS)
are synced — on a software project like ECD, `jsdPublic` is meaningless and
would leak dev/bot comments; (2) within those, only `jsdPublic` comments are
surfaced (see jira_client.fetch_comments).
"""
import logging

from django.conf import settings

logger = logging.getLogger(__name__)

# Imported at module scope so tests can patch portal.jira_sync.<name>.
from portal import jira_client, realtime, ticket_notify


def sync_ticket_comments(ticket, *, email_customer=None):
    """Append the ticket's new public Jira comments as staff messages. Flips the
    ticket to 'waiting on customer' and broadcasts a realtime nudge when any are
    added. Returns the count appended.

    email_customer defaults to settings.JIRA_SYNC_EMAIL_CUSTOMER — when True,
    each ingested comment is also emailed to the customer via the threaded
    staff-reply path.
    """
    from portal.models import Ticket, TicketMessage
    from portal.views.tickets import log_ticket_activity

    if email_customer is None:
        email_customer = getattr(settings, 'JIRA_SYNC_EMAIL_CUSTOMER', False)

    from django.db import IntegrityError, transaction
    from django.utils.dateparse import parse_datetime

    # Only service-desk projects sync comments. A bug linked to an engineering
    # project (e.g. ECD) shows status only — its comments are dev/bot chatter
    # and `jsdPublic` there doesn't mean "customer-facing".
    allowed = {p.upper() for p in getattr(settings, 'JIRA_SYNC_PROJECTS', ['SUP'])}

    created = []
    to_email = []
    for link in ticket.jira_links.all():
        if link.key.split('-')[0].upper() not in allowed:
            continue
        # Insert oldest-first so the portal thread reads chronologically,
        # independent of the order Jira returns comments in.
        comments = sorted(jira_client.fetch_comments(link.key),
                          key=lambda c: c.get('created', ''))
        for c in comments:
            if not c.get('public'):
                continue
            cid = str(c.get('id') or '')
            # Dedup per-ticket: the same Jira issue can be linked to more than
            # one ticket, and the comment must reach each of their threads.
            if not cid or TicketMessage.objects.filter(
                    ticket=ticket, jira_comment_id=cid).exists():
                continue
            body = (c.get('body') or '').strip() or '(no content)'
            try:
                # atomic + catch guards the check-then-create against a
                # concurrent pass (cron vs loop worker) racing on the same
                # comment — the DB unique constraint makes the loser a no-op.
                with transaction.atomic():
                    msg = TicketMessage.objects.create(
                        ticket=ticket, author=None, author_email='', body=body,
                        origin=TicketMessage.ORIGIN_STAFF, jira_comment_id=cid)
            except IntegrityError:
                continue  # another pass ingested this comment first
            log_ticket_activity(ticket, 'message_sent', actor=None,
                                source='jira', jira_key=link.key)
            created.append(msg)
            # Only email replies authored AFTER we linked the issue. Comments
            # older than the link are historical backfill (JSM already emailed
            # them) — ingesting them must never re-notify the customer.
            cdt = parse_datetime(c.get('created') or '')
            if cdt is None or cdt >= link.created_at:
                to_email.append(msg)

    if not created:
        return 0

    ticket.status = Ticket.STATUS_WAITING_ON_CUSTOMER
    ticket.save(update_fields=['status', 'updated_at'])

    if email_customer:
        for msg in to_email:
            try:
                ticket_notify.notify_staff_reply(ticket, msg)
            except Exception as e:  # a mail failure must never lose the message
                logger.error('jira_sync: email failed for %s: %s',
                             ticket.display_number, e)
    try:
        realtime.notify_ticket(ticket, 'staff_reply')
    except Exception as e:  # realtime is a best-effort nudge
        logger.warning('jira_sync: realtime notify failed: %s', e)

    logger.info('jira_sync: appended %s comment(s) to %s',
                len(created), ticket.display_number)
    return len(created)
