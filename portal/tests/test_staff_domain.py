import json

from django.test import TestCase, override_settings

from portal.models import PortalUser


@override_settings(STAFF_EMAIL_DOMAINS=['citemed.com'])
class StaffDomainAutoProvisionTest(TestCase):
    """A first sign-in from one of our own domains should become an agent.

    The interesting cases aren't the happy path — they're the ones where this
    must NOT fire, since it widens the TG-672 access allowlist.
    """

    url = '/api/auth/request-magic-link/'

    def _request(self, email):
        return self.client.post(
            self.url, data=json.dumps({'email': email}),
            content_type='application/json',
        )

    def test_new_staff_email_is_provisioned_as_agent(self):
        res = self._request('newcolleague@citemed.com')
        self.assertEqual(res.status_code, 200)
        user = PortalUser.objects.get(email='newcolleague@citemed.com')
        self.assertEqual(user.role, PortalUser.ROLE_ADMIN)
        self.assertTrue(user.access_enabled)

    def test_unknown_outside_email_is_still_refused(self):
        res = self._request('stranger@example.com')
        self.assertEqual(res.status_code, 403)
        self.assertFalse(PortalUser.objects.filter(email='stranger@example.com').exists())

    def test_lookalike_domain_is_refused(self):
        """`citemed.com.evil.io` must not pass — the check is exact, not a suffix."""
        res = self._request('attacker@citemed.com.evil.io')
        self.assertEqual(res.status_code, 403)
        self.assertFalse(
            PortalUser.objects.filter(email='attacker@citemed.com.evil.io').exists())

    def test_existing_customer_on_staff_domain_is_not_upgraded(self):
        """A deliberate demotion must survive the user signing in again."""
        PortalUser.objects.create(
            email='contractor@citemed.com', role=PortalUser.ROLE_CUSTOMER)
        self._request('contractor@citemed.com')
        user = PortalUser.objects.get(email='contractor@citemed.com')
        self.assertEqual(user.role, PortalUser.ROLE_CUSTOMER)

    def test_disabled_staff_account_is_not_resurrected(self):
        """Offboarding sticks: a disabled account can't re-enable itself."""
        PortalUser.objects.create(
            email='offboarded@citemed.com', role=PortalUser.ROLE_ADMIN,
            access_enabled=False)
        res = self._request('offboarded@citemed.com')
        self.assertEqual(res.status_code, 403)
        user = PortalUser.objects.get(email='offboarded@citemed.com')
        self.assertFalse(user.access_enabled)

    @override_settings(STAFF_EMAIL_DOMAINS=[])
    def test_empty_setting_disables_the_whole_path(self):
        res = self._request('newcolleague@citemed.com')
        self.assertEqual(res.status_code, 403)
        self.assertFalse(
            PortalUser.objects.filter(email='newcolleague@citemed.com').exists())
