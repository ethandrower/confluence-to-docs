"""Channels middleware that resolves the portal's custom session identity
(session['portal_user_id'] -> PortalUser) into scope['portal_user']. The app
does not use django.contrib.auth.login, so AuthMiddlewareStack/scope['user']
would be AnonymousUser — this is the WS equivalent of require_portal_user."""
from channels.db import database_sync_to_async


@database_sync_to_async
def _load_portal_user(session):
    # `session` is a lazily-loaded Django SessionBase (DB-backed in this app).
    # Its first attribute access issues a sync ORM query, so the read itself
    # — not just the PortalUser lookup — must happen inside this
    # database_sync_to_async wrapper. Doing `session.get(...)` directly in the
    # async `__call__` below would raise SynchronousOnlyOperation, since
    # Channels middleware runs on the event-loop thread.
    user_id = session.get('portal_user_id') if session else None
    if not user_id:
        return None
    from portal.models import PortalUser
    return PortalUser.objects.filter(pk=user_id).first()


class PortalUserMiddleware:
    def __init__(self, inner):
        self.inner = inner

    async def __call__(self, scope, receive, send):
        scope['portal_user'] = await _load_portal_user(scope.get('session'))
        return await self.inner(scope, receive, send)
