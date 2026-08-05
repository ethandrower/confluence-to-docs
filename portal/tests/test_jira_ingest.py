"""Jira→portal request ingestion.

A customer who emails support@ (or uses the Atlassian customer portal) creates
a JSM request that the portal never sees — it has to be recreated by hand. This
closes that gap by matching the Jira reporter's email against the PortalUser
allowlist: an exact hit means a real, onboarded customer (and tells us which
company), anything else — bots, sales spam, staff — is ignored.

Units under test:
  - jira_client.search_issues  — JQL search, paginated, best-effort
  - jira_ingest.ingest_requests — match reporter → create + link a Ticket
"""
from types import SimpleNamespace
from unittest import mock

from django.core.management import call_command
from django.test import TestCase

from portal import jira_client, jira_ingest
from portal.models import (
    Company, JiraTicketLink, PortalUser, Ticket, TicketMessage,
)


def issue(key='SUP-637', email='ddonaho@mirion.com', summary='Search Engine Issues',
          description='The searches are very slow.'):
    """A JSM request shaped the way search_issues returns it."""
    return {'key': key, 'fields': {
        'summary': summary,
        'reporter': {'emailAddress': email, 'displayName': 'Darby Donaho'},
        'description': {'type': 'doc', 'content': [{'type': 'paragraph', 'content': [
            {'type': 'text', 'text': description}]}]},
    }}


class SearchIssuesTest(TestCase):
    creds = dict(CONFLUENCE_DOMAIN='x.atlassian.net',
                 CONFLUENCE_EMAIL='e@x.com', CONFLUENCE_API_TOKEN='tok')

    def _resp(self, status=200, payload=None):
        return SimpleNamespace(status_code=status, json=lambda: payload or {})

    @mock.patch('portal.jira_client.requests.post')
    def test_returns_issues_from_jql_search(self, mpost):
        mpost.return_value = self._resp(200, {'issues': [
            {'key': 'SUP-637', 'fields': {'summary': 'Search Engine Issues'}},
        ], 'isLast': True})
        with self.settings(**self.creds):
            out = jira_client.search_issues('project = SUP')
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]['key'], 'SUP-637')

    @mock.patch('portal.jira_client.requests.post')
    def test_follows_pagination_across_pages(self, mpost):
        mpost.side_effect = [
            self._resp(200, {'issues': [{'key': 'SUP-1'}], 'nextPageToken': 'p2'}),
            self._resp(200, {'issues': [{'key': 'SUP-2'}], 'isLast': True}),
        ]
        with self.settings(**self.creds):
            out = jira_client.search_issues('project = SUP')
        self.assertEqual([i['key'] for i in out], ['SUP-1', 'SUP-2'])

    @mock.patch('portal.jira_client.requests.post')
    def test_non_200_is_not_treated_as_results(self, mpost):
        # A rejected JQL still returns a JSON body; it must never be mistaken
        # for a result set, or a bad query would look like "nothing to ingest".
        mpost.return_value = SimpleNamespace(
            status_code=400, text='bad jql',
            json=lambda: {'issues': [{'key': 'SUP-999'}]})
        with self.settings(**self.creds):
            self.assertEqual(jira_client.search_issues('bad jql'), [])

    @mock.patch('portal.jira_client.requests.post', side_effect=Exception('boom'))
    def test_exception_returns_empty(self, mpost):
        with self.settings(**self.creds):
            self.assertEqual(jira_client.search_issues('project = SUP'), [])

    def test_missing_creds_returns_empty(self):
        with self.settings(CONFLUENCE_DOMAIN='', CONFLUENCE_EMAIL='',
                           CONFLUENCE_API_TOKEN=''):
            self.assertEqual(jira_client.search_issues('project = SUP'), [])


class IngestRequestsTest(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name='SunNuclear')
        self.customer = PortalUser.objects.create(
            email='ddonaho@mirion.com', name='Darby',
            role=PortalUser.ROLE_CUSTOMER, company=self.company)

    def _run(self, issues, **settings_kw):
        opts = dict(JIRA_INGEST=True, JIRA_INGEST_PROJECT='SUP')
        opts.update(settings_kw)
        with self.settings(**opts):
            with mock.patch('portal.jira_ingest.jira_client.search_issues',
                            return_value=issues):
                with mock.patch('portal.jira_ingest.jira_client.create_remote_link'):
                    return jira_ingest.ingest_requests()

    def test_matched_customer_gets_a_linked_ticket(self):
        created = self._run([issue()])
        self.assertEqual(created, 1)
        t = Ticket.objects.get()
        self.assertEqual(t.company, self.company)
        self.assertEqual(t.created_by, self.customer)
        self.assertEqual(t.subject, 'Search Engine Issues')
        self.assertEqual(
            list(t.jira_links.values_list('key', flat=True)), ['SUP-637'])

    def test_issue_body_becomes_the_first_message(self):
        self._run([issue(description='The searches are very slow.')])
        m = TicketMessage.objects.get()
        self.assertEqual(m.body, 'The searches are very slow.')
        self.assertEqual(m.origin, TicketMessage.ORIGIN_EMAIL)

    def test_unknown_reporter_is_ignored(self):
        # Scraper bots, sales spam and unonboarded senders all land here.
        self.assertEqual(self._run([issue(email='sales@upweb.com')]), 0)
        self.assertEqual(Ticket.objects.count(), 0)

    def test_staff_reporter_is_ignored(self):
        # Staff file Jira issues routinely; those are not customer tickets.
        # Seeded as an admin by migration 0005, so update rather than create.
        PortalUser.objects.update_or_create(
            email='edrower@citemed.com',
            defaults={'role': PortalUser.ROLE_OWNER, 'company': self.company})
        self.assertEqual(self._run([issue(email='edrower@citemed.com')]), 0)
        self.assertEqual(Ticket.objects.count(), 0)

    def test_disabled_customer_is_ignored(self):
        self.customer.access_enabled = False
        self.customer.save(update_fields=['access_enabled'])
        self.assertEqual(self._run([issue()]), 0)
        self.assertEqual(Ticket.objects.count(), 0)

    def test_customer_without_company_is_ignored(self):
        # Ticket.company is non-nullable; a companyless match must not 500.
        self.customer.company = None
        self.customer.save(update_fields=['company'])
        self.assertEqual(self._run([issue()]), 0)
        self.assertEqual(Ticket.objects.count(), 0)

    def test_hidden_reporter_email_is_ignored(self):
        iss = issue()
        iss['fields']['reporter'] = {'displayName': 'Someone'}
        self.assertEqual(self._run([iss]), 0)

    def test_already_linked_issue_is_not_ingested_twice(self):
        self._run([issue()])
        self.assertEqual(self._run([issue()]), 0)
        self.assertEqual(Ticket.objects.count(), 1)

    def test_link_from_any_ticket_blocks_reingest(self):
        # An issue linked by hand (staff pasted the key) must not be duplicated.
        t = Ticket.objects.create(company=self.company, subject='pasted by staff')
        JiraTicketLink.objects.create(ticket=t, key='SUP-637')
        self.assertEqual(self._run([issue()]), 0)
        self.assertEqual(Ticket.objects.count(), 1)

    def test_disabled_by_default(self):
        with self.settings(JIRA_INGEST=False):
            with mock.patch('portal.jira_ingest.jira_client.search_issues') as ms:
                self.assertEqual(jira_ingest.ingest_requests(), 0)
        ms.assert_not_called()

    def test_customer_is_not_emailed(self):
        # JSM already sent its own "request received" auto-reply; a portal
        # confirmation on top would be a duplicate notification.
        from django.core import mail
        mail.outbox = []
        self._run([issue()])
        self.assertEqual(mail.outbox, [])

    def test_links_back_to_the_portal_ticket(self):
        with self.settings(JIRA_INGEST=True, FRONTEND_URL='https://support.citemed.com'):
            with mock.patch('portal.jira_ingest.jira_client.search_issues',
                            return_value=[issue()]):
                with mock.patch('portal.jira_ingest.jira_client.create_remote_link') as mrl:
                    jira_ingest.ingest_requests()
        t = Ticket.objects.get()
        mrl.assert_called_once()
        self.assertEqual(mrl.call_args[0][0], 'SUP-637')
        self.assertIn(f'/manage/tickets/{t.number}', mrl.call_args[0][1])

    def test_cutoff_is_applied_to_the_query(self):
        with self.settings(JIRA_INGEST=True, JIRA_INGEST_SINCE='2026-08-01'):
            with mock.patch('portal.jira_ingest.jira_client.search_issues',
                            return_value=[]) as ms:
                jira_ingest.ingest_requests()
        self.assertIn('2026-08-01', ms.call_args[0][0])

    def test_dry_run_reports_without_writing(self):
        self.assertEqual(self._run([issue()], JIRA_INGEST=True), 1)
        Ticket.objects.all().delete()
        JiraTicketLink.objects.all().delete()
        with self.settings(JIRA_INGEST=True):
            with mock.patch('portal.jira_ingest.jira_client.search_issues',
                            return_value=[issue()]):
                n = jira_ingest.ingest_requests(dry_run=True)
        self.assertEqual(n, 1)
        self.assertEqual(Ticket.objects.count(), 0)


class IngestCommandTest(TestCase):
    @mock.patch('portal.management.commands.ingest_jira_requests.ingest_requests',
                return_value=0)
    def test_writes_by_default(self, ming):
        call_command('ingest_jira_requests')
        self.assertEqual(ming.call_args.kwargs, {'dry_run': False})

    @mock.patch('portal.management.commands.ingest_jira_requests.ingest_requests',
                return_value=0)
    def test_dry_run_flag_is_passed_through(self, ming):
        call_command('ingest_jira_requests', '--dry-run')
        self.assertEqual(ming.call_args.kwargs, {'dry_run': True})


class IngestRobustnessTest(TestCase):
    """One bad issue must never cost us the rest of the batch."""

    def setUp(self):
        self.company = Company.objects.create(name='SunNuclear')
        self.customer = PortalUser.objects.create(
            email='ddonaho@mirion.com', role=PortalUser.ROLE_CUSTOMER,
            company=self.company)

    def test_plain_string_description_does_not_raise(self):
        # Not every issue carries an ADF body — a v2-created issue can return a
        # bare string, and that must not explode.
        self.assertEqual(jira_client.adf_to_text('plain text body'),
                         'plain text body')

    def test_one_broken_issue_does_not_abort_the_pass(self):
        bad = issue(key='SUP-1')
        bad['fields']['description'] = 'a plain string, not ADF'
        good = issue(key='SUP-2')
        with self.settings(JIRA_INGEST=True):
            with mock.patch('portal.jira_ingest.jira_client.search_issues',
                            return_value=[bad, good]):
                with mock.patch('portal.jira_ingest.jira_client.create_remote_link'):
                    created = jira_ingest.ingest_requests()
        self.assertEqual(created, 2)
        self.assertEqual(
            set(JiraTicketLink.objects.values_list('key', flat=True)),
            {'SUP-1', 'SUP-2'})
