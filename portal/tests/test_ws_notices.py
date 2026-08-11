"""Notices must appear without a refresh (#49).

Someone reading a docs page during an incident has no reason to reload, so a
notice that only shows on next navigation is a notice they may never see.

Reuses the real-session + cookie-header connection pattern from
test_ws_consumers.py — direct scope['session'] injection doesn't survive
SessionMiddlewareStack — and keeps connect/receive/disconnect for one
communicator inside a single async_to_sync coroutine.
"""
from asgiref.sync import async_to_sync
from channels.db import database_sync_to_async
from channels.testing import WebsocketCommunicator
from django.conf import settings
from django.contrib.sessions.backends.db import SessionStore
from django.test import TransactionTestCase, override_settings

from citemed.asgi import application
from portal.models import Company, PortalUser, SiteNotice


def _connect(path, portal_user_id=None):
    session = SessionStore()
    if portal_user_id:
        session['portal_user_id'] = portal_user_id
    session.save()
    cookie_header = f'{settings.SESSION_COOKIE_NAME}={session.session_key}'.encode()
    headers = [(b'cookie', cookie_header), (b'origin', b'http://localhost')]
    return WebsocketCommunicator(application, path, headers=headers)


@override_settings(CHANNEL_LAYERS={'default': {'BACKEND': 'channels.layers.InMemoryChannelLayer'}})
class NoticeChannelTests(TransactionTestCase):
    def setUp(self):
        self.acme = Company.objects.create(name='Acme')
        self.globex = Company.objects.create(name='Globex')
        self.acme_user = PortalUser.objects.create(
            email='a@acme.com', company=self.acme, role=PortalUser.ROLE_CUSTOMER)
        self.globex_user = PortalUser.objects.create(
            email='g@globex.com', company=self.globex, role=PortalUser.ROLE_CUSTOMER)
        self.admin = PortalUser.objects.create(
            email='agent@citemed.com', role=PortalUser.ROLE_ADMIN)

    def _raise_notice(self, payload):
        """POST as the agent, the way the admin UI does."""
        def do_post():
            client = self.client
            session = client.session
            session['portal_user_id'] = self.admin.id
            session.save()
            import json
            response = client.post(
                '/api/admin/notices/', data=json.dumps(payload),
                content_type='application/json')
            assert response.status_code == 201, response.content
            return response.json()['notice']['id']
        return do_post

    def test_refuses_an_unauthenticated_connection(self):
        """Not a public status page (EC-SOP-07 §5.2), on the socket too."""
        communicator = _connect('/ws/notices/')

        async def scenario():
            connected, code = await communicator.connect()
            assert not connected
            assert code == 4403

        async_to_sync(scenario)()

    def test_a_platform_wide_notice_nudges_a_connected_customer(self):
        communicator = _connect('/ws/notices/', self.acme_user.id)

        async def scenario():
            connected, _ = await communicator.connect()
            assert connected
            await database_sync_to_async(self._raise_notice({'message': 'Uploads failing'}))()

            got = await communicator.receive_json_from(timeout=2)
            assert got['type'] == 'notice.changed', got
            assert got['event'] == 'raised', got
            # Consistent with the ticket nudges: the socket carries no content,
            # the client refetches through the REST endpoint that enforces
            # tenant scoping. A message body on the wire would bypass that.
            assert 'message' not in got, got

            await communicator.disconnect()

        async_to_sync(scenario)()

    def test_a_company_scoped_notice_does_not_nudge_another_tenant(self):
        """The nudge is content-free, but its arrival still tells you something
        happened — so scoping has to hold on the socket, not only in REST."""
        outsider = _connect('/ws/notices/', self.globex_user.id)

        async def scenario():
            connected, _ = await outsider.connect()
            assert connected
            await database_sync_to_async(self._raise_notice(
                {'message': 'Your sync is delayed', 'company_ids': [self.acme.id]}))()

            assert await outsider.receive_nothing(timeout=1)
            await outsider.disconnect()

        async_to_sync(scenario)()

    def test_a_company_scoped_notice_nudges_the_named_tenant(self):
        insider = _connect('/ws/notices/', self.acme_user.id)

        async def scenario():
            connected, _ = await insider.connect()
            assert connected
            await database_sync_to_async(self._raise_notice(
                {'message': 'Your sync is delayed', 'company_ids': [self.acme.id]}))()

            got = await insider.receive_json_from(timeout=2)
            assert got['type'] == 'notice.changed', got

            await insider.disconnect()

        async_to_sync(scenario)()

    def test_retiring_a_notice_nudges_so_the_banner_clears_itself(self):
        """Otherwise a resolved incident keeps warning people until they reload."""
        communicator = _connect('/ws/notices/', self.acme_user.id)

        async def scenario():
            connected, _ = await communicator.connect()
            assert connected
            notice_id = await database_sync_to_async(
                self._raise_notice({'message': 'Uploads failing'}))()
            await communicator.receive_json_from(timeout=2)  # the 'raised' nudge

            def do_retire():
                response = self.client.delete(f'/api/admin/notices/{notice_id}/')
                assert response.status_code == 200, response.content

            await database_sync_to_async(do_retire)()
            got = await communicator.receive_json_from(timeout=2)
            assert got['event'] == 'retired', got

            await communicator.disconnect()

        async_to_sync(scenario)()

    def test_an_agent_with_no_company_still_hears_platform_wide_notices(self):
        communicator = _connect('/ws/notices/', self.admin.id)

        async def scenario():
            connected, _ = await communicator.connect()
            assert connected
            await database_sync_to_async(self._raise_notice({'message': 'Uploads failing'}))()
            got = await communicator.receive_json_from(timeout=2)
            assert got['type'] == 'notice.changed', got

            await communicator.disconnect()

        async_to_sync(scenario)()
