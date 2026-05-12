import json
import logging

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.http import JsonResponse
from django.template.loader import render_to_string
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from portal.models import ContactSubmission
from portal.rate_limit import client_ip, is_rate_limited

logger = logging.getLogger(__name__)


CATEGORY_LABELS = {
    'question': 'Question',
    'bug': 'Bug Report',
    'feature': 'Feature Request',
    'docs': 'Documentation Issue',
    'other': 'Other',
}

# Max contact-form submissions per IP per hour.
CONTACT_RATE_MAX = 5
CONTACT_RATE_WINDOW = 60 * 60


def _build_bodies(submission, category_label):
    ctx = {
        'customer_name': submission.name,
        'customer_email': submission.email,
        'category_label': category_label,
        'subject': submission.subject,
        'message': submission.message,
        'submission_id': submission.pk,
        'submitted_at': submission.created_at.strftime('%b %-d, %Y at %H:%M UTC'),
    }
    return (
        render_to_string('emails/contact_ticket.txt', ctx),
        render_to_string('emails/contact_ticket.html', ctx),
    )


@csrf_exempt
@require_POST
def submit_ticket(request):
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'error': 'Invalid request body'}, status=400)

    ip = client_ip(request)
    if is_rate_limited('contact-submit', ip, CONTACT_RATE_MAX, CONTACT_RATE_WINDOW):
        logger.warning('Contact form rate limit hit for ip=%s', ip)
        return JsonResponse(
            {'error': 'Too many requests. Please try again later.'},
            status=429,
        )

    name = (data.get('name') or '').strip()
    email = (data.get('email') or '').strip()
    category = data.get('category', 'other')
    subject = (data.get('subject') or '').strip()
    message = (data.get('message') or '').strip()

    errors = {}
    if not name:
        errors['name'] = 'Name is required'
    if not email:
        errors['email'] = 'Email is required'
    if not subject:
        errors['subject'] = 'Subject is required'
    if not message:
        errors['message'] = 'Message is required'
    if errors:
        return JsonResponse({'errors': errors}, status=400)

    # Persist BEFORE sending so we never lose the submission if SMTP fails.
    submission = ContactSubmission.objects.create(
        name=name,
        email=email,
        category=category,
        subject=subject,
        message=message,
        ip_address=ip,
        status=ContactSubmission.STATUS_PENDING,
    )

    category_label = CATEGORY_LABELS.get(category, category)
    text_body, html_body = _build_bodies(submission, category_label)

    try:
        msg = EmailMultiAlternatives(
            subject=f'[{category_label}] {subject}',
            body=text_body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[settings.SUPPORT_EMAIL],
            reply_to=[email],
            headers={
                'X-Portal-Submission-Id': str(submission.pk),
                # Same tracking-off rationale as the magic-link email:
                # the tracking pixel causes Gmail to show "loading
                # external images" before render. We don't need open
                # tracking for an internal staff notification anyway.
                # Mailgun maps these X-Mailgun-* SMTP headers to its
                # o:tracking-* API options.
                'X-Mailgun-Track-Opens': 'no',
                'X-Mailgun-Track-Clicks': 'no',
            },
        )
        msg.attach_alternative(html_body, 'text/html')
        msg.send()
    except Exception as exc:
        logger.exception(
            'Failed to send contact submission id=%s from=%s', submission.pk, email
        )
        submission.status = ContactSubmission.STATUS_FAILED
        submission.error = f'{type(exc).__name__}: {exc}'
        submission.save(update_fields=['status', 'error'])
        return JsonResponse(
            {'error': 'Failed to send message. Please try again.'},
            status=500,
        )

    submission.status = ContactSubmission.STATUS_SENT
    submission.sent_at = timezone.now()
    submission.save(update_fields=['status', 'sent_at'])

    logger.info('Contact submission id=%s sent from=%s', submission.pk, email)
    return JsonResponse({'ok': True, 'message': 'Your request has been submitted.'})
