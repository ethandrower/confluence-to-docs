from django.http import JsonResponse
from django.views.decorators.http import require_GET
from django.db import connection, models
from portal.models import DocPage
from portal.serializers import DocPageTreeSerializer, DocPageDetailSerializer


@require_GET
def page_tree(request):
    """Return the full page tree (root pages with nested children)."""
    roots = DocPage.objects.filter(
        parent__isnull=True, is_published=True
    ).order_by('position', 'title')
    data = DocPageTreeSerializer(roots, many=True).data
    return JsonResponse({'results': data})


@require_GET
def page_detail(request, slug):
    try:
        page = DocPage.objects.get(slug=slug, is_published=True)
    except DocPage.DoesNotExist:
        return JsonResponse({'error': 'Not found'}, status=404)
    data = DocPageDetailSerializer(page).data
    return JsonResponse(data)


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

    results = [{'slug': p.slug, 'title': p.title} for p in pages]
    return JsonResponse({'results': results})
