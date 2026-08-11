"""Customer-facing incident and maintenance notices (#49).

Every read here is behind a portal session. EC-SOP-07 §5.2 states CiteMed does
not operate a PUBLIC status page, so this must not quietly become one — the
banner is for people already signed in.

It also does not discharge the SOP's obligation. §5.2 names email to the
designated account contact as the channel, and this banner shares fate with the
portal: same host, same web container, unreachable exactly when a SEV-1 is in
progress. It supplements that email; it never replaces it.
"""
from django.http import JsonResponse
from django.views.decorators.http import require_GET, require_POST

from portal.decorators import require_portal_user
from portal.models import NoticeDismissal, SiteNotice

#: Cap on the history response. Generous next to any plausible incident count,
#: and present only so one endpoint can't return an unbounded list.
HISTORY_LIMIT = 50


def notice_dict(notice):
    """Customer-visible shape. No `created_by` — which agent raised a notice is
    internal, and the customer only needs to know what is happening."""
    return {
        'id': notice.id,
        'level': notice.level,
        'message': notice.message,
        'link_url': notice.link_url,
        'link_label': notice.link_label,
        'dismissible': notice.is_dismissible,
        'starts_at': notice.starts_at.isoformat(),
        'ends_at': notice.ends_at.isoformat() if notice.ends_at else None,
        'retired_at': notice.retired_at.isoformat() if notice.retired_at else None,
    }


@require_portal_user
@require_GET
def notices(request):
    """The banner's source. Live, in-scope, and not already dismissed by
    this user."""
    user = request.portal_user
    dismissed = NoticeDismissal.objects.filter(user=user).values_list('notice_id', flat=True)
    live = SiteNotice.currently_visible(
        queryset=SiteNotice.for_user(user)
    ).exclude(pk__in=dismissed).prefetch_related('companies')
    return JsonResponse({'notices': [notice_dict(n) for n in live]})


@require_portal_user
@require_GET
def history(request):
    """Past and present notices — the "log of incidents and resolutions"
    TG-421 asked for, and the reason retiring a notice is not a delete.

    Includes dismissed notices (dismissing hides the banner, not the record) and
    retired ones, but never notices whose window hasn't opened: `starts_at` in
    the future means "not announced yet", and history must not pre-empt it.
    """
    from django.utils import timezone

    in_scope = SiteNotice.for_user(request.portal_user).filter(
        starts_at__lte=timezone.now()
    ).order_by('-starts_at')[:HISTORY_LIMIT]
    return JsonResponse({'notices': [notice_dict(n) for n in in_scope]})


@require_portal_user
@require_POST
def dismiss(request, notice_id):
    """Hide a notice for THIS user only — a colleague clearing a banner must not
    clear it for the rest of their company."""
    user = request.portal_user
    # Resolved through for_user, so an id from another tenant is a 404 rather
    # than a writeable handle.
    notice = SiteNotice.for_user(user).filter(pk=notice_id).first()
    if notice is None:
        return JsonResponse({'error': 'Not found'}, status=404)
    if not notice.is_dismissible:
        # Enforced here and not merely by hiding the button: this endpoint is
        # reachable directly, and a critical notice staying put is the point.
        return JsonResponse({'error': 'This notice cannot be dismissed'}, status=400)
    # get_or_create, so a double-click or a retry is a no-op rather than an
    # IntegrityError on the unique constraint.
    NoticeDismissal.objects.get_or_create(notice=notice, user=user)
    return JsonResponse({'ok': True})
