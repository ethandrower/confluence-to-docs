import secrets
from datetime import timedelta
from django.http import JsonResponse
from django.views.decorators.http import require_POST, require_GET
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from django.core.mail import send_mail
from django.conf import settings
from django.utils.decorators import method_decorator
import json
import logging

logger = logging.getLogger(__name__)


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

    from portal.models import PortalUser, MagicLinkToken

    user, _ = PortalUser.objects.get_or_create(email=email)
    token = MagicLinkToken.objects.create(
        user=user,
        token=secrets.token_urlsafe(32),
        expires_at=timezone.now() + timedelta(minutes=settings.PORTAL_MAGIC_LINK_EXPIRY_MINUTES),
    )

    frontend_url = getattr(settings, 'FRONTEND_URL', 'http://localhost:5173')
    magic_url = f"{frontend_url}/auth/verify?token={token.token}"

    try:
        send_mail(
            subject='Your CiteMed Support Portal login link',
            message=f"Click to log in:\n\n{magic_url}\n\nThis link expires in {settings.PORTAL_MAGIC_LINK_EXPIRY_MINUTES} minutes.",
            html_message=f"""
            <p>Click the link below to log in to the CiteMed Support Portal:</p>
            <p><a href="{magic_url}">Log in to CiteMed Support Portal</a></p>
            <p>This link expires in {settings.PORTAL_MAGIC_LINK_EXPIRY_MINUTES} minutes.</p>
            <p>If you didn't request this, you can ignore this email.</p>
            """,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[email],
            fail_silently=False,
        )
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

    return JsonResponse({
        'user': {'id': user.pk, 'email': user.email, 'name': user.name},
    })


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

    return JsonResponse({
        'user': {'id': user.pk, 'email': user.email, 'name': user.name},
    })


@csrf_exempt
@require_POST
def logout(request):
    request.session.flush()
    return JsonResponse({'message': 'Logged out'})
