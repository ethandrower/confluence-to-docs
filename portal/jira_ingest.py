"""Ingest customer-raised JSM requests into the portal.

A customer who emails support@ (or uses the Atlassian customer portal) creates a
Jira request the portal never sees, so staff have to recreate it by hand. This
closes that gap.

The filter is the PortalUser allowlist, matched on the Jira reporter's email:
an exact hit means a real, onboarded customer AND tells us their company.
Everything else — scraper bots, sales spam, staff, unonboarded senders — has no
matching customer row and is ignored. Over 180 days of real SUP traffic that
selects 1 issue out of 408, with no false positives.
"""
import logging

from django.conf import settings

logger = logging.getLogger(__name__)

# Module scope so tests can patch portal.jira_ingest.<name>.
from portal import jira_client


def _match_customer(email):
    """The enabled customer account for `email`, or None. Staff (owner/admin)
    never match — they file through Jira routinely and are not customers."""
    from portal.models import PortalUser
    if not email:
        return None
    user = PortalUser.objects.filter(
        email__iexact=email.strip(), role=PortalUser.ROLE_CUSTOMER,
        access_enabled=True).first()
    # Ticket.company is non-nullable, and a companyless account has no tenant
    # to file under — skip rather than crash the whole pass.
    if not user or not user.company_id:
        return None
    return user


def ingest_requests(dry_run=False):
    """Create a portal ticket for each unlinked JSM request whose reporter is a
    known customer. Returns the number of tickets created (or, under dry_run,
    the number that would be).

    Gated by settings.JIRA_INGEST — a no-op until switched on, so it can ship
    dark and be observed via `--dry-run` before it writes anything.
    """
    from portal.models import JiraTicketLink, Ticket, TicketMessage

    if not getattr(settings, 'JIRA_INGEST', False):
        return 0

    project = getattr(settings, 'JIRA_INGEST_PROJECT', 'SUP')
    jql = f'project = {project}'
    # Cutoff so switching this on doesn't backfill months of old requests.
    since = getattr(settings, 'JIRA_INGEST_SINCE', '')
    if since:
        jql += f' AND created >= "{since}"'
    jql += ' ORDER BY created DESC'

    issues = jira_client.search_issues(
        jql, fields=['summary', 'reporter', 'description'])

    # One query for every key already linked to ANY ticket — an issue a staff
    # member linked by hand must not be ingested a second time.
    linked = set(JiraTicketLink.objects.values_list('key', flat=True))

    site = (getattr(settings, 'FRONTEND_URL', '') or '').rstrip('/')
    created = 0
    for iss in issues:
        key = iss.get('key') or ''
        if not key or key in linked:
            continue
        fields = iss.get('fields') or {}
        user = _match_customer((fields.get('reporter') or {}).get('emailAddress'))
        if not user:
            continue

        created += 1
        subject = (fields.get('summary') or '(no subject)')[:512]
        if dry_run:
            logger.info('jira_ingest[dry-run]: would ingest %s for %s (%s)',
                        key, user.email, subject)
            continue

        ticket = Ticket.objects.create(
            company=user.company, created_by=user, subject=subject,
            status=Ticket.STATUS_WAITING_ON_SUPPORT)
        body = jira_client.adf_to_text(fields.get('description')).strip()
        TicketMessage.objects.create(
            ticket=ticket, author=user, author_email=user.email,
            body=body or '(no content)', origin=TicketMessage.ORIGIN_EMAIL)
        JiraTicketLink.objects.create(ticket=ticket, key=key)
        linked.add(key)
        # No customer email: JSM already sent its own "request received"
        # auto-reply, and a portal confirmation on top would duplicate it.
        jira_client.create_remote_link(
            key, f'{site}/manage/tickets/{ticket.number}',
            f'{ticket.display_number} in CiteMed Support')
        logger.info('jira_ingest: %s → %s (%s)', key, ticket.display_number,
                    user.email)

    return created
