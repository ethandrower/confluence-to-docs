import secrets
from datetime import timedelta
from django.http import JsonResponse
from django.views.decorators.http import require_POST, require_GET
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.conf import settings
from django.utils.decorators import method_decorator
import json
import logging

from portal.rate_limit import client_ip, is_rate_limited


def _user_payload(portal_user, request=None):
    """
    Build the `user` dict the frontend stores. Includes is_admin + admin_url
    iff there's an ACTIVE Django superuser whose email matches this portal
    user's email — that linkage is what grants admin access here.

    `admin_url` is only included for actual admins so the obfuscated
    ADMIN_PATH never leaks to ordinary logged-in users.

    The admin_url is built as an absolute URL via build_absolute_uri so it
    resolves correctly in both:
      - dev (Vite on :5173 + Django on :8001 are different origins; a
        relative path on the Vite origin doesn't hit Django at all)
      - prod (Dokku serves both from one origin; absolute URL still works)
    """
    User = get_user_model()
    is_admin = User.objects.filter(
        email__iexact=portal_user.email,
        is_superuser=True,
        is_active=True,
    ).exists()

    payload = {
        'id': portal_user.pk,
        'email': portal_user.email,
        'name': portal_user.name,
        'is_admin': is_admin,
    }
    if is_admin:
        relative = f'/{settings.ADMIN_PATH}/'
        payload['admin_url'] = request.build_absolute_uri(relative) if request else relative
    return payload

logger = logging.getLogger(__name__)

# Per-IP: cap requests from one source (prevents bot floods, Mailgun bill abuse).
# Per-email: cap requests targeting one mailbox (prevents using the form to
# harass a specific person with login emails they didn't ask for).
MAGIC_LINK_IP_MAX = 10
MAGIC_LINK_IP_WINDOW = 60 * 60  # 1 hour
MAGIC_LINK_EMAIL_MAX = 5
MAGIC_LINK_EMAIL_WINDOW = 60 * 60


@csrf_exempt
@require_POST
def request_magic_link(request):
    try:
        data = json.loads(request.body)
        email = data.get('email', '').strip().lower()
    except Exception:
        return JsonResponse({'error': 'Invalid request'}, status=400)

    if not email or '@' not in email:
        return JsonResponse({'error': 'Valid email required'}, status=400)

    # Rate limit BEFORE creating any DB rows or sending email. Two buckets:
    # one by source IP, one by target email — checked independently. Either
    # tripping returns a generic 429 (so we don't reveal whether the email
    # has been used before / give an enumeration oracle).
    ip = client_ip(request)
    ip_limited = is_rate_limited('magic-link-ip', ip, MAGIC_LINK_IP_MAX, MAGIC_LINK_IP_WINDOW)
    email_limited = is_rate_limited(
        'magic-link-email', email, MAGIC_LINK_EMAIL_MAX, MAGIC_LINK_EMAIL_WINDOW
    )
    if ip_limited or email_limited:
        logger.warning(
            'Magic-link rate limit hit ip=%s email=%s ip_limited=%s email_limited=%s',
            ip, email, ip_limited, email_limited,
        )
        return JsonResponse(
            {'error': 'Too many requests. Please try again later.'},
            status=429,
        )

    from portal.models import PortalUser, MagicLinkToken

    user, _ = PortalUser.objects.get_or_create(email=email)
    token = MagicLinkToken.objects.create(
        user=user,
        token=secrets.token_urlsafe(32),
        expires_at=timezone.now() + timedelta(minutes=settings.PORTAL_MAGIC_LINK_EXPIRY_MINUTES),
    )

    frontend_url = getattr(settings, 'FRONTEND_URL', 'http://localhost:5173')
    magic_url = f"{frontend_url}/auth/verify?token={token.token}"

    ctx = {
        'company_name': 'CiteMed',
        'product_name': 'Support Portal',
        'magic_url': magic_url,
        'expiry_minutes': settings.PORTAL_MAGIC_LINK_EXPIRY_MINUTES,
        'recipient_email': email,
    }

    try:
        msg = EmailMultiAlternatives(
            subject='Your CiteMed Support Portal sign-in link',
            body=render_to_string('emails/magic_link.txt', ctx),
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[email],
            # Disable Mailgun's open/click tracking on auth emails:
            # the tracking pixel triggers Gmail's "loading external
            # images" prompt and click-rewriting makes login URLs look
            # like phishing redirects. Both are bad UX on a sign-in
            # link. Mailgun reads these as `o:tracking-*` directives.
            headers={
                'X-Mailgun-Track-Opens': 'no',
                'X-Mailgun-Track-Clicks': 'no',
            },
        )
        msg.attach_alternative(
            render_to_string('emails/magic_link.html', ctx),
            'text/html',
        )
        msg.send()
    except Exception as e:
        logger.error(f"Failed to send magic link email to {email}: {e}")
        # Don't expose email errors to prevent enumeration
        pass

    return JsonResponse({'message': 'Magic link sent if email exists'})


@require_GET
def verify_magic_link(request):
    token_str = request.GET.get('token', '')
    if not token_str:
        return JsonResponse({'error': 'Token required'}, status=400)

    from portal.models import MagicLinkToken

    try:
        token = MagicLinkToken.objects.select_related('user').get(token=token_str)
    except MagicLinkToken.DoesNotExist:
        return JsonResponse({'error': 'Invalid token'}, status=401)

    if not token.is_valid():
        return JsonResponse({'error': 'Token expired or already used'}, status=401)

    user = token.user
    token.used = True
    token.save(update_fields=['used'])

    user.last_login = timezone.now()
    user.save(update_fields=['last_login'])

    request.session['portal_user_id'] = user.pk
    request.session.save()

    return JsonResponse({'user': _user_payload(user, request)})


@require_GET
def me(request):
    user_id = request.session.get('portal_user_id')
    if not user_id:
        return JsonResponse({'error': 'Not authenticated'}, status=401)

    from portal.models import PortalUser

    try:
        user = PortalUser.objects.get(pk=user_id)
    except PortalUser.DoesNotExist:
        return JsonResponse({'error': 'Not authenticated'}, status=401)

    return JsonResponse({'user': _user_payload(user, request)})


@csrf_exempt
@require_POST
def logout(request):
    request.session.flush()
    return JsonResponse({'message': 'Logged out'})
