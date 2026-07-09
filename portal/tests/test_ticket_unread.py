from django.test import TestCase

from portal.models import Company, PortalUser, Ticket, TicketMessage, TicketRead


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


class UnreadListTest(TestCase):
    def setUp(self):
        self.co = Company.objects.create(name='Acme')
        self.other = Company.objects.create(name='Other')
        self.user = PortalUser.objects.create(email='c@acme.com', company=self.co, role=PortalUser.ROLE_CUSTOMER)
        self.t = Ticket.objects.create(company=self.co, created_by=self.user, subject='x')

    def _login(self):
        s = self.client.session; s['portal_user_id'] = self.user.id; s.save()

    def _row(self, number):
        r = self.client.get('/api/tickets/')
        self.assertEqual(r.status_code, 200)
        return next(t for t in r.json()['tickets'] if t['number'] == number)

    def test_unread_true_when_staff_reply_and_never_opened(self):
        self._login()
        TicketMessage.objects.create(ticket=self.t, author=self.user, author_email='s@x.com',
                                     body='hi', origin=TicketMessage.ORIGIN_STAFF)
        self.assertTrue(self._row(self.t.number)['unread'])

    def test_unread_false_after_opening(self):
        self._login()
        TicketMessage.objects.create(ticket=self.t, author=self.user, author_email='s@x.com',
                                     body='hi', origin=TicketMessage.ORIGIN_STAFF)
        self.client.get(f'/api/tickets/{self.t.number}/')  # marks read
        self.assertFalse(self._row(self.t.number)['unread'])

    def test_own_and_internal_messages_do_not_mark_unread(self):
        self._login()
        TicketMessage.objects.create(ticket=self.t, author=self.user, author_email='c@acme.com',
                                     body='mine', origin=TicketMessage.ORIGIN_PORTAL)
        TicketMessage.objects.create(ticket=self.t, author=self.user, author_email='s@x.com',
                                     body='note', origin=TicketMessage.ORIGIN_STAFF, is_internal=True)
        self.assertFalse(self._row(self.t.number)['unread'])

    def test_other_company_ticket_never_in_list(self):
        # Tenant isolation: another company's staff-replied ticket is outside
        # Ticket.for_user(self.user), so it can never surface as unread here.
        other_user = PortalUser.objects.create(email='o@other.com', company=self.other,
                                               role=PortalUser.ROLE_CUSTOMER)
        other_t = Ticket.objects.create(company=self.other, created_by=other_user, subject='y')
        TicketMessage.objects.create(ticket=other_t, author=other_user, author_email='s@x.com',
                                     body='hi', origin=TicketMessage.ORIGIN_STAFF)
        self._login()
        r = self.client.get('/api/tickets/')
        self.assertEqual(r.status_code, 200)
        numbers = [t['number'] for t in r.json()['tickets']]
        self.assertNotIn(other_t.number, numbers)

    def test_new_staff_message_re_marks_unread_after_read(self):
        self._login()
        TicketMessage.objects.create(ticket=self.t, author=self.user, author_email='s@x.com',
                                     body='hi', origin=TicketMessage.ORIGIN_STAFF)
        self.client.get(f'/api/tickets/{self.t.number}/')  # marks read
        self.assertFalse(self._row(self.t.number)['unread'])
        TicketMessage.objects.create(ticket=self.t, author=self.user, author_email='s@x.com',
                                     body='newer', origin=TicketMessage.ORIGIN_STAFF)
        self.assertTrue(self._row(self.t.number)['unread'])
