import json
from unittest import mock

from django.test import TestCase

from portal.models import Company, JiraTicketLink, PortalUser, Ticket


class ManualJiraLinkTest(TestCase):
    """Linking an existing Jira issue by key or URL.

    The point of validating is that a mistyped key passes the format check
    perfectly well, so without a existence check it links to nothing and shows
    a permanent "status unavailable" the agent can't diagnose.
    """

    def setUp(self):
        self.company = Company.objects.create(name='Acme')
        self.agent = PortalUser.objects.create(
            email='alice@citemed.com', role=PortalUser.ROLE_ADMIN)
        self.ticket = Ticket.objects.create(company=self.company, subject='Broken')
        session = self.client.session
        session['portal_user_id'] = self.agent.pk
        session.save()

    def _link(self, key, action='add'):
        return self.client.post(
            f'/api/admin/tickets/{self.ticket.number}/jira/',
            data=json.dumps({'action': action, 'key': key}),
            content_type='application/json')

    @mock.patch('portal.views.tickets_admin._defer')
    @mock.patch('portal.jira_client.fetch_issue')
    @mock.patch('portal.jira_client.verify_issue')
    def test_links_a_real_issue_and_stores_its_status(self, verify, fetch, defer):
        verify.return_value = ('ok', {'status': 'In Progress',
                                      'status_category': 'indeterminate',
                                      'summary': 'Real issue'})
        fetch.return_value = None
        res = self._link('ECD-2246')
        self.assertEqual(res.status_code, 200)
        link = JiraTicketLink.objects.get(ticket=self.ticket, key='ECD-2246')
        self.assertEqual(link.cached_status, 'In Progress')
        self.assertEqual(link.cached_summary, 'Real issue')

    @mock.patch('portal.views.tickets_admin._defer')
    @mock.patch('portal.jira_client.verify_issue')
    def test_accepts_a_pasted_jira_url(self, verify, defer):
        verify.return_value = ('ok', {'status': 'Draft', 'status_category': 'new',
                                      'summary': 's'})
        res = self._link('https://citemed.atlassian.net/browse/ECD-2246')
        self.assertEqual(res.status_code, 200)
        self.assertTrue(
            JiraTicketLink.objects.filter(ticket=self.ticket, key='ECD-2246').exists())

    @mock.patch('portal.jira_client.verify_issue')
    def test_a_nonexistent_key_is_rejected_and_creates_no_link(self, verify):
        verify.return_value = ('missing', None)
        res = self._link('ECD-999999')
        self.assertEqual(res.status_code, 400)
        self.assertIn("doesn't exist", res.json()['error'])
        self.assertFalse(JiraTicketLink.objects.filter(ticket=self.ticket).exists())

    @mock.patch('portal.views.tickets_admin._defer')
    @mock.patch('portal.jira_client.verify_issue')
    def test_an_unreachable_jira_still_links_but_warns(self, verify, defer):
        """An outage must not stop an agent recording a link they know is right."""
        verify.return_value = ('unreachable', None)
        res = self._link('ECD-2246')
        self.assertEqual(res.status_code, 200)
        self.assertIn('could not be reached', res.json()['warning'])
        self.assertTrue(
            JiraTicketLink.objects.filter(ticket=self.ticket, key='ECD-2246').exists())

    def test_a_malformed_key_is_rejected(self):
        res = self._link('not a key')
        self.assertEqual(res.status_code, 400)
        self.assertIn('Jira key', res.json()['error'])

    @mock.patch('portal.views.tickets_admin._defer')
    @mock.patch('portal.jira_client.verify_issue')
    def test_unlinking_needs_no_verification(self, verify, defer):
        """Removing a link must work even for an issue Jira can't resolve —
        otherwise a bad link recorded earlier could never be cleaned up."""
        JiraTicketLink.objects.create(ticket=self.ticket, key='ECD-999999')
        res = self._link('ECD-999999', action='remove')
        self.assertEqual(res.status_code, 200)
        self.assertFalse(JiraTicketLink.objects.filter(ticket=self.ticket).exists())
        verify.assert_not_called()


class VerifyIssueTest(TestCase):
    """404 is the only unambiguous 'this key is wrong'."""

    @mock.patch('portal.jira_client.requests.get')
    @mock.patch('portal.jira_client._creds', return_value=('x.atlassian.net', ('e', 't')))
    def test_404_is_missing(self, creds, get):
        get.return_value = mock.Mock(status_code=404)
        from portal import jira_client
        self.assertEqual(jira_client.verify_issue('ECD-1')[0], 'missing')

    @mock.patch('portal.jira_client.requests.get')
    @mock.patch('portal.jira_client._creds', return_value=('x.atlassian.net', ('e', 't')))
    def test_403_is_unreachable_not_missing(self, creds, get):
        """A permissions problem shouldn't be reported to the agent as a typo."""
        get.return_value = mock.Mock(status_code=403)
        from portal import jira_client
        self.assertEqual(jira_client.verify_issue('ECD-1')[0], 'unreachable')

    @mock.patch('portal.jira_client.requests.get', side_effect=Exception('boom'))
    @mock.patch('portal.jira_client._creds', return_value=('x.atlassian.net', ('e', 't')))
    def test_network_failure_is_unreachable(self, creds, get):
        from portal import jira_client
        self.assertEqual(jira_client.verify_issue('ECD-1')[0], 'unreachable')

    @mock.patch('portal.jira_client._creds', return_value=(None, None))
    def test_missing_credentials_is_unreachable(self, creds):
        from portal import jira_client
        self.assertEqual(jira_client.verify_issue('ECD-1')[0], 'unreachable')
