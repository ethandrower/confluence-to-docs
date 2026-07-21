"""Option A: portal CREATES + links the Jira issue via the API (ECD-2246),
replacing the fragile email-intake path. Reliable (we get the key back and
link immediately), works identically in dev and prod, no duplicate.

Units under test:
  - jira_client.create_issue        — POST an issue, return its key (best-effort)
  - jira_sync.provision_ticket_issue — gate, idempotency, create + link + backlink
  - provision_jira_issues command    — selects open, unlinked tickets
  - intake suppression               — no duplicate JSM email-intake issue
"""
from types import SimpleNamespace
from unittest import mock

from django.core import mail
from django.core.management import call_command
from django.test import TestCase, override_settings

from portal import jira_client, jira_sync
from portal.models import (
    Company, JiraTicketLink, PortalUser, Ticket, TicketMessage,
)

CREDS = dict(CONFLUENCE_DOMAIN='x.atlassian.net',
             CONFLUENCE_EMAIL='e@x.com', CONFLUENCE_API_TOKEN='tok')


class CreateIssueTest(TestCase):
    def _resp(self, status, payload=None):
        return SimpleNamespace(status_code=status, json=lambda: payload or {})

    @mock.patch('portal.jira_client.requests.post')
    def test_returns_key_and_sends_expected_payload(self, mpost):
        mpost.return_value = self._resp(201, {'key': 'SUP-500'})
        with self.settings(**CREDS):
            key = jira_client.create_issue('SUP', 'A summary', 'the body', '10103')
        self.assertEqual(key, 'SUP-500')
        fields = mpost.call_args.kwargs['json']['fields']
        self.assertEqual(fields['project'], {'key': 'SUP'})
        self.assertEqual(fields['issuetype'], {'id': '10103'})
        self.assertEqual(fields['summary'], 'A summary')
        self.assertEqual(fields['description']['type'], 'doc')

    @mock.patch('portal.jira_client.requests.post')
    def test_non_2xx_returns_none(self, mpost):
        mpost.return_value = self._resp(400, {'errors': {'x': 'y'}})
        with self.settings(**CREDS):
            self.assertIsNone(jira_client.create_issue('SUP', 's', 'b', '10103'))

    def test_missing_creds_returns_none(self):
        with self.settings(CONFLUENCE_DOMAIN='', CONFLUENCE_EMAIL='', CONFLUENCE_API_TOKEN=''):
            self.assertIsNone(jira_client.create_issue('SUP', 's', 'b', '10103'))


class ProvisionTicketIssueTest(TestCase):
    def setUp(self):
        self.co = Company.objects.create(name='Acme')
        self.cust = PortalUser.objects.create(
            email='c@acme.com', company=self.co, role=PortalUser.ROLE_CUSTOMER)
        self.t = Ticket.objects.create(
            company=self.co, created_by=self.cust, subject='Need help',
            status=Ticket.STATUS_WAITING_ON_SUPPORT)
        TicketMessage.objects.create(
            ticket=self.t, author=self.cust, author_email='c@acme.com',
            body='the problem', origin=TicketMessage.ORIGIN_PORTAL)

    @mock.patch('portal.jira_sync.jira_client.create_remote_link', return_value=True)
    @mock.patch('portal.jira_sync.jira_client.add_comment', return_value=True)
    @mock.patch('portal.jira_sync.jira_client.fetch_issue', return_value=None)
    @mock.patch('portal.jira_sync.jira_client.create_issue', return_value='SUP-501')
    def test_creates_and_links_when_enabled(self, mcreate, mfetch, mcomment, mlink):
        with self.settings(JIRA_AUTO_CREATE=True, JIRA_TICKET_PROJECT='SUP',
                           JIRA_TICKET_ISSUE_TYPE_ID='10103'):
            key = jira_sync.provision_ticket_issue(self.t)
        self.assertEqual(key, 'SUP-501')
        self.assertTrue(JiraTicketLink.objects.filter(ticket=self.t, key='SUP-501').exists())
        mcreate.assert_called_once()
        # backlink note on the created issue is INTERNAL (never customer-visible)
        self.assertIs(mcomment.call_args.kwargs.get('internal'), True)

    @mock.patch('portal.jira_sync.jira_client.create_issue')
    def test_gated_off_by_default(self, mcreate):
        with self.settings(JIRA_AUTO_CREATE=False):
            self.assertIsNone(jira_sync.provision_ticket_issue(self.t))
        mcreate.assert_not_called()

    @mock.patch('portal.jira_sync.jira_client.create_issue', return_value='SUP-9')
    def test_idempotent_when_already_linked(self, mcreate):
        JiraTicketLink.objects.create(ticket=self.t, key='SUP-1')
        with self.settings(JIRA_AUTO_CREATE=True, JIRA_TICKET_PROJECT='SUP',
                           JIRA_TICKET_ISSUE_TYPE_ID='10103'):
            self.assertIsNone(jira_sync.provision_ticket_issue(self.t))
        mcreate.assert_not_called()

    @mock.patch('portal.jira_sync.jira_client.create_issue', return_value=None)
    def test_create_failure_leaves_ticket_unlinked(self, mcreate):
        with self.settings(JIRA_AUTO_CREATE=True, JIRA_TICKET_PROJECT='SUP',
                           JIRA_TICKET_ISSUE_TYPE_ID='10103'):
            self.assertIsNone(jira_sync.provision_ticket_issue(self.t))
        self.assertFalse(self.t.jira_links.exists())


class ProvisionCommandTest(TestCase):
    def setUp(self):
        self.co = Company.objects.create(name='Acme')
        self.cust = PortalUser.objects.create(
            email='c@acme.com', company=self.co, role=PortalUser.ROLE_CUSTOMER)

        def _t(subject, status, linked):
            t = Ticket.objects.create(company=self.co, created_by=self.cust,
                                      subject=subject, status=status)
            if linked:
                JiraTicketLink.objects.create(ticket=t, key='SUP-1')
            return t

        self.open_unlinked = _t('a', Ticket.STATUS_WAITING_ON_SUPPORT, False)
        self.open_linked = _t('b', Ticket.STATUS_WAITING_ON_SUPPORT, True)
        self.closed_unlinked = _t('c', Ticket.STATUS_CLOSED, False)

    @mock.patch('portal.management.commands.provision_jira_issues.provision_ticket_issue',
                return_value=None)
    def test_provisions_only_open_unlinked(self, mprov):
        call_command('provision_jira_issues')
        seen = {c.args[0].number for c in mprov.call_args_list}
        self.assertEqual(seen, {self.open_unlinked.number})


class IntakeSuppressionTest(TestCase):
    """When the portal creates the Jira issue itself (auto-create), it must NOT
    also email the JSM intake — that would make a duplicate issue."""
    def setUp(self):
        self.co = Company.objects.create(name='Acme')
        self.cust = PortalUser.objects.create(
            email='c@acme.com', company=self.co, role=PortalUser.ROLE_CUSTOMER)
        self.t = Ticket.objects.create(company=self.co, created_by=self.cust, subject='X')
        self.first = TicketMessage.objects.create(
            ticket=self.t, author=self.cust, author_email='c@acme.com',
            body='hi', origin=TicketMessage.ORIGIN_PORTAL)

    @override_settings(JIRA_AUTO_CREATE=True, SUPPORT_EMAIL='support@x.com')
    def test_no_intake_email_when_auto_create(self):
        from portal import ticket_notify
        ticket_notify.notify_ticket_created(self.t, self.first)
        # The staff/intake email to SUPPORT_EMAIL must not be sent.
        self.assertFalse(any('support@x.com' in m.to for m in mail.outbox))

    @override_settings(JIRA_AUTO_CREATE=False, SUPPORT_EMAIL='support@x.com')
    def test_intake_email_sent_when_not_auto_create(self):
        from portal import ticket_notify
        ticket_notify.notify_ticket_created(self.t, self.first)
        self.assertTrue(any('support@x.com' in m.to for m in mail.outbox))
