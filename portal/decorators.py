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

        if not PortalUser.objects.filter(pk=user_id).exists():
            # Stale session — clear and reject.
            request.session.flush()
            return JsonResponse({'error': 'Authentication required'}, status=401)

        return view_func(request, *args, **kwargs)

    return wrapped
