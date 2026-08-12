"""Public health endpoint that Dokku gates deploys on, and an external monitor
polls (#50).

Unauthenticated by necessity — neither Dokku's checker nor an uptime monitor
carries a session. So the response says which subsystem is unhealthy and
nothing else: no versions, no settings, no counts, no exception text. Failure
detail goes to the log, where it is useful and not world-readable.
"""
from django.http import JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from portal import health


@never_cache
@require_GET
def healthz(request):
    """200 when every dependency answers, 503 otherwise.

    The non-200 is the whole point: Dokku's zero-downtime check fails the
    release rather than promoting a container that can't reach its database.
    """
    checks = health.run_checks()
    status = health.overall_status(checks)
    return JsonResponse(
        {'status': status, 'checks': checks},
        status=200 if status == health.STATUS_OK else 503,
    )
