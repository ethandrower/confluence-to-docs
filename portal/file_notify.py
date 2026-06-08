"""Best-effort email notifications for file sharing (Mailgun via Django mail).

Every function swallows errors and logs — a failed email must never block the
core action (upload, request, review).
"""
import logging

from django.conf import settings
from django.core.mail import send_mail

logger = logging.getLogger(__name__)


def _from():
    return getattr(settings, 'DEFAULT_FROM_EMAIL', None) or 'support@citemed.com'


def _company_emails(company):
    from portal.models import PortalUser
    return [
        e for e in PortalUser.objects.filter(company=company, access_enabled=True)
        .values_list('email', flat=True) if e
    ]


def _site():
    return getattr(settings, 'FRONTEND_URL', 'https://support.citemed.com').rstrip('/')


def _send(subject, body, recipients):
    recipients = [r for r in recipients if r]
    if not recipients:
        return
    try:
        send_mail(subject, body, _from(), recipients, fail_silently=True)
    except Exception as e:  # pragma: no cover - defensive
        logger.warning("file_notify send failed (%s): %s", subject, e)


def notify_request_created(bucket):
    body = (
        f"CiteMed has requested documents from you: “{bucket.title}”.\n\n"
        f"{bucket.description or ''}\n\n"
        f"Upload them here: {_site()}/files"
    )
    _send("CiteMed needs documents from you", body, _company_emails(bucket.company))


def notify_revision(file):
    note = f"\n\nReviewer note: {file.review_notes}" if file.review_notes else ""
    body = (
        f"A file you shared needs revision: “{file.original_name}”.{note}\n\n"
        f"Please re-upload an updated version here: {_site()}/files"
    )
    _send("A shared file needs revision", body, _company_emails(file.company))


def notify_upload(file):
    """Tell the CSM who created the request that the customer uploaded."""
    csm = getattr(file.bucket, 'requested_by', None)
    if not csm or not csm.email:
        return
    body = (
        f"{file.company.name} uploaded “{file.original_name}” "
        f"to “{file.bucket.title}”.\n\nReview it in Manage → Files."
    )
    _send(f"New upload from {file.company.name}", body, [csm.email])
