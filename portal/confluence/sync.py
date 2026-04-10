import logging
import os
import re
import urllib.parse
from django.utils.text import slugify as django_slugify
from django.conf import settings
from django.utils import timezone
from .client import ConfluenceClient
from .transformer import StorageTransformer
from ..models import DocPage, DocImage

logger = logging.getLogger(__name__)


def _sanitize_attachment_filename(filename):
    """
    Confluence sometimes stores attachments with filenames like
    'image?url=https%3A%2F%2F...' (gitbook imports). These are unservable
    because HTTP treats '?' as a query string separator.

    Extracts a clean filesystem-safe name, preserving the original extension
    where possible.
    """
    if '?' not in filename:
        return filename

    path_part = filename.split('?')[0]
    path_part = urllib.parse.unquote(path_part)

    # path_part is often just 'image' — try to extract a better name from the URL value
    if path_part.lower() in ('image', 'attachment', 'file', ''):
        qs = filename.split('?', 1)[1]
        params = urllib.parse.parse_qs(qs)
        url_val = params.get('url', [''])[0]
        if url_val:
            # Double URL-decode (values are often double-encoded)
            url_decoded = urllib.parse.unquote(urllib.parse.unquote(url_val))
            url_path = url_decoded.split('?')[0]
            last_seg = url_path.rstrip('/').rsplit('/', 1)[-1]
            if last_seg:
                path_part = last_seg

    # Strip any remaining unsafe chars (keep alphanumeric, dot, dash, underscore, space)
    path_part = re.sub(r'[^\w\s.\-]', '_', path_part).strip()
    return path_part or 'attachment'


def make_unique_slug(title, confluence_id, existing_slug=None):
    base = django_slugify(title) or confluence_id
    if existing_slug and existing_slug.startswith(base):
        return existing_slug
    slug = base
    counter = 1
    while DocPage.objects.filter(slug=slug).exclude(confluence_id=confluence_id).exists():
        slug = f'{base}-{counter}'
        counter += 1
    return slug


def get_image_url(page_id, filename):
    """Return URL for a synced image."""
    return f'/media/confluence/{page_id}/{filename}'


def sync_space(space_key, full=True, since=None):
    """
    Sync all pages from a Confluence space.
    full=True: sync all pages regardless of version
    full=False (incremental): only sync pages changed since last sync
    """
    client = ConfluenceClient()
    synced = 0
    skipped = 0
    errors = 0

    logger.info(f"Starting {'full' if full else 'incremental'} sync for space: {space_key}")

    # Build page slug lookup for internal link resolution
    slug_map = {p.confluence_id: p.slug for p in DocPage.objects.filter(space_key=space_key)}
    title_to_slug = {p.title: p.slug for p in DocPage.objects.filter(space_key=space_key)}

    def image_resolver(filename, page_id=None):
        if page_id:
            return get_image_url(page_id, filename)
        return f'/media/confluence/{filename}'

    def page_slug_resolver(title):
        slug = title_to_slug.get(title)
        if slug:
            return f'/docs/{slug}'
        return f'/docs/{django_slugify(title)}'

    transformer = StorageTransformer(
        image_resolver=image_resolver,
        page_slug_resolver=page_slug_resolver,
    )

    all_pages = list(client.get_all_pages(space_key))
    logger.info(f"Found {len(all_pages)} pages in space {space_key}")

    # Fetch full body for each page (needed for ancestors + content)
    page_bodies = {}  # confluence_id -> full_page response
    for i, page_data in enumerate(all_pages):
        confluence_id = str(page_data['id'])
        try:
            full_page = client.get_page_body(confluence_id)
            page_bodies[confluence_id] = full_page
        except Exception as e:
            logger.error(f"  Failed to fetch body for {confluence_id}: {e}")

    # Sort pages so parents are always processed before children
    # (fewer ancestors = higher in the tree = process first)
    def ancestor_depth(page_data):
        cid = str(page_data['id'])
        full = page_bodies.get(cid, {})
        return len(full.get('ancestors', []))

    all_pages.sort(key=ancestor_depth)

    # Pass 1: upsert all pages (parent set where already in DB, null otherwise)
    for i, page_data in enumerate(all_pages):
        confluence_id = str(page_data['id'])
        title = page_data.get('title', 'Untitled')
        version_number = page_data.get('version', {}).get('number', 1)
        full_page = page_bodies.get(confluence_id, {})

        try:
            existing = DocPage.objects.filter(confluence_id=confluence_id).first()

            if not full and existing and existing.confluence_version >= version_number:
                skipped += 1
                continue

            body = full_page.get('body', {}).get('storage', {}).get('value', '')

            # Resolve parent — safe now because we sorted parents-first
            parent_obj = None
            ancestors = full_page.get('ancestors', [])
            if ancestors:
                parent_confluence_id = str(ancestors[-1]['id'])
                parent_obj = DocPage.objects.filter(confluence_id=parent_confluence_id).first()

            page_image_resolver = lambda filename, cid=confluence_id: get_image_url(cid, filename)
            page_transformer = StorageTransformer(
                image_resolver=page_image_resolver,
                page_slug_resolver=page_slug_resolver,
            )
            rendered = page_transformer.transform(body)

            slug = make_unique_slug(title, confluence_id, existing.slug if existing else None)
            title_to_slug[title] = slug

            page, created = DocPage.objects.update_or_create(
                confluence_id=confluence_id,
                defaults={
                    'slug': slug,
                    'title': title,
                    'parent': parent_obj,
                    'rendered_html': rendered,
                    'raw_storage': body,
                    'confluence_version': version_number,
                    'version': (existing.version + 1) if existing else 1,
                    'space_key': space_key,
                    'is_published': True,
                    'position': i,
                }
            )

            _sync_attachments(client, page, confluence_id, full_page)

            synced += 1
            action = 'Created' if created else 'Updated'
            logger.info(f"  [{i+1}/{len(all_pages)}] {action}: {title} (v{version_number})")

        except Exception as e:
            errors += 1
            logger.error(f"  Error syncing page {confluence_id} ({title}): {e}", exc_info=True)

    logger.info(f"Sync complete — synced: {synced}, skipped: {skipped}, errors: {errors}")
    return {'synced': synced, 'skipped': skipped, 'errors': errors}


def _sync_attachments(client, page, confluence_id, page_data):
    """
    Download image attachments from Confluence and upload to the configured
    storage backend (local MEDIA_ROOT in dev, S3 in production).

    After upload, rewrites the placeholder src URLs in rendered_html to the
    actual storage URL so images serve correctly regardless of backend.
    """
    import re
    from django.core.files.storage import default_storage
    from django.core.files.base import ContentFile

    raw = page.raw_storage
    filenames = re.findall(r'ri:filename="([^"]+)"', raw)
    if not filenames:
        return

    html_updated = False
    rendered = page.rendered_html

    for filename in filenames:
        cache_key = f'{confluence_id}:{filename}'
        existing = DocImage.objects.filter(confluence_id=cache_key).first()

        if existing:
            # Image already stored — just make sure the rendered_html URL is current
            actual_url = default_storage.url(existing.local_path)
            placeholder = get_image_url(confluence_id, filename)
            if placeholder in rendered and actual_url != placeholder:
                rendered = rendered.replace(placeholder, actual_url)
                html_updated = True
            continue

        try:
            response = client.download_attachment(confluence_id, filename)
            if response is None:
                logger.warning(f"    Attachment not found: {filename} on page {confluence_id}")
                continue

            content = response.content
            content_type = response.headers.get('Content-Type', 'image/png')
            safe_name = _sanitize_attachment_filename(filename)
            storage_path = f'confluence/{confluence_id}/{safe_name}'

            # Save to storage backend (local or S3 depending on settings)
            saved_path = default_storage.save(storage_path, ContentFile(content))
            actual_url = default_storage.url(saved_path)

            DocImage.objects.create(
                confluence_id=cache_key,
                page=page,
                local_path=saved_path,
                original_filename=filename,
                content_type=content_type,
            )

            # Rewrite placeholder URL in rendered HTML to actual storage URL
            placeholder = get_image_url(confluence_id, filename)
            if placeholder in rendered:
                rendered = rendered.replace(placeholder, actual_url)
                html_updated = True

            logger.debug(f"    Saved attachment: {filename} → {actual_url}")

        except Exception as e:
            logger.warning(f"    Failed to download attachment {filename}: {e}")

    if html_updated:
        page.rendered_html = rendered
        page.save(update_fields=['rendered_html'])
