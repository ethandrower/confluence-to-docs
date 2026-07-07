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
