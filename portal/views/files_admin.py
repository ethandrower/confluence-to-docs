"""Admin file-sharing endpoints (Phase 1): company switcher, per-company view,
and a "download all" zip. Gated to portal admins via require_portal_admin.
Read-only on the admin side in V1 (no upload/rename/delete) for audit-trail
simplicity."""
import io
import json
import zipfile

from django.http import JsonResponse, HttpResponse, HttpResponseRedirect
from django.utils.dateparse import parse_datetime, parse_date
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from portal import file_storage
from portal.decorators import require_portal_admin
from portal.models import Company, Bucket, SharedFile
from portal.serializers import BucketSerializer
from portal.views.files import get_general_bucket, log_activity


def _parse_due(value):
    """Accept an ISO datetime or a plain YYYY-MM-DD date; return aware datetime or None."""
    if not value:
        return None
    dt = parse_datetime(value)
    if dt is None:
        d = parse_date(value)
        if d:
            dt = timezone.datetime(d.year, d.month, d.day)
    if dt and timezone.is_naive(dt):
        dt = timezone.make_aware(dt, timezone.get_current_timezone())
    return dt


@require_portal_admin
def companies(request):
    out = []
    for c in Company.objects.all().order_by('name'):
        file_count = SharedFile.objects.filter(
            company=c, deleted_at__isnull=True, state=SharedFile.STATE_READY,
        ).count()
        open_requests = Bucket.objects.filter(
            company=c, kind=Bucket.KIND_REQUEST,
        ).exclude(status='complete').count()
        out.append({
            'id': c.id, 'name': c.name,
            'file_count': file_count, 'open_request_count': open_requests,
        })
    return JsonResponse({'companies': out})


@require_portal_admin
def company_files(request, company_id):
    company = Company.objects.filter(id=company_id).first()
    if not company:
        return JsonResponse({'error': 'Company not found.'}, status=404)
    get_general_bucket(company)
    buckets = Bucket.objects.filter(company=company)
    return JsonResponse({
        'company': {'id': company.id, 'name': company.name},
        'buckets': BucketSerializer(buckets, many=True).data,
    })


@require_portal_admin
def company_download_all(request, company_id):
    company = Company.objects.filter(id=company_id).first()
    if not company:
        return JsonResponse({'error': 'Company not found.'}, status=404)
    files = SharedFile.objects.filter(
        company=company, deleted_at__isnull=True, state=SharedFile.STATE_READY,
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        import requests
        for f in files:
            try:
                data = requests.get(file_storage.presign_get(f.storage_key), timeout=120).content
                zf.writestr(f.original_name, data)
            except Exception:
                continue
    log_activity(company, 'download', actor=request.portal_user, bulk=True, count=files.count())
    resp = HttpResponse(buf.getvalue(), content_type='application/zip')
    resp['Content-Disposition'] = f'attachment; filename="{company.name}-files.zip"'
    return resp


@csrf_exempt
@require_portal_admin
@require_http_methods(['POST'])
def create_request(request):
    """CSM/admin creates a request bucket asking a company for specific docs."""
    data = json.loads(request.body or '{}')
    company = Company.objects.filter(id=data.get('company_id')).first()
    if not company:
        return JsonResponse({'error': 'Company not found.'}, status=404)
    title = (data.get('title') or '').strip()
    if not title:
        return JsonResponse({'error': 'Title required.'}, status=400)
    status = data.get('status') or 'open'
    if status not in ('open', 'partial', 'complete'):
        status = 'open'
    b = Bucket.objects.create(
        company=company, kind=Bucket.KIND_REQUEST, title=title,
        description=data.get('description', ''), due_at=_parse_due(data.get('due_at')),
        status=status, requested_by=request.portal_user,
    )
    log_activity(company, 'request_created', actor=request.portal_user, bucket=b, title=title)
    return JsonResponse(BucketSerializer(b).data, status=201)


@csrf_exempt
@require_portal_admin
@require_http_methods(['PATCH', 'DELETE'])
def update_request(request, bucket_id):
    b = Bucket.objects.filter(id=bucket_id, kind=Bucket.KIND_REQUEST).first()
    if not b:
        return JsonResponse({'error': 'Request not found.'}, status=404)
    if request.method == 'DELETE':
        log_activity(b.company, 'request_deleted', actor=request.portal_user, title=b.title)
        b.delete()
        return JsonResponse({'ok': True})
    data = json.loads(request.body or '{}')
    if 'title' in data:
        title = (data.get('title') or '').strip()
        if not title:
            return JsonResponse({'error': 'Title required.'}, status=400)
        b.title = title
    if 'description' in data:
        b.description = data.get('description', '')
    if 'due_at' in data:
        b.due_at = _parse_due(data.get('due_at'))
    if 'status' in data and data.get('status') in ('open', 'partial', 'complete'):
        b.status = data.get('status')
    b.save()
    return JsonResponse(BucketSerializer(b).data)


@require_portal_admin
def inbox(request):
    """Cross-client 'to-process' inbox: recent uploads across ALL companies.

    Available to all CiteMed staff (owner/admin). Newest first. Optional
    filters: ?status=unprocessed|all (default unprocessed), ?company=<id>,
    ?limit=<n> (default 100, max 300).
    """
    status = request.GET.get('status', 'unprocessed')
    qs = (
        SharedFile.objects
        .filter(deleted_at__isnull=True, state=SharedFile.STATE_READY)
        .select_related('company', 'bucket', 'uploaded_by')
    )
    if status == 'unprocessed':
        qs = qs.filter(processed=False)
    company_id = request.GET.get('company')
    if company_id:
        qs = qs.filter(company_id=company_id)
    try:
        limit = min(int(request.GET.get('limit', 100)), 300)
    except (TypeError, ValueError):
        limit = 100

    items = []
    for f in qs.order_by('-uploaded_at')[:limit]:
        items.append({
            'id': f.id,
            'original_name': f.original_name,
            'size_bytes': f.size_bytes,
            'uploaded_at': f.uploaded_at.isoformat(),
            'uploaded_by_name': (f.uploaded_by.name or f.uploaded_by.email) if f.uploaded_by else None,
            'company': {'id': f.company_id, 'name': f.company.name},
            'bucket': {'id': f.bucket_id, 'title': f.bucket.title, 'kind': f.bucket.kind},
            'processed': f.processed,
        })
    unprocessed_total = SharedFile.objects.filter(
        deleted_at__isnull=True, state=SharedFile.STATE_READY, processed=False,
    ).count()
    return JsonResponse({'items': items, 'unprocessed_total': unprocessed_total})


@csrf_exempt
@require_portal_admin
@require_http_methods(['PATCH'])
def set_processed(request, file_id):
    f = SharedFile.objects.filter(id=file_id, deleted_at__isnull=True).first()
    if not f:
        return JsonResponse({'error': 'File not found.'}, status=404)
    data = json.loads(request.body or '{}')
    processed = bool(data.get('processed', True))
    from django.utils import timezone
    f.processed = processed
    f.processed_at = timezone.now() if processed else None
    f.processed_by = request.portal_user if processed else None
    f.save(update_fields=['processed', 'processed_at', 'processed_by'])
    log_activity(f.company, 'processed' if processed else 'unprocessed',
                 actor=request.portal_user, file=f, name=f.original_name)
    return JsonResponse({'ok': True, 'processed': f.processed})


@require_portal_admin
def admin_file_download(request, file_id):
    """Presigned download of any company's file (admin-scoped)."""
    f = SharedFile.objects.filter(id=file_id, deleted_at__isnull=True).first()
    if not f:
        return JsonResponse({'error': 'File not found.'}, status=404)
    from django.http import HttpResponseRedirect
    url = file_storage.presign_get(f.storage_key, download_name=f.original_name)
    log_activity(f.company, 'download', actor=request.portal_user, file=f, name=f.original_name)
    return HttpResponseRedirect(url)
