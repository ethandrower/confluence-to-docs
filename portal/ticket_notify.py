"""Best-effort branded email notifications for support tickets.

Same contract as portal/file_notify.py: synchronous sends, try/except so a
mail failure never blocks the ticket action, every send logged with sent=N.

Additionally emits real threading headers (Message-ID / In-Reply-To /
References) so customer inboxes thread the conversation, plus a
Reply-To token address that is dormant until Phase 2 (inbound email).
"""
import logging
import secrets
import uuid
from email.utils import parseaddr

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils import timezone

from portal.models import TicketMessage

logger = logging.getLogger(__name__)

PRODUCT_NAME = 'CiteMed Support'


def _from():
    return getattr(settings, 'DEFAULT_FROM_EMAIL', None) or 'support@citemed.com'


def _site():
    return getattr(settings, 'FRONTEND_URL', 'https://support.citemed.com').rstrip('/')


def _mail_domain():
    # Domain part of DEFAULT_FROM_EMAIL. DEFAULT_FROM_EMAIL may be either a
    # bare address ("noreply@x.com") or "Display Name <noreply@x.com>", so
    # parse out the bare address first — otherwise the domain picks up a
    # trailing ">" and produces an invalid Message-ID / unroutable Reply-To.
    bare_addr = parseaddr(_from())[1] or _from()
    return bare_addr.rsplit('@', 1)[-1]


def _customer_recipients(ticket):
    emails = []
    # Only include created_by when it's the CUSTOMER (self-serve tickets). For
    # on-behalf tickets created_by is the staff member — they must not receive
    # the customer-facing "we received your request" mail; the real customer is
    # in cc_emails (folded in at on-behalf create).
    cb = ticket.created_by
    if cb and cb.email and cb.role == 'customer':
        emails.append(cb.email)
    emails.extend(e for e in (ticket.cc_emails or []) if e)
    seen = set()
    deduped = []
    for e in emails:
        key = e.lower()
        if key not in seen:
            seen.add(key)
            deduped.append(e)
    return deduped  # dedupe case-insensitively, keep first-seen casing + order


def _dedupe(emails):
    seen = set()
    out = []
    for e in emails:
        if not e:
            continue
        key = e.lower()
        if key not in seen:
            seen.add(key)
            out.append(e)
    return out


def _all_agent_emails():
    """Every agent, for the creation fan-out only.

    A new ticket belongs to nobody yet, so everyone who could pick it up should
    see it. Once it's assigned, follow-ups narrow to `_staff_recipients`.
    """
    from portal.models import PortalUser
    return list(
        PortalUser.objects
        .filter(role__in=[PortalUser.ROLE_ADMIN, PortalUser.ROLE_OWNER],
                access_enabled=True)
        .exclude(email='')
        .values_list('email', flat=True)
    )


def _staff_recipients(ticket):
    """Staff who are ON this ticket: whoever picked it up, plus watchers.

    The shared inbox is always copied so nothing can fall through the cracks
    while a ticket is unassigned — or after, as an archive.

    Watchers are internal; they never appear in any customer-facing payload.
    """
    emails = []
    if ticket.assignee_id and ticket.assignee and ticket.assignee.email:
        emails.append(ticket.assignee.email)
    emails.extend(w.email for w in ticket.watchers.all() if w.email)
    support = getattr(settings, 'SUPPORT_EMAIL', None)
    if support:
        emails.append(support)
    return _dedupe(emails)


def _send_staff_notice(ticket, recipients, *, heading, body):
    """Plain internal notice — no customer threading headers, since these go to
    staff and must not join the customer-visible email thread."""
    recipients = _dedupe(recipients)
    if not recipients:
        return
    try:
        text = render_to_string('emails/notification.txt', {
            'product_name': PRODUCT_NAME,
            'heading': heading,
            'body': body[:2000],
            'note': '', 'cta_label': 'Open in admin',
            'cta_url': f'{_site()}/manage/tickets/{ticket.number}',
        })
        msg = EmailMultiAlternatives(
            f'[{ticket.display_number}] {ticket.subject}', text, _from(), recipients)
        sent = msg.send()
        logger.info('ticket_notify staff notice → %s (sent=%s)', recipients, sent)
    except Exception as e:
        logger.error('ticket_notify staff notice failed: %s', e)


def _thread_headers(ticket, message):
    """Generate + persist Message-ID / reply token; chain References."""
    domain = _mail_domain()
    if not message.email_message_id:
        message.email_message_id = f'<ticket-{ticket.number}-{uuid.uuid4().hex}@{domain}>'
    if not message.reply_token:
        message.reply_token = secrets.token_urlsafe(24)
    # Persisted before send() runs, on purpose: this is a best-effort-send
    # contract (see module docstring), and regenerating on retry is
    # idempotent. If the send below fails, the id/token are already saved
    # but were never actually emailed — a harmless "phantom" id (RFC 5322
    # allows References/In-Reply-To to point at ids the recipient never
    # saw). The tradeoff we want is the opposite failure mode: the id
    # stored in the DB must always match what was (attempted to be) sent,
    # so any future thread lookup or notify_status anchor is never stale.
    message.save(update_fields=['email_message_id', 'reply_token'])

    prior_ids = list(
        ticket.messages.exclude(pk=message.pk)
        .exclude(email_message_id='')
        .order_by('created_at')
        .values_list('email_message_id', flat=True)
    )
    headers = {
        'Message-ID': message.email_message_id,
        'Reply-To': f'ticket-{ticket.number}+{message.reply_token}@{domain}',
    }
    if prior_ids:
        headers['In-Reply-To'] = prior_ids[-1]
        headers['References'] = ' '.join(prior_ids[-10:])
    return headers


def _esp_message_id(msg):
    """Mailgun's message-id from the Anymail send status, if available. Absent
    under the console/test-less backend (dev). For one Mailgun API call all
    recipients share one id; if Anymail hands back a set, take one."""
    status = getattr(msg, 'anymail_status', None)
    mid = getattr(status, 'message_id', None)
    if isinstance(mid, (set, list, tuple)):
        mid = next(iter(mid), None)
    # Compare to None (not truthiness): the test backend uses id 0, which is
    # a valid id, and real Mailgun ids are non-empty strings anyway.
    return '' if mid is None else str(mid)


def _record_delivery(message, status, detail='', esp_id=''):
    """Persist the submission outcome onto the message it belongs to."""
    message.delivery_status = status
    message.delivery_detail = detail[:256]
    message.delivery_attempted_at = timezone.now()
    fields = ['delivery_status', 'delivery_detail', 'delivery_attempted_at']
    if esp_id:
        message.esp_message_id = esp_id[:256]
        fields.append('esp_message_id')
    message.save(update_fields=fields)


def _send_threaded(ticket, message, recipients, *, heading, body,
                   cta_label, cta_url, note='', track=False):
    """Send a threaded customer-facing email. When `track` is set, record the
    submission outcome (sent/failed) on `message` so the UI can surface whether
    the mail actually left. `track=False` for anchor-only reuse (notify_status),
    which must not clobber the anchor message's own status."""
    recipients = [r for r in recipients if r]
    if not recipients:
        return
    subject = f'[{ticket.display_number}] {ticket.subject}'
    ctx = {
        'product_name': PRODUCT_NAME, 'heading': heading, 'body': body,
        'note': note, 'cta_label': cta_label, 'cta_url': cta_url,
        # These are the only emails that carry a ticket Reply-To (set in
        # _thread_headers below), so they are the only ones a customer can
        # actually reply to. Every other user of this template — magic links,
        # file notices, staff notices — sends from the noreply address and
        # keeps the "do not reply" footer, which is true for them.
        'can_reply': True,
    }
    try:
        headers = _thread_headers(ticket, message)
        text = render_to_string('emails/notification.txt', ctx)
        html = render_to_string('emails/notification.html', ctx)
        msg = EmailMultiAlternatives(subject, text, _from(), recipients,
                                     headers=headers)
        msg.attach_alternative(html, 'text/html')
        sent = msg.send()
        logger.info('ticket_notify sent (%s) → %s (sent=%s)',
                    subject, recipients, sent)
        if track:
            _record_delivery(message, TicketMessage.DELIVERY_SENT,
                             esp_id=_esp_message_id(msg))
    except Exception as e:
        logger.error('ticket_notify failed (%s) → %s: %s',
                     subject, recipients, e)
        if track:
            _record_delivery(message, TicketMessage.DELIVERY_FAILED,
                             f'{type(e).__name__}: {e}')


def notify_ticket_created(ticket, first_message):
    """Confirmation to customer + CCs (covers both self-serve and on-behalf)."""
    _send_threaded(
        ticket, first_message, _customer_recipients(ticket),
        heading=f'Ticket {ticket.display_number} opened',
        body=f'We received your request "{ticket.subject}". '
             'We will reply by email; you can also follow the conversation in your portal.',
        cta_label='View your ticket',
        cta_url=f'{_site()}/support/{ticket.number}',
        track=True,
    )
    # When the portal creates the Jira issue itself (Option A), do NOT email the
    # JSM intake — that would create a duplicate issue. The portal admin + the
    # realtime nav badge already surface new tickets to staff.
    if not getattr(settings, 'JIRA_AUTO_CREATE', False):
        _notify_support_new(ticket, first_message)


def _notify_support_new(ticket, first_message):
    """New ticket → every agent, plus the shared inbox.

    This is the one notification that fans out widely: an unassigned ticket is
    nobody's yet, so everyone who could pick it up needs to see it. Every later
    notification narrows to the people actually on the ticket.
    """
    support = getattr(settings, 'SUPPORT_EMAIL', None)
    recipients = _all_agent_emails() + ([support] if support else [])
    # An agent opening a ticket on a customer's behalf already knows about it.
    author = getattr(first_message, 'author', None)
    if author and author.email:
        recipients = [e for e in recipients if e.lower() != author.email.lower()]
    _send_staff_notice(
        ticket, recipients,
        heading=f'New ticket {ticket.display_number} from {ticket.company.name}',
        body=first_message.body,
    )


def notify_staff_reply(ticket, message):
    """Staff replied → email customer + CCs. Internal notes never leave."""
    if message.is_internal:
        return
    _send_threaded(
        ticket, message, _customer_recipients(ticket),
        heading=f'New reply on {ticket.display_number}',
        body=message.body,
        cta_label='View & reply',
        cta_url=f'{_site()}/support/{ticket.number}',
        track=True,
    )


def notify_customer_reply(ticket, message):
    """Customer replied → the staff who are on this ticket.

    Not a fan-out to every agent: once someone has picked the ticket up, the
    follow-up is theirs and their watchers'. The shared inbox stays copied.
    """
    _send_staff_notice(
        ticket, _staff_recipients(ticket),
        heading=f'Customer reply on {ticket.display_number}',
        body=message.body,
    )


def notify_assigned(ticket, actor=None):
    """Tell an agent a ticket is now theirs — unless they claimed it themselves,
    in which case they plainly already know."""
    assignee = ticket.assignee
    if not assignee or not assignee.email:
        return
    if actor and actor.pk == assignee.pk:
        return
    by = (actor.name or actor.email) if actor else 'A colleague'
    _send_staff_notice(
        ticket, [assignee.email],
        heading=f'{ticket.display_number} was assigned to you',
        body=f'{by} assigned you “{ticket.subject}” for {ticket.company.name}.',
    )


def notify_status(ticket, message=None):
    """Resolved/closed → tell customer + CCs. `message` optional anchor for
    threading; falls back to last outbound message."""
    anchor = message or ticket.messages.exclude(email_message_id='').last()
    if anchor is None:
        anchor = ticket.messages.last()
    if anchor is None:
        return
    label = dict(ticket.STATUS_CHOICES).get(ticket.status, ticket.status)
    _send_threaded(
        ticket, anchor, _customer_recipients(ticket),
        heading=f'{ticket.display_number} marked {label}',
        body=f'Your ticket "{ticket.subject}" is now {label}. '
             'Reply any time to reopen it.',
        cta_label='View your ticket',
        cta_url=f'{_site()}/support/{ticket.number}',
    )
