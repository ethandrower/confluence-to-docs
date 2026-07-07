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
    if ticket.created_by and ticket.created_by.email:
        emails.append(ticket.created_by.email)
    emails.extend(e for e in (ticket.cc_emails or []) if e)
    seen = set()
    deduped = []
    for e in emails:
        key = e.lower()
        if key not in seen:
            seen.add(key)
            deduped.append(e)
    return deduped  # dedupe case-insensitively, keep first-seen casing + order


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
    _notify_support_new(ticket, first_message)


def _notify_support_new(ticket, first_message):
    support = getattr(settings, 'SUPPORT_EMAIL', None)
    if not support:
        return
    try:
        text = render_to_string('emails/notification.txt', {
            'product_name': PRODUCT_NAME,
            'heading': f'New ticket {ticket.display_number} from {ticket.company.name}',
            'body': first_message.body[:2000],
            'note': '', 'cta_label': 'Open in admin',
            'cta_url': f'{_site()}/manage',
        })
        msg = EmailMultiAlternatives(
            f'[{ticket.display_number}] {ticket.subject}', text, _from(), [support])
        sent = msg.send()
        logger.info('ticket_notify staff-new sent → %s (sent=%s)', support, sent)
    except Exception as e:
        logger.error('ticket_notify staff-new failed: %s', e)


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
    """Customer replied → nudge support inbox email."""
    support = getattr(settings, 'SUPPORT_EMAIL', None)
    if not support:
        return
    try:
        text = render_to_string('emails/notification.txt', {
            'product_name': PRODUCT_NAME,
            'heading': f'Customer reply on {ticket.display_number}',
            'body': message.body[:2000],
            'note': '', 'cta_label': 'Open in admin',
            'cta_url': f'{_site()}/manage',
        })
        msg = EmailMultiAlternatives(
            f'[{ticket.display_number}] {ticket.subject}', text, _from(), [support])
        sent = msg.send()
        logger.info('ticket_notify customer-reply sent → %s (sent=%s)', support, sent)
    except Exception as e:
        logger.error('ticket_notify customer-reply failed: %s', e)


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
