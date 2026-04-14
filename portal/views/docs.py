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


@require_GET
def page_tree(request):
    """Return the full page tree grouped by space."""
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
        sections.append({
            'space_key': space_key,
            'label': SPACE_LABELS.get(space_key, space_key),
            'pages': data,
        })

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
