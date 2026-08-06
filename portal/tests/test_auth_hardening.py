"""Auth hardening (GitHub #7, #2).

Session fixation: an attacker who can plant a session id in a victim's browser
(shared machine, a stray Set-Cookie, an XSS elsewhere on the origin) keeps that
id valid across the victim's login unless the id is rotated. Every path that
elevates an anonymous session to an authenticated one must rotate it — here
via `session.flush()` in `_start_authenticated_session`, which rotates the id
AND drops the old session server-side (see that helper for why it's preferred
over `cycle_key()`).
"""
import json
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
        r = self.client.post('/api/auth/verify/',
                             data=json.dumps({'token': token.token}),
                             content_type='application/json')
        self.assertEqual(r.status_code, 200)
        self.assertNotEqual(self.client.session.session_key, old)

    def test_magic_link_login_drops_pre_login_session_data(self):
        # Rotation is only half of it — anything the attacker planted in the
        # old session must not survive into the authenticated one.
        self._anonymous_session_key()
        token = self._token('t0ken2')
        self.client.post('/api/auth/verify/',
                         data=json.dumps({'token': token.token}),
                         content_type='application/json')
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


class MagicLinkVerifyMethodTest(TestCase):
    """GitHub #7. Verification was GET with the token in the query string, so
    the single-use credential landed in gunicorn/nginx access logs. Moving the
    exchange to POST keeps it in the body, out of the log line."""

    def setUp(self):
        self.co = Company.objects.create(name='Acme')
        self.user = PortalUser.objects.create(
            email='c@acme.com', company=self.co, role=PortalUser.ROLE_CUSTOMER)

    def _token(self, value='tok'):
        return MagicLinkToken.objects.create(
            user=self.user, token=value,
            expires_at=timezone.now() + timedelta(minutes=15))

    def test_get_is_rejected(self):
        t = self._token()
        r = self.client.get('/api/auth/verify/', {'token': t.token})
        self.assertEqual(r.status_code, 405)

    def test_post_with_token_in_body_logs_the_user_in(self):
        t = self._token()
        r = self.client.post('/api/auth/verify/',
                             data=json.dumps({'token': t.token}),
                             content_type='application/json')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()['user']['email'], self.user.email)
        self.assertEqual(self.client.session.get('portal_user_id'), self.user.pk)

    def test_post_without_token_is_a_400(self):
        r = self.client.post('/api/auth/verify/', data='{}',
                             content_type='application/json')
        self.assertEqual(r.status_code, 400)

    def test_token_is_single_use(self):
        t = self._token()
        body = json.dumps({'token': t.token})
        self.client.post('/api/auth/verify/', data=body,
                         content_type='application/json')
        again = self.client.post('/api/auth/verify/', data=body,
                                 content_type='application/json')
        self.assertEqual(again.status_code, 401)


class EveryUnsafeEndpointRequiresCsrfTest(TestCase):
    """Sampling three endpoints proves little — @csrf_exempt could be added
    back to any view, or a new unsafe endpoint could ship without one.

    This walks the URLconf, finds every portal view that accepts an unsafe
    method, and asserts each rejects a tokenless request. CsrfViewMiddleware
    runs before the view, so a 403 lands regardless of whether the object id
    exists or the user is authorised — which is exactly what we want to assert.
    """

    def setUp(self):
        self.client = Client(enforce_csrf_checks=True)
        co = Company.objects.create(name='Acme')
        user = PortalUser.objects.create(
            email='c@acme.com', company=co, role=PortalUser.ROLE_CUSTOMER)
        s = self.client.session
        s['portal_user_id'] = user.id
        s.save()

    def _unsafe_endpoints(self):
        import inspect
        import re as _re
        from portal import urls as purls
        for p in purls.urlpatterns:
            cb = p.callback
            if not getattr(cb, '__module__', '').startswith('portal.views'):
                continue
            try:
                src = inspect.getsource(cb)
            except OSError:  # pragma: no cover
                continue
            methods = [m for m in ('POST', 'PATCH', 'DELETE', 'PUT')
                       if f"'{m}'" in src]
            if not methods:
                continue
            path = '/api/' + _re.sub(r'<[^:]+:[^>]+>', '1', str(p.pattern))
            yield path, methods, cb.__name__

    def test_every_unsafe_endpoint_rejects_a_tokenless_request(self):
        checked, failures = 0, []
        for path, methods, name in self._unsafe_endpoints():
            for method in methods:
                r = getattr(self.client, method.lower())(
                    path, data='{}', content_type='application/json')
                checked += 1
                if r.status_code != 403:
                    failures.append(f'{method} {path} ({name}) → {r.status_code}')
        self.assertEqual(failures, [], f'endpoints not CSRF-protected: {failures}')
        # Guard the guard: if the discovery ever stops finding endpoints this
        # test would vacuously pass.
        self.assertGreaterEqual(checked, 24)
