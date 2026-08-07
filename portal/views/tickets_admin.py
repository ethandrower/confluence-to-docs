"""Admin support-ticket endpoints. Gated via require_portal_admin.
Reuses serializer helpers from portal.views.tickets to keep one source of
truth for the JSON shapes."""
import json
import logging
import threading

from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

import re

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from portal import jira_client, realtime, ticket_notify
from portal.decorators import require_portal_admin
from portal.models import Company, JiraTicketLink, PortalUser, Ticket, TicketMessage
from portal.rate_limit import is_rate_limited
from portal.views.tickets import (
    _clean_ccs, _message_dict, _ticket_dict, _with_message_count,
    log_ticket_activity,
)

logger = logging.getLogger(__name__)


def _defer(fn):
    """Run a best-effort side-effect off the request path, in a daemon thread,
    so slow external calls (e.g. Jira) never block the admin's response. Tests
    patch this to run synchronously. The target must not touch the DB (no
    per-thread connection is managed here)."""
    def _runner():
        try:
            fn()
        except Exception as e:  # a background best-effort task must never crash
            logger.warning('deferred task failed: %s', e)
    threading.Thread(target=_runner, daemon=True).start()

# Max rows the admin "All" list returns without pagination (spec §4e/§6).
ADMIN_LIST_CAP = 200
# Re-fetch a linked Jira issue's status at most this often.
JIRA_CACHE_SECONDS = 60
JIRA_KEY_RE = re.compile(r'^[A-Z][A-Z0-9]+-\d+$')
_JIRA_BROWSE_RE = re.compile(r'/browse/([A-Za-z][A-Za-z0-9]+-\d+)', re.I)


def _extract_jira_key(raw):
    """Normalize a pasted Jira reference to a KEY. Accepts what agents actually
    paste: a bare key (SUP-374), a classic browse URL (.../browse/SUP-374?...),
    or a JSM agent/portal URL where the key is a path segment
    (.../servicedesk/projects/SUP/.../SUP-374). A search/list URL, where the key
    only appears in the query string, is intentionally NOT matched — it's not a
    single issue. Anything unrecognized is returned as-is for JIRA_KEY_RE to
    reject downstream."""
    raw = (raw or '').strip()
    if not raw:
        return ''
    if JIRA_KEY_RE.match(raw.upper()):
        return raw.upper()
    m = _JIRA_BROWSE_RE.search(raw)
    if m:
        return m.group(1).upper()
    # Last key-shaped PATH segment; drop query/hash so we never lift a token out
    # of a ?jql=… search URL.
    path = raw.split('?', 1)[0].split('#', 1)[0]
    for seg in reversed(path.split('/')):
        if JIRA_KEY_RE.match(seg.strip().upper()):
            return seg.strip().upper()
    return raw.upper()


def _assignee_dict(t):
    u = t.assignee
    return {'id': u.id, 'email': u.email, 'name': u.name} if u else None


def _watchers_list(t):
    return [{'id': u.id, 'email': u.email, 'name': u.name}
            for u in t.watchers.all()]


def _admin_dict(t, message_count=None):
    d = _ticket_dict(t, message_count=message_count)
    d.update({
        'company': {'id': t.company_id, 'name': t.company.name},
        'cc_emails': t.cc_emails,
        'created_by_email': t.created_by.email if t.created_by else '',
        # Who it's for. `has_portal_access` is the bit staff need: false means
        # this person only ever sees the thread by email, so a reply that says
        # "see the portal" would be telling them to go somewhere they can't.
        'requester': {
            'email': t.requester_email or (t.requester.email if t.requester else ''),
            'name': t.requester.name if t.requester else '',
            'has_portal_access': bool(t.requester and t.requester.access_enabled),
        } if (t.requester_id or t.requester_email) else None,
        # Staff-only. These keys must never migrate into _ticket_dict,
        # which the customer endpoints share.
        'assignee': _assignee_dict(t),
        'watchers': _watchers_list(t),
        'priority': t.priority,
    })
    return d


def _jira_link_dict(link):
    domain = getattr(settings, 'CONFLUENCE_DOMAIN', '')
    return {
        'key': link.key,
        'status': link.cached_status,
        'status_category': link.cached_status_category,
        'summary': link.cached_summary,
        'url': f'https://{domain}/browse/{link.key}' if domain else '',
    }


def _refresh_jira_links(ticket):
    """Refresh each linked issue's cached status if stale, then return the
    serialized links. Best-effort — a failed fetch keeps the stale cache."""
    now = timezone.now()
    for link in ticket.jira_links.all():
        stale = (link.fetched_at is None
                 or (now - link.fetched_at).total_seconds() > JIRA_CACHE_SECONDS)
        if stale:
            data = jira_client.fetch_issue(link.key)
            if data:
                link.cached_status = data['status'][:64]
                link.cached_status_category = data['status_category'][:32]
                link.cached_summary = data['summary'][:512]
                link.fetched_at = now
                link.save(update_fields=['cached_status', 'cached_status_category',
                                         'cached_summary', 'fetched_at'])
    return [_jira_link_dict(l) for l in ticket.jira_links.all()]


def _get(number):
    return Ticket.objects.select_related('company', 'created_by')\
                         .filter(number=number).first()


def _nudge_reply_in_portal(ticket, key):
    """On a service-desk link, drop a remote link + an INTERNAL note telling
    agents to reply to the customer in the portal, not Jira — closing the
    "replied in Jira, customer never saw it" footgun. Best-effort. Skipped for
    non-service-desk projects (e.g. engineering bugs), which aren't a customer
    reply surface, per settings.JIRA_SYNC_PROJECTS."""
    allowed = {p.upper() for p in getattr(settings, 'JIRA_SYNC_PROJECTS', ['SUP'])}
    if key.split('-')[0].upper() not in allowed:
        return
    site = (getattr(settings, 'FRONTEND_URL', '') or '').rstrip('/')
    admin_url = f'{site}/manage/tickets/{ticket.number}'
    jira_client.create_remote_link(
        key, admin_url, f'{ticket.display_number} in CiteMed Support')
    jira_client.add_comment(key, (
        f'💬 Linked to CiteMed Support ticket {ticket.display_number}. Reply to the '
        f'customer in the portal (not in Jira): {admin_url}'), internal=True)


@require_http_methods(['GET'])
@require_portal_admin
def inbox(request):
    qs = _with_message_count(
        Ticket.objects.select_related('company', 'created_by')
        .filter(status=Ticket.STATUS_WAITING_ON_SUPPORT)
    ).order_by('updated_at')
    items = [_admin_dict(t, message_count=t._mc) for t in qs]
    return JsonResponse({'tickets': items, 'awaiting_total': len(items)})


@require_http_methods(['GET', 'POST'])
@require_portal_admin
def collection(request):
    if request.method == 'GET':
        qs = _with_message_count(
            Ticket.objects.select_related('company', 'created_by')
        ).order_by('-updated_at')
        company_id = request.GET.get('company')
        if company_id:
            qs = qs.filter(company_id=company_id)
        status = request.GET.get('status')
        if status:
            qs = qs.filter(status=status)
        # Fetch one past the cap so we can flag truncation without an extra
        # COUNT. No pagination yet (spec §6) — the flag drives a UI hint.
        rows = list(qs[:ADMIN_LIST_CAP + 1])
        truncated = len(rows) > ADMIN_LIST_CAP
        return JsonResponse({
            'tickets': [_admin_dict(t, message_count=t._mc)
                        for t in rows[:ADMIN_LIST_CAP]],
            'truncated': truncated,
        })

    # POST — create on behalf of a customer
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'error': 'Invalid request body'}, status=400)
    company = Company.objects.filter(id=data.get('company_id')).first()
    subject = (data.get('subject') or '').strip()
    body = (data.get('body') or '').strip()
    if not company or not subject or not body:
        return JsonResponse({'error': 'company_id, subject and body are required'},
                            status=400)
    ccs = _clean_ccs(data.get('cc_emails'))
    customer_email = (data.get('customer_email') or '').strip()
    if customer_email and customer_email not in ccs:
        ccs = _clean_ccs([customer_email] + ccs)

    category = data.get('category') or 'question'
    if category not in dict(Ticket.CATEGORY_CHOICES):
        category = 'other'

    # Resolve the named customer to a real account where one exists, so the
    # ticket reaches them in the portal and not just by email. When it doesn't,
    # the address is still recorded and the response says so — an agent who
    # types an address with no account should find that out at create time,
    # not from a customer who never saw the thread.
    requester = (PortalUser.objects.filter(email__iexact=customer_email).first()
                 if customer_email else None)

    user = request.portal_user
    ticket = Ticket.objects.create(
        company=company, created_by=user, subject=subject[:512],
        requester=requester, requester_email=customer_email,
        category=category, cc_emails=ccs,
        # Brand-new on-behalf ticket: nothing has been asked of the customer
        # yet, so 'open' (not 'waiting on customer', which read as misleading
        # to testers). Staff move it to waiting_on_customer once they reply.
        status=Ticket.STATUS_OPEN)
    first = TicketMessage.objects.create(
        ticket=ticket, author=user, author_email=user.email,
        body=body, origin=TicketMessage.ORIGIN_STAFF)
    log_ticket_activity(ticket, 'created', actor=user, on_behalf=True)
    ticket_notify.notify_ticket_created(ticket, first)
    transaction.on_commit(lambda: realtime.notify_ticket(
        ticket, 'created', to_ticket=False))
    return JsonResponse(_admin_dict(ticket, message_count=1))


@require_http_methods(['GET'])
@require_portal_admin
def detail(request, number):
    t = _get(number)
    if not t:
        return JsonResponse({'error': 'Not found'}, status=404)
    msgs = list(t.messages.all())
    d = _admin_dict(t, message_count=len(msgs))
    d['messages'] = [dict(_message_dict(m), is_internal=m.is_internal,
                          delivery_detail=m.delivery_detail)
                     for m in msgs]
    d['activity'] = [{
        'action': a.action, 'detail': a.detail,
        'actor': (a.actor.name or a.actor.email) if a.actor else '',
        'created_at': a.created_at.isoformat(),
    } for a in t.activity.all()[:50]]
    d['jira_links'] = _refresh_jira_links(t)
    return JsonResponse(d)


@require_http_methods(['POST'])
@require_portal_admin
def reply(request, number):
    t = _get(number)
    if not t:
        return JsonResponse({'error': 'Not found'}, status=404)
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'error': 'Invalid request body'}, status=400)
    body = (data.get('body') or '').strip()
    if not body:
        return JsonResponse({'error': 'Message is required'}, status=400)
    is_internal = bool(data.get('is_internal'))

    user = request.portal_user
    # Answering an unclaimed ticket is picking it up. Doing it implicitly keeps
    # ownership honest without asking agents to remember a second click; an
    # explicit reassign still wins, since this only fires when nobody owns it.
    claimed = False
    if t.assignee_id is None:
        t.assignee = user
        t.save(update_fields=['assignee', 'updated_at'])
        log_ticket_activity(t, 'assigned', actor=user,
                            assignee=(user.name or user.email), auto=True)
        claimed = True
    m = TicketMessage.objects.create(
        ticket=t, author=user, author_email=user.email, body=body,
        origin=TicketMessage.ORIGIN_STAFF, is_internal=is_internal)
    if not is_internal:
        t.status = Ticket.STATUS_WAITING_ON_CUSTOMER
        t.save(update_fields=['status', 'updated_at'])
        ticket_notify.notify_staff_reply(t, m)
    log_ticket_activity(t, 'note_added' if is_internal else 'message_sent',
                        actor=user)
    if is_internal:
        transaction.on_commit(lambda: realtime.notify_ticket(
            t, 'internal_note', to_ticket=False, to_company=False))
    else:
        transaction.on_commit(lambda: realtime.notify_ticket(t, 'staff_reply'))
    return JsonResponse({'ok': True,
                         'message': dict(_message_dict(m),
                                         is_internal=m.is_internal,
                                         delivery_detail=m.delivery_detail),
                         'status': t.status,
                         'assignee': _assignee_dict(t),
                         'auto_claimed': claimed})


@require_http_methods(['POST'])
@require_portal_admin
def resend_message(request, number, message_id):
    """Re-send a customer-facing message whose delivery failed (or to retry a
    stuck send). Re-uses the staff-reply send path, which records the new
    outcome on the message. Admin-only, rate-limited per ticket."""
    t = _get(number)
    if not t:
        return JsonResponse({'error': 'Not found'}, status=404)
    m = TicketMessage.objects.filter(id=message_id, ticket=t).first()
    if not m:
        return JsonResponse({'error': 'Not found'}, status=404)
    # Resend only re-emits staff replies to the customer. Never re-send a
    # customer's own message (would arrive dressed as a staff reply) or an
    # internal note (never leaves the building).
    if m.origin != TicketMessage.ORIGIN_STAFF or m.is_internal:
        return JsonResponse({'error': 'Only staff replies can be resent'},
                            status=400)
    if is_rate_limited('ticket-resend', f't{t.number}', 10, 60 * 60):
        return JsonResponse({'error': 'Too many resends, try later'}, status=429)
    ticket_notify.notify_staff_reply(t, m)
    m.refresh_from_db()
    return JsonResponse({'ok': True, 'delivery_status': m.delivery_status,
                         'delivery_detail': m.delivery_detail})


@require_http_methods(['POST'])
@require_portal_admin
def set_status(request, number):
    t = _get(number)
    if not t:
        return JsonResponse({'error': 'Not found'}, status=404)
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'error': 'Invalid request body'}, status=400)
    status = data.get('status')
    if status not in dict(Ticket.STATUS_CHOICES):
        return JsonResponse({'error': 'Invalid status'}, status=400)
    old = t.status
    t.status = status
    t.save(update_fields=['status', 'updated_at'])
    log_ticket_activity(t, 'status_changed', actor=request.portal_user,
                        old=old, new=status)
    transaction.on_commit(lambda: realtime.notify_ticket(t, 'status_changed'))
    if status in (Ticket.STATUS_RESOLVED, Ticket.STATUS_CLOSED):
        ticket_notify.notify_status(t)
    return JsonResponse({'ok': True, 'status': t.status})


@require_http_methods(['POST'])
@require_portal_admin
def set_priority(request, number):
    """Set the SLA priority. Staff-only by design — the field is an internal
    commitment, and it never reaches the customer payload. Deliberately does
    NOT email or notify the customer: severity is our triage signal, not a
    promise we make to them directly."""
    t = _get(number)
    if not t:
        return JsonResponse({'error': 'Not found'}, status=404)
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'error': 'Invalid request body'}, status=400)
    priority = data.get('priority')
    if priority not in dict(Ticket.PRIORITY_CHOICES):
        return JsonResponse({'error': 'Invalid priority'}, status=400)
    old = t.priority
    if old == priority:
        return JsonResponse({'ok': True, 'priority': t.priority})
    t.priority = priority
    t.save(update_fields=['priority', 'updated_at'])
    log_ticket_activity(t, 'priority_changed', actor=request.portal_user,
                        old=old, new=priority)
    # Nudge open admin tabs so a second agent sees the new severity; the
    # customer channel is intentionally untouched.
    transaction.on_commit(lambda: realtime.notify_ticket(t, 'priority_changed'))
    return JsonResponse({'ok': True, 'priority': t.priority})


@require_http_methods(['POST'])
@require_portal_admin
def set_jira(request, number):
    """Add or remove a Jira link. {action:'add'|'remove', key:'ECD-123'}.
    A ticket can have multiple links. Admin-only; never customer-visible."""
    t = _get(number)
    if not t:
        return JsonResponse({'error': 'Not found'}, status=404)
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'error': 'Invalid request body'}, status=400)
    action = data.get('action', 'add')
    key = _extract_jira_key(data.get('key'))
    warning = ''
    if action == 'remove':
        JiraTicketLink.objects.filter(ticket=t, key=key).delete()
        log_ticket_activity(t, 'jira_unlinked', actor=request.portal_user, key=key)
    else:
        if not JIRA_KEY_RE.match(key):
            return JsonResponse(
                {'error': 'Enter a Jira key (e.g. SUP-374) or paste a Jira issue URL'},
                status=400)
        # Confirm the issue is real before recording the link. A mistyped key
        # matches the format fine and would otherwise link silently, leaving a
        # permanent "status unavailable" the agent can't tell apart from Jira
        # being down. Only a definite 404 rejects — an outage or a permissions
        # error still lets the link through, with a warning.
        state, data_ = jira_client.verify_issue(key)
        if state == 'missing':
            return JsonResponse(
                {'error': f"{key} doesn't exist in Jira, or you don't have "
                          "access to it. Check the key and try again."},
                status=400)
        warning = ('' if state == 'ok' else
                   f'Linked {key}, but Jira could not be reached to confirm it '
                   'or read its status.')
        link, created = JiraTicketLink.objects.get_or_create(ticket=t, key=key)
        if created:
            if data_:
                link.cached_status = data_['status'][:64]
                link.cached_status_category = data_['status_category'][:32]
                link.cached_summary = data_['summary'][:512]
                link.fetched_at = timezone.now()
                link.save(update_fields=['cached_status', 'cached_status_category',
                                         'cached_summary', 'fetched_at'])
            log_ticket_activity(t, 'jira_linked', actor=request.portal_user, key=key)
            # Off the request path: the nudge makes 2 Jira writes that shouldn't
            # block the admin's "Link" click if Jira is slow.
            _defer(lambda: _nudge_reply_in_portal(t, key))
    t.save(update_fields=['updated_at'])
    return JsonResponse({'ok': True, 'jira_links': _refresh_jira_links(t),
                         'warning': warning})


@require_http_methods(['POST'])
@require_portal_admin
def set_cc(request, number):
    t = _get(number)
    if not t:
        return JsonResponse({'error': 'Not found'}, status=404)
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'error': 'Invalid request body'}, status=400)
    t.cc_emails = _clean_ccs(data.get('cc_emails'))
    t.save(update_fields=['cc_emails', 'updated_at'])
    log_ticket_activity(t, 'cc_changed', actor=request.portal_user,
                        cc_emails=t.cc_emails)
    transaction.on_commit(lambda: realtime.notify_ticket(t, 'cc_changed'))
    return JsonResponse({'ok': True, 'cc_emails': t.cc_emails})


@require_http_methods(['GET'])
@require_portal_admin
def escalation_options(request, number):
    """What the escalate form needs: targets, issue types, priorities, and the
    pre-composed description the agent can edit before filing."""
    from portal import escalation
    t = _get(number)
    if not t:
        return JsonResponse({'error': 'Not found'}, status=404)
    projects = escalation.allowed_projects()
    project = request.GET.get('project') or (projects[0] if projects else '')
    opts = escalation.escalation_options(project) if project else {
        'issue_types': [], 'priorities': []}
    return JsonResponse({
        'projects': projects,
        'project': project,
        'issue_types': opts.get('issue_types', []),
        'priorities': opts.get('priorities', []),
        'summary': f'[{t.display_number}] {t.subject}'[:255],
        'description': escalation.compose_description(t, _portal_ticket_url(t)),
        'already_linked': [l.key for l in t.jira_links.all()],
    })


def _portal_ticket_url(ticket):
    base = getattr(settings, 'FRONTEND_URL', '').rstrip('/')
    return f'{base}/manage/tickets/{ticket.number}' if base else ''


@require_http_methods(['POST'])
@require_portal_admin
def escalate(request, number):
    """Escalate this ticket into a real Jira issue (agent-initiated)."""
    from portal import escalation
    t = _get(number)
    if not t:
        return JsonResponse({'error': 'Not found'}, status=404)
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'error': 'Invalid request body'}, status=400)

    project = (data.get('project') or '').strip()
    issue_type_id = (data.get('issue_type_id') or '').strip()
    summary = (data.get('summary') or '').strip()
    description = (data.get('description') or '').strip()
    if not (project and issue_type_id and summary and description):
        return JsonResponse(
            {'error': 'project, issue_type_id, summary and description are required'},
            status=400)

    result = escalation.escalate(
        t, project=project, issue_type_id=issue_type_id, summary=summary,
        description=description, priority_id=data.get('priority_id') or None,
        actor=request.portal_user, portal_url=_portal_ticket_url(t))

    if not result.get('key'):
        return JsonResponse({'error': result.get('error') or 'Escalation failed'},
                            status=502)

    transaction.on_commit(lambda: realtime.notify_ticket(
        t, 'escalated', to_company=False))
    return JsonResponse({'ok': True, 'key': result['key'],
                         'epic_key': result.get('epic_key'),
                         'sprint_id': result.get('sprint_id'),
                         'warnings': result.get('warnings', []),
                         'jira_links': _refresh_jira_links(t)})


def _agents_qs():
    """Agents eligible to own a ticket."""
    return PortalUser.objects.filter(
        role__in=[PortalUser.ROLE_ADMIN, PortalUser.ROLE_OWNER],
        access_enabled=True,
    ).order_by('name', 'email')


@require_http_methods(['GET'])
@require_portal_admin
def agents(request):
    """Assignable agents, for the assignee and watcher pickers."""
    return JsonResponse({'agents': [
        {'id': u.id, 'email': u.email, 'name': u.name} for u in _agents_qs()
    ]})


@require_http_methods(['POST'])
@require_portal_admin
def set_assignee(request, number):
    """Assign a ticket, claim it, or hand it back to the queue.

    Body: {"assignee_id": <id>} to assign, {"assignee_id": null} to unassign,
    or {"assign_to_me": true} for the one-click claim.
    """
    t = _get(number)
    if not t:
        return JsonResponse({'error': 'Not found'}, status=404)
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'error': 'Invalid request body'}, status=400)

    actor = request.portal_user
    if data.get('assign_to_me'):
        assignee = actor
    elif not data.get('assignee_id'):
        assignee = None
    else:
        assignee = _agents_qs().filter(id=data.get('assignee_id')).first()
        if not assignee:
            # Only agents can own a ticket — assigning a customer would put a
            # name on it belonging to someone with no admin access at all.
            return JsonResponse({'error': 'That user is not an agent'}, status=400)

    if t.assignee_id == (assignee.pk if assignee else None):
        return JsonResponse({'ok': True, 'assignee': _assignee_dict(t)})

    t.assignee = assignee
    t.save(update_fields=['assignee', 'updated_at'])
    log_ticket_activity(
        t, 'assigned' if assignee else 'unassigned', actor=actor,
        assignee=(assignee.name or assignee.email) if assignee else '')
    if assignee:
        _defer(lambda: ticket_notify.notify_assigned(t, actor=actor))
    transaction.on_commit(lambda: realtime.notify_ticket(
        t, 'assigned', to_company=False))
    return JsonResponse({'ok': True, 'assignee': _assignee_dict(t)})


@require_http_methods(['POST'])
@require_portal_admin
def set_watchers(request, number):
    """Replace the internal watcher list. Staff-only — watchers are never
    serialized to the customer, unlike cc_emails."""
    t = _get(number)
    if not t:
        return JsonResponse({'error': 'Not found'}, status=404)
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'error': 'Invalid request body'}, status=400)
    ids = data.get('watcher_ids')
    if not isinstance(ids, list):
        return JsonResponse({'error': 'watcher_ids must be a list'}, status=400)
    chosen = list(_agents_qs().filter(id__in=ids))
    t.watchers.set(chosen)
    log_ticket_activity(t, 'watchers_changed', actor=request.portal_user,
                        watchers=[u.email for u in chosen])
    transaction.on_commit(lambda: realtime.notify_ticket(
        t, 'watchers_changed', to_company=False))
    return JsonResponse({'ok': True, 'watchers': _watchers_list(t)})
