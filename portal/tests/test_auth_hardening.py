"""Auth hardening (GitHub #7, #2).

Session fixation: an attacker who can plant a session id in a victim's browser
(shared machine, a stray Set-Cookie, an XSS elsewhere on the origin) keeps that
id valid across the victim's login unless the id is rotated. Every path that
elevates an anonymous session to an authenticated one must call
`session.cycle_key()`.
"""
from datetime import timedelta

from django.test import Client, TestCase
from django.utils import timezone

from portal.models import Company, MagicLinkToken, PortalUser, Ticket


class SessionFixationTest(TestCase):
    def setUp(self):
        self.co = Company.objects.create(name='Acme')
        self.user = PortalUser.objects.create(
            email='c@acme.com', company=self.co, role=PortalUser.ROLE_CUSTOMER)

    def _token(self, value):
        return MagicLinkToken.objects.create(
            user=self.user, token=value,
            expires_at=timezone.now() + timedelta(minutes=15))

    def _anonymous_session_key(self):
        """Establish a pre-login session, as a real browser would have."""
        s = self.client.session
        s['planted'] = 'attacker-value'
        s.save()
        self.client.cookies['sessionid'] = s.session_key
        return s.session_key

    def test_magic_link_login_rotates_the_session_id(self):
        old = self._anonymous_session_key()
        token = self._token('t0ken')
        r = self.client.get('/api/auth/verify/', {'token': token.token})
        self.assertEqual(r.status_code, 200)
        self.assertNotEqual(self.client.session.session_key, old)

    def test_magic_link_login_drops_pre_login_session_data(self):
        # Rotation is only half of it — anything the attacker planted in the
        # old session must not survive into the authenticated one.
        self._anonymous_session_key()
        token = self._token('t0ken2')
        self.client.get('/api/auth/verify/', {'token': token.token})
        self.assertIsNone(self.client.session.get('planted'))
        self.assertEqual(self.client.session.get('portal_user_id'), self.user.pk)

    def test_demo_login_rotates_the_session_id(self):
        demo = PortalUser.objects.create(
            email='demo@acme.com', company=self.co,
            role=PortalUser.ROLE_CUSTOMER, is_demo=True)
        old = self._anonymous_session_key()
        r = self.client.get('/api/auth/demo-login/', {'email': demo.email})
        self.assertIn(r.status_code, (200, 302))
        self.assertNotEqual(self.client.session.session_key, old)

    def test_demo_shortcut_in_request_magic_link_rotates_too(self):
        """request_magic_link signs in is_demo accounts directly — a third
        login path, and it must rotate like the other two."""
        demo = PortalUser.objects.create(
            email='demo2@acme.com', company=self.co,
            role=PortalUser.ROLE_CUSTOMER, is_demo=True)
        old = self._anonymous_session_key()
        r = self.client.post('/api/auth/request-magic-link/',
                             data='{"email": "demo2@acme.com"}',
                             content_type='application/json')
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json().get('demo'))
        self.assertNotEqual(self.client.session.session_key, old)
        self.assertEqual(self.client.session.get('portal_user_id'), demo.pk)


class CsrfEnforcementTest(TestCase):
    """GitHub #2. Every session-authenticated, state-changing endpoint must
    reject a request that carries no CSRF token. `@csrf_exempt` had spread to
    ~27 endpoints — ticket creation, replies, status changes, file operations
    and logout — all reachable cross-site with the victim's session cookie."""

    def setUp(self):
        # enforce_csrf_checks makes the test client behave like a real browser
        # request: no token, no pass.
        self.client = Client(enforce_csrf_checks=True)
        self.co = Company.objects.create(name='Acme')
        self.cust = PortalUser.objects.create(
            email='c@acme.com', company=self.co, role=PortalUser.ROLE_CUSTOMER)
        self.staff = PortalUser.objects.create(
            email='s@citemed.com', role=PortalUser.ROLE_ADMIN)

    def _login(self, user):
        s = self.client.session
        s['portal_user_id'] = user.id
        s.save()

    def test_logout_rejects_request_without_csrf_token(self):
        self._login(self.cust)
        r = self.client.post('/api/auth/logout/')
        self.assertEqual(r.status_code, 403)

    def test_ticket_create_rejects_request_without_csrf_token(self):
        self._login(self.cust)
        r = self.client.post('/api/tickets/', data='{"subject":"x","body":"y"}',
                             content_type='application/json')
        self.assertEqual(r.status_code, 403)

    def test_admin_status_change_rejects_request_without_csrf_token(self):
        self._login(self.staff)
        t = Ticket.objects.create(company=self.co, subject='x')
        r = self.client.post(f'/api/admin/tickets/{t.number}/status/',
                             data='{"status":"resolved"}',
                             content_type='application/json')
        self.assertEqual(r.status_code, 403)

    def test_me_plants_the_csrf_cookie_for_the_spa(self):
        # The SPA calls /auth/me/ on boot; that response is what gives the
        # browser a token to send back. Must work even when unauthenticated,
        # since the login POST needs it too.
        r = self.client.get('/api/auth/me/')
        self.assertEqual(r.status_code, 401)
        self.assertIn('csrftoken', r.cookies)
