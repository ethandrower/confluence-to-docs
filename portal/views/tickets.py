import json
import logging
from html import escape

from django.conf import settings
from django.core.cache import cache
from django.core.mail import EmailMultiAlternatives
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from portal.models import ContactSubmission

logger = logging.getLogger(__name__)


CATEGORY_LABELS = {
    'question': 'Question',
    'bug': 'Bug Report',
    'feature': 'Feature Request',
    'docs': 'Documentation Issue',
    'other': 'Other',
}

# Rate limit: max submissions per IP per window.
RATE_LIMIT_MAX = 5
RATE_LIMIT_WINDOW_SECONDS = 60 * 60  # 1 hour


def _client_ip(request):
    forwarded = request.META.get('HTTP_X_FORWARDED_FOR', '')
    if forwarded:
        return forwarded.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')


def _is_rate_limited(ip):
    if not ip:
        return False
    key = f'contact-submit:{ip}'
    count = cache.get(key, 0)
    if count >= RATE_LIMIT_MAX:
        return True
    # cache.incr requires key to exist; use add+incr pattern.
    if not cache.add(key, 1, RATE_LIMIT_WINDOW_SECONDS):
        cache.incr(key)
    return False


def _build_bodies(submission, category_label):
    text_body = (
        f'Name: {submission.name}\n'
        f'Email: {submission.email}\n'
        f'Category: {category_label}\n'
        f'\n'
        f'{submission.message}'
    )
    html_body = (
        f'<p><strong>Name:</strong> {escape(submission.name)}<br>'
        f'<strong>Email:</strong> <a href="mailto:{escape(submission.email)}">{escape(submission.email)}</a><br>'
        f'<strong>Category:</strong> {escape(category_label)}</p>'
        f'<hr>'
        f'<p style="white-space: pre-wrap;">{escape(submission.message)}</p>'
    )
    return text_body, html_body


@csrf_exempt
@require_POST
def submit_ticket(request):
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'error': 'Invalid request body'}, status=400)

    ip = _client_ip(request)
    if _is_rate_limited(ip):
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
            headers={'X-Portal-Submission-Id': str(submission.pk)},
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
