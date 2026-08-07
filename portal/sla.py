"""First-response SLA targets, per EC-SOP-07 §4.1.

    Priority     First response (doc)   modelled as
    URGENT       Same business day      end of the business day it arrived
    High         1 business day         9 business hours
    Standard     1-2 business days      18 business hours (the OUTER bound —
                                        flagging at the tighter end would
                                        report breaches the SLA doesn't claim)
    CSM Direct   Within 24 hours        24 CALENDAR hours (this tier is the
                                        one the doc states in hours, not
                                        business days, so a Friday request is
                                        due Saturday rather than Monday)

TWO DELIBERATE SIMPLIFICATIONS — read before treating output as contractual:

1. The doc defines Business Hours in "the client's primary operating time
   zone". We do not store a per-client time zone, so one company-wide zone is
   used (settings.SLA_TIMEZONE). A client several zones away will see a
   deadline off by those hours.
2. The doc excludes public holidays. There is no holiday calendar here, so
   holidays count as ordinary business days and a deadline spanning one will
   read as earlier than the SLA actually requires.

Both make this an INTERNAL triage aid, not a contractual measurement. It is
admin-only and never surfaces to a customer.
"""
import logging
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)


def _tz():
    return ZoneInfo(getattr(settings, 'SLA_TIMEZONE', 'America/New_York'))


DEFAULT_OPEN_HOUR = 9
DEFAULT_CLOSE_HOUR = 18


def _open_close():
    """Business open/close, falling back to the defaults if misconfigured.

    A zero-or-negative-length business day makes add_business_hours consume no
    time per iteration, so it walks the calendar until the date overflows. That
    matters more than it looks: is_breached runs once per row when the admin
    ticket list is serialized, so a single bad env var would 500 the queue
    staff work from. Degrade to sane hours and say so in the log instead.
    """
    open_h = getattr(settings, 'SLA_BUSINESS_OPEN_HOUR', DEFAULT_OPEN_HOUR)
    close_h = getattr(settings, 'SLA_BUSINESS_CLOSE_HOUR', DEFAULT_CLOSE_HOUR)
    if not (0 <= open_h < close_h <= 24):
        logger.warning(
            'SLA business hours are invalid (open=%s close=%s); falling back '
            'to %s-%s. Fix SLA_BUSINESS_OPEN_HOUR / SLA_BUSINESS_CLOSE_HOUR.',
            open_h, close_h, DEFAULT_OPEN_HOUR, DEFAULT_CLOSE_HOUR)
        open_h, close_h = DEFAULT_OPEN_HOUR, DEFAULT_CLOSE_HOUR
    return time(open_h), time(close_h) if close_h < 24 else time(23, 59, 59)


def _is_business_day(d):
    return d.weekday() < 5  # Mon-Fri; no holiday calendar (see module docstring)


def receipt_time(when):
    """When the request is DEEMED received: itself if inside business hours,
    otherwise the start of the next business day (doc §4.1 note)."""
    tz = _tz()
    # Django hands us aware datetimes; this is defensive. astimezone() on a
    # naive value assumes the SERVER's local zone, which is both wrong and
    # machine-dependent, so attach the SLA zone explicitly instead.
    when = when.replace(tzinfo=tz) if when.tzinfo is None else when.astimezone(tz)
    open_t, close_t = _open_close()

    while True:
        if not _is_business_day(when):
            when = datetime.combine(when.date() + timedelta(days=1), open_t, tzinfo=tz)
            continue
        if when.timetz().replace(tzinfo=None) < open_t:
            return datetime.combine(when.date(), open_t, tzinfo=tz)
        if when.timetz().replace(tzinfo=None) >= close_t:
            when = datetime.combine(when.date() + timedelta(days=1), open_t, tzinfo=tz)
            continue
        return when


def add_business_hours(start, hours):
    """`start` plus `hours` of business time, skipping evenings and weekends."""
    tz = _tz()
    open_t, close_t = _open_close()
    cur = receipt_time(start)
    remaining = timedelta(hours=hours)

    while remaining > timedelta(0):
        close_dt = datetime.combine(cur.date(), close_t, tzinfo=tz)
        available = close_dt - cur
        if available >= remaining:
            return cur + remaining
        remaining -= available
        # Next business day's opening bell.
        cur = datetime.combine(cur.date() + timedelta(days=1), open_t, tzinfo=tz)
        while not _is_business_day(cur):
            cur = datetime.combine(cur.date() + timedelta(days=1), open_t, tzinfo=tz)
    return cur


# business_hours, or calendar_hours where the doc states the target that way.
FIRST_RESPONSE_TARGETS = {
    'urgent':     {'end_of_business_day': True, 'label': 'Same business day'},
    'high':       {'business_hours': 9,         'label': '1 business day'},
    'standard':   {'business_hours': 18,        'label': '1–2 business days'},
    'csm_direct': {'calendar_hours': 24,        'label': 'Within 24 hours'},
}


def target_label(priority):
    return (FIRST_RESPONSE_TARGETS.get(priority) or {}).get('label', '')


def first_response_due(ticket):
    """The moment a first response is due, or None if the priority has no
    defined target."""
    spec = FIRST_RESPONSE_TARGETS.get(ticket.priority)
    if not spec:
        return None
    if spec.get('calendar_hours'):
        # Calendar, not business — deliberately not clamped to business hours.
        return ticket.created_at.astimezone(_tz()) + timedelta(
            hours=spec['calendar_hours'])
    received = receipt_time(ticket.created_at)
    if spec.get('end_of_business_day'):
        _, close_t = _open_close()
        return datetime.combine(received.date(), close_t, tzinfo=_tz())
    return add_business_hours(received, spec['business_hours'])


def is_breached(ticket, now=None):
    """True when the first response is late — either still outstanding past
    the deadline, or given after it. Answering in time settles it for good."""
    due = first_response_due(ticket)
    if due is None:
        return False
    if ticket.first_response_at:
        return ticket.first_response_at > due
    return (now or timezone.now()) > due


def record_first_response(ticket, message):
    """Stamp first_response_at when `message` is the first real reply to the
    customer. No-op otherwise, and never overwritten once set.

    Not a response: an internal note (the customer never sees it), a message
    from the customer, or the opening message of a staff-raised on-behalf
    ticket — that one records the request, it doesn't answer it.
    """
    from portal.models import TicketMessage
    if ticket.first_response_at:
        return False
    if message.origin != TicketMessage.ORIGIN_STAFF or message.is_internal:
        return False
    earliest = ticket.messages.order_by('created_at', 'id').first()
    if earliest and earliest.pk == message.pk:
        return False
    ticket.first_response_at = message.created_at
    ticket.save(update_fields=['first_response_at', 'updated_at'])
    return True
