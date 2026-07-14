"""Read-only, best-effort Jira client for showing a linked issue's live status
on a support ticket (admin-only). Reuses the Atlassian API token the Confluence
sync already uses. NEVER raises into the request path — returns None on any
failure, so the admin sees last-cached status (or "unavailable") instead of an
error.
"""
import logging

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

TIMEOUT = 5  # seconds


def fetch_issue(key):
    """Return {'status', 'status_category', 'summary'} for a Jira issue key,
    or None if creds are missing or the fetch fails."""
    domain = getattr(settings, 'CONFLUENCE_DOMAIN', '')
    email = getattr(settings, 'CONFLUENCE_EMAIL', '')
    token = getattr(settings, 'CONFLUENCE_API_TOKEN', '')
    if not (domain and email and token and key):
        return None
    url = f'https://{domain}/rest/api/3/issue/{key}'
    try:
        r = requests.get(
            url, params={'fields': 'status,summary'}, auth=(email, token),
            headers={'Accept': 'application/json'}, timeout=TIMEOUT,
        )
        if r.status_code != 200:
            logger.info('jira fetch %s → HTTP %s', key, r.status_code)
            return None
        fields = (r.json() or {}).get('fields', {}) or {}
        status = fields.get('status') or {}
        category = status.get('statusCategory') or {}
        return {
            'status': status.get('name', ''),
            'status_category': category.get('key', ''),  # new | indeterminate | done
            'summary': fields.get('summary', ''),
        }
    except Exception as e:  # network, timeout, JSON, anything
        logger.warning('jira fetch %s failed: %s', key, e)
        return None


def adf_to_text(node):
    """Flatten an Atlassian Document Format value to plain text.

    Jira Cloud returns comment bodies as ADF (a nested doc/paragraph/text tree),
    not a string. We only need a readable rendering: inline `text` and `mention`
    nodes concatenate, `hardBreak` becomes a newline, and block nodes
    (paragraph, heading, list item, …) are separated by a blank line. Unknown
    node types are traversed for their `content` so nothing is silently lost.
    """
    if not node:
        return ''
    node_type = node.get('type')
    if node_type == 'text':
        return node.get('text', '')
    if node_type == 'mention':
        return (node.get('attrs') or {}).get('text', '')
    if node_type == 'hardBreak':
        return '\n'
    children = node.get('content') or []
    # Block-level containers stack vertically; inline runs concatenate.
    BLOCK = {'doc', 'paragraph', 'heading', 'listItem', 'bulletList',
             'orderedList', 'blockquote', 'codeBlock'}
    if node_type in BLOCK:
        parts = [adf_to_text(c) for c in children]
        joined = '\n\n'.join(p for p in parts if p) if node_type == 'doc' \
            else ''.join(parts)
        return joined
    return ''.join(adf_to_text(c) for c in children)


def _creds():
    """(domain, auth) if configured, else (None, None)."""
    domain = getattr(settings, 'CONFLUENCE_DOMAIN', '')
    email = getattr(settings, 'CONFLUENCE_EMAIL', '')
    token = getattr(settings, 'CONFLUENCE_API_TOKEN', '')
    if domain and email and token:
        return domain, (email, token)
    return None, None


def _text_to_adf(text):
    """Plain text → an Atlassian Document Format doc (Jira comment bodies are
    ADF, not strings). Always returns a valid doc with at least one paragraph."""
    blocks = (text or '').split('\n\n')
    paragraphs = [
        {'type': 'paragraph',
         'content': ([{'type': 'text', 'text': b}] if b else [])}
        for b in blocks
    ] or [{'type': 'paragraph', 'content': []}]
    return {'type': 'doc', 'version': 1, 'content': paragraphs}


def add_comment(key, text, internal=False):
    """Add a comment to an issue. Returns True on success. Best-effort.

    On a JSM service desk a REST comment defaults to PUBLIC (customer-visible);
    pass internal=True to mark it internal via `sd.public.comment` — required
    for staff-facing notes that must never reach the customer."""
    domain, auth = _creds()
    if not (domain and key):
        return False
    payload = {'body': _text_to_adf(text)}
    if internal:
        payload['properties'] = [
            {'key': 'sd.public.comment', 'value': {'internal': True}}]
    try:
        r = requests.post(
            f'https://{domain}/rest/api/3/issue/{key}/comment', json=payload,
            auth=auth, headers={'Accept': 'application/json',
                                'Content-Type': 'application/json'}, timeout=TIMEOUT)
        return r.status_code in (200, 201)
    except Exception as e:
        logger.warning('jira comment on %s failed: %s', key, e)
        return False


def create_remote_link(key, url, title):
    """Add a 'remote link' on the issue pointing back to the portal ticket.
    Returns True on success. Best-effort."""
    domain, auth = _creds()
    if not (domain and key and url):
        return False
    try:
        r = requests.post(
            f'https://{domain}/rest/api/3/issue/{key}/remotelink',
            json={'object': {'url': url, 'title': title}},
            auth=auth, headers={'Accept': 'application/json',
                                'Content-Type': 'application/json'}, timeout=TIMEOUT)
        return r.status_code in (200, 201)
    except Exception as e:
        logger.warning('jira remotelink on %s failed: %s', key, e)
        return False


def fetch_comments(key, max_results=100):
    """Return a ticket-linked issue's comments as
    [{'id','author','body','created','public'}], oldest first. Best-effort:
    returns [] on missing creds or any failure (never raises into a caller).

    `public` mirrors JSM's `jsdPublic` (was this comment shown to the customer).
    It defaults to False when the flag is absent — fail-safe, so a comment Jira
    never marked customer-visible is never surfaced to a customer here.
    """
    domain = getattr(settings, 'CONFLUENCE_DOMAIN', '')
    email = getattr(settings, 'CONFLUENCE_EMAIL', '')
    token = getattr(settings, 'CONFLUENCE_API_TOKEN', '')
    if not (domain and email and token and key):
        return []
    url = f'https://{domain}/rest/api/3/issue/{key}/comment'
    try:
        r = requests.get(
            url, params={'maxResults': max_results}, auth=(email, token),
            headers={'Accept': 'application/json'}, timeout=TIMEOUT,
        )
        if r.status_code != 200:
            logger.info('jira comments %s → HTTP %s', key, r.status_code)
            return []
        comments = (r.json() or {}).get('comments', []) or []
        return [{
            'id': str(c.get('id') or ''),
            'author': (c.get('author') or {}).get('displayName', ''),
            'body': adf_to_text(c.get('body')),
            'created': c.get('created', ''),
            'public': bool(c.get('jsdPublic')),
        } for c in comments]
    except Exception as e:  # network, timeout, JSON, anything
        logger.warning('jira comments %s failed: %s', key, e)
        return []
