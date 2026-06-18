"""Best-effort, branded email notifications for file sharing.

Uses the same branded HTML shell as the magic-link email
(emails/notification.html / .txt). Sent synchronously (like the magic-link
email, which is proven on prod) and wrapped in try/except so a mail failure can
never block the core action (upload, request, review).
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
        msg = EmailMultiAlternatives(
            subject, text, _from(), recipients,
            headers={'X-Mailgun-Track-Opens': 'no', 'X-Mailgun-Track-Clicks': 'no'},
        )
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


def notify_revision(file):
    _send(
        'A shared file needs revision',
        _company_emails(file.company),
        heading='A file you shared needs revision',
        body=f'“{file.original_name}” needs an update before we can proceed. '
             'Please review the note below and re-upload an updated version.',
        note=file.review_notes,
        cta_label='Re-upload the file', cta_url=f'{_site()}/files',
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
    """Tell the CSM who created the request that the customer uploaded."""
    csm = getattr(file.bucket, 'requested_by', None)
    if not csm or not csm.email:
        return
    _send(
        f'New upload from {file.company.name}',
        [csm.email],
        heading=f'New upload from {file.company.name}',
        body=f'{file.company.name} uploaded “{file.original_name}” to “{file.bucket.title}”. '
             'Review it in Manage → Files.',
        cta_label='Review in the portal', cta_url=f'{_site()}/manage',
    )
