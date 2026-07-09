"""ESP delivery-tracking (ECD-2248).

Two entry points feed the same status-apply logic:
  - the Mailgun tracking webhook (Anymail signal) — real-time, used in prod;
  - the `poll_mailgun_events` command — pulls the Mailgun Events API, used
    where the webhook can't reach us (local dev) and as a prod backstop for
    missed events.
Both map an ESP delivery event to the TicketMessage that triggered the send
(via the ESP message-id captured at send) and update its delivery_status.
"""
import logging
import re

from anymail.signals import inbound, tracking
from django.dispatch import receiver

logger = logging.getLogger(__name__)

# Anymail-normalized / Mailgun event types → terminal delivery outcomes.
DELIVERED_EVENTS = {'delivered'}
FAILED_EVENTS = {'bounced', 'rejected', 'failed', 'complained', 'permanent_fail'}


def _find_message(esp_message_id):
    """Match tolerantly on the ESP message-id — the Events API returns it
    without angle brackets, Anymail/our capture may include them."""
    from portal.models import TicketMessage
    if not esp_message_id:
        return None
    bare = esp_message_id.strip('<>')
    for candidate in (esp_message_id, bare, f'<{bare}>'):
        m = TicketMessage.objects.filter(esp_message_id=candidate).first()
        if m:
            return m
    return None


def apply_delivery_event(esp_message_id, event_type, reason='', recipient=''):
    """Update the matching ticket message's delivery_status. Returns True if a
    message was updated. Ignores non-terminal events and unknown ids.

    One message can go to several recipients (customer + CCs) with different
    outcomes. To honor 'never silently drop a failure', a bounce/failure to ANY
    recipient wins and sticks — a later 'delivered' for another recipient does
    not clear it. The failing address is recorded so staff know which one."""
    from portal.models import TicketMessage
    if event_type not in (DELIVERED_EVENTS | FAILED_EVENTS):
        return False
    msg = _find_message(esp_message_id)
    if not msg:
        return False  # event for a non-ticket email (magic link, etc.)

    if event_type in FAILED_EVENTS:
        msg.delivery_status = TicketMessage.DELIVERY_BOUNCED
        detail = 'spam complaint' if event_type == 'complained' else (reason or event_type)
        if recipient:
            detail = f'{recipient}: {detail}'
        msg.delivery_detail = detail[:256]
    else:  # delivered
        if msg.delivery_status == TicketMessage.DELIVERY_BOUNCED:
            return False  # keep the known bounce; don't let another recipient hide it
        msg.delivery_status = TicketMessage.DELIVERY_DELIVERED
        msg.delivery_detail = ''

    msg.save(update_fields=['delivery_status', 'delivery_detail'])
    logger.info('delivery event=%s esp_id=%s msg=%s → %s',
                event_type, esp_message_id, msg.id, msg.delivery_status)
    return True


@receiver(tracking)
def handle_esp_tracking(sender, event, esp_name=None, **kwargs):
    reason = (getattr(event, 'description', None)
              or getattr(event, 'reject_reason', None) or '')
    apply_delivery_event(getattr(event, 'message_id', None),
                         getattr(event, 'event_type', None), reason,
                         getattr(event, 'recipient', '') or '')


# --- Inbound email replies (ECD-2250) ---------------------------------------
#
# Anymail's MailgunInboundWebhookView fires `inbound` with an
# AnymailInboundEvent whose `.message` is an AnymailInboundMessage (a parsed
# email.message.EmailMessage subclass). Two of its accessors are NOT plain
# strings, which the helpers below normalize:
#   - `message.from_email` is an anymail.utils.EmailAddress (has `.addr_spec`),
#     not a str.
#   - there is no `message.message_id` attribute at all for inbound events —
#     the RFC-5322 Message-ID must be read off the parsed headers via
#     `message.get('Message-Id')` (EmailMessage header lookup is
#     case-insensitive). `envelope_recipient`/`stripped_text`/`text` ARE
#     plain strings/None, set directly by the Mailgun webhook view.
# The unit tests exercise the receiver directly with a SimpleNamespace fake
# that sets `from_email`/`message_id` as plain values (no live Mailgun POST
# needed) — the helpers accept that shape too, so both real and fake
# messages work unchanged.

_RECIPIENT_RE = re.compile(r'^ticket-(?P<num>\d+)\+(?P<token>[^@]+)@', re.I)


def _addr_spec(value):
    """Normalize an Anymail address-like value to a bare email string.
    Handles anymail.utils.EmailAddress (`.addr_spec`), plain strings, and
    None."""
    if value is None:
        return ''
    addr_spec = getattr(value, 'addr_spec', None)
    if addr_spec is not None:
        return addr_spec
    return str(value)


def _message_id(message):
    """The inbound RFC-5322 Message-ID. Real AnymailInboundMessage objects
    expose it only via header lookup (`.get(...)`), not as an attribute."""
    mid = getattr(message, 'message_id', None)
    if mid:
        return mid
    getter = getattr(message, 'get', None)
    if callable(getter):
        return getter('Message-Id') or ''
    return ''


def _match_ticket(message):
    """Resolve the ticket from the inbound recipient (ticket-<n>+<token>@…),
    validating the token belongs to that ticket. Returns the Ticket or None."""
    from portal.models import Ticket, TicketMessage
    addr = getattr(message, 'envelope_recipient', None) or ''
    if not addr:
        to = getattr(message, 'to', '') or ''
        if isinstance(to, str):
            addr = to
        else:
            first = to[0] if to else None
            addr = _addr_spec(first) if first is not None else ''
    m = _RECIPIENT_RE.search(addr or '')
    if not m:
        return None
    ticket = Ticket.objects.filter(number=int(m.group('num'))).first()
    if not ticket:
        return None
    if not TicketMessage.objects.filter(ticket=ticket, reply_token=m.group('token')).exists():
        return None
    return ticket


def _sender_ok(ticket, from_email):
    frm = (from_email or '').strip().lower()
    if not frm:
        return False
    if ticket.created_by and frm == (ticket.created_by.email or '').lower():
        return True
    return frm in {c.lower() for c in (ticket.cc_emails or [])}


@receiver(inbound)
def handle_inbound(sender, event, **kwargs):
    """Append an emailed customer reply to its ticket. Drops anything that fails
    token or sender validation; dedupes on the inbound Message-ID. Attachments
    are noted on the message, not stored (full storage: ECD-2264)."""
    from django.db import transaction
    from portal.models import Ticket, TicketMessage
    from portal.views.tickets import log_ticket_activity
    from portal import ticket_notify, realtime

    message = event.message
    ticket = _match_ticket(message)
    if not ticket:
        logger.info('inbound: no ticket match, dropping')
        return
    from_email = _addr_spec(getattr(message, 'from_email', None))
    if not _sender_ok(ticket, from_email):
        logger.warning('inbound: sender %s not allowed on %s, dropping', from_email, ticket.display_number)
        return
    inbound_id = _message_id(message)
    if inbound_id and TicketMessage.objects.filter(email_message_id=inbound_id).exists():
        logger.info('inbound: duplicate %s, skipping', inbound_id)
        return

    body = (getattr(message, 'stripped_text', None) or getattr(message, 'text', '') or '').strip() or '(no text)'
    attachments = getattr(message, 'attachments', None) or []
    if attachments:
        body += (f'\n\n📎 {len(attachments)} attachment(s) received by email; '
                 'ask the customer to re-share them via the portal.')

    author = ticket.created_by
    msg = TicketMessage.objects.create(
        ticket=ticket, author=author, author_email=from_email.strip().lower(),
        body=body, origin=TicketMessage.ORIGIN_EMAIL, email_message_id=inbound_id)
    ticket.status = Ticket.STATUS_WAITING_ON_SUPPORT
    ticket.save(update_fields=['status', 'updated_at'])
    log_ticket_activity(ticket, 'message_sent', actor=author)
    try:
        ticket_notify.notify_customer_reply(ticket, msg)
    except Exception as e:  # notifying staff must never lose the captured reply
        logger.error('inbound: staff notify failed: %s', e)
    transaction.on_commit(lambda: realtime.notify_ticket(ticket, 'customer_reply'))
    logger.info('inbound: appended msg %s to %s', msg.id, ticket.display_number)
