"""Broadcast tests: ticket write endpoints must fan a tiny nudge to the
relevant Channels groups via portal.realtime.notify_ticket, fired on
transaction.on_commit so refetches see committed rows. Sockets carry no
ticket content — clients refetch via REST.

Reuses the real-session + cookie-header connection pattern from
test_ws_consumers.py (direct scope['session'] injection doesn't survive
SessionMiddlewareStack), and drives connect/receive/disconnect for a single
communicator inside one async_to_sync coroutine where ordering matters."""
from asgiref.sync import async_to_sync
from channels.db import database_sync_to_async
from channels.testing import WebsocketCommunicator
from django.conf import settings
from django.contrib.sessions.backends.db import SessionStore
from django.test import TransactionTestCase, override_settings

from citemed.asgi import application
from portal.models import Company, PortalUser, Ticket


def _connect(path, portal_user_id=None):
    """Same helper as test_ws_consumers.py — a real session row + cookie
    header, since PortalUserMiddleware resolves scope['session'] from the
    Cookie header via SessionMiddlewareStack, not from direct scope access."""
    session = SessionStore()
    if portal_user_id:
        session['portal_user_id'] = portal_user_id
    session.save()
    cookie_header = f'{settings.SESSION_COOKIE_NAME}={session.session_key}'.encode()
    headers = [(b'cookie', cookie_header), (b'origin', b'http://localhost')]
    return WebsocketCommunicator(application, path, headers=headers)


@override_settings(CHANNEL_LAYERS={'default': {'BACKEND': 'channels.layers.InMemoryChannelLayer'}})
class BroadcastTest(TransactionTestCase):
    def setUp(self):
        self.co = Company.objects.create(name='A')
        self.cust = PortalUser.objects.create(email='c@a.com', company=self.co, role=PortalUser.ROLE_CUSTOMER)
        self.admin = PortalUser.objects.create(email='adm@a.com', company=self.co, role=PortalUser.ROLE_ADMIN)
        self.t = Ticket.objects.create(company=self.co, created_by=self.cust, subject='x')

    def test_customer_reply_nudges_thread_and_admins(self):
        thread = _connect(f'/ws/tickets/{self.t.number}/', self.cust.id)
        admins = _connect('/ws/admin/tickets/', self.admin.id)

        async def scenario():
            connected_t, _ = await thread.connect()
            connected_a, _ = await admins.connect()
            assert connected_t
            assert connected_a

            def do_reply():
                c = self.client
                session = c.session
                session['portal_user_id'] = self.cust.id
                session.save()
                resp = c.post(f'/api/tickets/{self.t.number}/messages/',
                              data='{"body":"hi"}', content_type='application/json')
                assert resp.status_code == 200, resp.content

            # TransactionTestCase runs requests in autocommit (no outer atomic
            # wrapper, unlike TestCase), so transaction.on_commit() fires the
            # callback immediately when registered — captureOnCommitCallbacks
            # (a TestCase-only classmethod, not present on TransactionTestCase
            # in this Django version) isn't needed here.
            await database_sync_to_async(do_reply)()

            got_thread = await thread.receive_json_from(timeout=2)
            got_admin = await admins.receive_json_from(timeout=2)
            assert got_thread['type'] == 'ticket.changed'
            assert got_thread['event'] == 'customer_reply'
            assert got_admin['type'] == 'inbox.changed'
            assert got_admin['event'] == 'customer_reply'

            await thread.disconnect()
            await admins.disconnect()

        async_to_sync(scenario)()

    def test_internal_note_nudges_admins_only(self):
        thread = _connect(f'/ws/tickets/{self.t.number}/', self.cust.id)
        admins = _connect('/ws/admin/tickets/', self.admin.id)

        async def scenario():
            connected_t, _ = await thread.connect()
            connected_a, _ = await admins.connect()
            assert connected_t
            assert connected_a

            def do_note():
                c = self.client
                session = c.session
                session['portal_user_id'] = self.admin.id
                session.save()
                resp = c.post(f'/api/admin/tickets/{self.t.number}/messages/',
                              data='{"body":"note","is_internal":true}',
                              content_type='application/json')
                assert resp.status_code == 200, resp.content

            await database_sync_to_async(do_note)()

            got_admin = await admins.receive_json_from(timeout=2)
            assert got_admin['type'] == 'inbox.changed'
            assert got_admin['event'] == 'internal_note'
            assert await thread.receive_nothing()  # customer got nothing

            await thread.disconnect()
            await admins.disconnect()

        async_to_sync(scenario)()
