"""
Sync Confluence pages into the DocPage model from an MCP JSON dump.

Usage:
    python manage.py sync_from_mcp <path_to_json_file> [--space-key ECD]
    python manage.py sync_from_mcp --rerender   # re-process all existing pages

The JSON file should be the raw output from the MCP getPagesInConfluenceSpace tool.
"""
import json
import re

import markdown
from django.core.management.base import BaseCommand
from django.utils.text import slugify

from portal.models import DocPage


# ═══════════════════════════════════════════════════════════════
# STEP 1: Markdown preprocessing — fix Confluence export quirks
# ═══════════════════════════════════════════════════════════════

def preprocess_markdown(md):
    """
    Fix common issues in Confluence-exported markdown before HTML conversion.

    1. Normalize pipe tables (broken multi-line cells)
    2. Remove zero-width chars and Confluence placeholder noise
    3. Convert numbered bold headings to proper markdown headings
    4. Handle sub-section numbering patterns (3.1.1.)
    """
    if not md:
        return ''

    # Remove zero-width spaces that Confluence inserts
    md = md.replace('\u200c', '')

    # ── Fix tables ────────────────────────────────────────
    md = _fix_broken_tables(md)

    # ── Clean Confluence custom tags ──────────────────────
    md = _clean_custom_tags(md)

    # ── Fix structural patterns ───────────────────────────
    md = _fix_numbered_headings(md)

    return md


def _fix_broken_tables(md):
    """Collapse multi-line table rows back into single lines."""
    lines = md.split('\n')
    result = []
    row_buffer = None

    for line in lines:
        stripped = line.strip()

        if row_buffer is not None:
            if stripped == '':
                continue
            elif stripped.endswith('|') and not stripped.startswith('|'):
                row_buffer += ' ' + stripped
                result.append(row_buffer)
                row_buffer = None
            elif stripped.startswith('|') and stripped.endswith('|'):
                result.append(row_buffer + ' |')
                result.append(stripped)
                row_buffer = None
            elif stripped.startswith('|') and not stripped.endswith('|'):
                result.append(row_buffer + ' |')
                row_buffer = stripped
            elif stripped.startswith('#'):
                result.append(row_buffer + ' |')
                result.append(line)
                row_buffer = None
            else:
                row_buffer += ' ' + stripped
        elif stripped.startswith('|') and stripped.endswith('|'):
            result.append(line)
        elif stripped.startswith('|') and not stripped.endswith('|'):
            row_buffer = stripped
        else:
            result.append(line)

    if row_buffer is not None:
        result.append(row_buffer)

    return '\n'.join(result)


def _clean_custom_tags(md):
    """Strip Confluence-specific custom XML tags from markdown."""
    # Emoji shortcodes
    md = re.sub(
        r'<custom[^>]*data-type="emoji"[^>]*>(:[a-z_]+:)</custom>',
        lambda m: EMOJI_MAP.get(m.group(1), ''),
        md, flags=re.IGNORECASE
    )
    # Mentions
    md = re.sub(r'<custom[^>]*data-type="mention"[^>]*>[^<]*</custom>', '', md, flags=re.IGNORECASE)
    # Placeholders
    md = re.sub(r'<custom[^>]*data-type="placeholder"[^>]*>[^<]*</custom>', '', md, flags=re.IGNORECASE)
    # Status badges
    md = re.sub(
        r'<custom[^>]*data-type="status"[^>]*>([^<]*)</custom>',
        r'**\1**', md, flags=re.IGNORECASE
    )
    # Smart links
    md = re.sub(
        r'<custom[^>]*data-type="smartlink"[^>]*>(https?://[^<]*)</custom>',
        r'[\1](\1)', md, flags=re.IGNORECASE
    )
    # Remove remaining custom tags
    md = re.sub(r'</?custom[^>]*>', '', md, flags=re.IGNORECASE)
    return md


def _fix_numbered_headings(md):
    """
    Convert legal/policy numbered headings to proper markdown headings.

    Patterns handled:
      1. **HEADING TEXT**      → ## HEADING TEXT
      **HEADING TEXT**         → ## HEADING TEXT  (standalone bold ALL CAPS line)
      1. LABEL. Body text...  → keeps as list but with proper structure
      **3.1.1.** text         → **3.1.1.** text  (preserve sub-section numbering)
    """
    lines = md.split('\n')
    result = []

    for line in lines:
        stripped = line.strip()

        # Pattern: "1. **HEADING TEXT**" or "2. **HEADING TEXT**  "
        # A numbered item where the ENTIRE content is bold = section heading
        m = re.match(r'^\d+\.\s+\*\*([^*]+)\*\*\s*$', stripped)
        if m:
            heading_text = m.group(1).strip()
            result.append(f'\n## {heading_text}\n')
            continue

        # Pattern: "**ALL CAPS TEXT**" on its own line (not inside a sentence)
        m = re.match(r'^\*\*([A-Z][A-Z\s,\-&/]+)\*\*\s*$', stripped)
        if m:
            heading_text = m.group(1).strip()
            # Only convert if it's actually all caps (not just starting with caps)
            letters = re.sub(r'[^a-zA-Z]', '', heading_text)
            if letters and letters == letters.upper() and len(letters) >= 3:
                result.append(f'\n## {heading_text}\n')
                continue

        # Pattern: "1. ALL CAPS LABEL." standalone (no body text after)
        # These are sub-section headings like "1. PHYSICAL SECURITY MEASURES."
        # Convert to ### heading
        m = re.match(r'^\d+\.\s+([A-Z][A-Z\s,\-&/]+\.?)\s*$', stripped)
        if m:
            label = m.group(1).strip()
            letters = re.sub(r'[^a-zA-Z]', '', label)
            if letters and letters == letters.upper() and len(letters) >= 3:
                result.append(f'\n### {label}\n')
                continue

        # Pattern: "1. ALL CAPS LABEL. Body text continues..."
        # Convert to: "**LABEL.** Body text continues..."
        m = re.match(r'^\d+\.\s+([A-Z][A-Z\s,\-&/]+\.)\s+(.+)$', stripped)
        if m:
            label = m.group(1).strip()
            body = m.group(2).strip()
            letters = re.sub(r'[^a-zA-Z]', '', label)
            if letters and letters == letters.upper() and len(letters) >= 3:
                result.append(f'\n**{label}** {body}\n')
                continue

        # Pattern: "**3.1.1.**" or "**3.1.1.** TEXT" — sub-section numbering
        m = re.match(r'^\*\*(\d+(?:\.\d+)+\.?)\*\*\s*(.*)', stripped)
        if m:
            num = m.group(1)
            rest = m.group(2).strip()
            # Clean up empty <code> tags that sometimes appear
            rest = re.sub(r'`+', '', rest)
            if rest:
                result.append(f'\n**{num}** {rest}\n')
            else:
                result.append(f'\n**{num}**\n')
            continue

        result.append(line)

    return '\n'.join(result)


# ═══════════════════════════════════════════════════════════════
# STEP 2: HTML post-processing — fix structural issues
# ═══════════════════════════════════════════════════════════════

def postprocess_html(html):
    """
    Fix structural issues in the generated HTML.

    1. Add IDs to headings for TOC/anchor support
    2. Clean up empty paragraphs
    3. Fix orphaned list items that should be headings
    """
    if not html:
        return ''

    # Add IDs to headings that don't have them
    def add_heading_id(match):
        tag = match.group(1)
        attrs = match.group(2) or ''
        text = match.group(3)
        if 'id="' in attrs:
            return match.group(0)
        slug = re.sub(r'[^\w\s-]', '', text.lower()).strip()
        slug = re.sub(r'\s+', '-', slug)
        return f'<{tag} id="{slug}"{attrs}>{text}'

    html = re.sub(
        r'<(h[1-6])(\s[^>]*)?>([^<]+)',
        add_heading_id, html
    )

    # Remove empty paragraphs
    html = re.sub(r'<p>\s*</p>', '', html)

    # Remove excessive <br> tags (more than 2 in a row)
    html = re.sub(r'(<br\s*/?>){3,}', '<br><br>', html)

    # Fix bold-only list items that are really section headers
    # Pattern: <li><strong>ALL CAPS</strong></li> with nothing else
    def promote_list_heading(match):
        text = match.group(1).strip()
        letters = re.sub(r'[^a-zA-Z]', '', text)
        if letters and letters == letters.upper() and len(letters) >= 3:
            slug = re.sub(r'[^\w\s-]', '', text.lower()).strip()
            slug = re.sub(r'\s+', '-', slug)
            return f'</ol>\n<h3 id="{slug}">{text}</h3>\n<ol>'
        return match.group(0)

    html = re.sub(
        r'<li>\s*<strong>([^<]+)</strong>\s*</li>',
        promote_list_heading, html
    )

    # Also handle: <li><p><strong>ALL CAPS</strong></p></li>
    html = re.sub(
        r'<li>\s*<p>\s*<strong>([^<]+)</strong>\s*</p>\s*</li>',
        promote_list_heading, html
    )

    # Clean up empty <ol></ol> pairs left after promotion
    html = re.sub(r'<ol>\s*</ol>', '', html)

    return html


# ═══════════════════════════════════════════════════════════════
# STEP 3: Combined render pipeline
# ═══════════════════════════════════════════════════════════════

def render_markdown_to_html(md):
    """Full pipeline: preprocess → convert → post-process."""
    cleaned = preprocess_markdown(md)
    html = markdown.markdown(
        cleaned,
        extensions=['tables', 'fenced_code', 'codehilite', 'toc', 'nl2br'],
    )
    html = postprocess_html(html)
    return html, cleaned


# ═══════════════════════════════════════════════════════════════
# Emoji map
# ═══════════════════════════════════════════════════════════════

EMOJI_MAP = {
    ':blue_book:': '\U0001F4D8', ':clipboard:': '\U0001F4CB', ':thinking:': '\U0001F914',
    ':dart:': '\U0001F3AF', ':calendar_spiral:': '\U0001F5D3', ':triangular_flag_on_post:': '\U0001F6A9',
    ':link:': '\U0001F517', ':card_box:': '\U0001F5C3', ':white_check_mark:': '\u2705',
    ':star2:': '\U0001F31F', ':goal:': '\U0001F3AF', ':art:': '\U0001F3A8',
    ':speaking_head:': '\U0001F5E3', ':arrow_heading_up:': '\u2934\uFE0F',
    ':busts_in_silhouette:': '\U0001F465', ':rainbow:': '\U0001F308',
    ':books:': '\U0001F4DA', ':plus:': '\u2795', ':minus:': '\u2796',
    ':warning:': '\u26A0\uFE0F', ':bulb:': '\U0001F4A1', ':memo:': '\U0001F4DD',
    ':gear:': '\u2699\uFE0F', ':rocket:': '\U0001F680', ':lock:': '\U0001F512',
    ':key:': '\U0001F511', ':mag:': '\U0001F50D', ':wrench:': '\U0001F527',
    ':file_folder:': '\U0001F4C1', ':chart_with_upwards_trend:': '\U0001F4C8',
    ':construction:': '\U0001F6A7',
}


# ═══════════════════════════════════════════════════════════════
# Management command
# ═══════════════════════════════════════════════════════════════

class Command(BaseCommand):
    help = 'Load Confluence pages from an MCP JSON dump, or re-render existing pages'

    def add_arguments(self, parser):
        parser.add_argument('json_file', nargs='?', default=None,
                            help='Path to the MCP JSON dump file')
        parser.add_argument('--space-key', default='ECD',
                            help='Space key to tag pages with')
        parser.add_argument('--rerender', action='store_true',
                            help='Re-render all existing pages from raw_storage')

    def handle(self, *args, **options):
        if options['rerender']:
            return self._rerender()

        json_file = options['json_file']
        if not json_file:
            self.stderr.write(self.style.ERROR(
                'Provide a JSON file path, or use --rerender to re-process existing pages'
            ))
            return

        space_key = options['space_key']

        with open(json_file) as f:
            data = json.load(f)

        # MCP tool output is wrapped in [{type, text}] array
        if isinstance(data, list) and data and 'text' in data[0]:
            raw = json.loads(data[0]['text'])
        else:
            raw = data

        pages = raw.get('results', raw) if isinstance(raw, dict) else raw
        self.stdout.write(f'Found {len(pages)} pages in dump')

        page_map = {}
        for p in pages:
            page_map[str(p['id'])] = p

        created = 0
        updated = 0
        for idx, p in enumerate(pages):
            cid = str(p['id'])
            title = p.get('title', 'Untitled')
            body_md = p.get('body', '')
            version = p.get('version', {})
            version_num = version.get('number', 1) if isinstance(version, dict) else 1

            rendered_html, cleaned_md = render_markdown_to_html(body_md)

            # Generate unique slug
            base_slug = slugify(title)[:200] or f'page-{cid}'
            slug = base_slug
            counter = 1
            while DocPage.objects.filter(slug=slug).exclude(confluence_id=cid).exists():
                counter += 1
                slug = f'{base_slug}-{counter}'

            obj, was_created = DocPage.objects.update_or_create(
                confluence_id=cid,
                defaults={
                    'title': title,
                    'slug': slug,
                    'rendered_html': rendered_html,
                    'raw_storage': cleaned_md,
                    'version': version_num,
                    'confluence_version': version_num,
                    'space_key': space_key,
                    'is_published': True,
                    'position': idx,
                },
            )
            if was_created:
                created += 1
            else:
                updated += 1

        # Second pass: parent relationships
        linked = 0
        for p in pages:
            parent_id = p.get('parentId')
            if parent_id and str(parent_id) in page_map:
                try:
                    child = DocPage.objects.get(confluence_id=str(p['id']))
                    parent = DocPage.objects.get(confluence_id=str(parent_id))
                    if child.parent_id != parent.id:
                        child.parent = parent
                        child.save(update_fields=['parent'])
                        linked += 1
                except DocPage.DoesNotExist:
                    pass

        self.stdout.write(self.style.SUCCESS(
            f'Done: {created} created, {updated} updated, {linked} parent links set'
        ))

    def _rerender(self):
        """Re-render all existing pages from their raw_storage markdown."""
        pages = DocPage.objects.filter(is_published=True).exclude(raw_storage='')
        total = pages.count()
        self.stdout.write(f'Re-rendering {total} pages...')

        updated = 0
        errors = 0
        for page in pages.iterator():
            try:
                rendered_html, cleaned_md = render_markdown_to_html(page.raw_storage)
                page.rendered_html = rendered_html
                page.raw_storage = cleaned_md
                page.save(update_fields=['rendered_html', 'raw_storage'])
                updated += 1
            except Exception as e:
                errors += 1
                self.stderr.write(f'  Error on "{page.title}": {e}')

        self.stdout.write(self.style.SUCCESS(
            f'Done: {updated} pages re-rendered, {errors} errors'
        ))
