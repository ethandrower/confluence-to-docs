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

from anymail.signals import tracking
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


def apply_delivery_event(esp_message_id, event_type, reason=''):
    """Update the matching ticket message's delivery_status. Returns True if a
    message was updated. Ignores non-terminal events and unknown ids."""
    from portal.models import TicketMessage
    if event_type not in (DELIVERED_EVENTS | FAILED_EVENTS):
        return False
    msg = _find_message(esp_message_id)
    if not msg:
        return False  # event for a non-ticket email (magic link, etc.)
    if event_type in DELIVERED_EVENTS:
        msg.delivery_status = TicketMessage.DELIVERY_DELIVERED
        msg.delivery_detail = ''
    else:
        msg.delivery_status = TicketMessage.DELIVERY_BOUNCED
        msg.delivery_detail = (('spam complaint' if event_type == 'complained'
                                else reason) or event_type)[:256]
    msg.save(update_fields=['delivery_status', 'delivery_detail'])
    logger.info('delivery event=%s esp_id=%s msg=%s → %s',
                event_type, esp_message_id, msg.id, msg.delivery_status)
    return True


@receiver(tracking)
def handle_esp_tracking(sender, event, esp_name=None, **kwargs):
    reason = (getattr(event, 'description', None)
              or getattr(event, 'reject_reason', None) or '')
    apply_delivery_event(getattr(event, 'message_id', None),
                         getattr(event, 'event_type', None), reason)
