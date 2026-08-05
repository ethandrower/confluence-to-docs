import json
from unittest import mock

from django.test import TestCase, override_settings

from portal import escalation
from portal.models import (Company, JiraTicketLink, PortalUser, Ticket,
                           TicketMessage)


class ComposeDescriptionTest(TestCase):
    """The description is the whole point of escalating from the portal: it
    should carry the customer's report AND the agent's diagnosis."""

    def setUp(self):
        self.company = Company.objects.create(name='Acme Medical')
        self.agent = PortalUser.objects.create(
            email='alice@citemed.com', name='Alice', role=PortalUser.ROLE_ADMIN)
        self.customer = PortalUser.objects.create(
            email='jane@acme.com', role=PortalUser.ROLE_CUSTOMER, company=self.company)
        self.ticket = Ticket.objects.create(
            company=self.company, subject='Extraction fields not saving',
            category='bug', requester=self.customer,
            requester_email='jane@acme.com', assignee=self.agent)
        TicketMessage.objects.create(
            ticket=self.ticket, author=self.customer, author_email='jane@acme.com',
            body='Fields reset when I hit save.', origin=TicketMessage.ORIGIN_PORTAL)
        TicketMessage.objects.create(
            ticket=self.ticket, author=self.agent, author_email='alice@citemed.com',
            body='Reproduced on EBOS. Looks like the autosave race.',
            origin=TicketMessage.ORIGIN_STAFF, is_internal=True)

    def test_includes_the_original_report(self):
        text = escalation.compose_description(self.ticket)
        self.assertIn('Fields reset when I hit save.', text)
        self.assertIn('--- Original report ---', text)

    def test_includes_internal_agent_notes(self):
        text = escalation.compose_description(self.ticket)
        self.assertIn('Reproduced on EBOS', text)
        self.assertIn('Support notes (internal)', text)

    def test_carries_the_customer_context(self):
        text = escalation.compose_description(self.ticket, 'http://portal/manage/tickets/1')
        self.assertIn('Acme Medical', text)
        self.assertIn('jane@acme.com', text)
        self.assertIn(self.ticket.display_number, text)
        self.assertIn('http://portal/manage/tickets/1', text)


@override_settings(JIRA_ESCALATION_PROJECTS=['ECD', 'AI'])
class EscalateTest(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name='Acme')
        self.agent = PortalUser.objects.create(
            email='alice@citemed.com', role=PortalUser.ROLE_ADMIN)
        self.ticket = Ticket.objects.create(company=self.company, subject='Broken')

    def _escalate(self, **over):
        kwargs = dict(project='ECD', issue_type_id='10133', summary='[CS-1] Broken',
                      description='body', priority_id='2', actor=self.agent)
        kwargs.update(over)
        return escalation.escalate(self.ticket, **kwargs)

    @mock.patch('portal.jira_client.create_remote_link', return_value=True)
    @mock.patch('portal.jira_client.add_to_sprint', return_value=True)
    @mock.patch('portal.jira_client.active_sprint_id', return_value=42)
    @mock.patch('portal.jira_client.create_issue_ex', return_value='ECD-9001')
    @mock.patch('portal.jira_client.find_or_create_epic', return_value='ECD-500')
    def test_happy_path_files_under_epic_and_sprint(self, epic, create, sprint,
                                                    add, link):
        res = self._escalate()
        self.assertEqual(res['key'], 'ECD-9001')
        self.assertEqual(res['epic_key'], 'ECD-500')
        self.assertEqual(res['sprint_id'], 42)
        self.assertEqual(res['warnings'], [])
        create.assert_called_once()
        self.assertEqual(create.call_args.kwargs['parent_key'], 'ECD-500')
        self.assertEqual(create.call_args.kwargs['priority_id'], '2')
        add.assert_called_once_with(42, 'ECD-9001')

    @mock.patch('portal.jira_client.create_remote_link', return_value=True)
    @mock.patch('portal.jira_client.active_sprint_id', return_value=42)
    @mock.patch('portal.jira_client.create_issue_ex', return_value='ECD-9001')
    @mock.patch('portal.jira_client.find_or_create_epic', return_value='ECD-500')
    def test_links_the_issue_so_status_sync_picks_it_up(self, epic, create,
                                                        sprint, link):
        with mock.patch('portal.jira_client.add_to_sprint', return_value=True):
            self._escalate()
        self.assertTrue(
            JiraTicketLink.objects.filter(ticket=self.ticket, key='ECD-9001').exists())

    @mock.patch('portal.jira_client.create_remote_link', return_value=True)
    @mock.patch('portal.jira_client.add_to_sprint', return_value=True)
    @mock.patch('portal.jira_client.active_sprint_id', return_value=None)
    @mock.patch('portal.jira_client.create_issue_ex', return_value='ECD-9001')
    @mock.patch('portal.jira_client.find_or_create_epic', return_value='ECD-500')
    def test_no_active_sprint_warns_but_still_escalates(self, *_):
        res = self._escalate()
        self.assertEqual(res['key'], 'ECD-9001')
        self.assertTrue(any('backlog' in w for w in res['warnings']))

    @mock.patch('portal.jira_client.create_remote_link', return_value=True)
    @mock.patch('portal.jira_client.add_to_sprint', return_value=True)
    @mock.patch('portal.jira_client.active_sprint_id', return_value=42)
    @mock.patch('portal.jira_client.create_issue_ex', return_value='ECD-9001')
    @mock.patch('portal.jira_client.find_or_create_epic', return_value=None)
    def test_epic_failure_warns_but_still_escalates(self, *_):
        res = self._escalate()
        self.assertEqual(res['key'], 'ECD-9001')
        self.assertTrue(any('epic' in w.lower() for w in res['warnings']))

    @mock.patch('portal.jira_client.create_issue_ex', return_value=None)
    @mock.patch('portal.jira_client.find_or_create_epic', return_value='ECD-500')
    def test_a_rejected_issue_creates_no_link(self, epic, create):
        res = self._escalate()
        self.assertIsNone(res['key'])
        self.assertFalse(JiraTicketLink.objects.filter(ticket=self.ticket).exists())

    def test_an_unlisted_project_is_refused(self):
        res = self._escalate(project='SECRET')
        self.assertIsNone(res['key'])
        self.assertIn('not an escalation target', res['error'])


@override_settings(JIRA_ESCALATION_PROJECTS=['ECD', 'AI'])
class EscalateEndpointTest(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name='Acme')
        self.agent = PortalUser.objects.create(
            email='alice@citemed.com', role=PortalUser.ROLE_ADMIN)
        self.customer = PortalUser.objects.create(
            email='jane@acme.com', role=PortalUser.ROLE_CUSTOMER, company=self.company)
        self.ticket = Ticket.objects.create(company=self.company, subject='Broken')

    def _login(self, user):
        session = self.client.session
        session['portal_user_id'] = user.pk
        session.save()

    def test_customers_cannot_escalate(self):
        self._login(self.customer)
        res = self.client.post(
            f'/api/admin/tickets/{self.ticket.number}/escalate/',
            data=json.dumps({'project': 'ECD', 'issue_type_id': '1',
                             'summary': 's', 'description': 'd'}),
            content_type='application/json')
        self.assertIn(res.status_code, (401, 403))

    def test_missing_fields_are_rejected(self):
        self._login(self.agent)
        res = self.client.post(
            f'/api/admin/tickets/{self.ticket.number}/escalate/',
            data=json.dumps({'project': 'ECD'}), content_type='application/json')
        self.assertEqual(res.status_code, 400)

    @mock.patch('portal.jira_client.list_priorities', return_value=[{'id': '2', 'name': 'High'}])
    @mock.patch('portal.jira_client.list_issue_types', return_value=[{'id': '10133', 'name': 'Bug'}])
    def test_options_offer_targets_and_a_prefilled_description(self, types, prios):
        self._login(self.agent)
        body = self.client.get(
            f'/api/admin/tickets/{self.ticket.number}/escalate/options/').json()
        self.assertEqual(body['projects'], ['ECD', 'AI'])
        self.assertEqual(body['issue_types'][0]['name'], 'Bug')
        self.assertEqual(body['priorities'][0]['name'], 'High')
        self.assertIn(self.ticket.display_number, body['summary'])
        self.assertIn('Acme', body['description'])

    @mock.patch('portal.views.tickets_admin._refresh_jira_links', return_value=[])
    @mock.patch('portal.escalation.escalate')
    def test_a_jira_failure_surfaces_as_502(self, esc, refresh):
        esc.return_value = {'key': None, 'error': 'Jira rejected the issue.'}
        self._login(self.agent)
        res = self.client.post(
            f'/api/admin/tickets/{self.ticket.number}/escalate/',
            data=json.dumps({'project': 'ECD', 'issue_type_id': '10133',
                             'summary': 's', 'description': 'd'}),
            content_type='application/json')
        self.assertEqual(res.status_code, 502)
