"""Inbound email replies, exercised through the REAL webhook URL (ECD-2250).

test_inbound_email.py calls `handle_inbound` directly with a hand-rolled fake
message, which skips Anymail's Mailgun parsing entirely. That gap is why a
production misconfiguration — the Mailgun route using `store()` where Anymail
requires `forward()` — passed a green suite and silently swallowed every
customer reply for weeks.

These tests POST Mailgun-shaped, correctly-signed multipart payloads to
/api/webhooks/mailgun/inbound/ so the whole chain runs: signature validation →
Anymail's parser → the `inbound` signal → our handler → the database.
"""
import hashlib
import hmac
import json

from django.test import TestCase, override_settings
from django.urls import reverse

from portal.models import Company, PortalUser, Ticket, TicketMessage

SIGNING_KEY = 'test-signing-key'
MAIL_DOMAIN = 'notification.citemed.com'


def _signed(timestamp='1700000000', token='tok'):
    signature = hmac.new(
        key=SIGNING_KEY.encode('ascii'),
        msg=f'{timestamp}{token}'.encode('ascii'),
        digestmod=hashlib.sha256,
    ).hexdigest()
    return {'timestamp': timestamp, 'token': token, 'signature': signature}


@override_settings(ANYMAIL={'MAILGUN_API_KEY': 'unused',
                            'MAILGUN_WEBHOOK_SIGNING_KEY': SIGNING_KEY})
class InboundWebhookTest(TestCase):
    def setUp(self):
        self.co = Company.objects.create(name='Acme')
        self.cust = PortalUser.objects.create(
            email='cust@acme.com', company=self.co, role=PortalUser.ROLE_CUSTOMER)
        self.t = Ticket.objects.create(company=self.co, created_by=self.cust, subject='x')
        TicketMessage.objects.create(
            ticket=self.t, author=self.cust, author_email='staff@citemed.com',
            body='how can we help', origin=TicketMessage.ORIGIN_STAFF,
            reply_token='TOK123')
        self.reply_to = f'ticket-{self.t.number}+TOK123@{MAIL_DOMAIN}'
        self.url = reverse('mailgun-inbound')

    def _forward_payload(self, *, from_email='cust@acme.com', body='emailed reply',
                         message_id='<in-1@mail.example>'):
        """Exactly the fields Mailgun's forward() action POSTs."""
        return {
            'recipient': self.reply_to,
            'sender': from_email,
            'from': from_email,
            'subject': f'Re: [{self.t.display_number}] x',
            'body-plain': f'{body}\n\nOn Mon, CiteMed Support wrote:\n> how can we help',
            'stripped-text': body,
            'message-headers': json.dumps([
                ['From', from_email],
                ['To', self.reply_to],
                ['Subject', f'Re: [{self.t.display_number}] x'],
                ['Message-Id', message_id],
            ]),
            **_signed(),
        }

    def test_forward_payload_appends_reply_to_ticket(self):
        before = self.t.messages.count()
        resp = self.client.post(self.url, self._forward_payload())
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(self.t.messages.count(), before + 1)
        m = self.t.messages.order_by('-id').first()
        self.assertEqual(m.origin, TicketMessage.ORIGIN_EMAIL)
        self.assertEqual(m.body, 'emailed reply')          # quoted tail stripped
        self.assertEqual(m.author_email, 'cust@acme.com')
        self.assertEqual(m.email_message_id, '<in-1@mail.example>')
        self.t.refresh_from_db()
        self.assertEqual(self.t.status, Ticket.STATUS_WAITING_ON_SUPPORT)

    def test_store_action_payload_is_not_silently_accepted(self):
        """The prod outage: a route configured with store(notify=...) posts an
        `attachments` field, which Anymail refuses. Nothing may reach the ticket."""
        from anymail.exceptions import AnymailConfigurationError
        payload = self._forward_payload()
        payload['attachments'] = '[]'          # the store()-only field
        before = self.t.messages.count()
        with self.assertRaises(AnymailConfigurationError):
            self.client.post(self.url, payload)
        self.assertEqual(self.t.messages.count(), before)

    def test_bad_signature_rejected(self):
        payload = self._forward_payload()
        payload['signature'] = '0' * 64
        before = self.t.messages.count()
        resp = self.client.post(self.url, payload)
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(self.t.messages.count(), before)

    def test_sender_not_on_ticket_dropped(self):
        before = self.t.messages.count()
        resp = self.client.post(
            self.url, self._forward_payload(from_email='stranger@evil.com'))
        self.assertEqual(resp.status_code, 200)   # accepted from Mailgun, dropped by us
        self.assertEqual(self.t.messages.count(), before)
