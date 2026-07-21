import json
from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.core import mail
from django.utils import timezone

from portal.models import Company, PortalUser, Ticket, TicketMessage, TicketRead


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

    def test_staff_reply_records_delivery_sent(self):
        m = TicketMessage.objects.create(
            ticket=self.t, author=self.staff, author_email=self.staff.email,
            body='hi', origin='staff')
        from portal import ticket_notify
        ticket_notify.notify_staff_reply(self.t, m)
        m.refresh_from_db()
        self.assertEqual(m.delivery_status, TicketMessage.DELIVERY_SENT)
        self.assertTrue(m.delivery_attempted_at)
        self.assertEqual(m.delivery_detail, '')

    def test_send_failure_records_failed_with_detail(self):
        m = TicketMessage.objects.create(
            ticket=self.t, author=self.staff, author_email=self.staff.email,
            body='hi', origin='staff')
        from portal import ticket_notify
        with patch('portal.ticket_notify.EmailMultiAlternatives.send',
                   side_effect=RuntimeError('smtp boom')):
            ticket_notify.notify_staff_reply(self.t, m)
        m.refresh_from_db()
        self.assertEqual(m.delivery_status, TicketMessage.DELIVERY_FAILED)
        self.assertIn('boom', m.delivery_detail)

    def test_internal_note_delivery_not_applicable(self):
        m = TicketMessage.objects.create(
            ticket=self.t, author=self.staff, body='note', origin='staff',
            is_internal=True)
        from portal import ticket_notify
        ticket_notify.notify_staff_reply(self.t, m)
        m.refresh_from_db()
        self.assertEqual(m.delivery_status, TicketMessage.DELIVERY_NA)

    def test_send_captures_esp_message_id(self):
        # Anymail's test backend exposes anymail_status.message_id; we store it
        # so delivery webhooks can correlate events back to this message.
        m = TicketMessage.objects.create(
            ticket=self.t, author=self.staff, author_email=self.staff.email,
            body='hi', origin='staff')
        from portal import ticket_notify
        with override_settings(EMAIL_BACKEND='anymail.backends.test.EmailBackend'):
            ticket_notify.notify_staff_reply(self.t, m)
        m.refresh_from_db()
        self.assertTrue(m.esp_message_id)

    def test_delivery_webhook_marks_delivered(self):
        from anymail.signals import tracking, AnymailTrackingEvent
        m = TicketMessage.objects.create(
            ticket=self.t, author=self.staff, body='hi', origin='staff',
            delivery_status=TicketMessage.DELIVERY_SENT, esp_message_id='<abc@mg>')
        tracking.send(sender=object,
                      event=AnymailTrackingEvent(event_type='delivered', message_id='<abc@mg>'),
                      esp_name='Mailgun')
        m.refresh_from_db()
        self.assertEqual(m.delivery_status, TicketMessage.DELIVERY_DELIVERED)

    def test_delivery_webhook_marks_bounced_with_reason(self):
        from anymail.signals import tracking, AnymailTrackingEvent
        m = TicketMessage.objects.create(
            ticket=self.t, author=self.staff, body='hi', origin='staff',
            delivery_status=TicketMessage.DELIVERY_SENT, esp_message_id='<b@mg>')
        tracking.send(sender=object,
                      event=AnymailTrackingEvent(event_type='bounced', message_id='<b@mg>',
                                                 description='mailbox full'),
                      esp_name='Mailgun')
        m.refresh_from_db()
        self.assertEqual(m.delivery_status, TicketMessage.DELIVERY_BOUNCED)
        self.assertIn('mailbox full', m.delivery_detail)

    def test_onbehalf_recipients_exclude_staff_creator(self):
        # On-behalf ticket: created_by is staff, customer is in cc. The staff
        # creator must NOT receive the customer-facing confirmation.
        from portal import ticket_notify
        ob = Ticket.objects.create(company=self.acme, created_by=self.staff,
                                   subject='OB', cc_emails=['client@acme.com'])
        r = ticket_notify._customer_recipients(ob)
        self.assertIn('client@acme.com', r)
        self.assertNotIn(self.staff.email, r)

    def test_bounce_wins_over_later_delivered(self):
        # A bounce to one recipient must not be hidden by another recipient's
        # delivered event, regardless of arrival order.
        from portal.webhook_handlers import apply_delivery_event
        m = TicketMessage.objects.create(
            ticket=self.t, author=self.staff, body='hi', origin='staff',
            delivery_status=TicketMessage.DELIVERY_SENT, esp_message_id='<x@mg>')
        apply_delivery_event('x@mg', 'bounced', 'no such user', 'bad@x.com')
        apply_delivery_event('x@mg', 'delivered', '', 'good@x.com')  # later, other recipient
        m.refresh_from_db()
        self.assertEqual(m.delivery_status, TicketMessage.DELIVERY_BOUNCED)
        self.assertIn('bad@x.com', m.delivery_detail)

    def test_apply_delivery_event_matches_bracketless_id(self):
        # The Events API returns the message-id WITHOUT angle brackets; our
        # stored esp_message_id has them. Matching must be bracket-tolerant.
        from portal.webhook_handlers import apply_delivery_event
        m = TicketMessage.objects.create(
            ticket=self.t, author=self.staff, body='hi', origin='staff',
            delivery_status=TicketMessage.DELIVERY_SENT, esp_message_id='<abc@mg>')
        self.assertTrue(apply_delivery_event('abc@mg', 'delivered'))
        m.refresh_from_db()
        self.assertEqual(m.delivery_status, TicketMessage.DELIVERY_DELIVERED)

    def test_delivery_webhook_ignores_unknown_message_id(self):
        from anymail.signals import tracking, AnymailTrackingEvent
        m = TicketMessage.objects.create(
            ticket=self.t, author=self.staff, body='hi', origin='staff',
            delivery_status=TicketMessage.DELIVERY_SENT, esp_message_id='<known@mg>')
        # Event for a different id (e.g. a magic-link email) must not touch us.
        tracking.send(sender=object,
                      event=AnymailTrackingEvent(event_type='delivered', message_id='<other@mg>'),
                      esp_name='Mailgun')
        m.refresh_from_db()
        self.assertEqual(m.delivery_status, TicketMessage.DELIVERY_SENT)

    def test_status_notification_does_not_overwrite_anchor_delivery(self):
        # notify_status reuses an existing message as a threading anchor; it
        # must not clobber that message's own delivery_status.
        m = TicketMessage.objects.create(
            ticket=self.t, author=self.staff, author_email=self.staff.email,
            body='earlier reply', origin='staff',
            delivery_status=TicketMessage.DELIVERY_SENT)
        from portal import ticket_notify
        self.t.status = Ticket.STATUS_RESOLVED
        self.t.save(update_fields=['status'])
        ticket_notify.notify_status(self.t)
        m.refresh_from_db()
        self.assertEqual(m.delivery_status, TicketMessage.DELIVERY_SENT)

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

    def test_detail_hides_internal_messages_and_jira_links(self):
        from portal.models import JiraTicketLink
        t = Ticket.objects.create(company=self.acme, created_by=self.cust, subject='A')
        JiraTicketLink.objects.create(ticket=t, key='ENG-99')
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

    def test_customer_payload_has_status_but_not_delivery_detail(self):
        t = Ticket.objects.create(company=self.acme, created_by=self.cust, subject='A')
        staff = PortalUser.objects.create(email='p@citemed.com', role='admin')
        TicketMessage.objects.create(
            ticket=t, author=staff, body='reply', origin='staff',
            delivery_status=TicketMessage.DELIVERY_FAILED,
            delivery_detail='SMTPException: mailbox full')
        self._login()
        r = self.client.get(f'/api/tickets/{t.number}/')
        payload = r.json()
        self.assertIn('delivery_status', payload['messages'][0])
        raw = json.dumps(payload)
        self.assertNotIn('delivery_detail', raw)
        self.assertNotIn('mailbox full', raw)

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

    def test_list_message_count_correct_and_no_n_plus_1(self):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext
        self._login()

        def build(n):
            Ticket.objects.filter(company=self.acme).delete()
            for i in range(n):
                t = Ticket.objects.create(company=self.acme, created_by=self.cust,
                                          subject=f'T{i}')
                TicketMessage.objects.create(ticket=t, body='pub', origin='portal')
                TicketMessage.objects.create(ticket=t, body='note', origin='staff',
                                             is_internal=True)

        build(1)
        with CaptureQueriesContext(connection) as one:
            r = self.client.get('/api/tickets/')
        # message_count excludes the internal note
        self.assertEqual(r.json()['tickets'][0]['message_count'], 1)

        build(5)
        with CaptureQueriesContext(connection) as many:
            self.client.get('/api/tickets/')
        # Query count must not grow with the number of tickets.
        self.assertEqual(len(one.captured_queries), len(many.captured_queries))


class PrevReadAtTests(TestCase):
    """ticket_detail must return the read state as it was BEFORE this GET
    advances it, so the customer thread can draw a persistent "New" divider
    above replies that arrived since the previous visit."""

    def setUp(self):
        self.acme, self.cust = make_co_user()
        self.t = Ticket.objects.create(company=self.acme, created_by=self.cust, subject='S')
        TicketMessage.objects.create(ticket=self.t, body='hi', origin='portal',
                                     author_email=self.cust.email)

    def _login(self):
        s = self.client.session
        s['portal_user_id'] = self.cust.id
        s.save()

    def _url(self):
        return f'/api/tickets/{self.t.number}/'

    def test_first_open_returns_null_then_advances(self):
        self._login()
        r1 = self.client.get(self._url())
        self.assertEqual(r1.status_code, 200)
        self.assertIsNone(r1.json().get('prev_read_at'))  # never read before
        self.assertTrue(TicketRead.objects.filter(user=self.cust, ticket=self.t).exists())

    def test_second_open_returns_first_open_time_not_now(self):
        self._login()
        self.client.get(self._url())
        read = TicketRead.objects.get(user=self.cust, ticket=self.t)
        # Backdate so the returned value is distinguishable from "now".
        read.last_read_at = timezone.now() - timedelta(hours=1)
        read.save(update_fields=['last_read_at'])

        r2 = self.client.get(self._url())
        prev = r2.json().get('prev_read_at')
        self.assertIsNotNone(prev)
        self.assertLess(prev, timezone.now().isoformat())

        # The read row is still advanced to now despite prev_read_at being backdated.
        read.refresh_from_db()
        self.assertGreater(read.last_read_at, timezone.now() - timedelta(minutes=1))


class ExtractJiraKeyTest(TestCase):
    def test_accepts_the_forms_agents_actually_paste(self):
        from portal.views.tickets_admin import _extract_jira_key as ek
        # bare key (any case) + classic browse URL with query/hash
        self.assertEqual(ek('SUP-374'), 'SUP-374')
        self.assertEqual(ek('sup-374'), 'SUP-374')
        self.assertEqual(ek('https://citemed.atlassian.net/browse/SUP-374'), 'SUP-374')
        self.assertEqual(ek('https://citemed.atlassian.net/browse/SUP-374?focusedCommentId=1'), 'SUP-374')
        # JSM agent-view URL — key is a path segment, no /browse/
        self.assertEqual(
            ek('https://citemed.atlassian.net/jira/servicedesk/projects/SUP/queues/custom/1/SUP-374'),
            'SUP-374')

    def test_rejects_non_issue_references(self):
        from portal.views.tickets_admin import _extract_jira_key as ek
        from portal.views.tickets_admin import JIRA_KEY_RE
        # a search/list URL only has the key in the query string → NOT a single
        # issue → must not be accepted as a link
        out = ek('https://citemed.atlassian.net/jira/servicedesk/projects/SUP/list?jql=key%3DSUP-374')
        self.assertFalse(JIRA_KEY_RE.match(out))
        # free text stays and is rejected downstream
        self.assertFalse(JIRA_KEY_RE.match(ek('some note about the bug')))


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

    def test_on_behalf_create_status_is_open_not_waiting_on_customer(self):
        # A brand-new on-behalf ticket must not claim we're "waiting on the
        # customer" — nothing's been asked yet. It opens as 'open' (tester
        # feedback: the old waiting_on_customer default read as misleading).
        self._login()
        r = self.client.post('/api/admin/tickets/', data=json.dumps({
            'company_id': self.acme.id, 'subject': 'For you',
            'body': 'Opened on your behalf',
        }), content_type='application/json')
        self.assertEqual(r.status_code, 200)
        t = Ticket.objects.get(number=r.json()['number'])
        self.assertEqual(t.status, Ticket.STATUS_OPEN)

    @patch('portal.views.tickets_admin._defer', side_effect=lambda fn: fn())
    @patch('portal.views.tickets_admin.jira_client.create_remote_link')
    @patch('portal.views.tickets_admin.jira_client.add_comment')
    @patch('portal.views.tickets_admin.jira_client.fetch_issue', return_value=None)
    def test_linking_servicedesk_issue_posts_reply_in_portal_nudge(self, mfetch, mcomment, mlink, mdefer):
        self._login()
        with override_settings(JIRA_SYNC_PROJECTS=['SUP']):
            r = self.client.post(f'/api/admin/tickets/{self.t.number}/jira/',
                                 data=json.dumps({'action': 'add', 'key': 'SUP-5'}),
                                 content_type='application/json')
        self.assertEqual(r.status_code, 200)
        # Internal backlink note + a remote link on the service-desk issue.
        self.assertIs(mcomment.call_args.kwargs.get('internal'), True)
        mlink.assert_called_once()

    @patch('portal.views.tickets_admin._defer', lambda fn: None)
    @patch('portal.views.tickets_admin.jira_client.fetch_issue', return_value=None)
    def test_linking_accepts_pasted_jira_url(self, mfetch):
        # Users paste the full browse URL, not the bare key — extract the key
        # instead of rejecting it as "Invalid Jira key" (tester feedback).
        self._login()
        r = self.client.post(
            f'/api/admin/tickets/{self.t.number}/jira/',
            data=json.dumps({'action': 'add',
                             'key': 'https://citemed.atlassian.net/browse/SUP-374?foo=1'}),
            content_type='application/json')
        self.assertEqual(r.status_code, 200)
        from portal.models import JiraTicketLink
        self.assertTrue(JiraTicketLink.objects.filter(ticket=self.t, key='SUP-374').exists())

    @patch('portal.views.tickets_admin._defer', side_effect=lambda fn: fn())
    @patch('portal.views.tickets_admin.jira_client.create_remote_link')
    @patch('portal.views.tickets_admin.jira_client.add_comment')
    @patch('portal.views.tickets_admin.jira_client.fetch_issue', return_value=None)
    def test_linking_engineering_issue_posts_no_nudge(self, mfetch, mcomment, mlink, mdefer):
        # An ECD bug isn't a customer-reply surface — no "reply in the portal" note.
        self._login()
        with override_settings(JIRA_SYNC_PROJECTS=['SUP']):
            r = self.client.post(f'/api/admin/tickets/{self.t.number}/jira/',
                                 data=json.dumps({'action': 'add', 'key': 'ECD-5'}),
                                 content_type='application/json')
        self.assertEqual(r.status_code, 200)
        mcomment.assert_not_called()
        mlink.assert_not_called()

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

    def test_resend_resends_failed_message(self):
        m = TicketMessage.objects.create(
            ticket=self.t, author=self.staff, author_email=self.staff.email,
            body='hi', origin='staff',
            delivery_status=TicketMessage.DELIVERY_FAILED,
            delivery_detail='old error')
        self._login()
        r = self.client.post(
            f'/api/admin/tickets/{self.t.number}/messages/{m.id}/resend/')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()['delivery_status'], TicketMessage.DELIVERY_SENT)
        m.refresh_from_db()
        self.assertEqual(m.delivery_status, TicketMessage.DELIVERY_SENT)
        self.assertTrue(any(self.cust.email in x.to for x in mail.outbox))

    def test_resend_requires_admin(self):
        m = TicketMessage.objects.create(
            ticket=self.t, author=self.staff, body='hi', origin='staff',
            delivery_status=TicketMessage.DELIVERY_FAILED)
        self._login(self.cust)
        r = self.client.post(
            f'/api/admin/tickets/{self.t.number}/messages/{m.id}/resend/')
        self.assertEqual(r.status_code, 403)

    def test_resend_rejects_non_staff_message(self):
        # Resend is for staff replies only — never re-emit a customer's own
        # message back to them dressed up as a staff reply.
        m = TicketMessage.objects.create(
            ticket=self.t, author=self.cust, body='my question', origin='portal',
            delivery_status=TicketMessage.DELIVERY_FAILED)
        self._login()
        r = self.client.post(
            f'/api/admin/tickets/{self.t.number}/messages/{m.id}/resend/')
        self.assertEqual(r.status_code, 400)

    def test_resend_rejects_internal_note(self):
        m = TicketMessage.objects.create(
            ticket=self.t, author=self.staff, body='note', origin='staff',
            is_internal=True, delivery_status=TicketMessage.DELIVERY_NA)
        self._login()
        r = self.client.post(
            f'/api/admin/tickets/{self.t.number}/messages/{m.id}/resend/')
        self.assertEqual(r.status_code, 400)

    def test_resend_rejects_message_from_other_ticket(self):
        other = Ticket.objects.create(company=self.acme, created_by=self.cust,
                                      subject='Other')
        m = TicketMessage.objects.create(ticket=other, author=self.staff,
                                         body='hi', origin='staff')
        self._login()
        r = self.client.post(
            f'/api/admin/tickets/{self.t.number}/messages/{m.id}/resend/')
        self.assertEqual(r.status_code, 404)

    def test_on_behalf_create_rejects_invalid_category(self):
        self._login()
        r = self.client.post('/api/admin/tickets/', data=json.dumps({
            'company_id': self.acme.id, 'subject': 'S', 'body': 'B',
            'category': 'nonsense',
        }), content_type='application/json')
        self.assertEqual(r.status_code, 200)
        t = Ticket.objects.get(number=r.json()['number'])
        self.assertEqual(t.category, 'other')

    def test_collection_flags_truncation_at_200(self):
        self._login()
        # Small list is not truncated.
        r = self.client.get('/api/admin/tickets/')
        self.assertFalse(r.json()['truncated'])
        # Over the cap: exactly 200 returned, truncated=True.
        Ticket.objects.bulk_create([
            Ticket(number=1000 + i, company=self.acme, created_by=self.cust,
                   subject=f'B{i}') for i in range(201)
        ])
        r = self.client.get('/api/admin/tickets/')
        self.assertEqual(len(r.json()['tickets']), 200)
        self.assertTrue(r.json()['truncated'])

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

    @patch('portal.jira_client.fetch_issue')
    def test_jira_link_add_shows_live_status_in_admin_detail(self, fetch):
        fetch.return_value = {'status': 'In Progress',
                              'status_category': 'indeterminate', 'summary': 'Fix sync'}
        self._login()
        r = self.client.post(f'/api/admin/tickets/{self.t.number}/jira/',
                             data=json.dumps({'action': 'add', 'key': 'ECD-42'}),
                             content_type='application/json')
        self.assertEqual(r.status_code, 200)
        d = self.client.get(f'/api/admin/tickets/{self.t.number}/').json()
        link = next(j for j in d['jira_links'] if j['key'] == 'ECD-42')
        self.assertEqual(link['status'], 'In Progress')
        self.assertEqual(link['status_category'], 'indeterminate')

    @patch('portal.jira_client.fetch_issue', return_value=None)
    def test_jira_link_remove(self, _fetch):
        from portal.models import JiraTicketLink
        JiraTicketLink.objects.create(ticket=self.t, key='ECD-42')
        self._login()
        self.client.post(f'/api/admin/tickets/{self.t.number}/jira/',
                         data=json.dumps({'action': 'remove', 'key': 'ECD-42'}),
                         content_type='application/json')
        self.assertEqual(self.t.jira_links.count(), 0)

    def test_jira_add_rejects_invalid_key(self):
        self._login()
        r = self.client.post(f'/api/admin/tickets/{self.t.number}/jira/',
                             data=json.dumps({'action': 'add', 'key': 'not a key'}),
                             content_type='application/json')
        self.assertEqual(r.status_code, 400)

    @patch('portal.jira_client.fetch_issue', return_value=None)
    def test_jira_status_unavailable_degrades_gracefully(self, _fetch):
        # API failure must not 500; link is created, status just blank.
        self._login()
        r = self.client.post(f'/api/admin/tickets/{self.t.number}/jira/',
                             data=json.dumps({'action': 'add', 'key': 'ECD-7'}),
                             content_type='application/json')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()['jira_links'][0]['status'], '')
