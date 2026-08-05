"""Escalate a support ticket into a real Jira issue.

Distinct from `jira_sync.provision_ticket_issue`, which is an unattended cron
that mirrors tickets into a support project. This is a deliberate agent action:
the agent chooses the project, issue type and priority, edits the description,
and the result lands in the current sprint under the project's escalation epic
so it's picked up as real engineering work rather than parked in a backlog.

Every Jira call here is best-effort. A partial result is reported rather than
rolled back: an issue that exists but missed its sprint is fixable in Jira,
whereas a silent failure after the agent has told a customer "this is now a
bug" is not.
"""
import logging

from django.conf import settings

from portal import jira_client

logger = logging.getLogger(__name__)

# One durable epic per project — escalations stay findable in one place instead
# of scattering across the period-scoped bug epics.
EPIC_SUMMARY = 'Support Escalations'
EPIC_DESCRIPTION = (
    'Umbrella epic for customer issues escalated from the support portal.\n\n'
    'Issues here are created by a support agent from a portal ticket and carry '
    'a link back to that ticket. Created and reused automatically — please '
    'keep it open.'
)


def allowed_projects():
    return list(getattr(settings, 'JIRA_ESCALATION_PROJECTS', ['ECD', 'AI']))


def compose_description(ticket, portal_url=None):
    """Build the Jira description from the ticket and the agent's own notes.

    Internal notes are the agent's diagnosis and are exactly what engineering
    needs; they're safe to include because Jira is internal — but that's also
    why this must never be shown back to a customer.
    """
    lines = []
    lines.append(f'Escalated from support ticket {ticket.display_number}.')
    lines.append('')
    lines.append(f'Customer: {ticket.company.name}')
    requester = (ticket.requester_email
                 or (ticket.requester.email if ticket.requester_id else ''))
    if requester:
        lines.append(f'Requester: {requester}')
    if ticket.assignee_id and ticket.assignee:
        lines.append(f'Support agent: {ticket.assignee.name or ticket.assignee.email}')
    lines.append(f'Category: {ticket.category}')
    if portal_url:
        lines.append(f'Portal ticket: {portal_url}')

    messages = list(ticket.messages.order_by('created_at'))
    first = next((m for m in messages if not m.is_internal), None)
    if first:
        lines.append('')
        lines.append('--- Original report ---')
        lines.append(first.body.strip())

    notes = [m for m in messages if m.is_internal]
    if notes:
        lines.append('')
        lines.append('--- Support notes (internal) ---')
        for n in notes:
            who = n.author.name or n.author_email if n.author_id else n.author_email
            stamp = n.created_at.strftime('%Y-%m-%d %H:%M')
            lines.append(f'[{stamp}] {who}: {n.body.strip()}')

    replies = [m for m in messages
               if not m.is_internal and m is not first]
    if replies:
        lines.append('')
        lines.append('--- Conversation ---')
        for m in replies:
            who = 'Support' if m.origin == 'staff' else 'Customer'
            stamp = m.created_at.strftime('%Y-%m-%d %H:%M')
            lines.append(f'[{stamp}] {who}: {m.body.strip()}')

    return '\n'.join(lines)


def escalation_options(project):
    """Issue types and priorities the escalation form should offer."""
    return {
        'project': project,
        'issue_types': jira_client.list_issue_types(project),
        'priorities': jira_client.list_priorities(),
    }


def escalate(ticket, *, project, issue_type_id, summary, description,
             priority_id=None, actor=None, portal_url=None):
    """Create the Jira issue, file it under the epic and current sprint, link it.

    Returns {'key', 'epic_key', 'sprint_id', 'warnings'}; 'key' is None if the
    issue itself could not be created. Warnings name the steps that didn't
    land, so the agent finds out immediately rather than discovering later that
    an escalation never reached the sprint.
    """
    from portal.models import JiraTicketLink
    from portal.views.tickets import log_ticket_activity

    if project not in allowed_projects():
        return {'key': None, 'error': f'{project} is not an escalation target'}

    warnings = []

    epic_type_id = getattr(settings, 'JIRA_EPIC_ISSUE_TYPE_ID', '10000')
    epic_key = jira_client.find_or_create_epic(
        project, EPIC_SUMMARY, epic_type_id, EPIC_DESCRIPTION)
    if not epic_key:
        warnings.append('Could not find or create the Support Escalations epic; '
                        'the issue was filed without an epic.')

    key = jira_client.create_issue_ex(
        project, summary, description, issue_type_id,
        priority_id=priority_id, parent_key=epic_key)
    if not key:
        return {'key': None, 'epic_key': epic_key,
                'error': 'Jira rejected the issue. Nothing was created.'}

    sprint_id = jira_client.active_sprint_id(project)
    if sprint_id:
        if not jira_client.add_to_sprint(sprint_id, key):
            warnings.append(f'{key} was created but could not be added to the '
                            'active sprint.')
            sprint_id = None
    else:
        warnings.append(f'{project} has no active sprint; {key} is in the backlog.')

    # Reuse the existing link model, so live status sync works with no extra
    # wiring — the admin ticket view already refreshes every linked issue.
    JiraTicketLink.objects.get_or_create(ticket=ticket, key=key)
    log_ticket_activity(ticket, 'jira_linked', actor=actor, key=key,
                        escalated=True, project=project)

    if portal_url:
        jira_client.create_remote_link(
            key, portal_url, f'Support ticket {ticket.display_number}')

    return {'key': key, 'epic_key': epic_key, 'sprint_id': sprint_id,
            'warnings': warnings}
