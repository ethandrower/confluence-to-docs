"""Ticket priority (SLA doc — Priscilla, 2026-08-06).

Staff-assigned severity shown beside the status chip in the admin list. Set on
"our side" only: a customer who could raise their own ticket to Urgent would
make the field meaningless, so it is admin-write and admin-read — deliberately
absent from the customer serializer.
"""
import json

from django.test import TestCase

from portal.models import Company, PortalUser, Ticket, TicketMessage


class TicketPriorityModelTest(TestCase):
    def setUp(self):
        self.co = Company.objects.create(name='Acme')

    def test_new_ticket_defaults_to_standard(self):
        t = Ticket.objects.create(company=self.co, subject='x')
        self.assertEqual(t.priority, Ticket.PRIORITY_STANDARD)

    def test_the_four_sla_values_are_the_choices(self):
        self.assertEqual(
            [c[0] for c in Ticket.PRIORITY_CHOICES],
            ['urgent', 'high', 'standard', 'csm_direct'])


class TicketPriorityApiTest(TestCase):
    def setUp(self):
        self.co = Company.objects.create(name='Acme')
        self.cust = PortalUser.objects.create(
            email='c@acme.com', company=self.co, role=PortalUser.ROLE_CUSTOMER)
        self.staff = PortalUser.objects.create(
            email='s@citemed.com', role=PortalUser.ROLE_ADMIN)
        self.t = Ticket.objects.create(
            company=self.co, created_by=self.cust, subject='Help')

    def _login(self, user):
        s = self.client.session
        s['portal_user_id'] = user.id
        s.save()

    def _set(self, value, user=None):
        self._login(user or self.staff)
        return self.client.post(
            f'/api/admin/tickets/{self.t.number}/priority/',
            data=json.dumps({'priority': value}),
            content_type='application/json')

    def test_admin_can_set_priority(self):
        r = self._set('urgent')
        self.assertEqual(r.status_code, 200)
        self.t.refresh_from_db()
        self.assertEqual(self.t.priority, 'urgent')

    def test_invalid_priority_is_rejected(self):
        r = self._set('catastrophic')
        self.assertEqual(r.status_code, 400)
        self.t.refresh_from_db()
        self.assertEqual(self.t.priority, Ticket.PRIORITY_STANDARD)

    def test_customer_cannot_set_priority(self):
        r = self._set('urgent', user=self.cust)
        self.assertEqual(r.status_code, 403)
        self.t.refresh_from_db()
        self.assertEqual(self.t.priority, Ticket.PRIORITY_STANDARD)

    def test_change_is_recorded_in_activity(self):
        self._set('high')
        actions = list(self.t.activity.values_list('action', flat=True))
        self.assertIn('priority_changed', actions)

    def test_admin_list_exposes_priority(self):
        self._set('urgent')
        r = self.client.get('/api/admin/tickets/')
        row = next(x for x in r.json()['tickets'] if x['number'] == self.t.number)
        self.assertEqual(row['priority'], 'urgent')

    def test_customer_payload_never_exposes_priority(self):
        # Staff-internal: the customer must not see (or infer) their own
        # severity ranking from the API.
        self._set('urgent')
        TicketMessage.objects.create(
            ticket=self.t, author=self.cust, author_email=self.cust.email,
            body='hi', origin=TicketMessage.ORIGIN_PORTAL)
        self._login(self.cust)
        listing = self.client.get('/api/tickets/').json()['tickets']
        self.assertNotIn('priority', listing[0])
        detail = self.client.get(f'/api/tickets/{self.t.number}/').json()
        self.assertNotIn('priority', detail)
