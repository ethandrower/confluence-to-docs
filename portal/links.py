"""
Internal Confluence link resolution.

Confluence exports inter-page links as absolute Confluence URLs, e.g.
    https://citemed.atlassian.net/wiki/spaces/ECD/pages/12345/Some+Title

A portal reader clicking one is bounced to Confluence (which they can't
access). This module rewrites those links so they point at the equivalent
page inside the portal (/docs/<slug>), and unwraps links we can't resolve
(pages we don't host, folders/whiteboards/databases, "tiny" /wiki/x/ links)
so the reader sees plain text instead of a dead link to a login wall.

Used by:
  - the sync pipelines (so freshly synced HTML is clean), and
  - the `resolve_internal_links` management command (to fix existing pages).
"""
import re

from lxml import html as lxml_html
from lxml.etree import tostring


# Any link to our Confluence wiki host. Cheap pre-check + per-link guard.
_WIKI_MARKER = 'atlassian.net/wiki'

# Captures the numeric page ID from a Confluence *page* URL. Handles the
# normal form, the edit-v2 form, optional title slug, query string and
# trailing slash. Deliberately does NOT match /folder/, /whiteboard/,
# /database/, bare /spaces/<X>, or /wiki/x/ tiny links — those have no
# resolvable page target and get unwrapped.
_PAGE_ID_RE = re.compile(r'/wiki/spaces/[^/]+/pages/(?:edit-v2/)?(\d+)')

# Visible text that is itself a bare URL (Confluence often uses the raw URL
# as the link text for placeholder/create-page links). When we unwrap such a
# link we drop the text too — leaving a naked URL as plain text is uglier
# than a clean link and confuses readers.
_BARE_URL_TEXT_RE = re.compile(r'^\s*https?://', re.I)


def build_link_map(allowed_space_keys=None):
    """
    {confluence_id: (slug, title)} for every published page (optionally scoped
    to a set of allowed space keys, matching DOCS_ALLOWED_SPACES). Only pages
    in this map become live /docs/<slug> links; everything else is unwrapped.

    The title is carried so we can give resolved links a human-readable label
    when Confluence exported them with the raw URL as the anchor text.
    """
    from portal.models import DocPage

    qs = DocPage.objects.filter(is_published=True)
    if allowed_space_keys:
        qs = qs.filter(space_key__in=allowed_space_keys)
    return {
        cid: (slug, title)
        for cid, slug, title in qs.values_list('confluence_id', 'slug', 'title')
    }


def rewrite_internal_links(html_str, link_map):
    """
    Rewrite Confluence inter-page links in an HTML fragment.

    Returns (new_html, stats) where stats is a dict with counts:
      resolved   — links repointed to /docs/<slug>
      unwrapped  — dead Confluence links converted to plain text

    Non-Confluence links (external sites, mailto:, #anchors, existing
    /docs/ links) are left untouched.
    """
    stats = {'resolved': 0, 'unwrapped': 0}
    if not html_str or _WIKI_MARKER not in html_str:
        return html_str, stats

    # Wrap so we have a single root to parse and to serialize back from.
    frag = lxml_html.fragment_fromstring(html_str, create_parent='cm-root')

    # Collect first — mutating (drop_tag) while iterating the tree is unsafe.
    anchors = list(frag.iterfind('.//a'))
    for a in anchors:
        href = a.get('href', '')
        if not href or _WIKI_MARKER not in href:
            continue
        visible = (a.text_content() or '').strip()
        m = _PAGE_ID_RE.search(href)
        if m and m.group(1) in link_map:
            slug, title = link_map[m.group(1)]
            a.set('href', f"/docs/{slug}")
            # Confluence often exports the raw URL as the anchor text. If the
            # label is a bare URL (or empty), replace it with the target page's
            # title so the reader sees "Protocol Set-Up", not a wiki URL.
            if not visible or _BARE_URL_TEXT_RE.match(visible):
                for child in list(a):
                    a.remove(child)
                a.text = title
            stats['resolved'] += 1
        else:
            # Unresolvable Confluence link → unwrap.
            if not visible or _BARE_URL_TEXT_RE.match(visible):
                # Label is a raw URL (or empty) — drop the element entirely;
                # leaving a naked Confluence URL as text is worse than nothing.
                a.drop_tree()
            else:
                # Keep the meaningful link text, drop only the dead <a>.
                a.drop_tag()
            stats['unwrapped'] += 1

    if stats['resolved'] == 0 and stats['unwrapped'] == 0:
        return html_str, stats

    # Serialize the wrapper's inner HTML (text + children), not the wrapper.
    inner = frag.text or ''
    for child in frag:
        inner += tostring(child, encoding='unicode')
    return inner, stats
