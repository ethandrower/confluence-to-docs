import json
import logging

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.http import JsonResponse
from django.template.loader import render_to_string
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST, require_http_methods

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
            # Tracking is disabled globally via ANYMAIL SEND_DEFAULTS.
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


# ---------------------------------------------------------------------------
# Support tickets (Phase 1) — customer endpoints.
# All queries go through Ticket.for_user() (tenant chokepoint).
# ---------------------------------------------------------------------------
from portal import ticket_notify
from portal.decorators import require_portal_user
from portal.models import Ticket, TicketMessage, TicketActivity

TICKET_RATE_MAX = 20          # ticket creations per user-company per hour
TICKET_RATE_WINDOW = 60 * 60


def log_ticket_activity(ticket, action, actor=None, **detail):
    TicketActivity.objects.create(ticket=ticket, actor=actor,
                                  action=action, detail=detail)


STAFF_PUBLIC_NAME = 'CiteMed Support'


def _message_dict(m, for_customer=False):
    is_staff = m.origin == TicketMessage.ORIGIN_STAFF
    # Customer-facing payloads show one consistent support identity — never an
    # individual staffer's name or email (privacy for regulated customers).
    # Admin payloads pass for_customer=False and keep the real author.
    if is_staff and for_customer:
        return {
            'id': m.id,
            'body': m.body,
            'origin': m.origin,
            'author_name': STAFF_PUBLIC_NAME,
            'author_email': '',
            'is_staff': True,
            'delivery_status': m.delivery_status,
            'created_at': m.created_at.isoformat(),
        }
    # Never render a blank sender: fall back to author name → author email →
    # a role-appropriate label. Covers seeded/legacy rows and future inbound
    # email messages that may have no linked PortalUser.
    if m.author:
        author_name = m.author.name or m.author.email
    elif m.author_email:
        author_name = m.author_email
    else:
        author_name = STAFF_PUBLIC_NAME if is_staff else 'Customer'
    return {
        'id': m.id,
        'body': m.body,
        'origin': m.origin,
        'author_name': author_name,
        'author_email': (m.author.email if m.author else m.author_email),
        'is_staff': is_staff,
        'delivery_status': m.delivery_status,
        'created_at': m.created_at.isoformat(),
    }


def _with_message_count(qs):
    """Annotate `_mc` = non-internal message count, so list endpoints don't run
    a per-row COUNT (N+1). Matches the semantics _ticket_dict computes lazily."""
    from django.db.models import Count, Q
    return qs.annotate(
        _mc=Count('messages', filter=Q(messages__is_internal=False)))


def _ticket_dict(t, message_count=None):
    return {
        'number': t.number,
        'display_number': t.display_number,
        'subject': t.subject,
        'category': t.category,
        'status': t.status,
        'created_at': t.created_at.isoformat(),
        'updated_at': t.updated_at.isoformat(),
        'message_count': message_count if message_count is not None
                         else t.messages.filter(is_internal=False).count(),
    }


def _clean_ccs(raw):
    from django.core.validators import validate_email
    from django.core.exceptions import ValidationError
    # Only accept a JSON list; anything else (string, number, object, null)
    # is treated as "no CCs" rather than crashing on slice/iterate (→ 500).
    if not isinstance(raw, list):
        return []
    ccs = []
    for e in raw[:10]:
        if not isinstance(e, str):
            continue
        e = e.strip()
        if not e:
            continue
        try:
            validate_email(e)
            ccs.append(e)
        except ValidationError:
            pass
    return list(dict.fromkeys(ccs))


@csrf_exempt
@require_http_methods(['GET', 'POST'])
@require_portal_user
def tickets_collection(request):
    user = request.portal_user
    if request.method == 'GET':
        qs = _with_message_count(Ticket.for_user(user)).order_by('-updated_at')
        return JsonResponse({'tickets': [_ticket_dict(t, message_count=t._mc)
                                         for t in qs]})

    # POST — create
    if not user.company_id:
        return JsonResponse({'error': 'No company on your account'}, status=403)
    if is_rate_limited('ticket-create', f'co{user.company_id}',
                       TICKET_RATE_MAX, TICKET_RATE_WINDOW):
        return JsonResponse({'error': 'Too many tickets, try later'}, status=429)
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'error': 'Invalid request body'}, status=400)

    subject = (data.get('subject') or '').strip()
    body = (data.get('body') or '').strip()
    if not subject or not body:
        return JsonResponse({'error': 'Subject and message are required'}, status=400)
    category = data.get('category') or 'question'
    if category not in dict(Ticket.CATEGORY_CHOICES):
        category = 'other'

    ticket = Ticket.objects.create(
        company=user.company, created_by=user, subject=subject[:512],
        category=category, cc_emails=_clean_ccs(data.get('cc_emails')))
    first = TicketMessage.objects.create(
        ticket=ticket, author=user, author_email=user.email,
        body=body, origin=TicketMessage.ORIGIN_PORTAL)
    log_ticket_activity(ticket, 'created', actor=user)
    ticket_notify.notify_ticket_created(ticket, first)
    return JsonResponse(_ticket_dict(ticket, message_count=1))


def _own_ticket(request, number):
    return Ticket.for_user(request.portal_user).filter(number=number).first()


@require_http_methods(['GET'])
@require_portal_user
def ticket_detail(request, number):
    t = _own_ticket(request, number)
    if not t:
        return JsonResponse({'error': 'Not found'}, status=404)
    msgs = t.messages.filter(is_internal=False)
    data = _ticket_dict(t, message_count=msgs.count())
    data['cc_emails'] = t.cc_emails
    data['messages'] = [_message_dict(m, for_customer=True) for m in msgs]
    return JsonResponse(data)


@csrf_exempt
@require_http_methods(['POST'])
@require_portal_user
def ticket_reply(request, number):
    t = _own_ticket(request, number)
    if not t:
        return JsonResponse({'error': 'Not found'}, status=404)
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'error': 'Invalid request body'}, status=400)
    body = (data.get('body') or '').strip()
    if not body:
        return JsonResponse({'error': 'Message is required'}, status=400)

    user = request.portal_user
    m = TicketMessage.objects.create(
        ticket=t, author=user, author_email=user.email,
        body=body, origin=TicketMessage.ORIGIN_PORTAL)
    t.status = Ticket.STATUS_WAITING_ON_SUPPORT
    t.save(update_fields=['status', 'updated_at'])
    log_ticket_activity(t, 'message_sent', actor=user)
    ticket_notify.notify_customer_reply(t, m)
    return JsonResponse({'ok': True, 'message': _message_dict(m, for_customer=True),
                         'status': t.status})
