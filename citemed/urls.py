from django.contrib import admin
from django.urls import path, include, re_path
from django.conf import settings
from django.conf.urls.static import static
from django.http import HttpResponse, Http404
from django.views.decorators.cache import never_cache


@never_cache
def spa_index(request):
    """
    Serve the Vue SPA's index.html for any non-API, non-admin route.
    Vue Router takes over from there (client-side routing).

    `never_cache` ensures the HTML shell is always fresh even though the hashed
    JS/CSS assets it references can be cached aggressively by WhiteNoise.
    """
    index_path = settings.BASE_DIR / 'frontend' / 'dist' / 'index.html'
    if not index_path.exists():
        # Dev: frontend was never built. Tell the developer instead of 500ing.
        raise Http404(
            'frontend/dist/index.html not found. '
            'Run `cd frontend && npm run build` (or use `npm run dev` for the dev server).'
        )
    return HttpResponse(index_path.read_text(encoding='utf-8'), content_type='text/html')


urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include('portal.urls')),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

# Catch-all for SPA routes. MUST come last. The regex explicitly excludes
# paths that are handled by Django so we don't shadow them.
urlpatterns += [
    re_path(r'^(?!api/|admin/|static/|media/).*$', spa_index),
]
