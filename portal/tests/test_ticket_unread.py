from django.test import TestCase

from portal.models import Company, PortalUser, Ticket, TicketRead


class MarkReadTest(TestCase):
    def setUp(self):
        self.co = Company.objects.create(name='Acme')
        self.user = PortalUser.objects.create(email='c@acme.com', company=self.co, role=PortalUser.ROLE_CUSTOMER)
        self.t = Ticket.objects.create(company=self.co, created_by=self.user, subject='x')

    def _login(self):
        s = self.client.session
        s['portal_user_id'] = self.user.id
        s.save()

    def test_opening_thread_upserts_last_read(self):
        self._login()
        self.assertFalse(TicketRead.objects.filter(user=self.user, ticket=self.t).exists())
        r = self.client.get(f'/api/tickets/{self.t.number}/')
        self.assertEqual(r.status_code, 200)
        tr = TicketRead.objects.get(user=self.user, ticket=self.t)
        first = tr.last_read_at
        self.assertIsNotNone(first)
        # opening again updates the timestamp, no duplicate row
        self.client.get(f'/api/tickets/{self.t.number}/')
        self.assertEqual(TicketRead.objects.filter(user=self.user, ticket=self.t).count(), 1)
