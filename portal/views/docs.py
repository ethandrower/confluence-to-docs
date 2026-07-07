import re

from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.http import require_GET
from django.db import connection, models
from portal.decorators import require_portal_user
from portal.models import DocPage
from portal.serializers import DocPageTreeSerializer, DocPageDetailSerializer


def allowed_spaces():
    """
    Space keys this portal is allowed to surface, from DOCS_ALLOWED_SPACES.
    Empty setting = no restriction (all spaces visible) — the dev default.
    """
    return set(getattr(settings, 'DOCS_ALLOWED_SPACES', []) or [])


def published_pages():
    """
    Base queryset for everything the portal serves: published pages, scoped
    to the allowed spaces. Single source of truth so page_tree, search, and
    page_detail can never drift out of sync on what's visible.
    """
    qs = DocPage.objects.filter(is_published=True)
    spaces = allowed_spaces()
    if spaces:
        qs = qs.filter(space_key__in=spaces)
    if EXCLUDE_TITLES:
        qs = qs.exclude(title__in=EXCLUDE_TITLES)
    for prefix in EXCLUDE_PREFIXES:
        qs = qs.exclude(title__startswith=prefix)
    return qs


SPACE_LABELS = {
    'ECD': 'Evidence Cloud - Altus Release',
    'Ops': 'Operations',
    'ECC': 'Collective',
    'Engineerin': 'Engineering',
    'CHO': 'CiteMed Home',
    'GTM': 'Go To Market',
}

# Pages hidden from the portal entirely (internal docs that shouldn't surface
# to customers / auditors). Matched on exact title.
EXCLUDE_TITLES = {
    'Retrospective: V6.0.1',
    'SOP for Managing User Documentation in Confluence and Jira Knowledge Base',
}

# Titles starting with any of these are excluded everywhere — including pages
# nested under a published parent (which exact-title root filtering misses).
EXCLUDE_PREFIXES = ('Retrospective',)


def is_doc_excluded(title):
    """True if a page should never appear on the site (by exact title or prefix)."""
    if not title:
        return False
    if title in EXCLUDE_TITLES:
        return True
    return any(title.startswith(p) for p in EXCLUDE_PREFIXES)

# Display-title overrides — rename a page in the portal without touching
# Confluence. Keyed by the page's Confluence title.
TITLE_OVERRIDES = {
    'Customer Release Notes for Evidence Cloud': 'Release Notes',
}


def display_title(page):
    """Portal-facing title for a page, applying TITLE_OVERRIDES."""
    return TITLE_OVERRIDES.get(page.title, page.title)

# Pages whose direct children are version roots.
# Title pattern → matched exactly.
VERSION_CONTAINER_TITLES = [
    'User Documentation per Release Version',
]

# Regex to extract version label from page titles like "V5.5.8", "V5.5.4 - current version"
VERSION_LABEL_RE = re.compile(r'[Vv](\d+\.\d+(?:\.\d+)?)')

# Regex for legacy version pages like "(v1.0) Evidence Cloud Documentation"
LEGACY_VERSION_RE = re.compile(r'^\(v(\d+\.\d+(?:\.\d+)?)\)\s+')

# ── Explicit version config ──────────────────────────────────────────────
# When a space appears here we use these exact version roots + labels instead
# of the title-regex heuristic. Needed because release names like "Altus
# Release" carry no "vX.Y" token, so the heuristic can't see them.
#   confluence_id : the version's root page
#   label         : exact label shown in the switcher
#   unwrap_to     : (optional) show the children of THIS descendant as the
#                   version's top level — lets us skip wrapper pages and
#                   surface the modules directly ("clustered per module")
#   is_latest     : marks the default/latest version
# pinned_top: pages (by confluence_id) hoisted to the top of the latest version.
VERSION_CONFIG = {
    'ECD': {
        'versions': [
            {
                'confluence_id': '689274891',          # Altus Release (May, 2026)
                'label': 'Altus Release',
                'unwrap_to': '78184449',               # CiteMed Evidence Cloud → its 4 modules
                'is_latest': True,
            },
            {
                'confluence_id': '371032142',          # V5.5.4 - current version
                'label': 'V5.5.4 User Documentation',
            },
        ],
        'pinned_top': ['696516613'],                   # Getting Started → top of latest
    },
}

# Root-level pages to gather under a synthetic "Policies" group in the
# "Other Documentation" area, mirroring how Confluence clusters them.
POLICY_TITLES = [
    'Customer Service Policy',
    'Upgrade Policy',
    'Data Security',
    'CiteMed TRIAL SERVICES TERMS 030526',
]

# Per-space shaping of the "Other Documentation" group (everything outside the
# versioned docs). Keeps it to a flat, audit-friendly set instead of mirroring
# Confluence's deep wrapper nesting.
#   unwrap: container pages removed while their children are promoted up a level
#   hide:   pages (+ their subtrees) dropped from Other Documentation entirely
# Result for ECD: just "Release Notes" and "Policies" at the top level.
OTHER_DOC_UNWRAP = {
    'ECD': ['25985282', '251297800'],  # Evidence Cloud Documentation; Customer Resource Center & Quick Start Guide
}
OTHER_DOC_HIDE = {
    'ECD': ['27525123', '688979973'],  # User Documentation per Release Version; SOP … Knowledge Base
}


def _detect_versions_explicit(space_key):
    """
    Build versions from VERSION_CONFIG[space_key] — explicit roots + labels.

    Each version's `pages` are the serialized descendants of its root (or, when
    `unwrap_to` is set, the children of that descendant — surfacing modules
    directly). `pinned_top` pages are hoisted to the front of the latest
    version. Returns (versions_list, container_ids_set) where container_ids are
    all pages that belong to a version subtree (so page_tree drops them from
    the "Other Documentation" group).
    """
    cfg = VERSION_CONFIG[space_key]
    versions = []
    container_ids = set()

    def _subtree_ids(page):
        ids = {page.id}
        for c in page.children.all():
            ids |= _subtree_ids(c)
        return ids

    for vc in cfg['versions']:
        root = DocPage.objects.filter(
            confluence_id=vc['confluence_id'], space_key=space_key, is_published=True
        ).first()
        if not root:
            continue
        # Everything under the root is "claimed" by this version.
        container_ids |= _subtree_ids(root)

        # Where the version's visible tree starts (skip wrapper pages).
        display_root = root
        if vc.get('unwrap_to'):
            inner = DocPage.objects.filter(
                confluence_id=vc['unwrap_to'], is_published=True
            ).first()
            if inner:
                display_root = inner

        top = list(display_root.children.filter(is_published=True).order_by('position', 'title'))
        pages = DocPageTreeSerializer(top, many=True).data

        versions.append({
            'label': vc['label'],
            'title': root.title,
            'slug': root.slug,
            'confluence_id': root.confluence_id,
            'page_id': root.id,
            'is_latest': bool(vc.get('is_latest')),
            'pages': pages,
        })

    if not versions:
        return [], set()

    # Hoist pinned pages (e.g. Getting Started) to the top of the latest version.
    latest = next((v for v in versions if v['is_latest']), versions[0])
    for cid in reversed(cfg.get('pinned_top', [])):
        pin = DocPage.objects.filter(
            confluence_id=cid, space_key=space_key, is_published=True
        ).first()
        if not pin:
            continue
        container_ids |= _subtree_ids(pin)
        pinned_data = DocPageTreeSerializer([pin], many=True).data
        # Avoid duplicating if already present, then prepend.
        latest['pages'] = pinned_data + [p for p in latest['pages'] if p['id'] != pin.id]

    return versions, container_ids


def _detect_versions(space_key):
    """
    Detect version roots for a space.

    Returns (versions_list, container_ids_set) where:
    - versions_list: [{label, slug, confluence_id, is_latest, page_id}]
    - container_ids_set: set of DB IDs for the version container page and its
      ancestors up to the space root — these are structural pages the frontend
      should hide when version mode is active.
    """
    # Explicit config takes precedence over the title heuristic.
    if space_key in VERSION_CONFIG:
        return _detect_versions_explicit(space_key)

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
@require_portal_user
def page_tree(request):
    """Return the full page tree grouped by space, with version info."""
    spaces = sorted(set(
        published_pages().values_list('space_key', flat=True)
    ))

    sections = []
    for space_key in spaces:
        roots = published_pages().filter(
            parent__isnull=True, space_key=space_key
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

            # Build per-version page trees from each version root's children.
            # Explicit-config versions already carry their (unwrapped + pinned)
            # pages — don't clobber them; only build for heuristic versions.
            for v in versions:
                if v.get('pages') is not None:
                    continue
                try:
                    version_root = DocPage.objects.get(pk=v['page_id'])
                    version_children = version_root.children.filter(
                        is_published=True
                    ).order_by('position', 'title')
                    v['pages'] = DocPageTreeSerializer(version_children, many=True).data
                except DocPage.DoesNotExist:
                    v['pages'] = []

            # "Other Documentation" = pages not claimed by any version subtree.
            # Drop the whole container_ids set (version roots + their subtrees +
            # any pinned pages) so they don't double up below the versions, then
            # unwrap structural containers and hide non-customer pages so only
            # the curated set (e.g. Release Notes + Policies) remains, flat.
            def _ids_for(cids):
                return set(DocPage.objects.filter(
                    space_key=space_key, confluence_id__in=cids
                ).values_list('id', flat=True))
            other_promote = _ids_for(OTHER_DOC_UNWRAP.get(space_key, []))
            other_drop = container_ids | _ids_for(OTHER_DOC_HIDE.get(space_key, []))
            section['pages'] = _filter_tree(data, other_promote, other_drop)

        # Cluster policy pages under a synthetic "Policies" group.
        section['pages'] = _cluster_policies(section['pages'])

        sections.append(section)

    # Apply display-title overrides across the whole structure.
    for section in sections:
        _apply_title_overrides(section['pages'])
        for v in section.get('versions', []):
            _apply_title_overrides(v.get('pages', []))

    return JsonResponse({'sections': sections})


def _cluster_policies(pages):
    """
    Group top-level policy pages under a synthetic, non-navigable 'Policies'
    folder node (mirrors the Policies folder in Confluence, which our sync
    can't import as a page). Order is preserved; the group is inserted where
    the first policy page was.
    """
    if not POLICY_TITLES:
        return pages
    policy_nodes, rest, insert_at = [], [], None
    for i, p in enumerate(pages):
        if p.get('title') in POLICY_TITLES:
            if insert_at is None:
                insert_at = len(rest)
            policy_nodes.append(p)
        else:
            rest.append(p)
    if not policy_nodes:
        return pages
    group = {
        'id': 'group-policies',
        'title': 'Policies',
        'slug': '',
        'is_folder': True,
        'children': policy_nodes,
        'position': 9999,
    }
    rest.insert(insert_at if insert_at is not None else len(rest), group)
    return rest


def _apply_title_overrides(pages):
    """Recursively apply TITLE_OVERRIDES to a serialized page tree (in place)."""
    if not TITLE_OVERRIDES:
        return
    for p in pages:
        if p.get('title') in TITLE_OVERRIDES:
            p['title'] = TITLE_OVERRIDES[p['title']]
        if p.get('children'):
            _apply_title_overrides(p['children'])


@require_GET
@require_portal_user
def page_detail(request, slug):
    try:
        page = published_pages().get(slug=slug)
    except DocPage.DoesNotExist:
        return JsonResponse({'error': 'Not found'}, status=404)
    data = DocPageDetailSerializer(page).data
    data['title'] = display_title(page)
    # Private S3 bucket — sign image URLs fresh per request (see media_signing).
    from portal.media_signing import sign_media_urls
    data['rendered_html'] = sign_media_urls(data.get('rendered_html', ''))
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
@require_portal_user
def search_docs(request):
    q = request.GET.get('q', '').strip()
    if not q:
        return JsonResponse({'results': []})

    # Database-agnostic search. The previous Postgres branch ran SearchRank/@@
    # against `search_vector`, but that column is a plain TextField (not a
    # tsvector), so on Postgres it errored and search returned nothing in prod.
    # icontains over title + body is reliable on both backends and more than
    # fast enough for this corpus. Title matches rank above body-only matches.
    #
    # Two modes: the default (⌘K) matches the whole query as one literal
    # substring. `match=any` (ticket deflection) matches any individual word so
    # a multi-word subject that never appears verbatim can still surface docs.
    from django.db.models import Q, Case, When, IntegerField
    if request.GET.get('match') == 'any':
        terms = [w for w in q.split() if len(w) >= 3] or [q]
        body_q = Q()
        title_q = Q()
        for w in terms:
            body_q |= Q(title__icontains=w) | Q(raw_storage__icontains=w)
            title_q |= Q(title__icontains=w)
        pages = published_pages().filter(body_q).annotate(
            _title_hit=Case(When(title_q, then=0), default=1,
                            output_field=IntegerField())
        ).order_by('_title_hit', 'title')[:20]
    else:
        pages = published_pages().filter(
            Q(title__icontains=q) | Q(raw_storage__icontains=q)
        ).annotate(
            _title_hit=Case(
                When(title__icontains=q, then=0),
                default=1,
                output_field=IntegerField(),
            )
        ).order_by('_title_hit', 'title')[:20]

    results = []
    for p in pages:
        raw = p.raw_storage or ''
        snippet = _extract_snippet(raw, q)
        section = _find_section_heading(raw, q)
        space_label = SPACE_LABELS.get(p.space_key, p.space_key)
        results.append({
            'slug': p.slug,
            'title': display_title(p),
            'snippet': snippet,
            'section': section,
            'space': space_label,
        })

    return JsonResponse({'results': results})
