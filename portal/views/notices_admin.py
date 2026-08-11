"""Agent-side notice management (#49) — raise, edit and retire a notice without
a deploy, which is the whole point: an incident is in progress when you need it.

Gated to portal admins. Retiring sets `retired_at` rather than deleting, so the
customer-visible history survives the incident being resolved.
"""
import json

from django.http import JsonResponse
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.views.decorators.http import require_http_methods

from portal.decorators import require_portal_admin
from portal.models import Company, SiteNotice
from portal.views.notices import notice_dict

_LEVELS = {choice for choice, _ in SiteNotice.LEVEL_CHOICES}


def admin_notice_dict(notice):
    """Adds what an agent needs and a customer must not see: who raised it, and
    which companies it is scoped to."""
    return {
        **notice_dict(notice),
        'company_ids': [c.id for c in notice.companies.all()],
        'created_by': notice.created_by.email if notice.created_by else None,
        'created_at': notice.created_at.isoformat(),
    }


class ValidationError(Exception):
    """Carries a client-safe message; the caller turns it into a 400."""


def _parse_window(payload, current_start=None, current_end=None):
    """Resolve starts_at/ends_at from a payload, keeping current values for keys
    the caller didn't send (so a PATCH of just the message doesn't clear them)."""
    starts_at = current_start
    if 'starts_at' in payload:
        starts_at = _parse_dt(payload['starts_at'], 'starts_at') or timezone.now()

    ends_at = current_end
    if 'ends_at' in payload:
        # Explicit null is how the UI reopens an incident with no known end.
        ends_at = _parse_dt(payload['ends_at'], 'ends_at')

    if starts_at and ends_at and ends_at <= starts_at:
        # Accepting this would store a notice that can never appear.
        raise ValidationError('ends_at must be after starts_at')
    return starts_at, ends_at


def _parse_dt(value, field):
    if value in (None, ''):
        return None
    parsed = parse_datetime(value)
    if parsed is None:
        raise ValidationError(f'{field} must be an ISO 8601 datetime')
    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed, timezone.get_current_timezone())
    return parsed


def _clean_message(payload, current=None):
    if 'message' not in payload:
        return current
    message = (payload.get('message') or '').strip()
    if not message:
        # A blank banner is worse than no banner: it takes up the same space and
        # says nothing.
        raise ValidationError('message is required')
    return message


def _clean_level(payload, current=SiteNotice.LEVEL_INFO):
    if 'level' not in payload:
        return current
    level = payload['level']
    if level not in _LEVELS:
        raise ValidationError(f'level must be one of {sorted(_LEVELS)}')
    return level


@require_portal_admin
@require_http_methods(['GET', 'POST'])
def notices(request):
    if request.method == 'GET':
        # Retired ones included: managing history is part of the job, and an
        # agent needs to see what was said before to keep wording consistent.
        rows = SiteNotice.objects.all().prefetch_related('companies').select_related('created_by')
        return JsonResponse({'notices': [admin_notice_dict(n) for n in rows]})

    try:
        payload = json.loads(request.body or '{}')
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    try:
        message = _clean_message(payload)
        if message is None:
            raise ValidationError('message is required')
        level = _clean_level(payload)
        starts_at, ends_at = _parse_window(payload, current_start=timezone.now())
    except ValidationError as exc:
        return JsonResponse({'error': str(exc)}, status=400)

    notice = SiteNotice.objects.create(
        level=level,
        message=message,
        link_url=(payload.get('link_url') or '').strip(),
        link_label=(payload.get('link_label') or '').strip(),
        starts_at=starts_at,
        ends_at=ends_at,
        created_by=request.portal_user,
    )
    _set_companies(notice, payload)
    return JsonResponse({'notice': admin_notice_dict(notice)}, status=201)


@require_portal_admin
@require_http_methods(['PATCH', 'DELETE'])
def notice_detail(request, notice_id):
    notice = SiteNotice.objects.filter(pk=notice_id).first()
    if notice is None:
        return JsonResponse({'error': 'Not found'}, status=404)

    if request.method == 'DELETE':
        # Retire, never delete — the customer-visible history depends on the row
        # surviving.
        notice.retire()
        return JsonResponse({'notice': admin_notice_dict(notice)})

    try:
        payload = json.loads(request.body or '{}')
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    try:
        notice.message = _clean_message(payload, current=notice.message)
        notice.level = _clean_level(payload, current=notice.level)
        notice.starts_at, notice.ends_at = _parse_window(
            payload, current_start=notice.starts_at, current_end=notice.ends_at)
    except ValidationError as exc:
        return JsonResponse({'error': str(exc)}, status=400)

    if 'link_url' in payload:
        notice.link_url = (payload.get('link_url') or '').strip()
    if 'link_label' in payload:
        notice.link_label = (payload.get('link_label') or '').strip()
    if 'retired_at' in payload and payload['retired_at'] is None:
        # Un-retire, for the case where an incident was closed too early.
        notice.retired_at = None

    notice.save()
    _set_companies(notice, payload)
    return JsonResponse({'notice': admin_notice_dict(notice)})


def _set_companies(notice, payload):
    """Absent key leaves scoping alone; an empty list means "everyone"."""
    if 'company_ids' not in payload:
        return
    ids = payload.get('company_ids') or []
    notice.companies.set(Company.objects.filter(id__in=ids))
