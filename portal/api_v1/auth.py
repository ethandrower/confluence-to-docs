"""Bearer-token authentication for /api/v1/ — and nothing else.

Two properties matter more than the code:

1. It never consults `request.session`. A browser session, however privileged,
   authenticates nothing in this namespace.
2. It never produces a user. On success `request.user` stays anonymous and the
   ApiClient is returned as `request.auth` only, so no view, serializer or
   logging hook downstream can mistake a machine credential for a PortalUser
   and start applying (or skipping) per-user rules on its behalf.
"""
from django.contrib.auth.models import AnonymousUser
from drf_spectacular.extensions import OpenApiAuthenticationExtension
from rest_framework import exceptions
from rest_framework.authentication import BaseAuthentication, get_authorization_header
from rest_framework.permissions import BasePermission

from portal.models import ApiClient


class ApiClientAuthentication(BaseAuthentication):
    """`Authorization: Bearer <token>`, resolved against ApiClient.token_hash."""

    keyword = b'bearer'

    def authenticate(self, request):
        auth = get_authorization_header(request).split()

        # No bearer header at all: not our business. Returning None (rather
        # than failing) lets the schema view fall through to an admin session;
        # the data views have no second authenticator, so the request simply
        # arrives unauthenticated and the permission class rejects it as 401.
        if not auth or auth[0].lower() != self.keyword:
            return None

        if len(auth) != 2:
            raise exceptions.AuthenticationFailed(
                'Invalid Authorization header. Expected "Bearer <token>".')

        try:
            token = auth[1].decode('utf-8')
        except UnicodeError:
            raise exceptions.AuthenticationFailed(
                'Invalid Authorization header. Token contains invalid characters.')

        # Looked up by hash, so the raw token is never compared, logged or
        # stored — and the unique index makes the lookup constant-work.
        client = ApiClient.objects.filter(token_hash=ApiClient.hash_token(token)).first()
        if client is None:
            raise exceptions.AuthenticationFailed('Invalid API token.')
        if not client.enabled:
            # Same status and shape as an unknown token: a revoked credential
            # should not be able to confirm that it was ever a real one.
            raise exceptions.AuthenticationFailed('Invalid API token.')

        client.touch()
        return (AnonymousUser(), client)

    def authenticate_header(self, request):
        # Presence of this header is what makes DRF answer 401 rather than 403
        # for an unauthenticated request.
        return 'Bearer realm="api"'


class ApiClientAuthenticationScheme(OpenApiAuthenticationExtension):
    """Teach drf-spectacular what our authenticator is, so the published schema
    declares the security scheme and Swagger UI offers an Authorize box."""

    target_class = 'portal.api_v1.auth.ApiClientAuthentication'
    name = 'ApiClientToken'

    def get_security_definition(self, auto_schema):
        return {
            'type': 'http',
            'scheme': 'bearer',
            'description': (
                'Token issued by `manage.py create_api_client`, sent as '
                '`Authorization: Bearer <token>`. Revoked in the Django admin.'
            ),
        }


class IsApiClient(BasePermission):
    """Allow only a request carrying a valid, enabled ApiClient token.

    Checks `request.auth`, not `request.user.is_authenticated`. That is the
    whole point: a logged-in Django superuser or a portal session has an
    authenticated user and still fails here, because it has no `request.auth`.
    """

    message = 'A valid API token is required.'

    def has_permission(self, request, view):
        return isinstance(request.auth, ApiClient) and request.auth.enabled


class CanProvision(BasePermission):
    """`IsApiClient`, plus the explicit write capability.

    Kept as a separate class rather than a flag checked inside the view so that
    "which endpoints can write" is answerable by grepping for this name.
    """

    message = 'This API token is not permitted to provision.'

    def has_permission(self, request, view):
        client = request.auth
        return (isinstance(client, ApiClient) and client.enabled
                and client.can_provision)


class IsApiClientOrAdminSession(BasePermission):
    """Gate for the schema and Swagger UI only.

    An unauthenticated schema endpoint advertises the shape of the data to
    anyone who finds it, so it is gated — but a human reading the docs in a
    browser has a cookie, not a bearer token (a browser cannot attach an
    Authorization header to a normal navigation), so sessions are accepted
    here and ONLY here.

    Two kinds of session count, and both are needed. Django's `is_staff` covers
    someone in /django-admin/, but the portal's own agents are PortalUser rows
    with no Django user at all — gating on `is_staff` alone left the docs
    unreachable for every actual staff member, which defeats the point of
    shipping Swagger.
    """

    message = 'A valid API token or a staff session is required.'

    def has_permission(self, request, view):
        if isinstance(request.auth, ApiClient) and request.auth.enabled:
            return True

        user = getattr(request, 'user', None)
        if (user is not None and user.is_authenticated
                and getattr(user, 'is_active', False)
                and getattr(user, 'is_staff', False)):
            return True

        # Portal session. Routed through the same is_portal_admin chokepoint
        # the rest of the admin surface uses, so "who counts as staff" has one
        # definition rather than a second copy that can drift.
        from portal.decorators import is_portal_admin
        from portal.models import PortalUser

        user_id = request.session.get('portal_user_id')
        if not user_id:
            return False
        portal_user = PortalUser.objects.filter(pk=user_id).first()
        return bool(portal_user and portal_user.access_enabled
                    and is_portal_admin(portal_user))
