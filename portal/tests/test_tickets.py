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


class TicketNumberRaceTests(TestCase):
    """Concurrent creates can race on Max(number)+1 between the aggregate read
    and the INSERT. Ticket.save() must retry on the resulting IntegrityError
    instead of propagating it to the caller."""

    def setUp(self):
        self.acme, self.cust = make_co_user()

    def test_retries_on_duplicate_number_and_ends_with_distinct_numbers(self):
        from django.db.models import Max

        real_aggregate = Ticket.objects.aggregate
        state = {'calls': 0}

        def stale_aggregate(*args, **kwargs):
            # First call (for the second ticket) returns a stale Max so the
            # first INSERT attempt collides with the already-created ticket.
            state['calls'] += 1
            if state['calls'] == 1:
                return {'number__max': None}
            return real_aggregate(*args, **kwargs)

        t1 = Ticket.objects.create(company=self.acme, created_by=self.cust, subject='A')

        with patch.object(Ticket.objects, 'aggregate', side_effect=stale_aggregate):
            t2 = Ticket.objects.create(company=self.acme, created_by=self.cust, subject='B')

        self.assertNotEqual(t1.number, t2.number)
        self.assertEqual(
            sorted(Ticket.objects.values_list('number', flat=True)),
            [t1.number, t2.number],
        )


class CustomerTicketApiTests(TestCase):
    def setUp(self):
        self.acme, self.cust = make_co_user()
        self.globex, self.other = make_co_user('Globex', 'g@globex.com')

    def _login(self, user=None):
        s = self.client.session
        s['portal_user_id'] = (user or self.cust).id
        s.save()

    def test_create_ticket_returns_number_and_emails_confirmation(self):
        self._login()
        r = self.client.post('/api/tickets/', data=json.dumps({
            'subject': 'Sync broken', 'category': 'bug',
            'body': 'The nightly sync failed', 'cc_emails': ['boss@acme.com'],
        }), content_type='application/json')
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertTrue(body['display_number'].startswith('CS-'))
        t = Ticket.objects.get(number=body['number'])
        self.assertEqual(t.status, Ticket.STATUS_WAITING_ON_SUPPORT)
        self.assertEqual(t.messages.count(), 1)
        self.assertTrue(any('boss@acme.com' in m.to for m in mail.outbox))

    def test_list_excludes_other_companies(self):
        Ticket.objects.create(company=self.globex, created_by=self.other, subject='X')
        mine = Ticket.objects.create(company=self.acme, created_by=self.cust, subject='Mine')
        self._login()
        r = self.client.get('/api/tickets/')
        nums = [t['number'] for t in r.json()['tickets']]
        self.assertEqual(nums, [mine.number])

    def test_create_tolerates_malformed_cc_emails(self):
        self._login()
        for bad in [123, {'x': 1}, 'a@b.com', None]:
            r = self.client.post('/api/tickets/', data=json.dumps({
                'subject': 'S', 'category': 'question', 'body': 'B', 'cc_emails': bad,
            }), content_type='application/json')
            self.assertEqual(r.status_code, 200, f'cc_emails={bad!r} should not 500')

    def test_message_author_never_blank(self):
        from portal.views.tickets import _message_dict
        t = Ticket.objects.create(company=self.acme, created_by=self.cust, subject='A')
        cust_msg = TicketMessage.objects.create(ticket=t, body='hi', origin='portal')
        staff_msg = TicketMessage.objects.create(ticket=t, body='yo', origin='staff')
        self.assertEqual(_message_dict(cust_msg)['author_name'], 'Customer')
        self.assertEqual(_message_dict(staff_msg)['author_name'], 'CiteMed Support')
        email_msg = TicketMessage.objects.create(
            ticket=t, body='x', origin='email', author_email='ext@client.com')
        self.assertEqual(_message_dict(email_msg)['author_name'], 'ext@client.com')

    def test_detail_hides_internal_messages_and_jira_key(self):
        t = Ticket.objects.create(company=self.acme, created_by=self.cust,
                                  subject='A', jira_key='ENG-99')
        TicketMessage.objects.create(ticket=t, body='public', origin='staff')
        TicketMessage.objects.create(ticket=t, body='secret', origin='staff',
                                     is_internal=True)
        self._login()
        r = self.client.get(f'/api/tickets/{t.number}/')
        payload = json.dumps(r.json())
        self.assertNotIn('secret', payload)
        self.assertNotIn('ENG-99', payload)
        self.assertNotIn('jira', payload)

    def test_staff_identity_is_hidden_from_customer(self):
        # A customer must never see an individual staffer's name or email —
        # only the "CiteMed Support" facade. jira_key/internal notes are
        # already covered; this closes the staff-identity leak.
        staff = PortalUser.objects.create(
            email='priscilla@citemed.com', name='Priscilla Murphy', role='admin')
        t = Ticket.objects.create(company=self.acme, created_by=self.cust, subject='A')
        TicketMessage.objects.create(
            ticket=t, author=staff, author_email=staff.email,
            body='we are on it', origin='staff')
        self._login()
        r = self.client.get(f'/api/tickets/{t.number}/')
        payload = r.json()
        staff_msgs = [m for m in payload['messages'] if m['is_staff']]
        self.assertEqual(len(staff_msgs), 1)
        self.assertEqual(staff_msgs[0]['author_name'], 'CiteMed Support')
        self.assertFalse(staff_msgs[0].get('author_email'))
        raw = json.dumps(payload)
        self.assertNotIn('priscilla@citemed.com', raw)
        self.assertNotIn('Priscilla Murphy', raw)

    def test_cross_tenant_detail_404s(self):
        t = Ticket.objects.create(company=self.globex, created_by=self.other, subject='X')
        self._login()
        r = self.client.get(f'/api/tickets/{t.number}/')
        self.assertEqual(r.status_code, 404)

    def test_customer_reply_flips_status_and_reopens_resolved(self):
        t = Ticket.objects.create(company=self.acme, created_by=self.cust,
                                  subject='A', status=Ticket.STATUS_RESOLVED)
        self._login()
        r = self.client.post(f'/api/tickets/{t.number}/messages/',
                             data=json.dumps({'body': 'still broken'}),
                             content_type='application/json')
        self.assertEqual(r.status_code, 200)
        t.refresh_from_db()
        self.assertEqual(t.status, Ticket.STATUS_WAITING_ON_SUPPORT)

    def test_requires_auth(self):
        r = self.client.get('/api/tickets/')
        self.assertEqual(r.status_code, 401)


class AdminTicketApiTests(TestCase):
    def setUp(self):
        self.acme, self.cust = make_co_user()
        self.staff = PortalUser.objects.create(email='s@citemed.com', role='admin')
        self.t = Ticket.objects.create(company=self.acme, created_by=self.cust,
                                       subject='Help')

    def _login(self, user=None):
        s = self.client.session
        s['portal_user_id'] = (user or self.staff).id
        s.save()

    def test_customer_cannot_hit_admin_endpoints(self):
        self._login(self.cust)
        r = self.client.get('/api/admin/tickets/inbox/')
        self.assertEqual(r.status_code, 403)

    def test_inbox_lists_waiting_on_support_oldest_first(self):
        t2 = Ticket.objects.create(company=self.acme, created_by=self.cust,
                                   subject='Newer')
        done = Ticket.objects.create(company=self.acme, created_by=self.cust,
                                     subject='Done',
                                     status=Ticket.STATUS_RESOLVED)
        self._login()
        r = self.client.get('/api/admin/tickets/inbox/')
        nums = [x['number'] for x in r.json()['tickets']]
        self.assertEqual(nums, [self.t.number, t2.number])
        self.assertEqual(r.json()['awaiting_total'], 2)

    def test_staff_reply_flips_status_and_emails_customer(self):
        self._login()
        r = self.client.post(f'/api/admin/tickets/{self.t.number}/messages/',
                             data=json.dumps({'body': 'On it'}),
                             content_type='application/json')
        self.assertEqual(r.status_code, 200)
        self.t.refresh_from_db()
        self.assertEqual(self.t.status, Ticket.STATUS_WAITING_ON_CUSTOMER)
        self.assertTrue(any(self.cust.email in m.to for m in mail.outbox))

    def test_internal_note_no_email_no_status_change(self):
        self._login()
        before = self.t.status
        r = self.client.post(f'/api/admin/tickets/{self.t.number}/messages/',
                             data=json.dumps({'body': 'note', 'is_internal': True}),
                             content_type='application/json')
        self.assertEqual(r.status_code, 200)
        self.t.refresh_from_db()
        self.assertEqual(self.t.status, before)
        self.assertEqual(len(mail.outbox), 0)

    def test_on_behalf_create_adds_customer_email_to_ccs(self):
        self._login()
        r = self.client.post('/api/admin/tickets/', data=json.dumps({
            'company_id': self.acme.id, 'subject': 'For you',
            'body': 'Opened on your behalf',
            'customer_email': 'client@acme.com',
        }), content_type='application/json')
        self.assertEqual(r.status_code, 200)
        t = Ticket.objects.get(number=r.json()['number'])
        self.assertIn('client@acme.com', t.cc_emails)
        self.assertTrue(any('client@acme.com' in m.to for m in mail.outbox))

    def test_status_resolved_emails_customer(self):
        TicketMessage.objects.create(ticket=self.t, author=self.staff,
                                     body='hi', origin='staff')
        self._login()
        r = self.client.post(f'/api/admin/tickets/{self.t.number}/status/',
                             data=json.dumps({'status': 'resolved'}),
                             content_type='application/json')
        self.assertEqual(r.status_code, 200)
        self.t.refresh_from_db()
        self.assertEqual(self.t.status, Ticket.STATUS_RESOLVED)
        self.assertTrue(mail.outbox)

    def test_admin_sees_real_staff_identity(self):
        # The facade is customer-only; Priscilla must still see who replied.
        staff2 = PortalUser.objects.create(
            email='priscilla@citemed.com', name='Priscilla Murphy', role='admin')
        TicketMessage.objects.create(
            ticket=self.t, author=staff2, author_email=staff2.email,
            body='handled', origin='staff')
        self._login()
        r = self.client.get(f'/api/admin/tickets/{self.t.number}/')
        raw = json.dumps(r.json())
        self.assertIn('Priscilla Murphy', raw)

    def test_jira_key_set_and_visible_to_admin_only(self):
        self._login()
        self.client.post(f'/api/admin/tickets/{self.t.number}/jira/',
                         data=json.dumps({'jira_key': 'ENG-42'}),
                         content_type='application/json')
        r = self.client.get(f'/api/admin/tickets/{self.t.number}/')
        self.assertEqual(r.json()['jira_key'], 'ENG-42')
