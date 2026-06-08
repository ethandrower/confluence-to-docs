"""Customer + shared file-sharing endpoints (Phase 1).

All endpoints are company-scoped: a customer only ever sees/touches files
belonging to their own PortalUser.company. Uploads go directly browser→S3 via
a presigned PUT; Django issues the presigned URL and records metadata, never
streaming the bytes itself. Every action is written to FileActivity.
"""
import json
import logging

from django.conf import settings
from django.http import JsonResponse, HttpResponseRedirect
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from portal import file_storage
from portal.decorators import require_portal_user
from portal.models import Bucket, SharedFile, FileActivity
from portal.rate_limit import is_rate_limited
from portal.serializers import BucketSerializer

logger = logging.getLogger(__name__)


def get_general_bucket(company):
    """Idempotent per-company 'General uploads' bucket."""
    bucket, _ = Bucket.objects.get_or_create(
        company=company, kind=Bucket.KIND_GENERAL,
        defaults={'title': 'General uploads', 'status': 'general'},
    )
    return bucket


def log_activity(company, action, *, actor=None, file=None, bucket=None, **detail):
    """Append to the audit trail. Best-effort — never blocks the core action."""
    try:
        FileActivity.objects.create(
            company=company, action=action, actor=actor,
            file=file, bucket=bucket, detail=detail,
        )
    except Exception as e:
        logger.warning("log_activity(%s) failed: %s", action, e)


def _ext_ok(name):
    ext = name.rsplit('.', 1)[-1].lower() if '.' in name else ''
    return ext in settings.FILESHARE_ALLOWED_EXT


def _own_file(request, file_id):
    # Route through the scoped manager so isolation lives in one place.
    return SharedFile.for_user(request.portal_user).filter(id=file_id).first()


# ── Listing ──────────────────────────────────────────────────────────────
@require_portal_user
@require_http_methods(['GET'])
def buckets_list(request):
    user = request.portal_user
    if not user.company_id:
        return JsonResponse({'buckets': []})
    get_general_bucket(user.company)  # ensure it exists
    buckets = Bucket.objects.filter(company_id=user.company_id)
    return JsonResponse({'buckets': BucketSerializer(buckets, many=True).data})


# ── Upload (presigned PUT) ────────────────────────────────────────────────
@csrf_exempt
@require_portal_user
@require_http_methods(['POST'])
def upload_init(request):
    user = request.portal_user
    if not user.company_id:
        return JsonResponse({'error': 'No company is associated with your account.'}, status=403)
    # Bound how fast one account can mint upload slots (the rest of auth is
    # rate-limited; this endpoint creates rows + presigned URLs).
    if is_rate_limited('file-upload-init', str(user.id), 120, 3600):
        return JsonResponse({'error': 'Too many uploads right now — please slow down.'}, status=429)
    data = json.loads(request.body or '{}')
    name = (data.get('name') or '').strip()
    size = int(data.get('size') or 0)
    mime = (data.get('mime') or '').strip()
    if not name:
        return JsonResponse({'error': 'Filename required.'}, status=400)
    if not _ext_ok(name):
        return JsonResponse({'error': 'File type not allowed.'}, status=400)
    if size and size > settings.FILESHARE_MAX_BYTES:
        return JsonResponse({'error': 'File exceeds the size limit.'}, status=400)

    bucket_id = data.get('bucket_id')
    if bucket_id:
        bucket = Bucket.objects.filter(id=bucket_id, company_id=user.company_id).first()
        if not bucket:
            return JsonResponse({'error': 'Bucket not found.'}, status=404)
    else:
        bucket = get_general_bucket(user.company)

    f = SharedFile.objects.create(
        bucket=bucket, company_id=user.company_id, uploaded_by=user,
        original_name=name, storage_key='', mime_type=mime,
        size_bytes=size or None, state=SharedFile.STATE_UPLOADING,
    )
    f.storage_key = file_storage.build_key(user.company_id, bucket.id, f.id, name)
    f.save(update_fields=['storage_key'])
    return JsonResponse({
        'file_id': f.id,
        'upload_url': file_storage.presign_put(f.storage_key, mime),
    })


@csrf_exempt
@require_portal_user
@require_http_methods(['POST'])
def upload_complete(request):
    user = request.portal_user
    data = json.loads(request.body or '{}')
    f = SharedFile.for_user(user).filter(id=data.get('file_id')).first()
    if not f:
        return JsonResponse({'error': 'File not found.'}, status=404)
    size = file_storage.head_size(f.storage_key)
    if size is None:
        return JsonResponse({'error': 'Upload not found in storage.'}, status=400)
    if size > settings.FILESHARE_MAX_BYTES:
        file_storage.delete_object(f.storage_key)
        f.delete()
        return JsonResponse({'error': 'File exceeds the size limit.'}, status=400)
    # Reject content that contradicts its extension (HTML-as-PDF, etc.).
    if not file_storage.signature_ok(f.storage_key, f.original_name):
        file_storage.delete_object(f.storage_key)
        f.delete()
        return JsonResponse({'error': "File content doesn't match its type."}, status=400)
    f.size_bytes = size
    f.state = SharedFile.STATE_READY
    f.save(update_fields=['size_bytes', 'state'])
    log_activity(user.company, 'upload', actor=user, file=f, bucket=f.bucket,
                 name=f.original_name, size=size)
    try:
        from portal import file_notify
        file_notify.notify_upload(f)
    except Exception:
        pass
    return JsonResponse({'ok': True, 'file_id': f.id})


# ── Rename / soft-delete / download ───────────────────────────────────────
@csrf_exempt
@require_portal_user
@require_http_methods(['PATCH', 'DELETE'])
def file_detail(request, file_id):
    f = _own_file(request, file_id)
    if not f:
        return JsonResponse({'error': 'File not found.'}, status=404)
    if request.method == 'DELETE':
        f.deleted_at = timezone.now()
        f.save(update_fields=['deleted_at'])
        log_activity(request.portal_user.company, 'delete', actor=request.portal_user,
                     file=f, bucket=f.bucket, name=f.original_name)
        return JsonResponse({'ok': True})
    data = json.loads(request.body or '{}')
    new_name = (data.get('name') or '').strip()
    if not new_name:
        return JsonResponse({'error': 'Name required.'}, status=400)
    old = f.original_name
    f.original_name = new_name
    f.save(update_fields=['original_name'])
    log_activity(request.portal_user.company, 'rename', actor=request.portal_user,
                 file=f, old_name=old, new_name=new_name)
    return JsonResponse({'ok': True})


@require_portal_user
@require_http_methods(['GET'])
def file_download(request, file_id):
    f = _own_file(request, file_id)
    if not f:
        return JsonResponse({'error': 'File not found.'}, status=404)
    url = file_storage.presign_get(f.storage_key, download_name=f.original_name)
    log_activity(request.portal_user.company, 'download', actor=request.portal_user,
                 file=f, name=f.original_name)
    return HttpResponseRedirect(url)


# Only these types are ever served *inline*. The content-type is derived from
# the (validated) extension, NOT the client-supplied mime — otherwise a file
# uploaded as .pdf but declared text/html could execute inline when previewed
# (stored XSS). Anything else is served as a download instead.
_INLINE_MIME = {
    'pdf': 'application/pdf', 'png': 'image/png', 'jpg': 'image/jpeg',
    'jpeg': 'image/jpeg', 'gif': 'image/gif', 'webp': 'image/webp',
}


def inline_mime(name):
    ext = name.rsplit('.', 1)[-1].lower() if '.' in name else ''
    return _INLINE_MIME.get(ext)


@require_portal_user
@require_http_methods(['GET'])
def file_view(request, file_id):
    """Inline preview (PDF/image). For non-previewable types, falls back to a
    safe download so nothing untrusted is ever rendered inline."""
    f = _own_file(request, file_id)
    if not f:
        return JsonResponse({'error': 'File not found.'}, status=404)
    mime = inline_mime(f.original_name)
    if not mime:
        return HttpResponseRedirect(file_storage.presign_get(f.storage_key, download_name=f.original_name))
    return HttpResponseRedirect(file_storage.presign_view(f.storage_key, mime))
