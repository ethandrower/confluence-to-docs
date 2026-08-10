import json

from django.core import mail
from django.test import TestCase, override_settings

from portal import ticket_notify
from portal.models import Company, PortalUser, Ticket, TicketMessage


@override_settings(SUPPORT_EMAIL='support@citemed.com')
class NotificationAudienceTest(TestCase):
    """Creation fans out to every agent; everything after narrows to the
    people actually on the ticket."""

    def setUp(self):
        self.company = Company.objects.create(name='Acme')
        self.alice = PortalUser.objects.create(
            email='alice@citemed.com', name='Alice', role=PortalUser.ROLE_ADMIN)
        self.bob = PortalUser.objects.create(
            email='bob@citemed.com', name='Bob', role=PortalUser.ROLE_ADMIN)
        self.owner = PortalUser.objects.create(
            email='owner@citemed.com', role=PortalUser.ROLE_OWNER)
        self.disabled = PortalUser.objects.create(
            email='gone@citemed.com', role=PortalUser.ROLE_ADMIN, access_enabled=False)
        self.customer = PortalUser.objects.create(
            email='jane@acme.com', role=PortalUser.ROLE_CUSTOMER, company=self.company)
        self.ticket = Ticket.objects.create(company=self.company, subject='Broken')

    def test_all_enabled_agents_are_notified_on_create(self):
        # Containment, not equality: a data migration seeds real staff accounts
        # into every fresh database, so the list is never just our fixtures.
        agents = ticket_notify._all_agent_emails()
        for email in ('alice@citemed.com', 'bob@citemed.com', 'owner@citemed.com'):
            self.assertIn(email, agents)

    def test_disabled_agent_is_not_notified(self):
        self.assertNotIn('gone@citemed.com', ticket_notify._all_agent_emails())

    def test_customers_are_not_treated_as_agents(self):
        self.assertNotIn('jane@acme.com', ticket_notify._all_agent_emails())

    def test_unassigned_followups_still_reach_the_shared_inbox(self):
        self.assertEqual(ticket_notify._staff_recipients(self.ticket),
                         ['support@citemed.com'])

    def test_followups_go_to_assignee_and_watchers_not_everyone(self):
        self.ticket.assignee = self.alice
        self.ticket.save()
        self.ticket.watchers.set([self.bob])
        recipients = ticket_notify._staff_recipients(self.ticket)
        self.assertCountEqual(
            recipients,
            ['alice@citemed.com', 'bob@citemed.com', 'support@citemed.com'])
        # The uninvolved owner is not on this ticket.
        self.assertNotIn('owner@citemed.com', recipients)

    def test_customer_reply_emails_only_those_on_the_ticket(self):
        self.ticket.assignee = self.alice
        self.ticket.save()
        msg = TicketMessage.objects.create(
            ticket=self.ticket, author=self.customer,
            author_email=self.customer.email, body='Any update?',
            origin=TicketMessage.ORIGIN_PORTAL)
        mail.outbox = []
        ticket_notify.notify_customer_reply(self.ticket, msg)
        self.assertEqual(len(mail.outbox), 1)
        self.assertCountEqual(mail.outbox[0].to,
                              ['alice@citemed.com', 'support@citemed.com'])

    def test_self_claim_does_not_email_the_claimer(self):
        self.ticket.assignee = self.alice
        self.ticket.save()
        mail.outbox = []
        ticket_notify.notify_assigned(self.ticket, actor=self.alice)
        self.assertEqual(mail.outbox, [])

    def test_being_assigned_by_someone_else_does_email_you(self):
        self.ticket.assignee = self.alice
        self.ticket.save()
        mail.outbox = []
        ticket_notify.notify_assigned(self.ticket, actor=self.bob)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ['alice@citemed.com'])


class AssignmentEndpointTest(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name='Acme')
        self.alice = PortalUser.objects.create(
            email='alice@citemed.com', name='Alice', role=PortalUser.ROLE_ADMIN)
        self.bob = PortalUser.objects.create(
            email='bob@citemed.com', name='Bob', role=PortalUser.ROLE_ADMIN)
        self.customer = PortalUser.objects.create(
            email='jane@acme.com', role=PortalUser.ROLE_CUSTOMER, company=self.company)
        self.ticket = Ticket.objects.create(company=self.company, subject='Broken')

    def _login(self, user):
        session = self.client.session
        session['portal_user_id'] = user.pk
        session.save()

    def _post(self, path, payload):
        return self.client.post(path, data=json.dumps(payload),
                                content_type='application/json')

    def test_assign_to_me_claims_the_ticket(self):
        self._login(self.alice)
        res = self._post(f'/api/admin/tickets/{self.ticket.number}/assignee/',
                         {'assign_to_me': True})
        self.assertEqual(res.status_code, 200)
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.assignee, self.alice)

    def test_can_hand_a_ticket_back_to_the_queue(self):
        self.ticket.assignee = self.alice
        self.ticket.save()
        self._login(self.alice)
        self._post(f'/api/admin/tickets/{self.ticket.number}/assignee/',
                   {'assignee_id': None})
        self.ticket.refresh_from_db()
        self.assertIsNone(self.ticket.assignee)

    def test_a_customer_cannot_be_made_the_assignee(self):
        self._login(self.alice)
        res = self._post(f'/api/admin/tickets/{self.ticket.number}/assignee/',
                         {'assignee_id': self.customer.pk})
        self.assertEqual(res.status_code, 400)
        self.ticket.refresh_from_db()
        self.assertIsNone(self.ticket.assignee)

    def test_replying_to_an_unassigned_ticket_claims_it(self):
        self._login(self.bob)
        res = self._post(f'/api/admin/tickets/{self.ticket.number}/messages/',
                         {'body': 'Looking into it.'})
        self.assertTrue(res.json()['auto_claimed'])
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.assignee, self.bob)

    def test_replying_does_not_steal_an_assigned_ticket(self):
        self.ticket.assignee = self.alice
        self.ticket.save()
        self._login(self.bob)
        res = self._post(f'/api/admin/tickets/{self.ticket.number}/messages/',
                         {'body': 'Adding a note.'})
        self.assertFalse(res.json()['auto_claimed'])
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.assignee, self.alice)

    def test_watchers_are_limited_to_agents(self):
        self._login(self.alice)
        res = self._post(f'/api/admin/tickets/{self.ticket.number}/watchers/',
                         {'watcher_ids': [self.bob.pk, self.customer.pk]})
        self.assertEqual(res.status_code, 200)
        self.assertEqual([w['email'] for w in res.json()['watchers']],
                         ['bob@citemed.com'])

    def test_customers_cannot_reach_the_assignment_endpoints(self):
        self._login(self.customer)
        res = self._post(f'/api/admin/tickets/{self.ticket.number}/assignee/',
                         {'assign_to_me': True})
        self.assertIn(res.status_code, (401, 403))


class StaffDataStaysInternalTest(TestCase):
    """Watchers and assignee are staff concepts — the customer payload must
    not carry them, the way cc_emails deliberately does."""

    def setUp(self):
        self.company = Company.objects.create(name='Acme')
        self.agent = PortalUser.objects.create(
            email='alice@citemed.com', role=PortalUser.ROLE_ADMIN)
        self.watcher = PortalUser.objects.create(
            email='bob@citemed.com', role=PortalUser.ROLE_ADMIN)
        self.customer = PortalUser.objects.create(
            email='jane@acme.com', role=PortalUser.ROLE_CUSTOMER, company=self.company)
        self.ticket = Ticket.objects.create(
            company=self.company, subject='Broken', assignee=self.agent)
        self.ticket.watchers.set([self.watcher])

    def test_customer_detail_hides_assignee_and_watchers(self):
        session = self.client.session
        session['portal_user_id'] = self.customer.pk
        session.save()
        res = self.client.get(f'/api/tickets/{self.ticket.number}/')
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertNotIn('assignee', body)
        self.assertNotIn('watchers', body)
        self.assertNotIn('bob@citemed.com', json.dumps(body))
        self.assertNotIn('alice@citemed.com', json.dumps(body))

    def test_customer_list_hides_assignee_and_watchers(self):
        session = self.client.session
        session['portal_user_id'] = self.customer.pk
        session.save()
        body = self.client.get('/api/tickets/').json()
        self.assertNotIn('assignee', json.dumps(body))
        self.assertNotIn('bob@citemed.com', json.dumps(body))
