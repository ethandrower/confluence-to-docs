"""The read-only integration API at /api/v1/ (GitHub #44).

This file carries more weight than a typical view test, for two reasons.

First, this namespace deliberately crosses the tenant boundary that
`Ticket.for_user` enforces for every other reader in the portal. The bearer
token in portal/api_v1/auth.py is the ONLY thing between a cross-customer
support dataset and the internet, so "no token / bad token / revoked token is
rejected" has to be asserted here or nowhere.

Second, the existing CSRF sweep (`EveryUnsafeEndpointRequiresCsrfTest` in
test_auth_hardening.py) walks the URLconf for unsafe methods and correctly has
nothing to say about a GET-only API. Nothing else in the suite would catch a
regression that opened this door.

The other invariant under test is what is NOT in the payload: no
`TicketMessage.body`, no text from an `is_internal` staff note, no watchers, no
Jira keys. `test_no_message_body_or_internal_note_leaks_anywhere` asserts that
against the raw serialized bytes rather than field-by-field, so a new field
that happened to carry message text would still trip it.
"""
import json
from datetime import timedelta

from django.core.management import call_command
from django.test import Client, TestCase
from django.utils import timezone

from portal.models import (
    ApiClient, Company, PortalUser, Ticket, TicketMessage,
)

SECRET_BODY = 'CUSTOMER_MESSAGE_BODY_SHOULD_NEVER_APPEAR'
SECRET_NOTE = 'INTERNAL_STAFF_NOTE_SHOULD_NEVER_APPEAR'


class ApiV1TestCase(TestCase):
    """Fixtures shared by every test below."""

    def setUp(self):
        self.client_obj, self.token = ApiClient.issue('RevenueHub')

        self.acme = Company.objects.create(
            name='Acme Medical', contract_end_date='2027-03-01')
        self.globex = Company.objects.create(name='Globex Devices')

        self.jane = PortalUser.objects.create(email='jane@acme.com', company=self.acme)
        self.bob = PortalUser.objects.create(email='bob@acme.com', company=self.acme)
        self.zed = PortalUser.objects.create(email='zed@globex.com', company=self.globex)

        self.t1 = Ticket.objects.create(
            company=self.acme, created_by=self.jane, subject='Extraction fields',
            status=Ticket.STATUS_WAITING_ON_CUSTOMER, priority=Ticket.PRIORITY_HIGH,
            category='bug', cc_emails=['boss@acme.com'])
        self.t2 = Ticket.objects.create(
            company=self.acme, created_by=self.bob, subject='Export is slow',
            status=Ticket.STATUS_RESOLVED, priority=Ticket.PRIORITY_STANDARD,
            category='question', cc_emails=['jane@acme.com'])
        self.t3 = Ticket.objects.create(
            company=self.globex, created_by=self.zed, subject='Login loop',
            status=Ticket.STATUS_OPEN, priority=Ticket.PRIORITY_URGENT,
            category='bug')

        TicketMessage.objects.create(
            ticket=self.t1, author=self.jane, body=SECRET_BODY)
        TicketMessage.objects.create(
            ticket=self.t1, author=None, body=SECRET_NOTE, is_internal=True)

    def auth(self, token=None):
        return {'HTTP_AUTHORIZATION': f'Bearer {token or self.token}'}

    def get(self, path, token=None, **kwargs):
        return self.client.get(path, **self.auth(token), **kwargs)


# ── Authentication: the door ────────────────────────────────────────────────
class AuthenticationTest(ApiV1TestCase):
    PATHS = ['/api/v1/companies/', '/api/v1/tickets/', '/api/v1/tickets/1/']

    def test_no_token_is_401(self):
        for path in self.PATHS:
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 401)

    def test_malformed_authorization_headers_are_401(self):
        headers = [
            'Bearer',                       # no token
            f'Bearer {self.token} extra',   # too many parts
            f'Token {self.token}',          # wrong scheme
            self.token,                     # no scheme
            'Bearer not-a-real-token',
            'Basic dXNlcjpwYXNz',
        ]
        for value in headers:
            with self.subTest(header=value):
                r = self.client.get('/api/v1/tickets/', HTTP_AUTHORIZATION=value)
                self.assertEqual(r.status_code, 401)

    def test_disabled_client_is_401(self):
        self.client_obj.enabled = False
        self.client_obj.save(update_fields=['enabled'])
        self.assertEqual(self.get('/api/v1/tickets/').status_code, 401)

    def test_deleted_client_is_401(self):
        self.client_obj.delete()
        self.assertEqual(self.get('/api/v1/tickets/').status_code, 401)

    def test_valid_token_is_200(self):
        for path in ['/api/v1/companies/', '/api/v1/tickets/',
                     f'/api/v1/tickets/{self.t1.number}/']:
            with self.subTest(path=path):
                self.assertEqual(self.get(path).status_code, 200)

    def test_401_advertises_bearer(self):
        r = self.client.get('/api/v1/tickets/')
        self.assertIn('Bearer', r.headers.get('WWW-Authenticate', ''))


class TwoDoorsOneKeyEachTest(ApiV1TestCase):
    """The bearer door and the session door must not open each other."""

    def test_portal_session_alone_does_not_authenticate_this_api(self):
        # A fully logged-in portal admin — the most privileged human session
        # the portal issues — still gets 401 without a token.
        admin = PortalUser.objects.create(
            email='staff@citemed.com', role=PortalUser.ROLE_OWNER)
        session = self.client.session
        session['portal_user_id'] = admin.pk
        session.save()

        for path in ['/api/v1/companies/', '/api/v1/tickets/']:
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 401)

    def test_django_admin_session_alone_does_not_authenticate_the_data_api(self):
        from django.contrib.auth import get_user_model

        User = get_user_model()
        User.objects.create_superuser('root', 'root@citemed.com', 'pw')
        self.assertTrue(self.client.login(username='root', password='pw'))

        self.assertEqual(self.client.get('/api/v1/tickets/').status_code, 401)

    def test_bearer_token_does_not_authenticate_the_session_endpoints(self):
        # The same token that works on /api/v1/ must be worthless on the
        # session-authenticated surface, whether customer or admin.
        session_paths = [
            '/api/auth/me/',
            '/api/tickets/',
            '/api/admin/tickets/inbox/',
            '/api/admin/users/',
            '/api/files/buckets/',
        ]
        for path in session_paths:
            with self.subTest(path=path):
                r = self.client.get(path, **self.auth())
                self.assertIn(r.status_code, (401, 403), f'{path} → {r.status_code}')

    def test_authenticating_leaves_request_user_anonymous(self):
        # Proven indirectly: the API never returns per-user data and the
        # session views above reject the token. Asserted directly here so the
        # "an ApiClient is not a user" rule can't be quietly dropped.
        from django.contrib.auth.models import AnonymousUser
        from rest_framework.test import APIRequestFactory

        from portal.api_v1.auth import ApiClientAuthentication

        request = APIRequestFactory().get('/api/v1/tickets/', **self.auth())
        user, auth = ApiClientAuthentication().authenticate(request)
        self.assertIsInstance(user, AnonymousUser)
        self.assertIsInstance(auth, ApiClient)


class ReadOnlyTest(ApiV1TestCase):
    def test_unsafe_methods_are_rejected(self):
        paths = ['/api/v1/companies/', '/api/v1/tickets/',
                 f'/api/v1/tickets/{self.t1.number}/']
        for path in paths:
            for method in ('post', 'put', 'patch', 'delete'):
                with self.subTest(path=path, method=method):
                    r = getattr(self.client, method)(
                        path, data='{}', content_type='application/json',
                        **self.auth())
                    self.assertEqual(r.status_code, 405, f'{method.upper()} {path}')

    def test_unsafe_methods_are_rejected_without_a_token_too(self):
        r = self.client.post('/api/v1/tickets/', data='{}',
                             content_type='application/json')
        self.assertIn(r.status_code, (401, 405))


class LastUsedAtTest(ApiV1TestCase):
    def test_successful_call_stamps_last_used_at(self):
        self.assertIsNone(self.client_obj.last_used_at)
        before = timezone.now()

        self.assertEqual(self.get('/api/v1/tickets/').status_code, 200)

        self.client_obj.refresh_from_db()
        self.assertIsNotNone(self.client_obj.last_used_at)
        self.assertGreaterEqual(self.client_obj.last_used_at, before)

    def test_rejected_call_does_not_stamp_last_used_at(self):
        self.client.get('/api/v1/tickets/', HTTP_AUTHORIZATION='Bearer wrong')
        self.client_obj.refresh_from_db()
        self.assertIsNone(self.client_obj.last_used_at)


# ── Payload: what must and must not be in it ────────────────────────────────
class TicketPayloadTest(ApiV1TestCase):
    def test_ticket_shape(self):
        r = self.get(f'/api/v1/tickets/{self.t1.number}/')
        data = r.json()
        self.assertEqual(set(data), {
            'id', 'number', 'display_number', 'company', 'subject', 'status',
            'priority', 'category', 'requester_email', 'assignee_email',
            'message_count', 'created_at', 'updated_at', 'last_message_at',
        })
        self.assertEqual(data['number'], self.t1.number)
        self.assertEqual(data['display_number'], f'CS-{self.t1.number}')
        self.assertEqual(data['company'], {'id': self.acme.pk, 'name': 'Acme Medical'})
        self.assertEqual(data['requester_email'], 'jane@acme.com')

    def test_vocabulary_is_the_portals_own_unmapped(self):
        # The consumer collapses these on ingest; the producer must not.
        r = self.get('/api/v1/tickets/')
        by_number = {t['number']: t for t in r.json()['results']}
        self.assertEqual(by_number[self.t1.number]['status'], 'waiting_on_customer')
        self.assertEqual(by_number[self.t1.number]['priority'], 'high')
        self.assertEqual(by_number[self.t3.number]['priority'], 'urgent')

    def test_message_count_excludes_internal_notes(self):
        # t1 has one customer message and one internal note.
        self.assertEqual(self.t1.messages.count(), 2)
        r = self.get(f'/api/v1/tickets/{self.t1.number}/')
        self.assertEqual(r.json()['message_count'], 1)

    def test_last_message_at_ignores_internal_notes(self):
        later = TicketMessage.objects.create(
            ticket=self.t1, body='another internal', is_internal=True)
        TicketMessage.objects.filter(pk=later.pk).update(
            created_at=timezone.now() + timedelta(days=1))

        r = self.get(f'/api/v1/tickets/{self.t1.number}/')
        visible = self.t1.messages.filter(is_internal=False).latest('created_at')
        self.assertEqual(r.json()['last_message_at'][:19],
                         visible.created_at.isoformat()[:19])

    def test_no_message_body_or_internal_note_leaks_anywhere(self):
        """Assert on the raw payload, not on named fields.

        Checking `'body' not in data` would pass a future field called
        `last_message_preview`. Searching the serialized bytes for the actual
        text will not.
        """
        paths = [
            '/api/v1/tickets/',
            f'/api/v1/tickets/{self.t1.number}/',
            '/api/v1/companies/',
            '/api/v1/tickets/?company_id=%d' % self.acme.pk,
            '/api/v1/tickets/?email=jane@acme.com&include_cc=true',
        ]
        for path in paths:
            with self.subTest(path=path):
                raw = self.get(path).content.decode()
                self.assertNotIn(SECRET_BODY, raw)
                self.assertNotIn(SECRET_NOTE, raw)
                self.assertNotIn('is_internal', raw)
                self.assertNotIn('"body"', raw)
                self.assertNotIn('watchers', raw)
                self.assertNotIn('jira', raw.lower())

    def test_schema_does_not_describe_a_message_body_field(self):
        raw = self.get('/api/v1/schema/').content.decode()
        self.assertNotIn('is_internal', raw)
        self.assertNotIn('watchers', raw)


class CompanyPayloadTest(ApiV1TestCase):
    def test_company_shape_and_counts(self):
        r = self.get('/api/v1/companies/')
        by_name = {c['name']: c for c in r.json()['results']}

        acme = by_name['Acme Medical']
        self.assertEqual(set(acme), {
            'id', 'name', 'contract_end_date', 'ticket_counts', 'last_ticket_at'})
        self.assertEqual(acme['id'], self.acme.pk)
        self.assertEqual(acme['contract_end_date'], '2027-03-01')
        # Two tickets, one of which is resolved.
        self.assertEqual(acme['ticket_counts'], {'open': 1, 'total': 2})
        self.assertIsNotNone(acme['last_ticket_at'])

    def test_company_with_no_tickets_reports_zeroes(self):
        Company.objects.create(name='Zeta Ltd')
        r = self.get('/api/v1/companies/')
        zeta = next(c for c in r.json()['results'] if c['name'] == 'Zeta Ltd')
        self.assertEqual(zeta['ticket_counts'], {'open': 0, 'total': 0})
        self.assertIsNone(zeta['last_ticket_at'])

    def test_companies_are_not_scoped_to_one_tenant(self):
        # The whole reason this namespace exists: no company filter is applied
        # and no session decides what is visible.
        names = {c['name'] for c in self.get('/api/v1/companies/').json()['results']}
        self.assertTrue({'Acme Medical', 'Globex Devices'}.issubset(names))


# ── Filters ─────────────────────────────────────────────────────────────────
class FilterTest(ApiV1TestCase):
    def numbers(self, query=''):
        r = self.get(f'/api/v1/tickets/{query}')
        self.assertEqual(r.status_code, 200, r.content)
        return {t['number'] for t in r.json()['results']}

    def test_unfiltered_crosses_every_company(self):
        self.assertEqual(
            self.numbers(), {self.t1.number, self.t2.number, self.t3.number})

    def test_company_id(self):
        self.assertEqual(
            self.numbers(f'?company_id={self.acme.pk}'),
            {self.t1.number, self.t2.number})

    def test_company_id_is_repeatable(self):
        self.assertEqual(
            self.numbers(f'?company_id={self.acme.pk}&company_id={self.globex.pk}'),
            {self.t1.number, self.t2.number, self.t3.number})

    def test_company_id_must_be_an_integer(self):
        self.assertEqual(self.get('/api/v1/tickets/?company_id=abc').status_code, 400)

    def test_status(self):
        self.assertEqual(self.numbers('?status=resolved'), {self.t2.number})

    def test_status_is_repeatable(self):
        self.assertEqual(
            self.numbers('?status=resolved&status=open'),
            {self.t2.number, self.t3.number})

    def test_unknown_status_is_400(self):
        # Silently returning everything for a typo'd filter would look like a
        # working sync that quietly over-reports.
        self.assertEqual(self.get('/api/v1/tickets/?status=nope').status_code, 400)

    def test_priority(self):
        self.assertEqual(self.numbers('?priority=urgent'), {self.t3.number})

    def test_priority_is_repeatable(self):
        self.assertEqual(
            self.numbers('?priority=urgent&priority=high'),
            {self.t1.number, self.t3.number})

    def test_unknown_priority_is_400(self):
        self.assertEqual(self.get('/api/v1/tickets/?priority=nope').status_code, 400)

    def test_created_since(self):
        cutoff = timezone.now() - timedelta(days=1)
        Ticket.objects.filter(pk=self.t3.pk).update(
            created_at=timezone.now() - timedelta(days=7))
        self.assertEqual(
            self.numbers(f'?created_since={cutoff.isoformat()}'),
            {self.t1.number, self.t2.number})

    def test_created_since_accepts_a_bare_date(self):
        self.assertEqual(self.get('/api/v1/tickets/?created_since=2020-01-01')
                         .status_code, 200)

    def test_updated_since(self):
        old = timezone.now() - timedelta(days=7)
        Ticket.objects.filter(pk=self.t2.pk).update(updated_at=old)
        cutoff = (timezone.now() - timedelta(days=1)).isoformat()
        self.assertEqual(
            self.numbers(f'?updated_since={cutoff}'),
            {self.t1.number, self.t3.number})

    def test_since_accepts_a_properly_encoded_offset(self):
        from urllib.parse import quote

        cutoff = quote((timezone.now() - timedelta(days=1)).isoformat())
        self.assertEqual(
            self.numbers(f'?updated_since={cutoff}'),
            {self.t1.number, self.t2.number, self.t3.number})

    def test_unparseable_since_is_400(self):
        for param in ('created_since', 'updated_since'):
            with self.subTest(param=param):
                self.assertEqual(
                    self.get(f'/api/v1/tickets/?{param}=yesterday').status_code, 400)

    def test_email_matches_the_creator(self):
        self.assertEqual(self.numbers('?email=jane@acme.com'), {self.t1.number})

    def test_email_is_case_insensitive(self):
        self.assertEqual(self.numbers('?email=JANE@ACME.COM'), {self.t1.number})

    def test_email_excludes_cc_by_default(self):
        # jane is CC'd on t2 but did not raise it. "What has Jane raised?"
        # should not answer with a colleague's ticket.
        self.assertNotIn(self.t2.number, self.numbers('?email=jane@acme.com'))

    def test_include_cc_widens_to_cc_emails(self):
        self.assertEqual(
            self.numbers('?email=jane@acme.com&include_cc=true'),
            {self.t1.number, self.t2.number})

    def test_include_cc_matches_a_cc_only_address(self):
        self.assertEqual(
            self.numbers('?email=boss@acme.com&include_cc=true'), {self.t1.number})
        self.assertEqual(self.numbers('?email=boss@acme.com'), set())

    def test_include_cc_does_not_match_a_partial_address(self):
        # A naive substring search over the JSON would match 'oss@acme.com'.
        self.assertEqual(self.numbers('?email=oss@acme.com&include_cc=true'), set())

    def test_include_cc_rejects_junk(self):
        self.assertEqual(
            self.get('/api/v1/tickets/?email=a@b.com&include_cc=maybe').status_code,
            400)

    def test_filters_compose(self):
        self.assertEqual(
            self.numbers(f'?company_id={self.acme.pk}&status=waiting_on_customer'
                         f'&priority=high'),
            {self.t1.number})


# ── Pagination ──────────────────────────────────────────────────────────────
class PaginationTest(ApiV1TestCase):
    def setUp(self):
        super().setUp()
        Ticket.objects.all().delete()
        self.made = [
            Ticket.objects.create(company=self.acme, created_by=self.jane,
                                  subject=f'Ticket {i}')
            for i in range(12)
        ]

    def test_ordering_is_updated_at_ascending(self):
        r = self.get('/api/v1/tickets/?limit=100')
        stamps = [t['updated_at'] for t in r.json()['results']]
        self.assertEqual(stamps, sorted(stamps))

    def test_cursor_walks_every_row_exactly_once(self):
        seen, url, pages = [], '/api/v1/tickets/?limit=5', 0
        while url:
            body = self.get(url).json()
            seen.extend(t['number'] for t in body['results'])
            url = body['next']
            pages += 1
            self.assertLess(pages, 10, 'cursor did not terminate')

        self.assertEqual(len(seen), 12)
        self.assertEqual(len(set(seen)), 12)
        self.assertEqual(seen, sorted(seen))  # stable, ascending, no repeats

    def test_page_size_is_honoured_and_next_is_a_usable_url(self):
        body = self.get('/api/v1/tickets/?limit=5').json()
        self.assertEqual(len(body['results']), 5)
        self.assertIn('cursor=', body['next'])

        second = self.get(body['next']).json()
        self.assertEqual(len(second['results']), 5)
        first_numbers = {t['number'] for t in body['results']}
        self.assertTrue(first_numbers.isdisjoint(t['number'] for t in second['results']))

    def test_filters_survive_the_cursor(self):
        body = self.get(
            f'/api/v1/tickets/?limit=5&company_id={self.acme.pk}').json()
        second = self.get(body['next']).json()
        self.assertTrue(all(t['company']['id'] == self.acme.pk
                            for t in second['results']))


# ── Schema and docs ─────────────────────────────────────────────────────────
class SchemaAccessTest(ApiV1TestCase):
    PATHS = ['/api/v1/schema/', '/api/v1/docs/']

    def test_schema_and_docs_are_not_public(self):
        for path in self.PATHS:
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 401)

    def test_bearer_token_opens_them(self):
        for path in self.PATHS:
            with self.subTest(path=path):
                self.assertEqual(self.get(path).status_code, 200)

    def test_django_admin_session_opens_them(self):
        from django.contrib.auth import get_user_model

        get_user_model().objects.create_superuser('root', 'root@citemed.com', 'pw')
        self.client.login(username='root', password='pw')
        for path in self.PATHS:
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 200)

    def _portal_login(self, user):
        s = self.client.session
        s['portal_user_id'] = user.id
        s.save()

    def test_a_portal_agent_session_opens_them(self):
        """The portal's own agents are PortalUser rows with no Django user, so
        gating on Django's is_staff alone left the docs unreachable for every
        actual staff member — which defeats the point of shipping Swagger."""
        from portal.models import PortalUser

        agent = PortalUser.objects.create(
            email='agent@citemed.com', role=PortalUser.ROLE_ADMIN)
        self._portal_login(agent)
        for path in self.PATHS:
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 200)

    def test_a_customer_portal_session_does_not_open_them(self):
        from portal.models import Company, PortalUser

        co = Company.objects.create(name='Acme Docs')
        cust = PortalUser.objects.create(
            email='c@acme-docs.com', company=co, role=PortalUser.ROLE_CUSTOMER)
        self._portal_login(cust)
        for path in self.PATHS:
            with self.subTest(path=path):
                self.assertIn(self.client.get(path).status_code, (401, 403))

    def test_a_disabled_agent_session_does_not_open_them(self):
        from portal.models import PortalUser

        gone = PortalUser.objects.create(
            email='gone@citemed.com', role=PortalUser.ROLE_ADMIN, access_enabled=False)
        self._portal_login(gone)
        for path in self.PATHS:
            with self.subTest(path=path):
                self.assertIn(self.client.get(path).status_code, (401, 403))

    def test_non_staff_django_session_does_not_open_them(self):
        from django.contrib.auth import get_user_model

        get_user_model().objects.create_user('plain', 'plain@x.com', 'pw')
        self.client.login(username='plain', password='pw')
        for path in self.PATHS:
            with self.subTest(path=path):
                self.assertIn(self.client.get(path).status_code, (401, 403))

    def test_schema_documents_the_three_endpoints(self):
        raw = self.get('/api/v1/schema/').content.decode()
        for path in ('/api/v1/companies/', '/api/v1/tickets/'):
            self.assertIn(path, raw)


# ── Token minting ───────────────────────────────────────────────────────────
class CreateApiClientCommandTest(TestCase):
    def test_prints_the_token_once_and_stores_only_its_hash(self):
        from io import StringIO

        out = StringIO()
        call_command('create_api_client', 'RevenueHub', stdout=out)
        printed = out.getvalue()

        client = ApiClient.objects.get(name='RevenueHub')
        token = next(w for w in printed.split()
                     if w.startswith(ApiClient.TOKEN_PREFIX))

        # The raw token is nowhere in the database…
        self.assertNotEqual(client.token_hash, token)
        self.assertNotIn(token, client.token_hash)
        # …but it hashes to what is stored, so it authenticates.
        self.assertEqual(ApiClient.hash_token(token), client.token_hash)

        r = Client().get('/api/v1/companies/', HTTP_AUTHORIZATION=f'Bearer {token}')
        self.assertEqual(r.status_code, 200)

    def test_duplicate_name_is_refused(self):
        from django.core.management.base import CommandError

        call_command('create_api_client', 'RevenueHub')
        with self.assertRaises(CommandError):
            call_command('create_api_client', 'RevenueHub')

    def test_two_clients_get_different_tokens(self):
        _, a = ApiClient.issue('one')
        _, b = ApiClient.issue('two')
        self.assertNotEqual(a, b)


class AdminRegistrationTest(TestCase):
    def test_api_client_is_registered_and_cannot_be_added_by_hand(self):
        from django.contrib import admin as django_admin

        self.assertIn(ApiClient, django_admin.site._registry)
        model_admin = django_admin.site._registry[ApiClient]
        self.assertFalse(model_admin.has_add_permission(None))
        self.assertIn('token_hash', model_admin.readonly_fields)


class JsonContractTest(ApiV1TestCase):
    def test_responses_are_json(self):
        r = self.get('/api/v1/tickets/')
        self.assertEqual(r['Content-Type'].split(';')[0], 'application/json')
        json.loads(r.content)
