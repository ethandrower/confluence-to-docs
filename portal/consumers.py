"""WebSocket consumers. Authorize the connection against the portal identity,
join the right group, and relay tiny nudges. They NEVER serialize ticket
content — clients refetch via REST (which enforces customer/admin gating)."""
from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer

from portal.decorators import is_portal_admin


class TicketConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        user = self.scope.get('portal_user')
        if user is None:
            await self.close(code=4403)
            return
        number = self.scope['url_route']['kwargs']['number']
        if not await self._can_view(user, number):
            await self.close(code=4403)
            return
        self.group = f'ticket-{number}'
        await self.channel_layer.group_add(self.group, self.channel_name)
        await self.accept()

    async def disconnect(self, code):
        if hasattr(self, 'group'):
            await self.channel_layer.group_discard(self.group, self.channel_name)

    async def ticket_changed(self, event):
        await self.send_json({'type': 'ticket.changed',
                              'number': event['number'], 'event': event['event']})

    @database_sync_to_async
    def _can_view(self, user, number):
        from portal.models import Ticket
        # Customers see only their own company's tickets (for_user is
        # company-scoped); portal admins/staff handle ALL companies' threads,
        # so they must not be gated by company.
        if is_portal_admin(user):
            return True
        return Ticket.for_user(user).filter(number=number).exists()


class AdminInboxConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        user = self.scope.get('portal_user')
        if user is None or not await self._is_admin(user):
            await self.close(code=4403)
            return
        self.group = 'admins'
        await self.channel_layer.group_add(self.group, self.channel_name)
        await self.accept()

    async def disconnect(self, code):
        # Only discard if we actually joined — a rejected connection closes
        # before group_add, so guard like the other two consumers.
        if hasattr(self, 'group'):
            await self.channel_layer.group_discard(self.group, self.channel_name)

    async def inbox_changed(self, event):
        await self.send_json({'type': 'inbox.changed',
                              'number': event['number'], 'event': event['event']})

    @database_sync_to_async
    def _is_admin(self, user):
        return is_portal_admin(user)


class CustomerListConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        user = self.scope.get('portal_user')
        if user is None or not user.company_id:
            await self.close(code=4403)
            return
        self.group = f'co-{user.company_id}'
        await self.channel_layer.group_add(self.group, self.channel_name)
        await self.accept()

    async def disconnect(self, code):
        if hasattr(self, 'group'):
            await self.channel_layer.group_discard(self.group, self.channel_name)

    async def list_changed(self, event):
        await self.send_json({'type': 'list.changed',
                              'number': event['number'], 'event': event['event']})


class SiteNoticeConsumer(AsyncJsonWebsocketConsumer):
    """Incident/maintenance nudges (#49). Any signed-in portal user may listen —
    including agents, who have no company — but nothing is public: §5.2 commits
    to no public status page, so an unauthenticated socket is refused like any
    other.

    Joins the platform-wide group, plus the caller's company group when they
    have one, so a scoped notice reaches exactly the tenants it names.
    """
    async def connect(self):
        user = self.scope.get('portal_user')
        if user is None:
            await self.close(code=4403)
            return
        from portal.realtime import NOTICE_GROUP_ALL, notice_group_for_company

        self.groups_joined = [NOTICE_GROUP_ALL]
        if user.company_id:
            self.groups_joined.append(notice_group_for_company(user.company_id))
        for group in self.groups_joined:
            await self.channel_layer.group_add(group, self.channel_name)
        await self.accept()

    async def disconnect(self, code):
        # Guard like the other consumers: a rejected connection closes before
        # any group_add ran.
        for group in getattr(self, 'groups_joined', []):
            await self.channel_layer.group_discard(group, self.channel_name)

    async def notice_changed(self, event):
        await self.send_json({'type': 'notice.changed', 'event': event['event']})
