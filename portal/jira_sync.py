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


def provision_ticket_issue(ticket):
    """Option A: CREATE a Jira issue for `ticket` via the API and link it, so
    the portal gets the key back and S1 sync works — no fragile email intake,
    no duplicate. Gated by settings.JIRA_AUTO_CREATE; idempotent (skips an
    already-linked ticket); best-effort (a Jira failure leaves it unlinked,
    retried next cron). Returns the new Jira key or None.

    Runs from the provision_jira_issues cron, never the ticket-create request
    path — the create/link/backlink calls shouldn't add latency there."""
    from django.utils import timezone
    from portal.models import JiraTicketLink
    from portal.views.tickets import log_ticket_activity

    if not getattr(settings, 'JIRA_AUTO_CREATE', False):
        return None
    # Scope to the configured categories (default: bugs only).
    cats = getattr(settings, 'JIRA_AUTO_CREATE_CATEGORIES', ['bug'])
    if cats and ticket.category not in cats:
        return None
    if ticket.jira_links.exists():
        return None

    project = getattr(settings, 'JIRA_TICKET_PROJECT', 'SUP')
    issue_type = getattr(settings, 'JIRA_TICKET_ISSUE_TYPE_ID', '10103')
    first = ticket.messages.order_by('created_at').first()
    site = (getattr(settings, 'FRONTEND_URL', '') or '').rstrip('/')
    admin_url = f'{site}/manage/tickets/{ticket.number}'
    summary = f'[{ticket.display_number}] {ticket.subject}'
    body = (f'Portal ticket {ticket.display_number} — {ticket.company.name}\n\n'
            f'{first.body if first else ""}\n\n'
            f'Reply to the customer in the portal (not in Jira): {admin_url}')

    key = jira_client.create_issue(project, summary, body, issue_type)
    if not key:
        return None

    link, _ = JiraTicketLink.objects.get_or_create(ticket=ticket, key=key)
    data = jira_client.fetch_issue(key)
    if data:
        link.cached_status = data['status'][:64]
        link.cached_status_category = data['status_category'][:32]
        link.cached_summary = data['summary'][:512]
        link.fetched_at = timezone.now()
        link.save(update_fields=['cached_status', 'cached_status_category',
                                 'cached_summary', 'fetched_at'])
    jira_client.create_remote_link(
        key, admin_url, f'{ticket.display_number} in CiteMed Support')
    jira_client.add_comment(key, (
        f'💬 Linked to CiteMed Support ticket {ticket.display_number}. Reply to '
        f'the customer in the portal (not in Jira): {admin_url}'), internal=True)
    log_ticket_activity(ticket, 'jira_linked', actor=None, key=key, auto=True)
    logger.info('jira_provision: %s created + linked %s', ticket.display_number, key)
    return key
