"""Admin API: manage Companies and PortalUsers (TG-672).

All endpoints require an admin (portal role 'admin' or Django superuser) via
`require_portal_admin`. JSON in/out, consistent with the rest of the portal API.
"""
import json
import subprocess
import sys

from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from portal.decorators import require_portal_admin
from portal.models import Company, PortalUser


def _company_dict(c):
    return {
        'id': c.id,
        'name': c.name,
        'contract_end_date': c.contract_end_date.isoformat() if c.contract_end_date else None,
        'user_count': c.users.count(),
    }


def _user_dict(u):
    return {
        'id': u.id,
        'email': u.email,
        'name': u.name,
        'role': u.role,
        'access_enabled': u.access_enabled,
        'company_id': u.company_id,
        'company_name': u.company.name if u.company else None,
        'last_login': u.last_login.isoformat() if u.last_login else None,
        'created_at': u.created_at.isoformat() if u.created_at else None,
    }


def _parse(request):
    try:
        return json.loads(request.body or '{}')
    except Exception:
        return None


# ── Companies ──────────────────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(['GET', 'POST'])
@require_portal_admin
def companies(request):
    if request.method == 'GET':
        rows = Company.objects.all().order_by('name')
        return JsonResponse({'companies': [_company_dict(c) for c in rows]})

    data = _parse(request)
    if data is None:
        return JsonResponse({'error': 'Invalid request'}, status=400)
    name = (data.get('name') or '').strip()
    if not name:
        return JsonResponse({'error': 'Company name is required'}, status=400)
    if Company.objects.filter(name__iexact=name).exists():
        return JsonResponse({'error': 'A company with that name already exists'}, status=409)
    c = Company.objects.create(name=name, contract_end_date=data.get('contract_end_date') or None)
    return JsonResponse({'company': _company_dict(c)}, status=201)


@csrf_exempt
@require_http_methods(['PATCH', 'DELETE'])
@require_portal_admin
def company_detail(request, company_id):
    c = Company.objects.filter(pk=company_id).first()
    if not c:
        return JsonResponse({'error': 'Company not found'}, status=404)

    if request.method == 'DELETE':
        c.delete()  # users.company is SET_NULL — users are kept, just unlinked
        return JsonResponse({'ok': True})

    data = _parse(request)
    if data is None:
        return JsonResponse({'error': 'Invalid request'}, status=400)
    if 'name' in data:
        name = (data['name'] or '').strip()
        if not name:
            return JsonResponse({'error': 'Company name is required'}, status=400)
        if Company.objects.filter(name__iexact=name).exclude(pk=c.pk).exists():
            return JsonResponse({'error': 'A company with that name already exists'}, status=409)
        c.name = name
    if 'contract_end_date' in data:
        c.contract_end_date = data['contract_end_date'] or None
    c.save()
    return JsonResponse({'company': _company_dict(c)})


# ── Users ────────────────────────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(['GET', 'POST'])
@require_portal_admin
def users(request):
    if request.method == 'GET':
        rows = PortalUser.objects.select_related('company').order_by('email')
        return JsonResponse({'users': [_user_dict(u) for u in rows]})

    data = _parse(request)
    if data is None:
        return JsonResponse({'error': 'Invalid request'}, status=400)
    email = (data.get('email') or '').strip().lower()
    if not email or '@' not in email:
        return JsonResponse({'error': 'A valid email is required'}, status=400)
    if PortalUser.objects.filter(email__iexact=email).exists():
        return JsonResponse({'error': 'A user with that email already exists'}, status=409)

    role = data.get('role') if data.get('role') in (PortalUser.ROLE_ADMIN, PortalUser.ROLE_CUSTOMER) else PortalUser.ROLE_CUSTOMER
    company = _resolve_company(data.get('company_id'))
    u = PortalUser.objects.create(
        email=email,
        name=(data.get('name') or '').strip(),
        role=role,
        company=company,
        access_enabled=bool(data.get('access_enabled', True)),
    )
    return JsonResponse({'user': _user_dict(u)}, status=201)


@csrf_exempt
@require_http_methods(['PATCH', 'DELETE'])
@require_portal_admin
def user_detail(request, user_id):
    u = PortalUser.objects.filter(pk=user_id).select_related('company').first()
    if not u:
        return JsonResponse({'error': 'User not found'}, status=404)

    if request.method == 'DELETE':
        if u.pk == request.portal_user.pk:
            return JsonResponse({'error': "You can't remove your own account"}, status=400)
        u.delete()
        return JsonResponse({'ok': True})

    data = _parse(request)
    if data is None:
        return JsonResponse({'error': 'Invalid request'}, status=400)
    if 'name' in data:
        u.name = (data['name'] or '').strip()
    if 'role' in data and data['role'] in (PortalUser.ROLE_ADMIN, PortalUser.ROLE_CUSTOMER):
        u.role = data['role']
    if 'access_enabled' in data:
        # Guard: don't let an admin lock themselves out.
        if u.pk == request.portal_user.pk and not data['access_enabled']:
            return JsonResponse({'error': "You can't disable your own access"}, status=400)
        u.access_enabled = bool(data['access_enabled'])
    if 'company_id' in data:
        u.company = _resolve_company(data['company_id'])
    u.save()
    return JsonResponse({'user': _user_dict(u)})


def _resolve_company(company_id):
    if not company_id:
        return None
    return Company.objects.filter(pk=company_id).first()


# ── Sync from Confluence ─────────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(['POST'])
@require_portal_admin
def sync_docs(request):
    """Kick off `manage.py sync_confluence` detached; returns immediately."""
    try:
        subprocess.Popen(
            [sys.executable, 'manage.py', 'sync_confluence'],
            cwd=str(settings.BASE_DIR),
            start_new_session=True,
        )
    except Exception as e:
        return JsonResponse({'error': f'Could not start sync: {e}'}, status=500)
    return JsonResponse({'ok': True, 'message': 'Sync started — running in the background. Refresh docs in a minute.'})
