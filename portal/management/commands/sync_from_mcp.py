"""
Sync Confluence pages into the DocPage model from an MCP JSON dump.

Usage:
    python manage.py sync_from_mcp <path_to_json_file> [--space-key ECD]

The JSON file should be the raw output from the MCP getPagesInConfluenceSpace tool.
"""
import json
import re

import markdown
from django.core.management.base import BaseCommand
from django.utils.text import slugify

from portal.models import DocPage


def preprocess_markdown(md):
    """
    Fix common issues in Confluence-exported markdown before HTML conversion.

    1. Normalize pipe tables — the MCP markdown often has broken multi-line cells
       where content after a newline inside a table row loses its pipe structure.
       We detect this and merge continuation lines back into the table.

    2. Remove zero-width chars and Confluence placeholder noise.
    """
    if not md:
        return ''

    # Remove zero-width spaces (‌ = \u200c) that Confluence inserts
    md = md.replace('\u200c', '')

    # Fix tables: the markdown table extension breaks when cells contain newlines.
    # Confluence exports cells like:
    #   | 10 am - 14 am CET  \n  \nand/or  \n  \n18 pm - 22 pm CET | Product Manager |
    # We need to collapse newlines inside pipe-delimited rows into a single line.
    lines = md.split('\n')
    result = []
    row_buffer = None

    for line in lines:
        stripped = line.strip()

        if row_buffer is not None:
            # We're accumulating a multi-line table row
            if stripped == '':
                # Blank line inside a cell — skip it, keep buffering
                continue
            elif stripped.endswith('|') and not stripped.startswith('|'):
                # e.g. "Full Stack  |" or "18 pm - 22 pm CET | Product Manager  |"
                # Continuation that closes the row
                row_buffer += ' ' + stripped
                result.append(row_buffer)
                row_buffer = None
            elif stripped.startswith('|') and stripped.endswith('|'):
                # Previous row was incomplete — flush it, this is a new complete row
                result.append(row_buffer + ' |')
                result.append(stripped)
                row_buffer = None
            elif stripped.startswith('|') and not stripped.endswith('|'):
                # Previous row incomplete, new incomplete row — flush old, start new
                result.append(row_buffer + ' |')
                row_buffer = stripped
            elif stripped.startswith('#'):
                # Heading — table is over
                result.append(row_buffer + ' |')
                result.append(line)
                row_buffer = None
            else:
                # Plain text continuation inside a cell (e.g. "and/or")
                row_buffer += ' ' + stripped
        elif stripped.startswith('|') and stripped.endswith('|'):
            # Complete single-line row
            result.append(line)
        elif stripped.startswith('|') and not stripped.endswith('|'):
            # Row started but doesn't end — cell has newlines
            row_buffer = stripped
        else:
            result.append(line)

    if row_buffer is not None:
        result.append(row_buffer)

    md = '\n'.join(result)

    # Clean up <custom> tags in markdown source
    # Emoji shortcodes
    md = re.sub(
        r'<custom[^>]*data-type="emoji"[^>]*>(:[a-z_]+:)</custom>',
        lambda m: _emoji(m.group(1)),
        md, flags=re.IGNORECASE
    )
    # Mentions
    md = re.sub(r'<custom[^>]*data-type="mention"[^>]*>[^<]*</custom>', '', md, flags=re.IGNORECASE)
    # Placeholders
    md = re.sub(r'<custom[^>]*data-type="placeholder"[^>]*>[^<]*</custom>', '', md, flags=re.IGNORECASE)
    # Status badges
    md = re.sub(
        r'<custom[^>]*data-type="status"[^>]*>([^<]*)</custom>',
        r'**\1**',
        md, flags=re.IGNORECASE
    )
    # Smart links
    md = re.sub(
        r'<custom[^>]*data-type="smartlink"[^>]*>(https?://[^<]*)</custom>',
        r'[\1](\1)',
        md, flags=re.IGNORECASE
    )
    # Remove any remaining custom tags
    md = re.sub(r'</?custom[^>]*>', '', md, flags=re.IGNORECASE)

    return md


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
}


def _emoji(code):
    return EMOJI_MAP.get(code, '')


class Command(BaseCommand):
    help = 'Load Confluence pages from an MCP JSON dump into the database'

    def add_arguments(self, parser):
        parser.add_argument('json_file', help='Path to the MCP JSON dump file')
        parser.add_argument('--space-key', default='ECD', help='Space key to tag pages with')

    def handle(self, *args, **options):
        json_file = options['json_file']
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

            # Preprocess markdown to fix tables and clean custom tags
            cleaned_md = preprocess_markdown(body_md)

            # Convert markdown to HTML
            rendered_html = markdown.markdown(
                cleaned_md,
                extensions=['tables', 'fenced_code', 'codehilite', 'toc', 'nl2br'],
            )

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
