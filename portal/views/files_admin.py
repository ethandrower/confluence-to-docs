"""Admin file-sharing endpoints (Phase 1): company switcher, per-company view,
and a "download all" zip. Gated to portal admins via require_portal_admin.
Read-only on the admin side in V1 (no upload/rename/delete) for audit-trail
simplicity."""
import json
import tempfile
import zipfile

from django.db import transaction
from django.http import JsonResponse, FileResponse, HttpResponseRedirect
from django.utils.dateparse import parse_datetime, parse_date
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

# Bounds for the "download all" export so one large company can't OOM a worker.
_ZIP_MAX_FILES = 1000
_ZIP_MAX_BYTES = 3 * 1024 ** 3  # 3 GB total
_ZIP_SPOOL = 64 * 1024 * 1024   # keep ≤64 MB in RAM, then spill to disk

from portal import file_storage, file_notify
from portal.decorators import require_portal_admin
from portal.models import Company, Bucket, SharedFile, ChecklistItem
from portal.serializers import BucketSerializer, SharedFileSerializer, ChecklistItemSerializer
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
        'buckets': BucketSerializer(buckets, many=True, context={'staff': True}).data,
    })


@require_portal_admin
def company_download_all(request, company_id):
    """Stream a zip of a company's files. Written to a disk-backed temp file
    (not held twice in RAM), bounded by file count + total bytes, and any file
    that can't be fetched is recorded in an UNAVAILABLE.txt manifest so the
    export is never silently incomplete."""
    import requests

    company = Company.objects.filter(id=company_id).first()
    if not company:
        return JsonResponse({'error': 'Company not found.'}, status=404)
    files = SharedFile.objects.filter(
        company=company, deleted_at__isnull=True, state=SharedFile.STATE_READY,
    )[:_ZIP_MAX_FILES]

    tmp = tempfile.SpooledTemporaryFile(max_size=_ZIP_SPOOL)
    zipped, total, failed, used_names = 0, 0, [], set()
    with zipfile.ZipFile(tmp, 'w', zipfile.ZIP_DEFLATED) as zf:
        for f in files:
            if total >= _ZIP_MAX_BYTES:
                failed.append(f'{f.original_name} (export size limit reached)')
                continue
            try:
                r = requests.get(file_storage.presign_get(f.storage_key), timeout=120)
                r.raise_for_status()
                data = r.content
            except Exception:
                failed.append(f.original_name)
                continue
            total += len(data)
            # De-duplicate names so same-named files don't clobber each other.
            name = f.original_name
            if name in used_names:
                stem, _, ext = name.rpartition('.')
                name = f'{stem}-{f.id}.{ext}' if ext else f'{name}-{f.id}'
            used_names.add(name)
            zf.writestr(name, data)
            zipped += 1
        if failed:
            zf.writestr('UNAVAILABLE.txt',
                        'These files could not be included in this export:\n\n' + '\n'.join(failed))

    size = tmp.tell()
    tmp.seek(0)
    log_activity(company, 'download', actor=request.portal_user, bulk=True,
                 count=zipped, failed=len(failed))
    resp = FileResponse(tmp, content_type='application/zip')
    resp['Content-Disposition'] = f'attachment; filename="{company.name}-files.zip"'
    resp['Content-Length'] = str(size)
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
    try:
        file_notify.notify_request_created(b)
    except Exception:
        pass
    return JsonResponse(BucketSerializer(b, context={'staff': True}).data, status=201)


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


REVIEW_STATES = ('pending', 'review', 'approved', 'revision')


@csrf_exempt
@require_portal_admin
@require_http_methods(['PATCH'])
def set_review(request, file_id):
    """Set a file's review status + notes. Emails the customer on 'revision'."""
    f = SharedFile.objects.filter(id=file_id, deleted_at__isnull=True).select_related('company').first()
    if not f:
        return JsonResponse({'error': 'File not found.'}, status=404)
    data = json.loads(request.body or '{}')
    from django.utils import timezone

    new_status = data.get('review_status')
    status_changed = new_status in REVIEW_STATES and new_status != f.review_status
    notes_changed = 'notes' in data and (data.get('notes') or '').strip() != f.review_notes
    if not status_changed and not notes_changed:
        return JsonResponse(SharedFileSerializer(f, context={'staff': True}).data)

    if status_changed:
        f.review_status = new_status
    if 'notes' in data:
        f.review_notes = (data.get('notes') or '').strip()
    f.reviewed_by = request.portal_user
    f.reviewed_at = timezone.now()
    f.save(update_fields=['review_status', 'review_notes', 'reviewed_by', 'reviewed_at'])

    if status_changed:
        log_activity(f.company, 'status_change', actor=request.portal_user, file=f, to=f.review_status)
        if f.review_status == 'revision':
            try:
                file_notify.notify_revision(f)
            except Exception:
                pass
    return JsonResponse(SharedFileSerializer(f, context={'staff': True}).data)


@csrf_exempt
@require_portal_admin
@require_http_methods(['POST'])
def create_checklist_item(request):
    data = json.loads(request.body or '{}')
    bucket = Bucket.objects.filter(id=data.get('bucket_id'), kind=Bucket.KIND_REQUEST).first()
    if not bucket:
        return JsonResponse({'error': 'Request bucket not found.'}, status=404)
    text = (data.get('text') or '').strip()
    if not text:
        return JsonResponse({'error': 'Text required.'}, status=400)
    with transaction.atomic():
        position = bucket.checklist.select_for_update().count()
        item = ChecklistItem.objects.create(
            bucket=bucket, text=text, position=position, created_by=request.portal_user,
        )
    return JsonResponse(ChecklistItemSerializer(item).data, status=201)


@csrf_exempt
@require_portal_admin
@require_http_methods(['PATCH', 'DELETE'])
def checklist_item(request, item_id):
    item = ChecklistItem.objects.select_related('bucket').filter(id=item_id).first()
    if not item:
        return JsonResponse({'error': 'Item not found.'}, status=404)
    if request.method == 'DELETE':
        item.delete()
        return JsonResponse({'ok': True})
    data = json.loads(request.body or '{}')
    if 'text' in data:
        text = (data.get('text') or '').strip()
        if not text:
            return JsonResponse({'error': 'Text required.'}, status=400)
        item.text = text
    if 'linked_file_id' in data:
        fid = data.get('linked_file_id')
        if fid is None:
            item.linked_file = None
        else:
            f = SharedFile.objects.filter(
                id=fid, company_id=item.bucket.company_id, deleted_at__isnull=True,
            ).first()
            if not f:
                return JsonResponse({'error': 'File not found in this company.'}, status=404)
            item.linked_file = f
    item.save()
    return JsonResponse(ChecklistItemSerializer(item).data)


@require_portal_admin
def admin_file_download(request, file_id):
    """Presigned download of any company's file (admin-scoped)."""
    f = SharedFile.objects.filter(id=file_id, deleted_at__isnull=True).first()
    if not f:
        return JsonResponse({'error': 'File not found.'}, status=404)
    url = file_storage.presign_get(f.storage_key, download_name=f.original_name)
    log_activity(f.company, 'download', actor=request.portal_user, file=f, name=f.original_name)
    return HttpResponseRedirect(url)


@require_portal_admin
def admin_file_view(request, file_id):
    """Inline preview (PDF/image) of any company's file (admin-scoped). Content
    type is derived server-side from the extension; non-previewable types fall
    back to a download so untrusted content can't render inline in the admin's
    origin (stored-XSS guard)."""
    f = SharedFile.objects.filter(id=file_id, deleted_at__isnull=True).first()
    if not f:
        return JsonResponse({'error': 'File not found.'}, status=404)
    from portal.views.files import inline_mime
    mime = inline_mime(f.original_name)
    if not mime:
        return HttpResponseRedirect(file_storage.presign_get(f.storage_key, download_name=f.original_name))
    return HttpResponseRedirect(file_storage.presign_view(f.storage_key, mime))
