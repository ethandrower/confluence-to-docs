"""
Confluence client for the docs portal sync engine.

Thin wrapper around trinity-atlassian-cli that:
- Uses Django settings for credentials (rather than trinity's env/config resolution)
- Adds attachment downloading (not in trinity)
- Provides the get_all_pages generator used by sync.py
"""
import os
import requests
import logging
from django.conf import settings

logger = logging.getLogger(__name__)


def _trinity_env():
    """Temporarily set trinity's expected env vars from Django settings."""
    return {
        'ATLASSIAN_EMAIL': settings.CONFLUENCE_EMAIL,
        'ATLASSIAN_API_TOKEN': settings.CONFLUENCE_API_TOKEN,
        'ATLASSIAN_DOMAIN': settings.CONFLUENCE_DOMAIN,
    }


class ConfluenceClient:
    def __init__(self):
        self.domain = settings.CONFLUENCE_DOMAIN
        self.auth = (settings.CONFLUENCE_EMAIL, settings.CONFLUENCE_API_TOKEN)
        self.base = f"https://{self.domain}/wiki"
        # Inject credentials into env so trinity's auth.py picks them up
        os.environ.setdefault('ATLASSIAN_EMAIL', settings.CONFLUENCE_EMAIL)
        os.environ.setdefault('ATLASSIAN_API_TOKEN', settings.CONFLUENCE_API_TOKEN)
        os.environ.setdefault('ATLASSIAN_DOMAIN', settings.CONFLUENCE_DOMAIN)
        # Override in case they were already set with different values
        os.environ['ATLASSIAN_EMAIL'] = settings.CONFLUENCE_EMAIL
        os.environ['ATLASSIAN_API_TOKEN'] = settings.CONFLUENCE_API_TOKEN
        os.environ['ATLASSIAN_DOMAIN'] = settings.CONFLUENCE_DOMAIN

    def get_all_pages(self, space_key):
        """
        Generator yielding all pages in a space via trinity's list_space_pages.
        Normalises the response shape to match what sync.py expects.
        """
        from trinity.confluence.list_space_pages import list_space_pages
        result = list_space_pages(space_key)
        if result.get('error'):
            raise RuntimeError(f"list_space_pages failed: {result.get('message')}")
        for page in result.get('pages', []):
            # Normalise to the shape sync.py reads:
            # page['version']['number'], page['ancestors'], page['id'], page['title']
            yield {
                'id': page['id'],
                'title': page['title'],
                'version': {'number': page.get('version', 1)},
                'ancestors': [
                    {'id': a['id'], 'title': a['title']}
                    for a in page.get('ancestors', [])
                ],
            }

    def get_page_body(self, page_id):
        """
        Fetch a page with storage-format body via trinity's get_confluence_page.
        Normalises response to the shape sync.py expects.
        """
        from trinity.confluence.get_page import get_confluence_page
        result = get_confluence_page(page_id, include_body=True, include_ancestors=True)
        if result.get('error'):
            raise RuntimeError(f"get_confluence_page failed: {result.get('message')}")
        # Normalise: sync.py reads full_page['body']['storage']['value'] and full_page['ancestors']
        return {
            'id': result.get('id'),
            'title': result.get('title'),
            'version': {'number': result.get('version', 1)},
            'ancestors': [
                {'id': a['id'], 'title': a['title']}
                for a in result.get('ancestors', [])
            ],
            'body': {
                'storage': {
                    'value': result.get('body', ''),
                }
            },
        }

    def download_attachment(self, page_id, filename):
        """
        Download a binary attachment from a Confluence page.
        Not in trinity (portal-specific) — uses direct authenticated request.
        Returns a requests.Response with stream=True, or None if not found.
        """
        session = requests.Session()
        session.auth = self.auth
        try:
            r = session.get(
                f"{self.base}/rest/api/content/{page_id}/child/attachment",
                params={'filename': filename},
                timeout=30,
            )
            r.raise_for_status()
            results = r.json().get('results', [])
            if not results:
                return None
            download_url = results[0]['_links']['download']
            return session.get(f"{self.base}{download_url}", stream=True, timeout=60)
        except Exception as e:
            logger.warning(f"download_attachment({page_id}, {filename}): {e}")
            return None
