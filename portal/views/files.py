"""Customer + shared file-sharing endpoints (Phase 1).

All endpoints are company-scoped: a customer only ever sees/touches files
belonging to their own PortalUser.company. Uploads go directly browser→S3 via
a presigned PUT; Django issues the presigned URL and records metadata, never
streaming the bytes itself. Every action is written to FileActivity.
"""
import json
import logging

from django.conf import settings
from django.db import transaction
from django.http import JsonResponse, HttpResponseRedirect
from django.utils import timezone
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
    # `allowed_ext` travels with the listing so the uploader can report what a
    # dropped folder will skip BEFORE uploading it. Duplicating the list in JS
    # would let the two drift, and the drift would show up as a file the UI
    # promised to take and the server then refused.
    allowed = sorted(settings.FILESHARE_ALLOWED_EXT)
    if not user.company_id:
        return JsonResponse({'buckets': [], 'allowed_ext': allowed})
    get_general_bucket(user.company)  # ensure it exists
    buckets = Bucket.objects.filter(company_id=user.company_id)
    return JsonResponse({
        'buckets': BucketSerializer(buckets, many=True).data,
        'allowed_ext': allowed,
    })


# ── Folders ───────────────────────────────────────────────────────────────
# Customers create and arrange these themselves; that's the point of the
# feature. Requests and the General uploads root are staff/system concepts and
# stay outside the tree — see the Bucket docstring.
MAX_FOLDER_TITLE = 120


def _resolve_parent(user, parent_id):
    """Resolve a parent folder for the acting user, or explain why not.

    Returns (parent_or_None, error_response_or_None). Everything goes through
    Bucket.for_user, so a parent id belonging to another company is simply not
    found — the move never sees it.
    """
    if parent_id in (None, '', 0):
        return None, None
    parent = Bucket.for_user(user).filter(id=parent_id).first()
    if not parent:
        return None, JsonResponse({'error': 'Folder not found.'}, status=404)
    if parent.kind != Bucket.KIND_FOLDER:
        # Refusing this is what keeps a document request from being buried
        # inside someone's folder tree.
        return None, JsonResponse(
            {'error': 'Only folders can contain other folders.'}, status=400)
    return parent, None


def _clean_title(raw):
    title = (raw or '').strip()
    if not title:
        return None, JsonResponse({'error': 'Folder name required.'}, status=400)
    if len(title) > MAX_FOLDER_TITLE:
        return None, JsonResponse(
            {'error': f'Folder name must be {MAX_FOLDER_TITLE} characters or fewer.'},
            status=400)
    if '/' in title:
        return None, JsonResponse(
            {'error': 'Folder names can’t contain “/”.'}, status=400)
    return title, None


def _duplicate_sibling(user, title, parent, exclude_id=None):
    """A second "Reports" beside the first is a usability trap, not a feature."""
    qs = Bucket.for_user(user).filter(
        kind=Bucket.KIND_FOLDER, parent=parent, title__iexact=title)
    if exclude_id:
        qs = qs.exclude(id=exclude_id)
    return qs.exists()


@require_portal_user
@require_http_methods(['POST'])
def folder_create(request):
    user = request.portal_user
    if not user.company_id:
        return JsonResponse({'error': 'No company is associated with your account.'}, status=403)
    data = json.loads(request.body or '{}')
    title, err = _clean_title(data.get('title'))
    if err:
        return err
    parent, err = _resolve_parent(user, data.get('parent_id'))
    if err:
        return err
    if parent and parent.level + 1 > Bucket.MAX_DEPTH:
        return JsonResponse(
            {'error': f'Folders can only be {Bucket.MAX_DEPTH} levels deep.'}, status=400)
    if _duplicate_sibling(user, title, parent):
        return JsonResponse(
            {'error': 'A folder with that name is already here.'}, status=409)
    folder = Bucket.objects.create(
        company_id=user.company_id, kind=Bucket.KIND_FOLDER, title=title,
        parent=parent, created_by=user, status='general',
    )
    log_activity(user.company, 'folder_create', actor=user, bucket=folder,
                 title=title, parent_id=parent.id if parent else None)
    return JsonResponse({'folder': BucketSerializer(folder).data}, status=201)


# A dropped folder tree is bounded so one gesture can't mint thousands of rows.
MAX_ENSURE_PATHS = 500


@require_portal_user
@require_http_methods(['POST'])
def folders_ensure_path(request):
    """Resolve each relative path to a folder id, creating what's missing.

    Folder upload needs this to be one server-side call. A dropped tree is N
    files each carrying a path like "2024/q1", and walking that client-side
    would be a round trip per segment *and* racy: two files in the same new
    subfolder would each try to create it and one would lose to the duplicate
    check. Deciding reuse-or-create exactly once per path, in a transaction,
    is what makes the tree come out right.

    Returns {path: bucket_id}. The empty path maps to the root the upload was
    dropped on, so callers can treat loose files and nested ones identically.
    """
    user = request.portal_user
    if not user.company_id:
        return JsonResponse({'error': 'No company is associated with your account.'}, status=403)

    data = json.loads(request.body or '{}')
    root, err = _resolve_parent(user, data.get('root_id'))
    if err:
        return err

    paths = data.get('paths') or []
    if not isinstance(paths, list):
        return JsonResponse({'error': 'paths must be a list.'}, status=400)
    if len(paths) > MAX_ENSURE_PATHS:
        return JsonResponse(
            {'error': f'Too many folders at once (limit {MAX_ENSURE_PATHS}).'}, status=400)

    base_level = root.level if root else 0
    resolved = {'': root.id if root else None}
    # Keyed by (parent_id, lowercased title) so repeated segments across paths
    # resolve to the same row without re-querying.
    seen = {}

    with transaction.atomic():
        for raw in paths:
            if not isinstance(raw, str):
                return JsonResponse({'error': 'paths must be strings.'}, status=400)
            # Normalise: strip slashes, drop empty segments ("a//b") and any
            # "." / ".." a zip or odd filesystem might produce.
            segments = [s.strip() for s in raw.split('/')]
            segments = [s for s in segments if s and s not in ('.', '..')]
            if not segments:
                continue

            key = '/'.join(segments)
            if key in resolved:
                continue
            if base_level + len(segments) > Bucket.MAX_DEPTH:
                return JsonResponse(
                    {'error': f'“{key}” nests deeper than {Bucket.MAX_DEPTH} levels.'},
                    status=400)

            parent = root
            walked = []
            for segment in segments:
                title, terr = _clean_title(segment)
                if terr:
                    return terr
                walked.append(title)
                cache_key = (parent.id if parent else None, title.lower())
                folder = seen.get(cache_key)
                if folder is None:
                    # Reuse an existing folder of that name rather than making
                    # a second one — re-uploading a tree must merge, not fork.
                    folder = Bucket.for_user(user).filter(
                        kind=Bucket.KIND_FOLDER, parent=parent, title__iexact=title,
                    ).first()
                if folder is None:
                    folder = Bucket.objects.create(
                        company_id=user.company_id, kind=Bucket.KIND_FOLDER,
                        title=title, parent=parent, created_by=user, status='general',
                    )
                    log_activity(user.company, 'folder_create', actor=user, bucket=folder,
                                 title=title, parent_id=parent.id if parent else None)
                seen[cache_key] = folder
                resolved['/'.join(walked)] = folder.id
                parent = folder

    return JsonResponse({'folders': resolved})


@require_portal_user
@require_http_methods(['PATCH', 'DELETE'])
def folder_detail(request, folder_id):
    user = request.portal_user
    folder = Bucket.for_user(user).filter(id=folder_id).first()
    if not folder:
        return JsonResponse({'error': 'Folder not found.'}, status=404)
    if folder.kind != Bucket.KIND_FOLDER:
        return JsonResponse(
            {'error': 'Only folders you created can be renamed or removed.'}, status=400)

    if request.method == 'DELETE':
        # Refuse rather than cascade. The FK is CASCADE so a company delete can
        # collect the tree in one pass, which means an unguarded delete here
        # would silently take every file underneath with it.
        if folder.children.exists():
            return JsonResponse(
                {'error': 'This folder still has subfolders. Empty it first.'}, status=409)
        if folder.files.filter(deleted_at__isnull=True).exists():
            return JsonResponse(
                {'error': 'This folder still has files. Move or delete them first.'},
                status=409)
        log_activity(user.company, 'folder_delete', actor=user, title=folder.title)
        folder.delete()
        return JsonResponse({'ok': True})

    data = json.loads(request.body or '{}')
    fields = []

    if 'title' in data:
        title, err = _clean_title(data.get('title'))
        if err:
            return err
        if _duplicate_sibling(user, title, folder.parent, exclude_id=folder.id):
            return JsonResponse(
                {'error': 'A folder with that name is already here.'}, status=409)
        folder.title = title
        fields.append('title')

    if 'parent_id' in data:
        parent, err = _resolve_parent(user, data.get('parent_id'))
        if err:
            return err
        if parent:
            # Moving a folder into itself or its own descendant would detach
            # the subtree from the root entirely — it becomes unreachable and
            # unlistable, with the files still inside it.
            if parent.is_descendant_of(folder):
                return JsonResponse(
                    {'error': 'A folder can’t be moved inside itself.'}, status=400)
            if parent.level + 1 + folder.subtree_height() > Bucket.MAX_DEPTH:
                return JsonResponse(
                    {'error': f'That would nest deeper than {Bucket.MAX_DEPTH} levels.'},
                    status=400)
        if _duplicate_sibling(user, folder.title, parent, exclude_id=folder.id):
            return JsonResponse(
                {'error': 'A folder with that name is already there.'}, status=409)
        folder.parent = parent
        fields.append('parent')

    if not fields:
        return JsonResponse({'error': 'Nothing to update.'}, status=400)
    folder.save(update_fields=fields + ['updated_at'])
    log_activity(user.company, 'folder_update', actor=user, bucket=folder,
                 changed=fields, title=folder.title)
    return JsonResponse({'folder': BucketSerializer(folder).data})


@require_portal_user
@require_http_methods(['POST'])
def files_move(request):
    """Move files into a folder (or a request bucket, or back to General).

    The destination is resolved through Bucket.for_user rather than trusted
    from the body: a file's own `company` doesn't change when it moves, so
    checking only the file would let a valid file be re-homed under another
    tenant's folder and pass every later scoping check.
    """
    user = request.portal_user
    data = json.loads(request.body or '{}')
    ids = data.get('file_ids') or []
    if not isinstance(ids, list) or not ids:
        return JsonResponse({'error': 'file_ids must be a non-empty list.'}, status=400)
    target = Bucket.for_user(user).filter(id=data.get('bucket_id')).first()
    if not target:
        return JsonResponse({'error': 'Destination folder not found.'}, status=404)

    files = list(SharedFile.for_user(user).filter(id__in=ids))
    if len(files) != len(set(ids)):
        # Partial matches mean at least one id was another tenant's or deleted.
        # Refuse the whole batch rather than half-moving a selection.
        return JsonResponse({'error': 'Some of those files could not be found.'}, status=404)

    for f in files:
        f.bucket = target
    SharedFile.objects.bulk_update(files, ['bucket'])
    for f in files:
        log_activity(user.company, 'file_move', actor=user, file=f, bucket=target,
                     name=f.original_name, to=target.title)
    return JsonResponse({'ok': True, 'moved': len(files), 'bucket_id': target.id})


# ── Upload (presigned PUT) ────────────────────────────────────────────────
@require_portal_user
@require_http_methods(['POST'])
def upload_init(request):
    user = request.portal_user
    if not user.company_id:
        return JsonResponse({'error': 'No company is associated with your account.'}, status=403)
    # Bound how fast one account can mint upload slots (the rest of auth is
    # rate-limited; this endpoint creates rows + presigned URLs).
    if is_rate_limited('file-upload-init', str(user.id),
                       settings.FILESHARE_UPLOAD_RATE, 3600):
        # Tell the client how long to hold. Without this the uploader guesses,
        # and a queue of workers each guessing wrong earns another 429 apiece.
        # The window rolls continuously, so re-checking every minute drains a
        # oversized batch slowly instead of failing it outright.
        resp = JsonResponse({
            'error': 'Too many uploads right now — please slow down.',
            'retry_after': 60,
        }, status=429)
        resp['Retry-After'] = '60'
        return resp
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

    # Small files stay on the single-PUT path: one round trip, nothing to gain
    # from splitting. The response shape is unchanged for them, so an older
    # client keeps working.
    if size <= settings.FILESHARE_MULTIPART_THRESHOLD:
        return JsonResponse({
            'file_id': f.id,
            'upload_url': file_storage.presign_put(f.storage_key, mime),
        })

    part_size, part_count = file_storage.part_plan(size)
    f.upload_id = file_storage.create_multipart(f.storage_key, mime)
    f.save(update_fields=['upload_id'])
    return JsonResponse({
        'file_id': f.id,
        'multipart': True,
        'part_size': part_size,
        'part_count': part_count,
    })


# Presigning every part up front would mean one huge response whose URLs all
# expire together; batching lets a slow upload re-presign what it still needs.
MAX_PART_BATCH = 50


@require_portal_user
@require_http_methods(['POST'])
def upload_parts(request):
    """Presign a batch of part PUTs for an in-flight multipart upload."""
    user = request.portal_user
    data = json.loads(request.body or '{}')
    f = SharedFile.for_user(user).filter(
        id=data.get('file_id'), state=SharedFile.STATE_UPLOADING).first()
    if not f or not f.upload_id:
        return JsonResponse({'error': 'Upload not found.'}, status=404)

    numbers = data.get('part_numbers') or []
    if not isinstance(numbers, list) or not numbers:
        return JsonResponse({'error': 'part_numbers required.'}, status=400)
    if len(numbers) > MAX_PART_BATCH:
        return JsonResponse(
            {'error': f'At most {MAX_PART_BATCH} parts per request.'}, status=400)
    try:
        numbers = [int(n) for n in numbers]
    except (TypeError, ValueError):
        return JsonResponse({'error': 'part_numbers must be integers.'}, status=400)
    # S3 numbers parts from 1 and allows at most 10,000.
    if any(n < 1 or n > 10000 for n in numbers):
        return JsonResponse({'error': 'part number out of range.'}, status=400)

    return JsonResponse({'urls': {
        str(n): file_storage.presign_part(f.storage_key, f.upload_id, n)
        for n in numbers
    }})


@require_portal_user
@require_http_methods(['POST'])
def upload_abort(request):
    """Give up on an in-flight upload and reclaim its storage.

    Parts of an abandoned multipart upload are billed until aborted and do not
    appear in a listing, so leaving them is a silent cost.
    """
    user = request.portal_user
    data = json.loads(request.body or '{}')
    f = SharedFile.for_user(user).filter(
        id=data.get('file_id'), state=SharedFile.STATE_UPLOADING).first()
    if not f:
        return JsonResponse({'error': 'Upload not found.'}, status=404)
    if f.upload_id:
        file_storage.abort_multipart(f.storage_key, f.upload_id)
    else:
        file_storage.delete_object(f.storage_key)
    f.delete()
    return JsonResponse({'ok': True})


@require_portal_user
@require_http_methods(['POST'])
def upload_complete(request):
    user = request.portal_user
    data = json.loads(request.body or '{}')
    f = SharedFile.for_user(user).filter(id=data.get('file_id')).first()
    if not f:
        return JsonResponse({'error': 'File not found.'}, status=404)

    # A multipart upload isn't an object until its parts are assembled, so this
    # has to happen before the size and signature checks below — those read the
    # finished object.
    if f.upload_id:
        parts = data.get('parts') or []
        if not parts:
            return JsonResponse({'error': 'Missing part list.'}, status=400)
        try:
            file_storage.complete_multipart(f.storage_key, f.upload_id, [
                {'PartNumber': int(p['PartNumber']), 'ETag': p['ETag']} for p in parts
            ])
        except (KeyError, TypeError, ValueError):
            return JsonResponse({'error': 'Malformed part list.'}, status=400)
        except Exception:
            logger.exception('complete_multipart failed for file %s', f.id)
            return JsonResponse({'error': 'Could not assemble the upload.'}, status=400)
        f.upload_id = ''
        f.save(update_fields=['upload_id'])

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
