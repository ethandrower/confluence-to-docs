"""Admin support-ticket endpoints. Gated via require_portal_admin.
Reuses serializer helpers from portal.views.tickets to keep one source of
truth for the JSON shapes."""
import json

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from portal import ticket_notify
from portal.decorators import require_portal_admin
from portal.models import Company, Ticket, TicketMessage
from portal.rate_limit import is_rate_limited
from portal.views.tickets import (
    _clean_ccs, _message_dict, _ticket_dict, _with_message_count,
    log_ticket_activity,
)

# Max rows the admin "All" list returns without pagination (spec §4e/§6).
ADMIN_LIST_CAP = 200


def _admin_dict(t, message_count=None):
    d = _ticket_dict(t, message_count=message_count)
    d.update({
        'company': {'id': t.company_id, 'name': t.company.name},
        'jira_key': t.jira_key,
        'cc_emails': t.cc_emails,
        'created_by_email': t.created_by.email if t.created_by else '',
    })
    return d


def _get(number):
    return Ticket.objects.select_related('company', 'created_by')\
                         .filter(number=number).first()


@require_http_methods(['GET'])
@require_portal_admin
def inbox(request):
    qs = _with_message_count(
        Ticket.objects.select_related('company', 'created_by')
        .filter(status=Ticket.STATUS_WAITING_ON_SUPPORT)
    ).order_by('updated_at')
    items = [_admin_dict(t, message_count=t._mc) for t in qs]
    return JsonResponse({'tickets': items, 'awaiting_total': len(items)})


@csrf_exempt
@require_http_methods(['GET', 'POST'])
@require_portal_admin
def collection(request):
    if request.method == 'GET':
        qs = _with_message_count(
            Ticket.objects.select_related('company', 'created_by')
        ).order_by('-updated_at')
        company_id = request.GET.get('company')
        if company_id:
            qs = qs.filter(company_id=company_id)
        status = request.GET.get('status')
        if status:
            qs = qs.filter(status=status)
        # Fetch one past the cap so we can flag truncation without an extra
        # COUNT. No pagination yet (spec §6) — the flag drives a UI hint.
        rows = list(qs[:ADMIN_LIST_CAP + 1])
        truncated = len(rows) > ADMIN_LIST_CAP
        return JsonResponse({
            'tickets': [_admin_dict(t, message_count=t._mc)
                        for t in rows[:ADMIN_LIST_CAP]],
            'truncated': truncated,
        })

    # POST — create on behalf of a customer
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'error': 'Invalid request body'}, status=400)
    company = Company.objects.filter(id=data.get('company_id')).first()
    subject = (data.get('subject') or '').strip()
    body = (data.get('body') or '').strip()
    if not company or not subject or not body:
        return JsonResponse({'error': 'company_id, subject and body are required'},
                            status=400)
    ccs = _clean_ccs(data.get('cc_emails'))
    customer_email = (data.get('customer_email') or '').strip()
    if customer_email and customer_email not in ccs:
        ccs = _clean_ccs([customer_email] + ccs)

    category = data.get('category') or 'question'
    if category not in dict(Ticket.CATEGORY_CHOICES):
        category = 'other'

    user = request.portal_user
    ticket = Ticket.objects.create(
        company=company, created_by=user, subject=subject[:512],
        category=category, cc_emails=ccs,
        status=Ticket.STATUS_WAITING_ON_CUSTOMER)
    first = TicketMessage.objects.create(
        ticket=ticket, author=user, author_email=user.email,
        body=body, origin=TicketMessage.ORIGIN_STAFF)
    log_ticket_activity(ticket, 'created', actor=user, on_behalf=True)
    ticket_notify.notify_ticket_created(ticket, first)
    return JsonResponse(_admin_dict(ticket, message_count=1))


@require_http_methods(['GET'])
@require_portal_admin
def detail(request, number):
    t = _get(number)
    if not t:
        return JsonResponse({'error': 'Not found'}, status=404)
    msgs = list(t.messages.all())
    d = _admin_dict(t, message_count=len(msgs))
    d['messages'] = [dict(_message_dict(m), is_internal=m.is_internal,
                          delivery_detail=m.delivery_detail)
                     for m in msgs]
    d['activity'] = [{
        'action': a.action, 'detail': a.detail,
        'actor': a.actor.email if a.actor else '',
        'created_at': a.created_at.isoformat(),
    } for a in t.activity.all()[:50]]
    return JsonResponse(d)


@csrf_exempt
@require_http_methods(['POST'])
@require_portal_admin
def reply(request, number):
    t = _get(number)
    if not t:
        return JsonResponse({'error': 'Not found'}, status=404)
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'error': 'Invalid request body'}, status=400)
    body = (data.get('body') or '').strip()
    if not body:
        return JsonResponse({'error': 'Message is required'}, status=400)
    is_internal = bool(data.get('is_internal'))

    user = request.portal_user
    m = TicketMessage.objects.create(
        ticket=t, author=user, author_email=user.email, body=body,
        origin=TicketMessage.ORIGIN_STAFF, is_internal=is_internal)
    if not is_internal:
        t.status = Ticket.STATUS_WAITING_ON_CUSTOMER
        t.save(update_fields=['status', 'updated_at'])
        ticket_notify.notify_staff_reply(t, m)
    log_ticket_activity(t, 'note_added' if is_internal else 'message_sent',
                        actor=user)
    return JsonResponse({'ok': True,
                         'message': dict(_message_dict(m),
                                         is_internal=m.is_internal,
                                         delivery_detail=m.delivery_detail),
                         'status': t.status})


@csrf_exempt
@require_http_methods(['POST'])
@require_portal_admin
def resend_message(request, number, message_id):
    """Re-send a customer-facing message whose delivery failed (or to retry a
    stuck send). Re-uses the staff-reply send path, which records the new
    outcome on the message. Admin-only, rate-limited per ticket."""
    t = _get(number)
    if not t:
        return JsonResponse({'error': 'Not found'}, status=404)
    m = TicketMessage.objects.filter(id=message_id, ticket=t).first()
    if not m:
        return JsonResponse({'error': 'Not found'}, status=404)
    # Resend only re-emits staff replies to the customer. Never re-send a
    # customer's own message (would arrive dressed as a staff reply) or an
    # internal note (never leaves the building).
    if m.origin != TicketMessage.ORIGIN_STAFF or m.is_internal:
        return JsonResponse({'error': 'Only staff replies can be resent'},
                            status=400)
    if is_rate_limited('ticket-resend', f't{t.number}', 10, 60 * 60):
        return JsonResponse({'error': 'Too many resends, try later'}, status=429)
    ticket_notify.notify_staff_reply(t, m)
    m.refresh_from_db()
    return JsonResponse({'ok': True, 'delivery_status': m.delivery_status,
                         'delivery_detail': m.delivery_detail})


@csrf_exempt
@require_http_methods(['POST'])
@require_portal_admin
def set_status(request, number):
    t = _get(number)
    if not t:
        return JsonResponse({'error': 'Not found'}, status=404)
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'error': 'Invalid request body'}, status=400)
    status = data.get('status')
    if status not in dict(Ticket.STATUS_CHOICES):
        return JsonResponse({'error': 'Invalid status'}, status=400)
    old = t.status
    t.status = status
    t.save(update_fields=['status', 'updated_at'])
    log_ticket_activity(t, 'status_changed', actor=request.portal_user,
                        old=old, new=status)
    if status in (Ticket.STATUS_RESOLVED, Ticket.STATUS_CLOSED):
        ticket_notify.notify_status(t)
    return JsonResponse({'ok': True, 'status': t.status})


@csrf_exempt
@require_http_methods(['POST'])
@require_portal_admin
def set_jira(request, number):
    t = _get(number)
    if not t:
        return JsonResponse({'error': 'Not found'}, status=404)
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'error': 'Invalid request body'}, status=400)
    t.jira_key = (data.get('jira_key') or '').strip()[:32]
    t.save(update_fields=['jira_key', 'updated_at'])
    log_ticket_activity(t, 'jira_linked', actor=request.portal_user,
                        jira_key=t.jira_key)
    return JsonResponse({'ok': True, 'jira_key': t.jira_key})


@csrf_exempt
@require_http_methods(['POST'])
@require_portal_admin
def set_cc(request, number):
    t = _get(number)
    if not t:
        return JsonResponse({'error': 'Not found'}, status=404)
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'error': 'Invalid request body'}, status=400)
    t.cc_emails = _clean_ccs(data.get('cc_emails'))
    t.save(update_fields=['cc_emails', 'updated_at'])
    log_ticket_activity(t, 'cc_changed', actor=request.portal_user,
                        cc_emails=t.cc_emails)
    return JsonResponse({'ok': True, 'cc_emails': t.cc_emails})
