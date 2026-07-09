from types import SimpleNamespace
from django.test import TestCase
from portal.models import Company, PortalUser, Ticket, TicketMessage
from portal import webhook_handlers


def _attach(name):
    return SimpleNamespace(get_filename=lambda: name)


def _inbound_event(*, recipient, from_email, text='emailed reply', message_id='<in-1@mg>', attachments=None):
    msg = SimpleNamespace(
        envelope_recipient=recipient, to=recipient, from_email=from_email,
        stripped_text=text, text=text, message_id=message_id,
        attachments=attachments or [],
    )
    return SimpleNamespace(message=msg)


class InboundHandlerTest(TestCase):
    def setUp(self):
        self.co = Company.objects.create(name='Acme')
        self.cust = PortalUser.objects.create(email='cust@acme.com', company=self.co, role=PortalUser.ROLE_CUSTOMER)
        self.t = Ticket.objects.create(company=self.co, created_by=self.cust, subject='x')
        # A prior outbound message carrying the reply token the customer answers to.
        self.staff_msg = TicketMessage.objects.create(
            ticket=self.t, author=self.cust, author_email='staff@citemed.com', body='how can we help',
            origin=TicketMessage.ORIGIN_STAFF, reply_token='TOK123')
        self.recipient = f'ticket-{self.t.number}+TOK123@notification.citemed.com'

    def _fire(self, event):
        webhook_handlers.handle_inbound(sender=None, event=event)

    def test_valid_reply_appends_message(self):
        before = self.t.messages.count()
        self._fire(_inbound_event(recipient=self.recipient, from_email='cust@acme.com'))
        self.t.refresh_from_db()
        self.assertEqual(self.t.messages.count(), before + 1)
        m = self.t.messages.order_by('-id').first()
        self.assertEqual(m.origin, TicketMessage.ORIGIN_EMAIL)
        self.assertEqual(m.body, 'emailed reply')
        self.assertEqual(self.t.status, Ticket.STATUS_WAITING_ON_SUPPORT)

    def test_invalid_token_dropped(self):
        before = self.t.messages.count()
        bad = f'ticket-{self.t.number}+WRONG@notification.citemed.com'
        self._fire(_inbound_event(recipient=bad, from_email='cust@acme.com'))
        self.assertEqual(self.t.messages.count(), before)

    def test_sender_mismatch_dropped(self):
        before = self.t.messages.count()
        self._fire(_inbound_event(recipient=self.recipient, from_email='stranger@evil.com'))
        self.assertEqual(self.t.messages.count(), before)

    def test_cc_sender_allowed(self):
        self.t.cc_emails = ['helper@acme.com']; self.t.save(update_fields=['cc_emails'])
        before = self.t.messages.count()
        self._fire(_inbound_event(recipient=self.recipient, from_email='helper@acme.com'))
        self.assertEqual(self.t.messages.count(), before + 1)

    def test_duplicate_message_id_deduped(self):
        self._fire(_inbound_event(recipient=self.recipient, from_email='cust@acme.com', message_id='<dup@mg>'))
        n = self.t.messages.count()
        self._fire(_inbound_event(recipient=self.recipient, from_email='cust@acme.com', message_id='<dup@mg>'))
        self.assertEqual(self.t.messages.count(), n)

    def test_attachments_noted_not_stored(self):
        self._fire(_inbound_event(recipient=self.recipient, from_email='cust@acme.com',
                                  attachments=[_attach('a.pdf'), _attach('b.png')]))
        m = self.t.messages.order_by('-id').first()
        self.assertIn('2 attachment', m.body.lower())

    def test_token_from_another_ticket_cannot_post(self):
        # Ticket B: different number, different reply token.
        tb = Ticket.objects.create(company=self.co, created_by=self.cust, subject='y')
        TicketMessage.objects.create(
            ticket=tb, author=self.cust, author_email='staff@citemed.com',
            body='hi from b', origin=TicketMessage.ORIGIN_STAFF, reply_token='TOKB')
        a_before, b_before = self.t.messages.count(), tb.messages.count()
        # Recipient targets ticket B's NUMBER but ticket A's TOKEN — the token
        # does not belong to B, so _match_ticket returns None and nothing lands.
        crafted = f'ticket-{tb.number}+TOK123@notification.citemed.com'
        self._fire(_inbound_event(recipient=crafted, from_email='cust@acme.com'))
        self.assertEqual(self.t.messages.count(), a_before)
        self.assertEqual(tb.messages.count(), b_before)
        # B's own token still works.
        good = f'ticket-{tb.number}+TOKB@notification.citemed.com'
        self._fire(_inbound_event(recipient=good, from_email='cust@acme.com'))
        self.assertEqual(tb.messages.count(), b_before + 1)

    def test_blank_token_recipient_dropped(self):
        before = self.t.messages.count()
        blank = f'ticket-{self.t.number}+@notification.citemed.com'
        self._fire(_inbound_event(recipient=blank, from_email='cust@acme.com'))
        self.assertEqual(self.t.messages.count(), before)
