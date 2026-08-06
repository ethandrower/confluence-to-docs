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
from django.db import transaction

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

    settings.JIRA_INGEST gates WRITING, not looking. With the flag off the cron
    entry (which passes no --dry-run) is a no-op, so this ships dark — but
    `--dry-run` still queries and reports. That ordering matters: the whole
    documented rollout is "deploy dark, watch --dry-run for a few days, then
    enable", and gating the read too would leave arming the live
    every-5-minute writer as the only way to preview a single match.
    """
    from portal.models import JiraTicketLink, Ticket, TicketMessage

    if not dry_run and not getattr(settings, 'JIRA_INGEST', False):
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
    # Log what we SCANNED, not just what we ingested. search_issues is
    # best-effort and swallows auth/network failures, so "ingested 0" alone
    # can't distinguish a healthy quiet run from a rotated API token — but
    # "scanned 0" against a live service desk is always wrong and says so.
    if not issues:
        logger.warning('jira_ingest: search returned no issues for %r — '
                       'expected at least some on a live project; check '
                       'CONFLUENCE_* credentials and the JQL', jql)
    else:
        logger.info('jira_ingest: scanned %s issue(s) for %r', len(issues), jql)

    # One query for every key already linked to ANY ticket — an issue a staff
    # member linked by hand must not be ingested a second time.
    linked = set(JiraTicketLink.objects.values_list('key', flat=True))

    site = (getattr(settings, 'FRONTEND_URL', '') or '').rstrip('/')
    created = 0
    for iss in issues:
        # The guard wraps the WHOLE iteration, not just the writes: reporter
        # extraction below parses payload we don't control, and a shape we
        # didn't anticipate there would otherwise abort the pass and silently
        # skip every remaining issue.
        try:
            key = (iss or {}).get('key') or ''
            if not key or key in linked:
                continue
            fields = iss.get('fields') or {}
            user = _match_customer((fields.get('reporter') or {}).get('emailAddress'))
            if not user:
                continue

            subject = (fields.get('summary') or '(no subject)')[:512]
            if dry_run:
                created += 1
                logger.info('jira_ingest[dry-run]: would ingest %s for %s (%s)',
                            key, user.email, subject)
                continue

            with transaction.atomic():
                # `linked` is a snapshot from the top of the run. Re-check here
                # so a concurrent pass (a manual run overlapping the 5-minute
                # cron) doesn't file the same request twice as two
                # customer-facing tickets. This narrows the window rather than
                # closing it: JiraTicketLink has no unique constraint on `key`
                # alone, because one issue may legitimately link to several
                # tickets. Closing it properly needs either that constraint
                # (scoped to ingested links) or a run lock.
                if JiraTicketLink.objects.filter(key=key).exists():
                    logger.info('jira_ingest: %s linked concurrently, skipping', key)
                    continue
                ticket = Ticket.objects.create(
                    company=user.company, created_by=user, subject=subject,
                    status=Ticket.STATUS_WAITING_ON_SUPPORT)
                body = jira_client.adf_to_text(fields.get('description')).strip()
                TicketMessage.objects.create(
                    ticket=ticket, author=user, author_email=user.email,
                    body=body or '(no content)',
                    origin=TicketMessage.ORIGIN_EMAIL)
                JiraTicketLink.objects.create(ticket=ticket, key=key)
        except Exception as e:
            logger.error('jira_ingest: %s failed, skipping: %s',
                         (iss or {}).get('key', '?'), e)
            continue

        created += 1
        linked.add(key)
        # No customer email: JSM already sent its own "request received"
        # auto-reply, and a portal confirmation on top would duplicate it.
        jira_client.create_remote_link(
            key, f'{site}/manage/tickets/{ticket.number}',
            f'{ticket.display_number} in CiteMed Support')
        logger.info('jira_ingest: %s → %s (%s)', key, ticket.display_number,
                    user.email)

    return created
