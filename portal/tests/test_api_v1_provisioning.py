"""The write surface at /api/v1/provisioning/.

This file matters for the same reason test_api_v1.py does, only more so: until
provisioning shipped, /api/v1/ could not change anything. These endpoints create
customer LOGINS, so the tests below are less about the happy path than about the
four things that must never happen —

  * a read-only token being able to write (the capability is separate, and off
    by default, so every token issued before this existed stays read-only);
  * a repeat run creating duplicates, or failing (the caller's sync is
    at-least-once by design);
  * creating a user emailing them (provisioning runs before kickoff);
  * an email address being moved between companies without a human deciding.
"""
from django.core import mail
from django.test import Client, TestCase

from portal.models import ApiClient, Company, PortalUser

COMPANIES = '/api/v1/provisioning/companies/'


def _users(company_id):
    return f'/api/v1/provisioning/companies/{company_id}/users/'


class ProvisioningApiTestCase(TestCase):
    def setUp(self):
        self.client = Client()
        self.writer, self.write_token = ApiClient.issue('RevenueHub provisioning')
        self.writer.can_provision = True
        self.writer.save(update_fields=['can_provision'])
        self.reader, self.read_token = ApiClient.issue('RevenueHub read')

    def post(self, path, payload, token=None):
        return self.client.post(
            path, data=payload, content_type='application/json',
            HTTP_AUTHORIZATION=f'Bearer {token or self.write_token}')

    def get(self, path, token=None):
        return self.client.get(
            path, HTTP_AUTHORIZATION=f'Bearer {token or self.write_token}')


class WriteCapabilityTests(ProvisioningApiTestCase):
    """Reading and creating logins are different grants."""

    def test_a_read_token_cannot_provision(self):
        r = self.post(COMPANIES, {'name': 'Acme'}, token=self.read_token)
        self.assertEqual(r.status_code, 403)
        self.assertFalse(Company.objects.filter(name='Acme').exists())

    def test_tokens_are_read_only_unless_asked_for(self):
        """The default is what protects every token issued before this shipped."""
        client, _ = ApiClient.issue('Some other consumer')
        self.assertFalse(client.can_provision)

    def test_no_token_is_rejected(self):
        r = self.client.post(COMPANIES, data={'name': 'Acme'},
                             content_type='application/json')
        self.assertEqual(r.status_code, 401)

    def test_a_revoked_token_cannot_provision(self):
        """401, not 403: auth.py rejects a disabled client in the authenticator
        with the same answer it gives an unknown token, so a revoked credential
        cannot confirm it was ever a real one."""
        self.writer.enabled = False
        self.writer.save(update_fields=['enabled'])
        r = self.post(COMPANIES, {'name': 'Acme'})
        self.assertEqual(r.status_code, 401)
        self.assertFalse(Company.objects.filter(name='Acme').exists())

    def test_a_session_is_not_a_door_into_this_namespace(self):
        co = Company.objects.create(name='Acme')
        user = PortalUser.objects.create(email='a@acme.com', company=co,
                                         role=PortalUser.ROLE_ADMIN)
        s = self.client.session
        s['portal_user_id'] = user.id
        s.save()
        r = self.client.post(COMPANIES, data={'name': 'Other'},
                             content_type='application/json')
        self.assertEqual(r.status_code, 401)

    def test_the_read_endpoints_are_still_read_only(self):
        """Adding a write surface must not have loosened the old one."""
        r = self.post('/api/v1/companies/', {'name': 'Acme'})
        self.assertEqual(r.status_code, 405)


class CompanyProvisioningTests(ProvisioningApiTestCase):
    def test_creating_a_company(self):
        r = self.post(COMPANIES, {'name': 'STAAR Surgical',
                                  'contract_end_date': '2027-03-31'})
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.json()['name'], 'STAAR Surgical')
        co = Company.objects.get(name='STAAR Surgical')
        self.assertEqual(str(co.contract_end_date), '2027-03-31')

    def test_posting_the_same_company_again_returns_it_rather_than_failing(self):
        """The caller's sync is at-least-once; a 409 here would make it unsafe
        to re-run, which is the same as not being able to run it twice."""
        first = self.post(COMPANIES, {'name': 'STAAR Surgical'})
        second = self.post(COMPANIES, {'name': 'STAAR Surgical'})
        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(first.json()['id'], second.json()['id'])
        self.assertEqual(Company.objects.filter(name='STAAR Surgical').count(), 1)

    def test_a_later_contract_date_updates_the_existing_row(self):
        self.post(COMPANIES, {'name': 'Acme', 'contract_end_date': '2027-01-01'})
        self.post(COMPANIES, {'name': 'Acme', 'contract_end_date': '2028-01-01'})
        self.assertEqual(str(Company.objects.get(name='Acme').contract_end_date),
                         '2028-01-01')

    def test_omitting_the_contract_date_says_nothing_rather_than_clearing_it(self):
        self.post(COMPANIES, {'name': 'Acme', 'contract_end_date': '2027-01-01'})
        self.post(COMPANIES, {'name': 'Acme'})
        self.assertEqual(str(Company.objects.get(name='Acme').contract_end_date),
                         '2027-01-01')

    def test_a_nameless_company_is_a_400(self):
        self.assertEqual(self.post(COMPANIES, {}).status_code, 400)


class UserProvisioningTests(ProvisioningApiTestCase):
    def setUp(self):
        super().setUp()
        self.co = Company.objects.create(name='STAAR Surgical')

    def test_creating_a_user(self):
        r = self.post(_users(self.co.pk), {
            'email': 'jo@staar.com', 'name': 'Jo Chen', 'role': 'admin'})
        self.assertEqual(r.status_code, 201)
        user = PortalUser.objects.get(email='jo@staar.com')
        self.assertEqual(user.company_id, self.co.pk)
        self.assertEqual(user.role, 'admin')
        self.assertTrue(user.access_enabled)

    def test_creating_a_user_sends_nothing(self):
        """Provisioning happens before kickoff. Eight users must not mean eight
        emails at a customer who has not been introduced to the portal yet."""
        for i in range(8):
            self.post(_users(self.co.pk), {'email': f'p{i}@staar.com'})
        self.assertEqual(len(mail.outbox), 0)

    def test_re_posting_a_user_updates_rather_than_duplicating(self):
        self.post(_users(self.co.pk), {'email': 'jo@staar.com', 'name': 'Jo'})
        r = self.post(_users(self.co.pk), {
            'email': 'jo@staar.com', 'name': 'Jo Chen', 'role': 'admin'})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(PortalUser.objects.filter(email='jo@staar.com').count(), 1)
        user = PortalUser.objects.get(email='jo@staar.com')
        self.assertEqual(user.name, 'Jo Chen')
        self.assertEqual(user.role, 'admin')

    def test_email_case_cannot_smuggle_a_duplicate_past_the_unique_index(self):
        self.post(_users(self.co.pk), {'email': 'jo@staar.com'})
        r = self.post(_users(self.co.pk), {'email': 'JO@STAAR.COM'})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.co.users.count(), 1)

    def test_an_address_registered_to_another_company_is_a_conflict(self):
        """Whichever company the row ends up on is whose tickets that person can
        read. Reassigning silently would move somebody's access on a typo."""
        other = Company.objects.create(name='Someone Else')
        PortalUser.objects.create(email='jo@staar.com', company=other)
        r = self.post(_users(self.co.pk), {'email': 'jo@staar.com'})
        self.assertEqual(r.status_code, 409)
        self.assertEqual(PortalUser.objects.get(email='jo@staar.com').company_id,
                         other.pk)

    def test_an_unattached_user_can_be_adopted(self):
        PortalUser.objects.create(email='jo@staar.com', company=None)
        r = self.post(_users(self.co.pk), {'email': 'jo@staar.com'})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(PortalUser.objects.get(email='jo@staar.com').company_id,
                         self.co.pk)

    def test_re_enabling_someone_who_came_back(self):
        PortalUser.objects.create(email='jo@staar.com', company=self.co,
                                  access_enabled=False)
        self.post(_users(self.co.pk), {'email': 'jo@staar.com',
                                       'access_enabled': True})
        self.assertTrue(PortalUser.objects.get(email='jo@staar.com').access_enabled)

    def test_is_demo_is_not_settable_from_the_api(self):
        """A demo account may sign in WITHOUT a magic link. It must never be
        reachable from a remote caller."""
        self.post(_users(self.co.pk), {'email': 'jo@staar.com', 'is_demo': True})
        self.assertFalse(PortalUser.objects.get(email='jo@staar.com').is_demo)

    def test_an_unknown_role_is_a_400(self):
        r = self.post(_users(self.co.pk), {'email': 'jo@staar.com',
                                           'role': 'superuser'})
        self.assertEqual(r.status_code, 400)
        self.assertFalse(self.co.users.exists())

    def test_the_default_role_is_customer(self):
        self.post(_users(self.co.pk), {'email': 'jo@staar.com'})
        self.assertEqual(PortalUser.objects.get(email='jo@staar.com').role,
                         PortalUser.ROLE_CUSTOMER)

    def test_an_unknown_company_is_a_404(self):
        self.assertEqual(
            self.post(_users(9999), {'email': 'jo@staar.com'}).status_code, 404)

    def test_listing_users_so_a_caller_can_reconcile(self):
        self.post(_users(self.co.pk), {'email': 'b@staar.com'})
        self.post(_users(self.co.pk), {'email': 'a@staar.com'})
        PortalUser.objects.create(email='nope@other.com',
                                  company=Company.objects.create(name='Other'))
        r = self.get(_users(self.co.pk))
        self.assertEqual(r.status_code, 200)
        self.assertEqual([u['email'] for u in r.json()],
                         ['a@staar.com', 'b@staar.com'])

    def test_listing_needs_the_capability_too(self):
        self.assertEqual(self.get(_users(self.co.pk),
                                  token=self.read_token).status_code, 403)
