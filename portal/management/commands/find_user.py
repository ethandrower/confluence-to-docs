"""Look up a PortalUser by email (prod diagnostics).

    python manage.py find_user --email someone@example.com
"""
from django.core.management.base import BaseCommand

from portal.models import PortalUser


class Command(BaseCommand):
    help = "Print whether a PortalUser exists for --email (and near matches)."

    def add_arguments(self, parser):
        parser.add_argument('--email', required=True)

    def handle(self, *args, **opts):
        email = opts['email'].strip()
        u = PortalUser.objects.filter(email__iexact=email).first()
        if u:
            self.stdout.write(self.style.SUCCESS(
                f"FOUND: {u.email} | role={u.role} | enabled={u.access_enabled} | "
                f"company={u.company.name if u.company else None}"
            ))
        else:
            self.stdout.write(self.style.WARNING(f"NOT FOUND: {email}"))
            stem = email.split('@')[0][:4]
            near = list(PortalUser.objects.filter(email__icontains=stem).values_list('email', flat=True))
            self.stdout.write(f"near matches ({stem}*): {near}")
