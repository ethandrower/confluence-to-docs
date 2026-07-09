"""Authentication decorators for portal API views."""
from functools import wraps

from django.http import JsonResponse


def require_portal_user(view_func):
    """
    Require an authenticated PortalUser session.

    Returns 401 if the request has no `portal_user_id` in session, or if the
    referenced user no longer exists. Use on docs API endpoints so the frontend
    auth gate is enforced server-side too.
    """

    @wraps(view_func)
    def wrapped(request, *args, **kwargs):
        user_id = request.session.get('portal_user_id')
        if not user_id:
            return JsonResponse({'error': 'Authentication required'}, status=401)

        # Lazy import to avoid circular imports with views.
        from portal.models import PortalUser

        user = PortalUser.objects.filter(pk=user_id).first()
        if not user:
            # Stale session — clear and reject.
            request.session.flush()
            return JsonResponse({'error': 'Authentication required'}, status=401)

        request.portal_user = user
        return view_func(request, *args, **kwargs)

    return wrapped


def is_portal_admin(portal_user):
    """True if this PortalUser is a portal owner/admin, or an active Django
    superuser matched by email. Single source of truth for admin gating,
    shared by require_portal_admin and the WS consumers."""
    if portal_user is None:
        return False
    from django.contrib.auth import get_user_model
    from portal.models import PortalUser

    User = get_user_model()
    is_super = User.objects.filter(
        email__iexact=portal_user.email, is_superuser=True, is_active=True
    ).exists()
    return (
        is_super
        or portal_user.role == PortalUser.ROLE_OWNER
        or portal_user.role == PortalUser.ROLE_ADMIN
    )


def require_portal_admin(view_func):
    """
    Require an authenticated PortalUser who is an admin — either portal role
    'admin' or an active Django superuser. Attaches the user as
    `request.portal_user`. Returns 401 if unauthenticated, 403 if not an admin.
    """

    @wraps(view_func)
    def wrapped(request, *args, **kwargs):
        user_id = request.session.get('portal_user_id')
        if not user_id:
            return JsonResponse({'error': 'Authentication required'}, status=401)

        from django.contrib.auth import get_user_model
        from portal.models import PortalUser

        user = PortalUser.objects.filter(pk=user_id).first()
        if not user:
            request.session.flush()
            return JsonResponse({'error': 'Authentication required'}, status=401)

        is_owner = (
            user.role == PortalUser.ROLE_OWNER
            or get_user_model().objects.filter(
                email__iexact=user.email, is_superuser=True, is_active=True).exists()
        )
        if not is_portal_admin(user):
            return JsonResponse({'error': 'Admin access required'}, status=403)

        request.portal_user = user
        request.is_owner = is_owner
        return view_func(request, *args, **kwargs)

    return wrapped
