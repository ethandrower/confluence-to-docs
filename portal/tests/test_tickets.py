import json
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.core import mail

from portal.models import Company, PortalUser, Ticket, TicketMessage


def make_co_user(name='Acme', email='a@acme.com', role='customer'):
    co = Company.objects.create(name=name)
    u = PortalUser.objects.create(email=email, company=co, role=role)
    return co, u


class TicketModelTests(TestCase):
    def setUp(self):
        self.acme, self.cust = make_co_user()
        self.globex, self.other = make_co_user('Globex', 'g@globex.com')
        self.staff = PortalUser.objects.create(email='s@citemed.com', role='admin')

    def test_numbers_are_sequential_and_display_formatted(self):
        t1 = Ticket.objects.create(company=self.acme, created_by=self.cust, subject='A')
        t2 = Ticket.objects.create(company=self.globex, created_by=self.other, subject='B')
        self.assertEqual(t2.number, t1.number + 1)
        self.assertEqual(t1.display_number, f'CS-{t1.number}')

    def test_for_user_scopes_to_own_company(self):
        t = Ticket.objects.create(company=self.acme, created_by=self.cust, subject='A')
        Ticket.objects.create(company=self.globex, created_by=self.other, subject='B')
        ids = list(Ticket.for_user(self.cust).values_list('id', flat=True))
        self.assertEqual(ids, [t.id])

    def test_for_user_without_company_sees_nothing(self):
        loner = PortalUser.objects.create(email='x@x.com', role='customer')
        Ticket.objects.create(company=self.acme, created_by=self.cust, subject='A')
        self.assertEqual(Ticket.for_user(loner).count(), 0)

    def test_default_status_is_waiting_on_support(self):
        t = Ticket.objects.create(company=self.acme, created_by=self.cust, subject='A')
        self.assertEqual(t.status, Ticket.STATUS_WAITING_ON_SUPPORT)


@override_settings(DEFAULT_FROM_EMAIL='CiteMed Support <noreply@notification.citemed.com>')
class TicketNotifyTests(TestCase):
    def setUp(self):
        self.acme, self.cust = make_co_user()
        self.staff = PortalUser.objects.create(email='s@citemed.com', role='admin')
        self.t = Ticket.objects.create(
            company=self.acme, created_by=self.cust,
            subject='Sync broken', cc_emails=['cc@ext.com'])

    def test_staff_reply_emails_customer_and_ccs_with_threading(self):
        m = TicketMessage.objects.create(
            ticket=self.t, author=self.staff, author_email=self.staff.email,
            body='We fixed it', origin='staff')
        from portal import ticket_notify
        ticket_notify.notify_staff_reply(self.t, m)
        self.assertEqual(len(mail.outbox), 1)
        sent = mail.outbox[0]
        self.assertIn('cc@ext.com', sent.to)
        self.assertIn(self.cust.email, sent.to)
        self.assertIn(f'[{self.t.display_number}]', sent.subject)
        m.refresh_from_db()
        self.assertTrue(m.email_message_id)
        self.assertTrue(m.reply_token)
        self.assertIn(m.email_message_id, sent.extra_headers.get('Message-ID', ''))
        self.assertIn(f'ticket-{self.t.number}+{m.reply_token}@',
                      sent.extra_headers.get('Reply-To', ''))

    def test_internal_note_is_never_emailed(self):
        m = TicketMessage.objects.create(
            ticket=self.t, author=self.staff, body='secret', origin='staff',
            is_internal=True)
        from portal import ticket_notify
        ticket_notify.notify_staff_reply(self.t, m)
        self.assertEqual(len(mail.outbox), 0)

    def test_references_chain_to_previous_message(self):
        from portal import ticket_notify
        m1 = TicketMessage.objects.create(ticket=self.t, author=self.staff,
                                          body='r1', origin='staff')
        ticket_notify.notify_staff_reply(self.t, m1)
        m2 = TicketMessage.objects.create(ticket=self.t, author=self.staff,
                                          body='r2', origin='staff')
        ticket_notify.notify_staff_reply(self.t, m2)
        m1.refresh_from_db()
        refs = mail.outbox[1].extra_headers.get('References', '')
        self.assertIn(m1.email_message_id, refs)

    def test_reply_to_and_message_id_are_valid_with_display_name_from(self):
        # Regression test for the display-name DEFAULT_FROM_EMAIL bug: the
        # domain must be parsed from the bare address, not from the raw
        # "Display Name <addr>" string, or Reply-To/Message-ID pick up a
        # stray trailing '>'.
        m = TicketMessage.objects.create(
            ticket=self.t, author=self.staff, author_email=self.staff.email,
            body='We fixed it', origin='staff')
        from portal import ticket_notify
        ticket_notify.notify_staff_reply(self.t, m)
        sent = mail.outbox[0]
        m.refresh_from_db()

        reply_to = sent.extra_headers.get('Reply-To', '')
        self.assertEqual(
            reply_to,
            f'ticket-{self.t.number}+{m.reply_token}@notification.citemed.com')

        message_id = sent.extra_headers.get('Message-ID', '')
        self.assertRegex(message_id, r'^<[^<>]+@notification\.citemed\.com>$')

    def test_customer_recipients_dedupe_case_insensitively(self):
        self.t.cc_emails = ['DUP@ext.com', 'dup@ext.com', 'other@ext.com']
        self.t.save(update_fields=['cc_emails'])
        from portal import ticket_notify
        recipients = ticket_notify._customer_recipients(self.t)
        lowered = [r.lower() for r in recipients]
        self.assertEqual(len(lowered), len(set(lowered)))
        # first-seen casing is preserved
        self.assertIn('DUP@ext.com', recipients)
        self.assertNotIn('dup@ext.com', recipients)
        self.assertIn('other@ext.com', recipients)
