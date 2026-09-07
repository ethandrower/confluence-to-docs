"""Admin file-sharing endpoints: company switcher, per-company view, a
"download all" zip, and the push side — staff-owned folders, staff uploads,
external links, and per-person share notifications. Gated to portal admins via
require_portal_admin.

The push half is the mirror of the customer half. Where a customer creates
folders in their own tree and uploads into them, staff create folders with
`origin='staff'` in a customer's tree and upload into those; the customer may
read and download what lands there but not rename, move, delete or add to it
(see the guards in views/files.py). Notifications are per-person rather than
per-company, and each one is recorded as a ShareNotice so an unopened delivery
can be nudged exactly twice and then left alone. How much of that actually
reaches an inbox is bounded separately, per recipient rather than per row —
see the rate-limit notes on ShareNotice."""
import json
import tempfile
import zipfile
from urllib.parse import urlparse

from django.conf import settings
from django.db import models, transaction
from django.http import JsonResponse, FileResponse, HttpResponseRedirect
from django.utils.dateparse import parse_datetime, parse_date
from django.utils import timezone
from django.views.decorators.http import require_http_methods

# Bounds for the "download all" export so one large company can't OOM a worker.
_ZIP_MAX_FILES = 1000
_ZIP_MAX_BYTES = 3 * 1024 ** 3  # 3 GB total
_ZIP_SPOOL = 64 * 1024 * 1024   # keep ≤64 MB in RAM, then spill to disk

from portal import file_storage, file_notify
from portal.decorators import require_portal_admin
from portal.models import (
    Company, Bucket, SharedFile, ChecklistItem, FileActivity, FileComment,
    PortalUser, ShareNotice,
)
from portal.serializers import (
    BucketSerializer, ChecklistItemSerializer, SharedFileSerializer,
)
from portal.views.files import (
    get_general_bucket, log_activity, _clean_title, _resolve_parent,
    _duplicate_sibling, _ext_ok,
)


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
    """The client list, and the only place "who has sent us something new" is
    answered now that the cross-client inbox is gone. `unseen_count` is what
    makes this list scannable — without it an agent would have to open every
    client to find the one that uploaded this morning."""
    ready = {'deleted_at__isnull': True, 'state': SharedFile.STATE_READY}
    out = []
    for c in Company.objects.all().order_by('name'):
        files = SharedFile.objects.filter(company=c, **ready)
        out.append({
            'id': c.id, 'name': c.name,
            'file_count': files.count(),
            'unseen_count': files.filter(processed=False).count(),
            'open_request_count': Bucket.objects.filter(
                company=c, kind=Bucket.KIND_REQUEST,
            ).exclude(status='complete').count(),
            'required_open_count': Bucket.objects.filter(
                company=c, kind=Bucket.KIND_REQUEST, required=True,
            ).exclude(status='complete').count(),
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
        # Defaults to false: a request has to be argued INTO the customer's
        # "needed from you" list, not out of it.
        required=bool(data.get('required')),
    )
    log_activity(company, 'request_created', actor=request.portal_user, bucket=b, title=title)
    try:
        file_notify.notify_request_created(b)
    except Exception:
        pass
    return JsonResponse(BucketSerializer(b, context={'staff': True}).data, status=201)


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
    if 'required' in data:
        b.required = bool(data.get('required'))
    became_complete = False
    if 'status' in data and data.get('status') in ('open', 'partial', 'complete'):
        became_complete = data['status'] == 'complete' and b.status != 'complete'
        b.status = data.get('status')
    b.save()
    if became_complete:
        try:
            file_notify.notify_request_complete(b)
        except Exception:
            pass
    return JsonResponse(BucketSerializer(b).data)


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


def _comment_dict(c):
    return {
        'id': c.id,
        'author': (c.author.name or c.author.email) if c.author else 'CiteMed',
        'body': c.body,
        'created_at': c.created_at.isoformat(),
    }


@require_portal_admin
@require_http_methods(['GET', 'POST'])
def file_comments(request, file_id):
    """Internal staff comment thread on a file (admin-only; never customer-facing)."""
    f = SharedFile.objects.filter(id=file_id, deleted_at__isnull=True).first()
    if not f:
        return JsonResponse({'error': 'File not found.'}, status=404)
    if request.method == 'GET':
        return JsonResponse({'comments': [_comment_dict(c) for c in f.comments.select_related('author')]})
    data = json.loads(request.body or '{}')
    body = (data.get('body') or '').strip()
    if not body:
        return JsonResponse({'error': 'Comment cannot be empty.'}, status=400)
    c = FileComment.objects.create(file=f, author=request.portal_user, body=body)
    log_activity(f.company, 'comment', actor=request.portal_user, file=f, name=f.original_name)
    return JsonResponse(_comment_dict(c), status=201)


@require_portal_admin
def activity(request):
    """Append-only audit trail of file-sharing actions (newest first).
    Optional ?company=<id> filter, ?limit (default 100, max 500)."""
    qs = FileActivity.objects.select_related('actor', 'company', 'file').order_by('-created_at')
    company_id = request.GET.get('company')
    if company_id:
        qs = qs.filter(company_id=company_id)
    try:
        limit = min(int(request.GET.get('limit', 100)), 500)
    except (TypeError, ValueError):
        limit = 100
    items = []
    for a in qs[:limit]:
        detail = a.detail if isinstance(a.detail, dict) else {}
        items.append({
            'id': a.id,
            'action': a.action,
            'actor': (a.actor.name or a.actor.email) if a.actor else 'system',
            'company': a.company.name if a.company else None,
            'file': a.file.original_name if a.file else detail.get('name'),
            'detail': detail,
            'created_at': a.created_at.isoformat(),
        })
    return JsonResponse({'items': items})


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


# ── Push: staff-owned folders, files and links ───────────────────────────
# Everything below writes into a CUSTOMER's tree, so the company is taken from
# the request rather than the session and every lookup is scoped through
# Bucket.for_company / SharedFile.for_company with that id.


def _staff_folder(folder_id):
    """A staff-origin folder by id, or None. Staff endpoints refuse to touch a
    customer's own folders: we can push into our own and read theirs, but
    silently renaming the filing system they built is not ours to do."""
    return Bucket.objects.filter(
        id=folder_id, kind=Bucket.KIND_FOLDER, origin=Bucket.ORIGIN_STAFF).first()


def _version_stamp(dt):
    """A row's version as an integer, for equality rather than nearness.

    Postgres keeps microseconds and a browser's Date only milliseconds, so the
    two sides have to be compared at the coarser of them or a token that went
    through JSON.parse would never match. Truncating is the way to absorb that
    and NOT a tolerance window: a window accepts a token that is merely close,
    which is precisely the rename that landed a moment ago — the collision this
    check exists to catch.
    """
    return int(dt.timestamp() * 1000)


def _clean_url(raw):
    """Validate an external link target. Returns (url, error_response)."""
    url = (raw or '').strip()
    if not url:
        return None, JsonResponse({'error': 'Link URL required.'}, status=400)
    if len(url) > 2048:
        return None, JsonResponse({'error': 'That URL is too long.'}, status=400)
    parsed = urlparse(url)
    # Allowlist rather than blocklist. 'javascript:' and 'data:' are the
    # obvious hazards in something the customer will click, but so is any
    # other scheme a browser handles specially, and enumerating those is a
    # losing game. Only http(s) is ever safe here. Applied even though links
    # are staff-authored today, so it stays true if that ever widens.
    if parsed.scheme not in ('http', 'https') or not parsed.netloc:
        return None, JsonResponse(
            {'error': 'Links must start with http:// or https://.'}, status=400)
    return url, None


@require_portal_admin
@require_http_methods(['POST'])
def staff_folder_create(request):
    """Create a folder in a customer's tree that belongs to us."""
    data = json.loads(request.body or '{}')
    company = Company.objects.filter(id=data.get('company_id')).first()
    if not company:
        return JsonResponse({'error': 'Company not found.'}, status=404)
    title, err = _clean_title(data.get('title'))
    if err:
        return err
    scope = Bucket.for_company(company.id)
    parent, err = _resolve_parent(scope, data.get('parent_id'))
    if err:
        return err
    # Our folders nest under our folders. Dropping one into a customer's
    # folder would make it deletable by them via a parent they do control.
    if parent and not parent.is_staff_origin:
        return JsonResponse(
            {'error': 'Shared folders can only be nested inside other shared folders.'},
            status=400)
    if parent and parent.level + 1 > Bucket.MAX_DEPTH:
        return JsonResponse(
            {'error': f'Folders can only be {Bucket.MAX_DEPTH} levels deep.'}, status=400)
    if _duplicate_sibling(scope, title, parent, Bucket.ORIGIN_STAFF):
        return JsonResponse(
            {'error': 'A shared folder with that name is already here.'}, status=409)
    folder = Bucket.objects.create(
        company=company, kind=Bucket.KIND_FOLDER, title=title,
        description=(data.get('description') or '').strip(),
        parent=parent, created_by=request.portal_user, status='general',
        origin=Bucket.ORIGIN_STAFF,
    )
    log_activity(company, 'staff_folder_create', actor=request.portal_user,
                 bucket=folder, title=title)
    return JsonResponse(
        {'folder': BucketSerializer(folder, context={'staff': True}).data}, status=201)


@require_portal_admin
@require_http_methods(['PATCH', 'DELETE'])
def staff_folder_detail(request, folder_id):
    folder = _staff_folder(folder_id)
    if not folder:
        return JsonResponse({'error': 'Shared folder not found.'}, status=404)

    if request.method == 'DELETE':
        # Once we have told someone about a folder, it stops being ours to
        # remove. The emptiness checks below stop a one-click cascade, but on
        # their own they are only a speed bump: delete the files one at a time
        # and the folder becomes deletable, taking a link the customer was
        # emailed down with it.
        #
        # A ShareNotice is the line rather than the folder's own existence
        # because a staff folder shows up in the customer's tree the moment it
        # is created (buckets_list does not filter on origin) — so "never
        # visible to them" is not a state that exists, and deleting a typo'd
        # folder in the first minute has to stay possible. Being *notified* is
        # the point of no return: that is when the folder acquires a life
        # outside this screen.
        #
        # Deletion is refused outright rather than offered as an archive
        # because there is no archived state yet; that is the follow-up this
        # guard is holding the line for.
        if ShareNotice.objects.filter(bucket=folder).exists():
            return JsonResponse(
                {'error': 'This folder has already been shared with the customer, '
                          'so it can’t be deleted.'}, status=409)
        # Same refuse-rather-than-cascade rule as the customer side: the FK is
        # CASCADE so an unguarded delete would take every delivered file with
        # it, including ones the customer has already been told about.
        if folder.children.exists():
            return JsonResponse(
                {'error': 'This folder still has subfolders. Empty it first.'}, status=409)
        if folder.files.filter(deleted_at__isnull=True).exists():
            return JsonResponse(
                {'error': 'This folder still has files. Remove them first.'}, status=409)
        log_activity(folder.company, 'staff_folder_delete', actor=request.portal_user,
                     title=folder.title)
        folder.delete()
        return JsonResponse({'ok': True})

    data = json.loads(request.body or '{}')
    # Optimistic concurrency. Two admins on the same account is the ordinary
    # case, not the exotic one, and without this the second rename silently
    # wins — the first admin keeps looking at a name that is no longer real and
    # has no way to find that out.
    #
    # The precondition is REQUIRED rather than honoured-when-present: a caller
    # that omits it would get exactly the clobbering behaviour this exists to
    # stop, and "the safe path is the one you have to opt into" is how a guard
    # ends up protecting nothing. Nothing calls this endpoint yet — the admin
    # UI creates shared folders but has no rename control — so requiring it
    # costs no caller anything today and sets the contract for the one that
    # eventually does.
    seen_at = parse_datetime(data.get('updated_at') or '')
    if seen_at is None:
        return JsonResponse(
            {'error': 'updated_at is required so a concurrent edit can be detected.'},
            status=400)
    if _version_stamp(folder.updated_at) != _version_stamp(seen_at):
        return JsonResponse(
            {'error': 'Someone else changed this folder. Reload and try again.'},
            status=409)
    title, err = _clean_title(data.get('title'))
    if err:
        return err
    if _duplicate_sibling(Bucket.for_company(folder.company_id), title, folder.parent,
                          Bucket.ORIGIN_STAFF, exclude_id=folder.id):
        return JsonResponse(
            {'error': 'A shared folder with that name is already here.'}, status=409)
    folder.title = title
    folder.save(update_fields=['title', 'updated_at'])
    log_activity(folder.company, 'staff_folder_update', actor=request.portal_user,
                 bucket=folder, title=title)
    return JsonResponse({'folder': BucketSerializer(folder, context={'staff': True}).data})


@require_portal_admin
@require_http_methods(['POST'])
def staff_upload_init(request):
    """Presign a PUT for a file WE are delivering into a staff folder."""
    data = json.loads(request.body or '{}')
    folder = _staff_folder(data.get('bucket_id'))
    if not folder:
        return JsonResponse({'error': 'Shared folder not found.'}, status=404)
    name = (data.get('name') or '').strip()
    size = int(data.get('size') or 0)
    mime = (data.get('mime') or '').strip()
    if not name:
        return JsonResponse({'error': 'Filename required.'}, status=400)
    if not _ext_ok(name):
        return JsonResponse({'error': 'File type not allowed.'}, status=400)
    if size and size > settings.FILESHARE_MAX_BYTES:
        return JsonResponse({'error': 'File exceeds the size limit.'}, status=400)
    f = SharedFile.objects.create(
        bucket=folder, company_id=folder.company_id, uploaded_by=request.portal_user,
        original_name=name, storage_key='', mime_type=mime,
        size_bytes=size or None, state=SharedFile.STATE_UPLOADING,
    )
    f.storage_key = file_storage.build_key(folder.company_id, folder.id, f.id, name)
    f.save(update_fields=['storage_key'])
    return JsonResponse({
        'file_id': f.id,
        'upload_url': file_storage.presign_put(f.storage_key, mime),
    })


@require_portal_admin
@require_http_methods(['POST'])
def staff_upload_complete(request):
    data = json.loads(request.body or '{}')
    f = (SharedFile.objects
         .select_related('bucket')
         .filter(id=data.get('file_id'), deleted_at__isnull=True,
                 bucket__origin=Bucket.ORIGIN_STAFF)
         .first())
    if not f:
        return JsonResponse({'error': 'File not found.'}, status=404)
    size = file_storage.head_size(f.storage_key)
    if size is None:
        return JsonResponse({'error': 'Upload not found in storage.'}, status=400)
    if size > settings.FILESHARE_MAX_BYTES:
        file_storage.delete_object(f.storage_key)
        f.delete()
        return JsonResponse({'error': 'File exceeds the size limit.'}, status=400)
    if not file_storage.signature_ok(f.storage_key, f.original_name):
        file_storage.delete_object(f.storage_key)
        f.delete()
        return JsonResponse({'error': "File content doesn't match its type."}, status=400)
    f.size_bytes = size
    f.state = SharedFile.STATE_READY
    # Ours by definition — nothing for staff to triage in their own upload.
    f.processed = True
    f.save(update_fields=['size_bytes', 'state', 'processed'])
    log_activity(f.company, 'staff_upload', actor=request.portal_user, file=f,
                 bucket=f.bucket, name=f.original_name, size=size)
    return JsonResponse({'ok': True, 'file_id': f.id})


@require_portal_admin
@require_http_methods(['POST'])
def staff_link_create(request):
    """Add a link — a row with no bytes behind it — to a staff folder."""
    data = json.loads(request.body or '{}')
    folder = _staff_folder(data.get('bucket_id'))
    if not folder:
        return JsonResponse({'error': 'Shared folder not found.'}, status=404)
    name = (data.get('name') or '').strip()
    if not name:
        return JsonResponse({'error': 'Link name required.'}, status=400)
    if len(name) > 512:
        return JsonResponse({'error': 'That name is too long.'}, status=400)
    url, err = _clean_url(data.get('url'))
    if err:
        return err
    f = SharedFile.objects.create(
        bucket=folder, company_id=folder.company_id, uploaded_by=request.portal_user,
        original_name=name, item_type=SharedFile.ITEM_LINK, external_url=url,
        storage_key='', mime_type='',
        # Ready on creation: there is no upload to wait for, and the listing
        # only ever shows READY rows.
        state=SharedFile.STATE_READY, processed=True,
    )
    log_activity(folder.company, 'link_create', actor=request.portal_user, file=f,
                 bucket=folder, name=name, url=url)
    return JsonResponse(
        {'file': SharedFileSerializer(f, context={'staff': True}).data}, status=201)


@require_portal_admin
@require_http_methods(['DELETE'])
def staff_item_delete(request, file_id):
    """Withdraw a delivered file or link."""
    f = (SharedFile.objects
         .select_related('bucket')
         .filter(id=file_id, deleted_at__isnull=True,
                 bucket__origin=Bucket.ORIGIN_STAFF)
         .first())
    if not f:
        return JsonResponse({'error': 'Item not found.'}, status=404)
    f.deleted_at = timezone.now()
    f.save(update_fields=['deleted_at'])
    log_activity(f.company, 'staff_item_delete', actor=request.portal_user,
                 bucket=f.bucket, name=f.original_name)
    return JsonResponse({'ok': True})


@require_portal_admin
@require_http_methods(['GET'])
def company_members(request, company_id):
    """Who a share can be sent to at this company.

    A scoped endpoint rather than a filter over the global user list: the
    eligibility rule (this company, access enabled) belongs next to the push
    that depends on it, not in a picker that would have to re-derive it and
    could drift.
    """
    rows = (PortalUser.objects
            .filter(company_id=company_id, access_enabled=True)
            .exclude(email='')
            .order_by('name', 'email'))
    return JsonResponse({'members': [
        {'id': u.id, 'email': u.email, 'name': u.name or '', 'role': u.role}
        for u in rows
    ]})


@require_portal_admin
@require_http_methods(['POST'])
def share_push(request):
    """Tell specific people that a folder — or one item in it — is waiting.

    Recipients are PortalUser ids belonging to the folder's company. Anything
    else is refused rather than silently dropped: a push that quietly notified
    four of the five people you picked would look identical to one that
    worked, and the difference only surfaces as a customer who never heard.
    """
    data = json.loads(request.body or '{}')
    folder = _staff_folder(data.get('bucket_id'))
    if not folder:
        return JsonResponse({'error': 'Shared folder not found.'}, status=404)

    item = None
    if data.get('file_id'):
        item = SharedFile.for_company(folder.company_id).filter(
            id=data['file_id'], bucket=folder).first()
        if not item:
            return JsonResponse({'error': 'Item not found in that folder.'}, status=404)

    ids = data.get('recipient_ids') or []
    if not isinstance(ids, list) or not ids:
        return JsonResponse({'error': 'Pick at least one person to notify.'}, status=400)
    recipients = list(PortalUser.objects.filter(
        id__in=ids, company_id=folder.company_id, access_enabled=True).exclude(email=''))
    if len(recipients) != len(set(ids)):
        return JsonResponse(
            {'error': 'Some of those people aren’t active members of this company.'},
            status=400)

    remind = bool(data.get('remind', True))
    notices, emailed, held = [], [], []
    for r in recipients:
        # Disarm this person's earlier unopened notices for the same folder
        # BEFORE adding the new one, so the nudge cycles don't stack. See
        # ShareNotice.supersede_open_notices.
        ShareNotice.supersede_open_notices(r.id, folder.id)
        # One row per person, created individually rather than bulk: the
        # counts here are a handful, and doing it this way keeps auto_now_add
        # and any future save-side logic honest.
        notices.append(ShareNotice.objects.create(
            bucket=folder, file=item, recipient=r,
            sent_by=request.portal_user, remind=remind,
        ))
    # One message per person, not one message addressed to all of them: the
    # recipient list is not something a customer needs to see, and a per-person
    # send is what lets the reminder loop talk to one of them later.
    #
    # The row is always written even when the email is held back: the push
    # happened, staff meant it, and it belongs in the status panel and the
    # RevenueHub feed. What the rate limit decides is whether it also lands in
    # someone's inbox — and `held` carries that back so the UI can say so
    # rather than reporting a delivery that never left.
    for n in notices:
        try:
            reason = file_notify.send_share_email(n)
        except Exception:
            reason = None
        (held if reason else emailed).append(n.recipient.email)
    log_activity(folder.company, 'share_push', actor=request.portal_user,
                 bucket=folder, file=item, name=(item.original_name if item else folder.title),
                 recipients=[r.email for r in recipients], remind=remind,
                 emailed=emailed, held=held)
    return JsonResponse({'ok': True, 'notified': len(notices),
                         'emailed': len(emailed), 'held': held}, status=201)


def _notice_dict(n, last_email_at=None):
    return {
        'user_id': n.recipient_id,
        'name': n.recipient.name or '',
        'email': n.recipient.email,
        'item': n.file.original_name if n.file else None,
        'sent_at': n.sent_at.isoformat(),
        # When an email last actually reached them, which is not the same as
        # when staff last pushed — the rate limit is the difference. The UI
        # uses this to warn before a re-notify that would be held anyway.
        #
        # Taken across ALL of this person's notices for the folder, not just
        # the newest one shown here. A held push writes a row with no send on
        # it, so reading this off the latest row alone would blank the warning
        # the moment the rate limit acted — the UI would re-tick them, and
        # staff would watch the same send get held again with no idea why.
        'last_email_at': (last_email_at or n.last_email_at).isoformat()
                         if (last_email_at or n.last_email_at) else None,
        'opened_at': n.first_opened_at.isoformat() if n.first_opened_at else None,
        'reminders_sent': n.reminder_count,
        'reminding': bool(n.remind and not n.first_opened_at and not n.exhausted),
    }


@require_portal_admin
@require_http_methods(['GET'])
def share_status(request, bucket_id):
    """Per-person delivery state for one shared folder.

    Shows the LATEST notice per recipient. Re-pushing a folder deliberately
    creates a new notice rather than resetting the old one, so a person can
    have several; what staff want to know is where the most recent one stands.
    """
    folder = _staff_folder(bucket_id)
    if not folder:
        return JsonResponse({'error': 'Shared folder not found.'}, status=404)
    # The last email that actually went to each person about this folder,
    # across every notice — see _notice_dict for why the newest row alone
    # would be wrong.
    last_emails = dict(
        ShareNotice.objects.filter(bucket=folder, last_email_at__isnull=False)
        .values_list('recipient_id')
        .annotate(models.Max('last_email_at'))
    )
    seen, latest = set(), []
    # Default ordering is -sent_at, so the first row seen per recipient is
    # their most recent notice.
    for n in ShareNotice.objects.filter(bucket=folder).select_related('recipient', 'file'):
        if n.recipient_id in seen:
            continue
        seen.add(n.recipient_id)
        latest.append(_notice_dict(n, last_emails.get(n.recipient_id)))
    return JsonResponse({
        'bucket_id': folder.id,
        'recipients': latest,
        'opened': sum(1 for r in latest if r['opened_at']),
        'total': len(latest),
    })
