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


def verify_issue(key):
    """Does this issue exist? Returns ('ok', data) | ('missing', None) |
    ('unreachable', None).

    `fetch_issue` collapses every failure to None, which is right for a
    best-effort status refresh but wrong when deciding whether to accept a key
    an agent typed: "that issue doesn't exist" and "Jira didn't answer" want
    opposite handling. Only an unambiguous 404 counts as missing — a 403, an
    outage or broken credentials all report unreachable, so a Jira problem
    never blocks an agent from recording a link they know is right.
    """
    domain, auth = _creds()
    if not (domain and key):
        return 'unreachable', None
    try:
        r = requests.get(
            f'https://{domain}/rest/api/3/issue/{key}',
            params={'fields': 'status,summary'}, auth=auth,
            headers={'Accept': 'application/json'}, timeout=TIMEOUT,
        )
        if r.status_code == 404:
            return 'missing', None
        if r.status_code != 200:
            logger.info('jira verify %s → HTTP %s', key, r.status_code)
            return 'unreachable', None
        fields = (r.json() or {}).get('fields', {}) or {}
        status = fields.get('status') or {}
        category = status.get('statusCategory') or {}
        return 'ok', {
            'status': status.get('name', ''),
            'status_category': category.get('key', ''),
            'summary': fields.get('summary', ''),
        }
    except Exception as e:
        logger.warning('jira verify %s failed: %s', key, e)
        return 'unreachable', None


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
    # Not every field is ADF — a v2-created issue can return a bare string for
    # description. Pass it straight through rather than raising.
    if isinstance(node, str):
        return node
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


def _get(path, params=None):
    """GET a Jira/Agile path, returning parsed JSON or None. Best-effort."""
    domain, auth = _creds()
    if not domain:
        return None
    try:
        r = requests.get(f'https://{domain}{path}', params=params, auth=auth,
                         headers={'Accept': 'application/json'}, timeout=TIMEOUT)
        if r.status_code != 200:
            logger.warning('jira GET %s → HTTP %s: %s', path, r.status_code, r.text[:200])
            return None
        return r.json()
    except Exception as e:
        logger.warning('jira GET %s failed: %s', path, e)
        return None


def list_issue_types(project):
    """Creatable, non-subtask issue types for a project: [{'id','name'}]."""
    data = _get('/rest/api/3/issue/createmeta',
                {'projectKeys': project, 'expand': 'projects.issuetypes'})
    projects = (data or {}).get('projects') or []
    if not projects:
        return []
    return [{'id': str(t.get('id')), 'name': t.get('name')}
            for t in projects[0].get('issuetypes', [])
            if not t.get('subtask') and t.get('hierarchyLevel', 0) == 0]


def list_priorities():
    """Jira priorities: [{'id','name'}]. Site-wide, not per project."""
    data = _get('/rest/api/3/priority')
    return [{'id': str(p.get('id')), 'name': p.get('name')} for p in (data or [])]


def find_epic(project, summary):
    """The open epic in `project` whose summary matches exactly, or None.

    Done/Declined epics are skipped so a closed one from a previous cycle
    doesn't silently swallow new escalations.
    """
    escaped = (summary or '').replace('"', '\\"')
    jql = (f'project = "{project}" AND issuetype = Epic '
           f'AND summary ~ "\\"{escaped}\\"" AND statusCategory != Done '
           f'ORDER BY created ASC')
    data = _get('/rest/api/3/search/jql', {'jql': jql, 'maxResults': 50,
                                           'fields': 'summary'})
    for issue in (data or {}).get('issues', []):
        # `~` is a fuzzy text match, so confirm the summary really is the one
        # we asked for before filing anything under it.
        if (issue.get('fields', {}).get('summary') or '').strip().lower() == summary.strip().lower():
            return issue.get('key')
    return None


def find_or_create_epic(project, summary, epic_type_id, description=''):
    """Return the key of `project`'s escalation epic, creating it if absent."""
    existing = find_epic(project, summary)
    if existing:
        return existing
    return create_issue(project, summary, description or summary, epic_type_id)


def active_sprint_id(project):
    """The id of the project board's active sprint, or None.

    Resolved at runtime through the Agile API rather than from a hardcoded
    custom-field id, because the sprint field id differs per site and both
    target projects have their own board.
    """
    boards = _get('/rest/agile/1.0/board', {'projectKeyOrId': project})
    for board in (boards or {}).get('values', []):
        sprints = _get(f"/rest/agile/1.0/board/{board.get('id')}/sprint",
                       {'state': 'active'})
        values = (sprints or {}).get('values') or []
        if values:
            return values[0].get('id')
    return None


def add_to_sprint(sprint_id, key):
    """Move an issue into a sprint. True on success."""
    domain, auth = _creds()
    if not (domain and sprint_id and key):
        return False
    try:
        r = requests.post(f'https://{domain}/rest/agile/1.0/sprint/{sprint_id}/issue',
                          json={'issues': [key]}, auth=auth,
                          headers={'Accept': 'application/json',
                                   'Content-Type': 'application/json'}, timeout=TIMEOUT)
        if r.status_code not in (200, 201, 204):
            logger.warning('jira sprint add %s → HTTP %s: %s',
                           key, r.status_code, r.text[:200])
            return False
        return True
    except Exception as e:
        logger.warning('jira sprint add %s failed: %s', key, e)
        return False


def create_issue(project, summary, body_text, issue_type_id):
    """Create a Jira issue and return its key, or None. Best-effort (never
    raises). This is Option A: the portal creates the issue via the API so it
    gets the key back and links immediately — reliable, no email dependency."""
    return create_issue_ex(project, summary, body_text, issue_type_id)


def create_issue_ex(project, summary, body_text, issue_type_id,
                    priority_id=None, parent_key=None):
    """create_issue plus optional priority and epic parent.

    If the create is rejected while carrying parent/priority, it retries once
    without them. A project whose screens don't expose those fields should
    still get the issue — an unparented escalation is recoverable, a lost one
    isn't. The caller learns what actually stuck by re-reading the issue.
    """
    domain, auth = _creds()
    if not (domain and project and summary and issue_type_id):
        return None

    def _post(fields):
        try:
            r = requests.post(
                f'https://{domain}/rest/api/3/issue', json={'fields': fields},
                auth=auth, headers={'Accept': 'application/json',
                                    'Content-Type': 'application/json'}, timeout=TIMEOUT)
            if r.status_code not in (200, 201):
                logger.warning('jira create in %s → HTTP %s: %s',
                               project, r.status_code, r.text[:300])
                return None, r.text[:300]
            return (r.json() or {}).get('key') or None, ''
        except Exception as e:
            logger.warning('jira create in %s failed: %s', project, e)
            return None, str(e)

    base = {
        'project': {'key': project},
        'issuetype': {'id': str(issue_type_id)},
        'summary': summary[:255],
        'description': _text_to_adf(body_text),
    }
    fields = dict(base)
    if priority_id:
        fields['priority'] = {'id': str(priority_id)}
    if parent_key:
        fields['parent'] = {'key': parent_key}

    key, _err = _post(fields)
    if key or fields == base:
        return key
    logger.info('jira create retry without parent/priority for %s', project)
    key, _err = _post(base)
    return key


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


def search_issues(jql, fields=None, max_results=100):
    """Return the issues matching `jql`, following pagination.

    Best-effort and never raises into a caller: missing creds give []; a
    failure part-way through pagination returns the pages gathered so far
    rather than discarding them, so a partial result is possible and is NOT
    distinguishable from a complete one here. Callers that care (see
    jira_ingest) should sanity-check the count rather than trust it.

    Matching is by JQL only — nothing in this function infers a portal ticket
    from an issue's summary text.
    """
    domain, auth = _creds()
    if not (domain and jql):
        return []
    issues, token = [], None
    try:
        while True:
            payload = {'jql': jql, 'maxResults': max_results,
                       'fields': fields or ['summary']}
            if token:
                payload['nextPageToken'] = token
            r = requests.post(
                f'https://{domain}/rest/api/3/search/jql', json=payload,
                auth=auth, headers={'Accept': 'application/json',
                                    'Content-Type': 'application/json'},
                timeout=TIMEOUT)
            if r.status_code != 200:
                logger.info('jira search → HTTP %s: %s', r.status_code, r.text[:200])
                return issues
            data = r.json() or {}
            issues.extend(data.get('issues') or [])
            token = data.get('nextPageToken')
            if not token or data.get('isLast'):
                return issues
    except Exception as e:  # network, timeout, JSON, anything
        logger.warning('jira search failed: %s', e)
        return issues


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
