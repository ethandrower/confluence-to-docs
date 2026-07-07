"""Inbound ESP webhook handling.

Tier B delivery tracking (ECD-2248): Anymail's Mailgun tracking webhook view
verifies the signature and fires the `anymail.signals.tracking` signal for each
delivery event. We map that event back to the TicketMessage it belongs to (via
the ESP message-id captured at send) and enrich its delivery_status so staff
see true delivered/bounced state, not just "the API accepted it".
"""
import logging

from anymail.signals import tracking
from django.dispatch import receiver

logger = logging.getLogger(__name__)

# Anymail normalizes ESP event types. We only act on terminal delivery outcomes.
_DELIVERED = {'delivered'}
_FAILED = {'bounced', 'rejected', 'failed', 'complained'}


@receiver(tracking)
def handle_esp_tracking(sender, event, esp_name=None, **kwargs):
    # Imported lazily to avoid app-loading order issues.
    from portal.models import TicketMessage

    mid = getattr(event, 'message_id', None)
    event_type = getattr(event, 'event_type', None)
    if not mid or event_type not in (_DELIVERED | _FAILED):
        return

    msg = TicketMessage.objects.filter(esp_message_id=mid).first()
    if not msg:
        # Event for a non-ticket email (magic link, contact form, file share).
        return

    if event_type in _DELIVERED:
        msg.delivery_status = TicketMessage.DELIVERY_DELIVERED
        msg.delivery_detail = ''
    else:
        msg.delivery_status = TicketMessage.DELIVERY_BOUNCED
        if event_type == 'complained':
            reason = 'spam complaint'
        else:
            reason = (getattr(event, 'description', None)
                      or getattr(event, 'reject_reason', None)
                      or event_type)
        msg.delivery_detail = str(reason)[:256]

    msg.save(update_fields=['delivery_status', 'delivery_detail'])
    logger.info('ticket delivery event=%s msg=%s esp_id=%s → %s',
                event_type, msg.id, mid, msg.delivery_status)
