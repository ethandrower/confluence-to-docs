"""Turning an agreed roster into portal accounts, and then into invitations.

TWO ACTS, NEVER ONE. REV-26's first rule is that provisioning never emails:
accounts land dormant, and the single thing that reaches a real customer is a
deliberate human click. That rule is the reason this module has two entry points
instead of one convenient `provision_and_invite`:

    provision(request, actor)     writes PortalUser rows. Sends nothing. Ever.
    send_invites(request, actor)  emails the people already provisioned.

Collapsing them would mean a mistyped roster puts eight emails in front of a
customer who has not been introduced yet, and there is no unsending that.

The two columns the customer's own spreadsheet carried are the outputs of these
two functions and of nothing else:

    added_at                  <- provision()
    activation_email_sent_at  <- send_invites()

Neither is settable from any request path, which is what makes them worth
believing. `portal/views/roster.py` returns them and accepts neither.
"""
import logging
import secrets
from datetime import timedelta

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils import timezone

from portal.models import MagicLinkToken, PortalUser, RequestedUser

logger = logging.getLogger(__name__)


def provision(user_request, actor=None):
    """Create or update a PortalUser for every person on the roster.

    Idempotent, and safe to re-run: a person already provisioned is brought up
    to date rather than duplicated, which matters because the natural response
    to a half-failed run is to press the button again.

    Returns {'created': n, 'updated': n, 'skipped': n, 'problems': [...]}.
    """
    company = user_request.company
    created = updated = skipped = 0
    problems = []

    for row in user_request.users.all():
        existing = PortalUser.objects.filter(email=row.email).first()

        if existing and existing.company_id and existing.company_id != company.pk:
            # One address cannot belong to two customers — whichever company it
            # lands on, that person can read that company's tickets. This is the
            # same refusal /api/v1/provisioning makes, for the same reason, and
            # it is a human's problem to resolve rather than something to paper
            # over by reassigning the FK.
            problems.append({
                'email': row.email,
                'message': 'Already registered to a different company.',
            })
            skipped += 1
            continue

        if existing is None:
            portal_user = PortalUser.objects.create(
                email=row.email,
                name=row.full_name,
                role=row.portal_role,
                company=company,
                access_enabled=True,
            )
            created += 1
        else:
            existing.company = company
            existing.name = existing.name or row.full_name
            existing.role = row.portal_role
            existing.access_enabled = True
            existing.save(update_fields=['company', 'name', 'role', 'access_enabled'])
            portal_user = existing
            updated += 1

        # added_at is stamped once. A re-run that only corrected a role should
        # not restate when the person was first set up.
        row.portal_user = portal_user
        if row.added_at is None:
            row.added_at = timezone.now()
        row.save(update_fields=['portal_user', 'added_at'])

    logger.info(
        'roster: provisioned request %s — created=%s updated=%s skipped=%s (by %s)',
        user_request.pk, created, updated, skipped,
        getattr(actor, 'email', 'system'))
    return {'created': created, 'updated': updated, 'skipped': skipped,
            'problems': problems}


def send_invites(user_request, actor=None, only_ids=None):
    """Email a sign-in link to provisioned people who have not had one.

    Only people with `added_at` set: inviting somebody who has no account yet
    sends them to a sign-in page that will refuse them, which is a worse first
    impression than no email at all.

    Re-sending is deliberate rather than automatic — `only_ids` is how staff
    nudge one person — but the default pass skips anybody already invited, so
    pressing the button twice does not mail everyone twice.
    """
    rows = user_request.users.filter(added_at__isnull=False)
    if only_ids:
        rows = rows.filter(pk__in=only_ids)
    else:
        rows = rows.filter(activation_email_sent_at__isnull=True)

    sent = 0
    problems = []
    frontend_url = getattr(settings, 'FRONTEND_URL', 'http://localhost:5173')
    expiry = settings.PORTAL_MAGIC_LINK_EXPIRY_MINUTES

    for row in rows.select_related('portal_user'):
        if row.portal_user is None:
            problems.append({'email': row.email,
                             'message': 'No portal account to invite.'})
            continue

        token = MagicLinkToken.objects.create(
            user=row.portal_user,
            token=secrets.token_urlsafe(32),
            expires_at=timezone.now() + timedelta(minutes=expiry),
        )
        ctx = {
            'company_name': 'CiteMed',
            'product_name': 'Support Portal',
            'magic_url': f'{frontend_url}/auth/verify?token={token.token}',
            'expiry_minutes': expiry,
            'recipient_email': row.email,
            'recipient_name': row.first_name or row.full_name,
            'customer_name': user_request.company.name,
            'modules': row.module_labels(),
            'role_label': dict(RequestedUser.ROLE_CHOICES).get(row.role_type, ''),
        }

        try:
            msg = EmailMultiAlternatives(
                subject='Your CiteMed Support Portal access is ready',
                body=render_to_string('emails/roster_invite.txt', ctx),
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[row.email],
            )
            msg.attach_alternative(
                render_to_string('emails/roster_invite.html', ctx), 'text/html')
            msg.send()
        except Exception as exc:
            # One bad address must not stop the rest of the roster. The failure
            # is recorded against the person so staff can see WHO to chase,
            # which a bare log line would not tell them.
            logger.error('roster: invite to %s failed: %s', row.email, exc)
            problems.append({'email': row.email, 'message': str(exc)})
            continue

        row.activation_email_sent_at = timezone.now()
        row.save(update_fields=['activation_email_sent_at'])
        sent += 1

    logger.info('roster: sent %s invite(s) for request %s (by %s)',
                sent, user_request.pk, getattr(actor, 'email', 'system'))
    return {'sent': sent, 'problems': problems}
