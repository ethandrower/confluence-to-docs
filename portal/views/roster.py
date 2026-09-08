"""The customer's half of the initial user request form (REV-45).

Every endpoint is company-scoped through `request.portal_user.company`, and a
UserRequest is only ever reached by that scope — never by trusting an id from
the client. A roster is a list of a customer's colleagues and their access
levels, so a cross-company read here would be a real disclosure, not a cosmetic
one.

WHAT THE CUSTOMER CAN AND CANNOT WRITE. They own the roster: who is on it, what
modules each person needs, what kind of access. They do not own its outcome —
`added_at` and `activation_email_sent_at` are set by provisioning and are absent
from every serializer's input path here. They are returned for display, so the
form can show what has happened, and there is no route that accepts them.
"""
import json
import logging

from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_http_methods

from portal import roster
from portal.decorators import require_portal_user
from portal.models import (
    MODULE_LABELS, RequestedUser, RosterImport, UserRequest,
)
from portal.rate_limit import is_rate_limited

logger = logging.getLogger(__name__)

#: An upload bigger than this is not a roster. Checked before the bytes are
#: parsed so a large file is refused rather than read into memory first.
MAX_UPLOAD_BYTES = 2 * 1024 * 1024


def requested_user_dict(user):
    """The shape the form renders.

    `added_at` / `activation_email_sent_at` appear here and nowhere on the way
    in. They are the two columns the customer's own spreadsheet carried, and the
    only honest source for them is the provisioning run.
    """
    return {
        'id': user.id,
        'first_name': user.first_name,
        'last_name': user.last_name,
        'email': user.email,
        'modules': user.modules,
        'module_labels': user.module_labels(),
        'role_type': user.role_type,
        'note': user.note,
        'source': user.source,
        # Read-only status.
        'added_at': user.added_at.isoformat() if user.added_at else None,
        'activation_email_sent_at': (
            user.activation_email_sent_at.isoformat()
            if user.activation_email_sent_at else None),
        'status_note': user.status_note,
    }


def request_dict(req, *, include_users=True):
    data = {
        'id': req.id,
        'status': req.status,
        'note': req.note,
        'editable': req.is_customer_editable,
        'company': req.company.name,
        'created_at': req.created_at.isoformat(),
        'sent_at': req.sent_at.isoformat() if req.sent_at else None,
        'submitted_at': req.submitted_at.isoformat() if req.submitted_at else None,
        # The picker's options travel with the request so the form never has to
        # know the module vocabulary itself, and a customer is never shown a
        # module they are not licensed for.
        'module_options': [{'key': k, 'label': MODULE_LABELS[k]}
                           for k in req.licensed_modules()],
        'role_options': [{'key': k, 'label': v}
                         for k, v in RequestedUser.ROLE_CHOICES],
    }
    if include_users:
        data['users'] = [requested_user_dict(u) for u in req.users.all()]
    return data


def _current_request(portal_user):
    """The request this customer is working on, or None.

    Newest first, and only ever within their own company. Deliberately does not
    take an id from the caller: there is exactly one roster a given customer
    should be editing, and letting the client name it would be a lookup that
    has to be re-secured on every endpoint.
    """
    if not portal_user.company_id:
        return None
    return (UserRequest.objects
            .filter(company_id=portal_user.company_id)
            .exclude(status=UserRequest.STATUS_DRAFT)
            .select_related('company')
            .prefetch_related('users')
            .first())


def _no_company():
    return JsonResponse(
        {'error': 'No company is associated with your account.'}, status=403)


def _not_editable():
    return JsonResponse(
        {'error': 'This form has been submitted and can no longer be edited. '
                  'Contact your CiteMed representative to reopen it.'},
        status=409)


# ── Reading the form ─────────────────────────────────────────────────────────

@require_portal_user
@require_GET
def current(request):
    """GET /api/roster/ — the form, or `null` when nothing has been sent."""
    if not request.portal_user.company_id:
        return _no_company()
    req = _current_request(request.portal_user)
    if req is None:
        return JsonResponse({'request': None})
    return JsonResponse({'request': request_dict(req)})


# ── Editing rows ─────────────────────────────────────────────────────────────

def _clean_row(payload, req):
    """(fields, error) for one submitted row.

    Modules are intersected with what the company is licensed for rather than
    trusted: the picker only offers licensed ones, but the picker is not the
    security boundary.
    """
    email = roster.normalise_email(payload.get('email'))
    if not email or '@' not in email:
        return None, JsonResponse(
            {'error': 'A valid email address is required.'}, status=400)

    allowed = set(req.licensed_modules())
    modules = [m for m in (payload.get('modules') or []) if m in allowed]

    role = payload.get('role_type')
    if role not in dict(RequestedUser.ROLE_CHOICES):
        role = RequestedUser.ROLE_VIEWER

    return {
        'email': email,
        'first_name': str(payload.get('first_name') or '').strip()[:128],
        'last_name': str(payload.get('last_name') or '').strip()[:128],
        'modules': modules,
        'role_type': role,
        'note': str(payload.get('note') or '').strip(),
    }, None


@require_portal_user
@require_http_methods(['POST'])
def users_collection(request):
    """POST /api/roster/users/ — add one person to the roster."""
    if not request.portal_user.company_id:
        return _no_company()
    req = _current_request(request.portal_user)
    if req is None:
        return JsonResponse({'error': 'No user request form is open.'}, status=404)
    if not req.is_customer_editable:
        return _not_editable()

    payload = json.loads(request.body or '{}')
    fields, err = _clean_row(payload, req)
    if err:
        return err

    # Upsert rather than 409. Adding somebody who is already listed is a
    # correction, not an error, and the form's own list is right there — a
    # customer doing it means they want the newer details.
    row, created = RequestedUser.objects.update_or_create(
        request=req, email=fields.pop('email'),
        defaults={**fields, 'source': RequestedUser.SOURCE_FORM},
    )
    return JsonResponse({'user': requested_user_dict(row)},
                        status=201 if created else 200)


@require_portal_user
@require_http_methods(['PATCH', 'DELETE'])
def user_detail(request, user_id):
    """PATCH/DELETE /api/roster/users/<id>/ — edit or remove one row."""
    if not request.portal_user.company_id:
        return _no_company()
    req = _current_request(request.portal_user)
    if req is None:
        return JsonResponse({'error': 'No user request form is open.'}, status=404)
    if not req.is_customer_editable:
        return _not_editable()

    # Scoped through the request, which is itself scoped to the company — an
    # id from another customer's roster simply does not resolve.
    row = req.users.filter(pk=user_id).first()
    if row is None:
        return JsonResponse({'error': 'Not found.'}, status=404)

    if request.method == 'DELETE':
        if row.added_at:
            # Already provisioned. Removing the row would hide a person who
            # actually has access, which is worse than an untidy list;
            # offboarding is a different act with a different audit trail.
            return JsonResponse(
                {'error': 'This person has already been set up. Contact your '
                          'CiteMed representative to remove their access.'},
                status=409)
        row.delete()
        return JsonResponse({'deleted': True})

    payload = json.loads(request.body or '{}')
    payload.setdefault('email', row.email)
    fields, err = _clean_row(payload, req)
    if err:
        return err
    for key, value in fields.items():
        setattr(row, key, value)
    try:
        row.save()
    except Exception:
        return JsonResponse(
            {'error': 'Somebody else on the roster already uses that address.'},
            status=409)
    return JsonResponse({'user': requested_user_dict(row)})


@require_portal_user
@require_http_methods(['POST'])
def submit(request):
    """POST /api/roster/submit/ — the customer says the roster is complete."""
    if not request.portal_user.company_id:
        return _no_company()
    req = _current_request(request.portal_user)
    if req is None:
        return JsonResponse({'error': 'No user request form is open.'}, status=404)
    if not req.is_customer_editable:
        return _not_editable()
    if not req.users.exists():
        return JsonResponse(
            {'error': 'Add at least one person before submitting.'}, status=400)
    # A roster still waiting on an import would be submitted incomplete, and
    # the customer would have no way to tell.
    if req.imports.filter(state__in=(RosterImport.STATE_CONFIRMED,
                                     RosterImport.STATE_APPLYING)).exists():
        return JsonResponse(
            {'error': 'An import is still being processed. Try again in a moment.'},
            status=409)

    req.status = UserRequest.STATUS_SUBMITTED
    req.submitted_at = timezone.now()
    req.save(update_fields=['status', 'submitted_at'])
    logger.info('roster: request %s submitted by %s (%s people)',
                req.pk, request.portal_user.email, req.users.count())
    return JsonResponse({'request': request_dict(req)})


# ── The template ─────────────────────────────────────────────────────────────

@require_portal_user
@require_GET
def template(request):
    """GET /api/roster/template.csv — the file to fill in.

    Handed out rather than described, because "use these column headings" in
    prose is how a sheet comes back with "E-mail" and a mapping step nobody
    should have needed.
    """
    response = HttpResponse(roster.template_csv(), content_type='text/csv')
    response['Content-Disposition'] = (
        'attachment; filename="citemed-user-request-template.csv"')
    return response


# ── Import: upload, review, confirm ──────────────────────────────────────────

def import_dict(job, *, include_preview=False, req=None):
    data = {
        'id': job.id,
        'filename': job.filename,
        'state': job.state,
        'headers': job.headers,
        'mapping': job.mapping,
        'row_count': len(job.rows or []),
        'created_count': job.created_count,
        'updated_count': job.updated_count,
        'skipped_count': job.skipped_count,
        'problems': job.problems,
        'error': job.error,
        'created_at': job.created_at.isoformat(),
        'applied_at': job.applied_at.isoformat() if job.applied_at else None,
    }
    if include_preview:
        target = req or job.request
        data['unmapped_headers'] = roster.unmapped_headers(job.headers, job.mapping)
        data['field_options'] = [
            {'key': k, 'label': v} for k, v in roster.FIELD_LABELS.items()]
        data['preview'] = roster.build_preview(
            job.headers, job.rows, job.mapping, target.licensed_modules())
    return data


@require_portal_user
@require_http_methods(['POST'])
def imports_collection(request):
    """POST /api/roster/imports/ — upload a spreadsheet and get a preview back.

    Parsing happens now, applying does not. The customer has to see what we
    understood before anything is written, which is the whole point of the
    confirmation step; and a 400-row apply does not belong on a request a proxy
    is timing out.
    """
    if not request.portal_user.company_id:
        return _no_company()
    req = _current_request(request.portal_user)
    if req is None:
        return JsonResponse({'error': 'No user request form is open.'}, status=404)
    if not req.is_customer_editable:
        return _not_editable()

    # Parsing is the expensive part of this endpoint and it runs before any
    # write, so it is the one worth rate limiting.
    if is_rate_limited('roster-import', str(request.portal_user.pk), 10, 300):
        return JsonResponse(
            {'error': 'Too many uploads. Wait a minute and try again.'}, status=429)

    upload = request.FILES.get('file')
    if upload is None:
        return JsonResponse({'error': 'No file was uploaded.'}, status=400)
    if upload.size > MAX_UPLOAD_BYTES:
        return JsonResponse(
            {'error': 'That file is too large to be a user list.'}, status=400)

    try:
        headers, rows = roster.parse_file(upload.name, upload.read())
    except roster.RosterParseError as exc:
        return JsonResponse({'error': str(exc)}, status=400)

    if len(rows) > RosterImport.MAX_ROWS:
        return JsonResponse(
            {'error': f'That file has {len(rows)} rows. The most that can be '
                      f'imported at once is {RosterImport.MAX_ROWS}.'},
            status=400)

    job = RosterImport.objects.create(
        request=req, uploaded_by=request.portal_user,
        filename=upload.name[:256], headers=headers, rows=rows,
        mapping=roster.sniff_mapping(headers),
    )
    logger.info('roster: import %s uploaded for request %s (%s rows)',
                job.pk, req.pk, len(rows))
    return JsonResponse({'import': import_dict(job, include_preview=True, req=req)},
                        status=201)


@require_portal_user
@require_http_methods(['GET', 'POST', 'DELETE'])
def import_detail(request, import_id):
    """GET   /api/roster/imports/<id>/  — preview and state
       POST  /api/roster/imports/<id>/  — correct the mapping, or confirm
       DELETE                           — discard it
    """
    if not request.portal_user.company_id:
        return _no_company()
    req = _current_request(request.portal_user)
    if req is None:
        return JsonResponse({'error': 'No user request form is open.'}, status=404)

    job = req.imports.filter(pk=import_id).first()
    if job is None:
        return JsonResponse({'error': 'Not found.'}, status=404)

    if request.method == 'GET':
        return JsonResponse({'import': import_dict(
            job, include_preview=job.state == RosterImport.STATE_PENDING_REVIEW,
            req=req)})

    if request.method == 'DELETE':
        if job.state in (RosterImport.STATE_APPLYING, RosterImport.STATE_DONE):
            return JsonResponse(
                {'error': 'This import has already run.'}, status=409)
        job.delete()
        return JsonResponse({'deleted': True})

    if not req.is_customer_editable:
        return _not_editable()
    if job.state != RosterImport.STATE_PENDING_REVIEW:
        return JsonResponse(
            {'error': 'This import has already been confirmed.'}, status=409)

    payload = json.loads(request.body or '{}')

    # A corrected mapping is saved even when the caller is not confirming yet,
    # so the preview can be re-rendered against it.
    if 'mapping' in payload:
        cleaned = {}
        for index, field in (payload.get('mapping') or {}).items():
            if not str(index).isdigit() or int(index) >= len(job.headers):
                continue
            if field in roster.FIELD_LABELS:
                cleaned[str(index)] = field
        job.mapping = cleaned
        job.save(update_fields=['mapping'])

    if not payload.get('confirm'):
        return JsonResponse({'import': import_dict(job, include_preview=True, req=req)})

    # Confirming does not apply. It hands the job to the cron runner, which is
    # what keeps a large roster off the request path — see RosterImport's
    # docstring for why this is not Celery.
    if roster.FIELD_EMAIL not in set(job.mapping.values()):
        return JsonResponse(
            {'error': 'Tell us which column holds the email address — without '
                      'it there is nothing to import people under.'}, status=400)

    job.state = RosterImport.STATE_CONFIRMED
    job.confirmed_at = timezone.now()
    job.save(update_fields=['state', 'confirmed_at'])
    logger.info('roster: import %s confirmed for request %s', job.pk, req.pk)
    return JsonResponse({'import': import_dict(job)})
