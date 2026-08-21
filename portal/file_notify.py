"""Best-effort, branded email notifications for file sharing.

Uses the same branded HTML shell as the magic-link email
(emails/notification.html / .txt). Sent synchronously (like the magic-link
email, which is proven on prod) and wrapped in try/except so a mail failure can
never block the core action (upload, request, reminder).
"""
import logging

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string

logger = logging.getLogger(__name__)

PRODUCT_NAME = 'CiteMed Support'


def _from():
    return getattr(settings, 'DEFAULT_FROM_EMAIL', None) or 'support@citemed.com'


def _site():
    return getattr(settings, 'FRONTEND_URL', 'https://support.citemed.com').rstrip('/')


def _company_emails(company):
    from portal.models import PortalUser
    return [
        e for e in PortalUser.objects.filter(company=company, access_enabled=True)
        .values_list('email', flat=True) if e
    ]


def _send(subject, recipients, *, heading, body, cta_label, cta_url, note=''):
    """Render the branded template and send (HTML + text), synchronously.
    Best-effort — any failure is logged, never raised to the caller."""
    recipients = [r for r in recipients if r]
    if not recipients:
        return
    ctx = {
        'product_name': PRODUCT_NAME, 'heading': heading, 'body': body,
        'note': note, 'cta_label': cta_label, 'cta_url': cta_url,
    }
    try:
        text = render_to_string('emails/notification.txt', ctx)
        html = render_to_string('emails/notification.html', ctx)
        msg = EmailMultiAlternatives(subject, text, _from(), recipients)
        msg.attach_alternative(html, 'text/html')
        sent = msg.send()
        logger.info("file_notify sent (%s) → %s (sent=%s)", subject, recipients, sent)
    except Exception as e:
        logger.error("file_notify failed (%s) → %s: %s", subject, recipients, e)


def notify_request_created(bucket):
    desc = f" {bucket.description}" if bucket.description else ''
    _send(
        'CiteMed needs documents from you',
        _company_emails(bucket.company),
        heading='CiteMed has requested documents',
        body=f'“{bucket.title}” —{desc} Please upload the requested files in your portal.',
        cta_label='Upload documents', cta_url=f'{_site()}/files',
    )


def notify_request_complete(bucket):
    """Closes the loop: tell the customer their submission was accepted."""
    _send(
        'Your submission is complete',
        _company_emails(bucket.company),
        heading='Your documents have been accepted',
        body=f'CiteMed has completed review of “{bucket.title}”. '
             'No further action is needed — thank you.',
        cta_label='View in your portal', cta_url=f'{_site()}/files',
    )


def notify_due_reminder(bucket, overdue=False):
    """Nudge the customer about an open request that's due soon or overdue."""
    if overdue:
        heading = 'A document request is overdue'
        body = (f'“{bucket.title}” was due and we haven’t received everything yet. '
                'Please upload the requested files when you can.')
    else:
        heading = 'Reminder: documents requested by CiteMed'
        body = (f'“{bucket.title}” is due soon. Please upload the requested files in your portal.')
    _send(
        'Reminder: CiteMed needs documents from you',
        _company_emails(bucket.company),
        heading=heading, body=body,
        cta_label='Upload documents', cta_url=f'{_site()}/files',
    )


def notify_upload(file):
    """Tell staff a customer uploaded something.

    This used to email only `bucket.requested_by` — the CSM who opened a
    document request — and return silently when there wasn't one. Every
    "General uploads" bucket is created by `get_general_bucket()` with no
    `requested_by`, and General is where the "Share files" button sends
    everything, so in practice most uploads notified nobody at all.

    The audience now mirrors the ticket rule so there's one notion of "who is
    on this account": the CSM who asked, when a request bucket names one, and
    otherwise every agent — because an unsolicited upload, like a new ticket,
    belongs to nobody yet. The shared inbox is always copied.
    """
    from portal.ticket_notify import _all_agent_emails, _dedupe

    csm = getattr(file.bucket, 'requested_by', None)
    recipients = [csm.email] if (csm and csm.email) else list(_all_agent_emails())
    support = getattr(settings, 'SUPPORT_EMAIL', None)
    if support:
        recipients.append(support)
    recipients = _dedupe(recipients)
    if not recipients:
        return
    _send(
        f'New upload from {file.company.name}',
        recipients,
        heading=f'New upload from {file.company.name}',
        body=f'{file.company.name} uploaded “{file.original_name}” to “{file.bucket.title}”. '
             'Review it in Manage → Files.',
        cta_label='Review in the portal', cta_url=f'{_site()}/manage',
    )


def _share_label(bucket, item):
    return item.original_name if item else bucket.title


def _share_cta(bucket):
    """Deep-link straight to the folder rather than the files root. The whole
    point of a push is that there is one specific thing to look at, and
    dropping someone on a file list they then have to search is how a
    delivery goes unopened."""
    return f'{_site()}/files?folder={bucket.id}'


def notify_share(bucket, item, recipient):
    """Tell ONE person that we have shared something with them.

    Sent per-recipient rather than to a combined To: line — the list of who
    else was notified is not something a customer needs, and a per-person send
    is what lets the reminder loop follow up with just one of them later.

    Goes from the noreply address with no Reply-To, so the template's "do not
    reply" footer is accurate for these; only ticket mail sets `can_reply`.
    """
    label = _share_label(bucket, item)
    if item is None:
        body = (f'We’ve shared the folder “{bucket.title}” with you. '
                'Everything inside stays available in your portal.')
    elif item.is_link:
        body = (f'We’ve added a link, “{item.original_name}”, to “{bucket.title}” '
                'in your portal.')
    else:
        body = f'We’ve shared “{item.original_name}” with you in “{bucket.title}”.'
    _send(
        f'CiteMed shared {label} with you',
        [recipient.email],
        heading=f'{label} is ready in your portal',
        body=body,
        cta_label='Open in portal', cta_url=_share_cta(bucket),
    )


def notify_share_reminder(notice):
    """Nudge one person who hasn't opened what we sent them.

    Capped at ShareNotice.MAX_REMINDERS by the caller. The copy stays plain on
    purpose: this is the second or third time they've heard from us about the
    same thing, and escalating the tone is how a useful reminder turns into
    something people filter.
    """
    label = _share_label(notice.bucket, notice.file)
    _send(
        f'Reminder: {label} is waiting in your portal',
        [notice.recipient.email],
        heading=f'You haven’t opened {label} yet',
        body=(f'We shared “{label}” with you and it’s still waiting in your portal. '
              'It stays there — you can open it whenever suits.'),
        cta_label='Open in portal', cta_url=_share_cta(notice.bucket),
    )
