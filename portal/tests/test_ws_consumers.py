from asgiref.sync import async_to_sync
from channels.testing import WebsocketCommunicator
from django.conf import settings
from django.contrib.sessions.backends.db import SessionStore
from django.test import TransactionTestCase, override_settings

from citemed.asgi import application
from portal.models import Company, PortalUser, Ticket


def _connect(path, portal_user_id=None):
    """Build a communicator authenticated via a real session + cookie header.

    Directly injecting `communicator.scope['session']` doesn't survive
    `SessionMiddlewareStack`, which rebuilds scope['session'] from the
    `Cookie` header (or lack thereof) before PortalUserMiddleware ever sees
    it. So we persist a real session row and hand Channels a session cookie,
    exactly like a browser would.
    """
    session = SessionStore()
    if portal_user_id:
        session['portal_user_id'] = portal_user_id
    session.save()
    cookie_header = f'{settings.SESSION_COOKIE_NAME}={session.session_key}'.encode()
    # AllowedHostsOriginValidator (outermost in citemed/asgi.py) rejects any
    # connection with no Origin header, regardless of auth — WebsocketCommunicator
    # sends none by default, so every connect() would 4xx before middleware even
    # runs unless we supply one matching ALLOWED_HOSTS.
    headers = [(b'cookie', cookie_header), (b'origin', b'http://localhost')]
    return WebsocketCommunicator(application, path, headers=headers)


def _connect_then_disconnect(communicator):
    """Run connect() and (if accepted) disconnect() inside ONE async_to_sync
    call. Each top-level async_to_sync() call spins up its own event loop and
    tears it down (via asyncio.run) once its coroutine returns, cancelling any
    task still alive in that loop — including the consumer's own background
    dispatch task. Calling connect() and disconnect() as two separate
    async_to_sync() invocations lets the first loop close before disconnect()
    ever runs, so the second call finds an already-cancelled application
    future. Keeping both in one coroutine keeps the consumer's task alive for
    the whole exchange."""

    async def scenario():
        connected, _ = await communicator.connect()
        if connected:
            await communicator.disconnect()
        return connected

    return async_to_sync(scenario)()


@override_settings(CHANNEL_LAYERS={'default': {'BACKEND': 'channels.layers.InMemoryChannelLayer'}})
class TicketConsumerAuthTest(TransactionTestCase):
    def setUp(self):
        self.co_a = Company.objects.create(name='A')
        self.co_b = Company.objects.create(name='B')
        self.cust_a = PortalUser.objects.create(email='a@a.com', company=self.co_a, role=PortalUser.ROLE_CUSTOMER)
        self.cust_b = PortalUser.objects.create(email='b@b.com', company=self.co_b, role=PortalUser.ROLE_CUSTOMER)
        self.ticket_a = Ticket.objects.create(company=self.co_a, created_by=self.cust_a, subject='x')

    def test_owner_can_connect_to_own_ticket(self):
        c = _connect(f'/ws/tickets/{self.ticket_a.number}/', self.cust_a.id)
        connected = _connect_then_disconnect(c)
        self.assertTrue(connected)

    def test_other_tenant_rejected(self):
        c = _connect(f'/ws/tickets/{self.ticket_a.number}/', self.cust_b.id)
        connected, _ = async_to_sync(c.connect)()
        self.assertFalse(connected)

    def test_anonymous_rejected(self):
        c = _connect(f'/ws/tickets/{self.ticket_a.number}/', None)
        connected, _ = async_to_sync(c.connect)()
        self.assertFalse(connected)


@override_settings(CHANNEL_LAYERS={'default': {'BACKEND': 'channels.layers.InMemoryChannelLayer'}})
class AdminAndCustomerListAuthTest(TransactionTestCase):
    def setUp(self):
        self.co = Company.objects.create(name='A')
        self.admin = PortalUser.objects.create(email='adm@a.com', company=self.co, role=PortalUser.ROLE_ADMIN)
        self.cust = PortalUser.objects.create(email='c@a.com', company=self.co, role=PortalUser.ROLE_CUSTOMER)

    def test_non_admin_rejected_from_admin_ws(self):
        c = _connect('/ws/admin/tickets/', self.cust.id)
        connected, _ = async_to_sync(c.connect)()
        self.assertFalse(connected)

    def test_admin_accepted(self):
        c = _connect('/ws/admin/tickets/', self.admin.id)
        connected = _connect_then_disconnect(c)
        self.assertTrue(connected)

    def test_customer_list_requires_company(self):
        c = _connect('/ws/customer/tickets/', self.cust.id)
        connected = _connect_then_disconnect(c)
        self.assertTrue(connected)
