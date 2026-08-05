"""Auth hardening (GitHub #7, #2).

Session fixation: an attacker who can plant a session id in a victim's browser
(shared machine, a stray Set-Cookie, an XSS elsewhere on the origin) keeps that
id valid across the victim's login unless the id is rotated. Every path that
elevates an anonymous session to an authenticated one must call
`session.cycle_key()`.
"""
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from portal.models import Company, MagicLinkToken, PortalUser


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
