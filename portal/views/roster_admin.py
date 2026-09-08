"""The staff half of the initial user request form (REV-45).

CS opens a request against a company, sends it, watches the roster arrive, and
then performs the two acts that change anything outside this app:

    POST .../provision   creates the portal accounts. Sends nothing.
    POST .../invite      emails the people who now have accounts.

They are separate endpoints because they are separate decisions — see
`portal/roster_provision.py` for why collapsing them is the one thing this
design will not do.
"""
import json
import logging

from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from portal import roster_provision
from portal.decorators import require_portal_admin
from portal.models import Company, MODULE_LABELS, UserRequest
from portal.views.roster import request_dict, requested_user_dict

logger = logging.getLogger(__name__)


def _summary(req):
    """List-row shape. Counts rather than rows — the list page shows twenty
    companies and does not need every roster in memory to do it."""
    users = list(req.users.all())
    return {
        'id': req.id,
        'company': req.company.name,
        'company_id': req.company_id,
        'status': req.status,
        'note': req.note,
        'created_at': req.created_at.isoformat(),
        'sent_at': req.sent_at.isoformat() if req.sent_at else None,
        'submitted_at': req.submitted_at.isoformat() if req.submitted_at else None,
        'user_count': len(users),
        'added_count': sum(1 for u in users if u.added_at),
        'invited_count': sum(1 for u in users if u.activation_email_sent_at),
    }


@require_portal_admin
@require_http_methods(['GET', 'POST'])
def requests_collection(request):
    """GET  /api/admin/roster/requests/   — every request, newest first
       POST /api/admin/roster/requests/   — open one against a company
    """
    if request.method == 'GET':
        qs = (UserRequest.objects
              .select_related('company')
              .prefetch_related('users')
              .all())
        company_id = request.GET.get('company_id')
        if company_id and company_id.isdigit():
            qs = qs.filter(company_id=int(company_id))
        return JsonResponse({'requests': [_summary(r) for r in qs]})

    payload = json.loads(request.body or '{}')
    company_id = payload.get('company_id')
    if not company_id:
        return JsonResponse({'error': 'A company is required.'}, status=400)
    company = get_object_or_404(Company, pk=company_id)

    # An open request per company is the useful invariant: two live forms for
    # one customer means two rosters and no answer to "which is the roster".
    existing = UserRequest.objects.filter(
        company=company,
        status__in=(UserRequest.STATUS_DRAFT, UserRequest.STATUS_SENT,
                    UserRequest.STATUS_SUBMITTED)).first()
    if existing:
        return JsonResponse(
            {'error': f'{company.name} already has an open user request.',
             'request_id': existing.pk}, status=409)

    req = UserRequest.objects.create(
        company=company,
        note=str(payload.get('note') or '').strip(),
        created_by=request.portal_user,
        # Opening one and not sending it has no use yet — there is no draft UI —
        # so it is sent on creation and `sent` is what the customer can edit.
        status=UserRequest.STATUS_SENT,
        sent_at=timezone.now(),
    )
    logger.info('roster: request %s opened for %s by %s',
                req.pk, company.name, request.portal_user.email)
    return JsonResponse({'request': _summary(req)}, status=201)


@require_portal_admin
@require_http_methods(['GET', 'POST'])
def request_detail(request, request_id):
    """GET  — the full roster
       POST — {"action": "reopen"|"close"|"provision"|"invite"}
    """
    req = get_object_or_404(
        UserRequest.objects.select_related('company').prefetch_related('users'),
        pk=request_id)

    if request.method == 'GET':
        data = request_dict(req)
        data['imports'] = [
            {'id': i.id, 'filename': i.filename, 'state': i.state,
             'created_count': i.created_count, 'updated_count': i.updated_count,
             'skipped_count': i.skipped_count, 'error': i.error,
             'created_at': i.created_at.isoformat()}
            for i in req.imports.all()]
        return JsonResponse({'request': data})

    payload = json.loads(request.body or '{}')
    action = payload.get('action')

    if action == 'reopen':
        # Deliberately a staff action. The customer cannot un-submit, because
        # provisioning may already have started reading the roster.
        req.status = UserRequest.STATUS_SENT
        req.submitted_at = None
        req.save(update_fields=['status', 'submitted_at'])
        logger.info('roster: request %s reopened by %s',
                    req.pk, request.portal_user.email)
        return JsonResponse({'request': _summary(req)})

    if action == 'close':
        req.status = UserRequest.STATUS_CLOSED
        req.save(update_fields=['status'])
        return JsonResponse({'request': _summary(req)})

    if action == 'provision':
        result = roster_provision.provision(req, actor=request.portal_user)
        return JsonResponse({
            'result': result,
            'request': request_dict(req.__class__.objects
                                    .select_related('company')
                                    .prefetch_related('users')
                                    .get(pk=req.pk)),
        })

    if action == 'invite':
        only = payload.get('user_ids') or None
        result = roster_provision.send_invites(
            req, actor=request.portal_user, only_ids=only)
        return JsonResponse({
            'result': result,
            'request': request_dict(req.__class__.objects
                                    .select_related('company')
                                    .prefetch_related('users')
                                    .get(pk=req.pk)),
        })

    return JsonResponse({'error': f'Unknown action: {action!r}'}, status=400)


@require_portal_admin
@require_http_methods(['POST'])
def user_status_note(request, user_id):
    """POST /api/admin/roster/users/<id>/note — annotate a person's status.

    The one escape hatch on the derived columns, for when an invite genuinely
    went out some other way. It writes a NOTE beside the timestamps and never
    the timestamps themselves, so "we emailed them from Outlook" and "the system
    sent it" never become the same claim.
    """
    from portal.models import RequestedUser

    row = get_object_or_404(RequestedUser, pk=user_id)
    payload = json.loads(request.body or '{}')
    row.status_note = str(payload.get('note') or '').strip()[:512]
    row.status_overridden_by = request.portal_user
    row.save(update_fields=['status_note', 'status_overridden_by'])
    logger.info('roster: status note on %s by %s',
                row.email, request.portal_user.email)
    return JsonResponse({'user': requested_user_dict(row)})


@require_portal_admin
@require_http_methods(['GET'])
def modules(request):
    """The module vocabulary, for the company-entitlement editor."""
    return JsonResponse({'modules': [{'key': k, 'label': v}
                                     for k, v in MODULE_LABELS.items()]})
