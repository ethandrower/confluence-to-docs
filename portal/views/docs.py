import re

from django.http import JsonResponse
from django.views.decorators.http import require_GET
from django.db import connection, models
from portal.models import DocPage
from portal.serializers import DocPageTreeSerializer, DocPageDetailSerializer


SPACE_LABELS = {
    'ECD': 'Evidence Cloud',
    'Ops': 'Operations',
    'ECC': 'Collective',
    'Engineerin': 'Engineering',
    'CHO': 'CiteMed Home',
    'GTM': 'Go To Market',
}

# Pages whose direct children are version roots.
# Title pattern → matched exactly.
VERSION_CONTAINER_TITLES = [
    'User Documentation per Release Version',
]

# Regex to extract version label from page titles like "V5.5.8", "V5.5.4 - current version"
VERSION_LABEL_RE = re.compile(r'[Vv](\d+\.\d+(?:\.\d+)?)')

# Regex for legacy version pages like "(v1.0) Evidence Cloud Documentation"
LEGACY_VERSION_RE = re.compile(r'^\(v(\d+\.\d+(?:\.\d+)?)\)\s+')


def _detect_versions(space_key):
    """
    Detect version roots for a space.

    Returns (versions_list, container_ids_set) where:
    - versions_list: [{label, slug, confluence_id, is_latest, page_id}]
    - container_ids_set: set of DB IDs for the version container page and its
      ancestors up to the space root — these are structural pages the frontend
      should hide when version mode is active.
    """
    versions = []
    container_ids = set()

    containers = DocPage.objects.filter(
        space_key=space_key,
        is_published=True,
        title__in=VERSION_CONTAINER_TITLES,
    )

    for container in containers:
        # Collect the container and all its ancestors — these are structural
        # pages that the version switcher replaces in the sidebar
        page = container
        while page:
            container_ids.add(page.id)
            page = page.parent

        children = container.children.filter(is_published=True).order_by('position', 'title')
        for child in children:
            m = VERSION_LABEL_RE.search(child.title)
            if m:
                # Also add version root pages to container_ids
                container_ids.add(child.id)
                versions.append({
                    'label': f'v{m.group(1)}',
                    'title': child.title,
                    'slug': child.slug,
                    'confluence_id': child.confluence_id,
                    'page_id': child.id,
                })

    # Also detect legacy version pages at root level, e.g. "(v1.0) Evidence Cloud Documentation"
    legacy_roots = DocPage.objects.filter(
        space_key=space_key,
        is_published=True,
        parent__isnull=True,
        title__regex=r'^\(v\d+\.\d+',
    )
    for page in legacy_roots:
        m = LEGACY_VERSION_RE.search(page.title)
        if m:
            container_ids.add(page.id)
            versions.append({
                'label': f'v{m.group(1)}',
                'title': page.title,
                'slug': page.slug,
                'confluence_id': page.confluence_id,
                'page_id': page.id,
            })

    if not versions:
        return [], set()

    # Sort by version number descending — latest first
    def version_sort_key(v):
        parts = v['label'].lstrip('v').split('.')
        return tuple(int(p) for p in parts)

    versions.sort(key=version_sort_key, reverse=True)

    for i, v in enumerate(versions):
        v['is_latest'] = (i == 0)

    return versions, container_ids


def _filter_tree(pages, promote_ids, drop_ids):
    """
    Recursively filter a serialized tree.
    - promote_ids: remove these nodes but keep their children promoted up
    - drop_ids: remove these nodes AND their entire subtree
    """
    result = []
    for page in pages:
        if page['id'] in drop_ids:
            # Drop entire subtree
            continue
        if page['id'] in promote_ids:
            # Skip this node but keep its non-dropped children promoted up
            if page.get('children'):
                result.extend(_filter_tree(page['children'], promote_ids, drop_ids))
            continue
        filtered = dict(page)
        if filtered.get('children'):
            filtered['children'] = _filter_tree(filtered['children'], promote_ids, drop_ids)
        result.append(filtered)
    return result


@require_GET
def page_tree(request):
    """Return the full page tree grouped by space, with version info."""
    spaces = sorted(set(
        DocPage.objects.filter(is_published=True)
        .values_list('space_key', flat=True)
    ))

    sections = []
    for space_key in spaces:
        roots = DocPage.objects.filter(
            parent__isnull=True, is_published=True, space_key=space_key
        ).order_by('position', 'title')
        data = DocPageTreeSerializer(roots, many=True).data

        section = {
            'space_key': space_key,
            'label': SPACE_LABELS.get(space_key, space_key),
            'pages': data,
        }

        # Detect versions for this space
        versions, container_ids = _detect_versions(space_key)
        if versions:
            section['versions'] = versions

            # Collect version root IDs — these and their subtrees
            # should be dropped entirely from general pages
            version_root_ids = set(v['page_id'] for v in versions)

            # Ancestor IDs (not version roots) should be promoted:
            # remove the structural wrapper but keep non-version children
            promote_ids = container_ids - version_root_ids

            # Build per-version page trees from each version root's children
            for v in versions:
                try:
                    version_root = DocPage.objects.get(pk=v['page_id'])
                    version_children = version_root.children.filter(
                        is_published=True
                    ).order_by('position', 'title')
                    v['pages'] = DocPageTreeSerializer(version_children, many=True).data
                except DocPage.DoesNotExist:
                    v['pages'] = []

            # Filter general pages:
            # - promote ancestor containers (keep their non-version children)
            # - drop version roots entirely (their content is in v['pages'])
            section['pages'] = _filter_tree(data, promote_ids, version_root_ids)

        sections.append(section)

    return JsonResponse({'sections': sections})


@require_GET
def page_detail(request, slug):
    try:
        page = DocPage.objects.get(slug=slug, is_published=True)
    except DocPage.DoesNotExist:
        return JsonResponse({'error': 'Not found'}, status=404)
    data = DocPageDetailSerializer(page).data
    return JsonResponse(data)


def _extract_snippet(text, query, context_chars=80):
    """Extract a text snippet around the first match with context."""
    if not text:
        return ''
    lower = text.lower()
    q_lower = query.lower()
    idx = lower.find(q_lower)
    if idx == -1:
        return text[:160].strip() + ('...' if len(text) > 160 else '')

    start = max(0, idx - context_chars)
    end = min(len(text), idx + len(query) + context_chars)

    snippet = text[start:end].strip()
    if start > 0:
        snippet = '...' + snippet
    if end < len(text):
        snippet = snippet + '...'
    return snippet


def _find_section_heading(text, query):
    """Find the nearest heading above the first match."""
    import re
    if not text:
        return None
    lower = text.lower()
    idx = lower.find(query.lower())
    if idx == -1:
        return None

    # Look backwards from match for markdown headings (# ...) or ALL CAPS lines
    before = text[:idx]
    lines = before.split('\n')

    for line in reversed(lines):
        stripped = line.strip()
        # Markdown heading
        m = re.match(r'^#{1,4}\s+(.+)', stripped)
        if m:
            return m.group(1).strip()
        # ALL CAPS line (likely a section heading)
        if stripped and len(stripped) > 3 and stripped == stripped.upper() and stripped[0].isalpha():
            return stripped.title()

    return None


@require_GET
def search_docs(request):
    q = request.GET.get('q', '').strip()
    if not q:
        return JsonResponse({'results': []})

    if connection.vendor == 'postgresql':
        from django.contrib.postgres.search import SearchQuery, SearchRank
        query = SearchQuery(q)
        pages = DocPage.objects.annotate(
            rank=SearchRank('search_vector', query)
        ).filter(
            search_vector=query, is_published=True
        ).order_by('-rank')[:20]
    else:
        from django.db.models import Q
        pages = DocPage.objects.filter(
            is_published=True
        ).filter(
            Q(title__icontains=q) | Q(raw_storage__icontains=q)
        )[:20]

    results = []
    for p in pages:
        raw = p.raw_storage or ''
        snippet = _extract_snippet(raw, q)
        section = _find_section_heading(raw, q)
        space_label = SPACE_LABELS.get(p.space_key, p.space_key)
        results.append({
            'slug': p.slug,
            'title': p.title,
            'snippet': snippet,
            'section': section,
            'space': space_label,
        })

    return JsonResponse({'results': results})
