import json

from django.test import TestCase

from portal.models import Company, PortalUser, Ticket


class OnBehalfRequesterTest(TestCase):
    """Staff opening a ticket for a named customer.

    `created_by` is the agent; `requester` is the person it's for. Before this
    existed the customer was only a CC, so the ticket reached their inbox but
    never their portal.
    """

    url = '/api/admin/tickets/'

    def setUp(self):
        self.company = Company.objects.create(name='Acme')
        self.agent = PortalUser.objects.create(
            email='agent@citemed.com', role=PortalUser.ROLE_ADMIN)
        self.customer = PortalUser.objects.create(
            email='jane@acme.com', name='Jane', role=PortalUser.ROLE_CUSTOMER,
            company=self.company)

    def _login(self, user):
        session = self.client.session
        session['portal_user_id'] = user.pk
        session.save()

    def _create(self, **overrides):
        payload = {
            'company_id': self.company.id,
            'customer_email': 'jane@acme.com',
            'subject': 'Extraction fields not saving',
            'body': 'Opening on your behalf.',
        }
        payload.update(overrides)
        return self.client.post(self.url, data=json.dumps(payload),
                                content_type='application/json')

    def test_requester_is_linked_to_the_named_account(self):
        self._login(self.agent)
        res = self._create()
        self.assertEqual(res.status_code, 200)
        ticket = Ticket.objects.get(number=res.json()['number'])
        self.assertEqual(ticket.requester, self.customer)
        self.assertEqual(ticket.requester_email, 'jane@acme.com')
        # The agent opened it, but it isn't *for* them.
        self.assertEqual(ticket.created_by, self.agent)

    def test_response_reports_portal_access(self):
        self._login(self.agent)
        body = self._create().json()
        self.assertEqual(body['requester']['email'], 'jane@acme.com')
        self.assertTrue(body['requester']['has_portal_access'])

    def test_unknown_email_is_recorded_but_flagged_as_no_access(self):
        """Staff should learn at create time that this person can't sign in."""
        self._login(self.agent)
        body = self._create(customer_email='nobody@elsewhere.com').json()
        ticket = Ticket.objects.get(number=body['number'])
        self.assertIsNone(ticket.requester)
        self.assertEqual(ticket.requester_email, 'nobody@elsewhere.com')
        self.assertFalse(body['requester']['has_portal_access'])

    def test_customer_sees_the_on_behalf_ticket(self):
        self._login(self.agent)
        number = self._create().json()['number']
        self.client.logout()
        self._login(self.customer)
        res = self.client.get('/api/tickets/')
        self.assertEqual(res.status_code, 200)
        self.assertIn(number, [t['number'] for t in res.json()['tickets']])


class ForUserScopingTest(TestCase):
    """`Ticket.for_user` is the tenant-isolation chokepoint — verify that
    matching on requester widened it by exactly the intended tickets."""

    def setUp(self):
        self.acme = Company.objects.create(name='Acme')
        self.other = Company.objects.create(name='Other Co')
        self.jane = PortalUser.objects.create(
            email='jane@acme.com', company=self.acme, role=PortalUser.ROLE_CUSTOMER)
        self.rival = PortalUser.objects.create(
            email='rival@other.com', company=self.other, role=PortalUser.ROLE_CUSTOMER)

    def test_company_tickets_are_still_visible(self):
        t = Ticket.objects.create(company=self.acme, subject='s')
        self.assertIn(t, Ticket.for_user(self.jane))

    def test_other_company_tickets_are_still_hidden(self):
        t = Ticket.objects.create(company=self.other, subject='s')
        self.assertNotIn(t, Ticket.for_user(self.jane))

    def test_requester_sees_a_ticket_filed_under_another_company(self):
        t = Ticket.objects.create(company=self.other, subject='s', requester=self.jane)
        self.assertIn(t, Ticket.for_user(self.jane))

    def test_being_requester_does_not_expose_anyone_elses_tickets(self):
        """The widened branch matches this user's pk only."""
        mine = Ticket.objects.create(company=self.other, subject='mine', requester=self.jane)
        theirs = Ticket.objects.create(company=self.other, subject='theirs', requester=self.rival)
        visible = list(Ticket.for_user(self.jane))
        self.assertIn(mine, visible)
        self.assertNotIn(theirs, visible)

    def test_user_with_no_company_sees_only_their_own_requests(self):
        orphan = PortalUser.objects.create(email='orphan@x.com', role=PortalUser.ROLE_CUSTOMER)
        mine = Ticket.objects.create(company=self.acme, subject='mine', requester=orphan)
        other = Ticket.objects.create(company=self.acme, subject='other')
        visible = list(Ticket.for_user(orphan))
        self.assertEqual(visible, [mine])
        self.assertNotIn(other, visible)

    def test_anonymous_sees_nothing(self):
        Ticket.objects.create(company=self.acme, subject='s')
        self.assertEqual(list(Ticket.for_user(None)), [])
