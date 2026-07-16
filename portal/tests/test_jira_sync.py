"""S1: Jira→portal comment sync (ECD-2246 tester feedback).

Pulls PUBLIC Jira comments into the portal thread as staff messages so replies
made in Jira are no longer lost to the customer. Three units under test:
  - jira_client.adf_to_text  — flatten Atlassian Document Format to plain text
  - jira_client.fetch_comments — read + normalize an issue's comments (best-effort)
  - jira_sync.sync_ticket_comments — append public comments, dedupe, flip status
"""
from types import SimpleNamespace
from unittest import mock

from django.core.management import call_command
from django.test import TestCase

from portal import jira_client, jira_sync
from portal.models import (
    Company, JiraTicketLink, PortalUser, Ticket, TicketMessage,
)


# A real-shaped ADF doc: text + @mention inline, as Jira Cloud returns.
DOC_MENTION = {
    'type': 'doc', 'version': 1, 'content': [
        {'type': 'paragraph', 'content': [
            {'type': 'text', 'text': 'Hello '},
            {'type': 'mention', 'attrs': {'text': '@Het Patel'}},
            {'type': 'text', 'text': ' please review.'},
        ]},
    ],
}


class AdfToTextTest(TestCase):
    def test_flattens_text_and_mention(self):
        self.assertEqual(jira_client.adf_to_text(DOC_MENTION),
                         'Hello @Het Patel please review.')

    def test_multiple_paragraphs_separated_by_blank_line(self):
        doc = {'type': 'doc', 'content': [
            {'type': 'paragraph', 'content': [{'type': 'text', 'text': 'First.'}]},
            {'type': 'paragraph', 'content': [{'type': 'text', 'text': 'Second.'}]},
        ]}
        self.assertEqual(jira_client.adf_to_text(doc), 'First.\n\nSecond.')

    def test_hardbreak_becomes_newline(self):
        doc = {'type': 'doc', 'content': [{'type': 'paragraph', 'content': [
            {'type': 'text', 'text': 'a'}, {'type': 'hardBreak'},
            {'type': 'text', 'text': 'b'}]}]}
        self.assertEqual(jira_client.adf_to_text(doc), 'a\nb')

    def test_none_and_empty_are_blank(self):
        self.assertEqual(jira_client.adf_to_text(None), '')
        self.assertEqual(jira_client.adf_to_text({}), '')


class FetchCommentsTest(TestCase):
    creds = dict(CONFLUENCE_DOMAIN='x.atlassian.net',
                 CONFLUENCE_EMAIL='e@x.com', CONFLUENCE_API_TOKEN='tok')

    def _resp(self, status=200, payload=None):
        return SimpleNamespace(status_code=status, json=lambda: payload or {})

    @mock.patch('portal.jira_client.requests.get')
    def test_parses_id_body_and_public_flag(self, mget):
        mget.return_value = self._resp(200, {'comments': [{
            'id': '38462', 'created': '2026-07-14T08:02:44.978-0500',
            'author': {'displayName': 'remington'}, 'jsdPublic': True,
            'body': {'type': 'doc', 'content': [{'type': 'paragraph', 'content': [
                {'type': 'text', 'text': 'Moving this along.'}]}]},
        }]})
        with self.settings(**self.creds):
            out = jira_client.fetch_comments('ECD-1')
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]['id'], '38462')
        self.assertEqual(out[0]['body'], 'Moving this along.')
        self.assertTrue(out[0]['public'])

    @mock.patch('portal.jira_client.requests.get')
    def test_missing_jsdpublic_defaults_to_not_public(self, mget):
        # Fail-safe: a comment Jira does NOT mark public must never surface to a
        # customer, so absent jsdPublic → public=False.
        mget.return_value = self._resp(200, {'comments': [{
            'id': '1', 'author': {'displayName': 'x'},
            'body': {'type': 'doc', 'content': []}}]})
        with self.settings(**self.creds):
            out = jira_client.fetch_comments('ECD-1')
        self.assertFalse(out[0]['public'])

    @mock.patch('portal.jira_client.requests.get')
    def test_http_error_returns_empty(self, mget):
        mget.return_value = self._resp(404, {})
        with self.settings(**self.creds):
            self.assertEqual(jira_client.fetch_comments('ECD-1'), [])

    @mock.patch('portal.jira_client.requests.get', side_effect=Exception('boom'))
    def test_exception_returns_empty(self, mget):
        with self.settings(**self.creds):
            self.assertEqual(jira_client.fetch_comments('ECD-1'), [])

    def test_missing_creds_returns_empty(self):
        with self.settings(CONFLUENCE_DOMAIN='', CONFLUENCE_EMAIL='',
                           CONFLUENCE_API_TOKEN=''):
            self.assertEqual(jira_client.fetch_comments('ECD-1'), [])


class SyncTicketCommentsTest(TestCase):
    def setUp(self):
        self.co = Company.objects.create(name='Acme')
        self.cust = PortalUser.objects.create(
            email='c@acme.com', company=self.co, role=PortalUser.ROLE_CUSTOMER)
        self.t = Ticket.objects.create(
            company=self.co, created_by=self.cust, subject='x',
            status=Ticket.STATUS_WAITING_ON_SUPPORT)
        # Service-desk link → comments are eligible to sync (default allowlist).
        JiraTicketLink.objects.create(ticket=self.t, key='SUP-1')

    @mock.patch('portal.jira_sync.jira_client.fetch_comments')
    def test_engineering_project_link_never_syncs_comments(self, mfc):
        # A bug linked to an engineering project (ECD) must NOT surface its
        # comments to the customer, even public ones — they're dev/bot chatter.
        JiraTicketLink.objects.filter(ticket=self.t).delete()
        JiraTicketLink.objects.create(ticket=self.t, key='ECD-42')
        mfc.return_value = [{'id': '1', 'author': 'dev', 'body': 'code review notes',
                             'created': '', 'public': True}]
        self.assertEqual(jira_sync.sync_ticket_comments(self.t), 0)
        self.assertEqual(self.t.messages.count(), 0)
        mfc.assert_not_called()  # guarded out before any fetch

    @mock.patch('portal.jira_sync.jira_client.fetch_comments')
    def test_public_comment_appended_as_staff_message(self, mfc):
        mfc.return_value = [{'id': '1', 'author': 'a', 'body': 'hi from jira',
                             'created': '', 'public': True}]
        n = jira_sync.sync_ticket_comments(self.t)
        self.assertEqual(n, 1)
        m = self.t.messages.order_by('-id').first()
        self.assertEqual(m.origin, TicketMessage.ORIGIN_STAFF)
        self.assertIsNone(m.author)  # renders under the CiteMed Support facade
        self.assertEqual(m.body, 'hi from jira')
        self.assertEqual(m.jira_comment_id, '1')
        self.t.refresh_from_db()
        self.assertEqual(self.t.status, Ticket.STATUS_WAITING_ON_CUSTOMER)

    @mock.patch('portal.jira_sync.jira_client.fetch_comments')
    def test_internal_comment_skipped(self, mfc):
        mfc.return_value = [{'id': '2', 'author': 'a', 'body': 'internal',
                             'created': '', 'public': False}]
        self.assertEqual(jira_sync.sync_ticket_comments(self.t), 0)
        self.assertEqual(self.t.messages.count(), 0)

    @mock.patch('portal.jira_sync.jira_client.fetch_comments')
    def test_same_issue_linked_to_two_tickets_syncs_to_both(self, mfc):
        # Dedup must be per-ticket: one Jira issue can legitimately be linked to
        # two tickets, and its public comment must reach BOTH threads.
        mfc.return_value = [{'id': '7', 'author': 'a', 'body': 'shared fix',
                             'created': '', 'public': True}]
        t2 = Ticket.objects.create(company=self.co, created_by=self.cust,
                                   subject='y', status=Ticket.STATUS_WAITING_ON_SUPPORT)
        JiraTicketLink.objects.create(ticket=t2, key='SUP-1')  # same key as self.t
        jira_sync.sync_ticket_comments(self.t)
        jira_sync.sync_ticket_comments(t2)
        self.assertEqual(self.t.messages.filter(jira_comment_id='7').count(), 1)
        self.assertEqual(t2.messages.filter(jira_comment_id='7').count(), 1)

    @mock.patch('portal.jira_sync.jira_client.fetch_comments')
    def test_dedupes_across_runs(self, mfc):
        mfc.return_value = [{'id': '3', 'author': 'a', 'body': 'once',
                             'created': '', 'public': True}]
        jira_sync.sync_ticket_comments(self.t)
        self.assertEqual(jira_sync.sync_ticket_comments(self.t), 0)
        self.assertEqual(self.t.messages.filter(jira_comment_id='3').count(), 1)

    @mock.patch('portal.jira_sync.ticket_notify.notify_staff_reply')
    @mock.patch('portal.jira_sync.jira_client.fetch_comments')
    def test_no_email_by_default(self, mfc, mnotify):
        mfc.return_value = [{'id': '4', 'author': 'a', 'body': 'x',
                             'created': '', 'public': True}]
        jira_sync.sync_ticket_comments(self.t)
        mnotify.assert_not_called()

    @mock.patch('portal.jira_sync.ticket_notify.notify_staff_reply')
    @mock.patch('portal.jira_sync.jira_client.fetch_comments')
    def test_emails_customer_when_enabled(self, mfc, mnotify):
        mfc.return_value = [{'id': '5', 'author': 'a', 'body': 'x',
                             'created': '', 'public': True}]
        jira_sync.sync_ticket_comments(self.t, email_customer=True)
        mnotify.assert_called_once()

    @mock.patch('portal.jira_sync.ticket_notify.notify_staff_reply')
    @mock.patch('portal.jira_sync.jira_client.fetch_comments')
    def test_backfilled_comment_ingested_but_not_emailed(self, mfc, mnotify):
        # A public comment authored BEFORE we linked the issue is historical
        # backfill (JSM already emailed it) — ingest for visibility, never
        # re-email, even with the flag on. Guards against first-sync spam.
        mfc.return_value = [{'id': '9', 'author': 'a', 'body': 'old reply',
                             'created': '2020-01-01T00:00:00-0500', 'public': True}]
        jira_sync.sync_ticket_comments(self.t, email_customer=True)
        self.assertTrue(self.t.messages.filter(jira_comment_id='9').exists())
        mnotify.assert_not_called()

    @mock.patch('portal.jira_sync.ticket_notify.notify_staff_reply')
    @mock.patch('portal.jira_sync.jira_client.fetch_comments')
    def test_comment_after_link_is_emailed(self, mfc, mnotify):
        mfc.return_value = [{'id': '10', 'author': 'a', 'body': 'fresh reply',
                             'created': '2099-01-01T00:00:00-0500', 'public': True}]
        jira_sync.sync_ticket_comments(self.t, email_customer=True)
        mnotify.assert_called_once()


class SyncCommandTest(TestCase):
    def setUp(self):
        self.co = Company.objects.create(name='Acme')
        self.cust = PortalUser.objects.create(
            email='c@acme.com', company=self.co, role=PortalUser.ROLE_CUSTOMER)

        def _ticket(subject, status, linked):
            t = Ticket.objects.create(company=self.co, created_by=self.cust,
                                      subject=subject, status=status)
            if linked:
                JiraTicketLink.objects.create(ticket=t, key='ECD-1')
            return t

        self.open_linked = _ticket('open+link', Ticket.STATUS_WAITING_ON_SUPPORT, True)
        self.unlinked = _ticket('open no link', Ticket.STATUS_WAITING_ON_SUPPORT, False)
        self.closed_linked = _ticket('closed+link', Ticket.STATUS_CLOSED, True)

    @mock.patch('portal.management.commands.sync_jira_comments.sync_ticket_comments',
                return_value=0)
    def test_syncs_only_open_linked_tickets(self, msync):
        call_command('sync_jira_comments')
        synced = {c.args[0].number for c in msync.call_args_list}
        self.assertIn(self.open_linked.number, synced)
        self.assertNotIn(self.unlinked.number, synced)      # no Jira link
        self.assertNotIn(self.closed_linked.number, synced)  # closed → skipped

    @mock.patch('portal.management.commands.sync_jira_comments.sync_ticket_comments',
                return_value=0)
    def test_ticket_flag_targets_one(self, msync):
        call_command('sync_jira_comments', '--ticket', str(self.open_linked.number))
        synced = {c.args[0].number for c in msync.call_args_list}
        self.assertEqual(synced, {self.open_linked.number})
