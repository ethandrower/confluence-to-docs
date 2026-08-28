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


def upload_recipients(file):
    """Who hears about an upload.

    This used to email only `bucket.requested_by` — the CSM who opened a
    document request — and return silently when there wasn't one. Every
    "General uploads" bucket is created by `get_general_bucket()` with no
    `requested_by`, and General is where the "Share files" button sends
    everything, so in practice most uploads notified nobody at all.

    The audience mirrors the ticket rule so there's one notion of "who is on
    this account": the CSM who asked, when a request bucket names one, and
    otherwise every agent — because an unsolicited upload, like a new ticket,
    belongs to nobody yet. The shared inbox is always copied.
    """
    from portal.ticket_notify import _all_agent_emails, _dedupe

    csm = getattr(file.bucket, 'requested_by', None)
    recipients = [csm.email] if (csm and csm.email) else list(_all_agent_emails())
    support = getattr(settings, 'SUPPORT_EMAIL', None)
    if support:
        recipients.append(support)
    return _dedupe(recipients)


def notify_upload(file):
    """Tell staff about one upload. See notify_upload_batch for the bulk path."""
    notify_upload_batch(file.company, [file], upload_recipients(file))


def notify_upload_batch(company, files, recipients):
    """One email for a batch of uploads sharing a company and an audience.

    The batch is what makes folder upload survivable: 150 files used to mean
    150 emails to every agent. Naming a few files and counting the rest keeps
    the message useful without turning it into a manifest — the portal is where
    you go to actually look at them.
    """
    files = list(files)
    if not recipients or not files:
        return

    n = len(files)
    # Distinct destinations, in the order encountered, so the mail says where
    # things landed rather than just how many arrived.
    places = []
    for f in files:
        title = f.bucket.title
        if title not in places:
            places.append(title)

    if n == 1:
        subject = f'New upload from {company.name}'
        body = (f'{company.name} uploaded “{files[0].original_name}” to “{places[0]}”. '
                'Review it in Manage → Files.')
    else:
        shown = ', '.join(f'“{f.original_name}”' for f in files[:3])
        more = f' and {n - 3} more' if n > 3 else ''
        where = places[0] if len(places) == 1 else f'{len(places)} folders'
        subject = f'{n} new uploads from {company.name}'
        body = (f'{company.name} uploaded {n} files to {where}: {shown}{more}. '
                'Review them in Manage → Files.')

    _send(
        subject,
        recipients,
        heading=subject,
        body=body,
        cta_label='Review in the portal', cta_url=f'{_site()}/manage',
    )
