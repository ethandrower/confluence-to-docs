"""Send a test file-sharing notification to verify email delivery in prod.

    python manage.py send_test_notification --to you@example.com
"""
from django.core.management.base import BaseCommand

from portal import file_notify


class Command(BaseCommand):
    help = "Send a test branded file-sharing notification email to --to."

    def add_arguments(self, parser):
        parser.add_argument('--to', required=True)

    def handle(self, *args, **opts):
        file_notify._send(
            'CiteMed file sharing — test',
            [opts['to']],
            heading='Test notification',
            body='If you can read this, file-sharing notification emails are working in production.',
            cta_label='Open the portal',
            cta_url='https://support.citemed.com/files',
        )
        self.stdout.write(self.style.SUCCESS(f"Test notification dispatched to {opts['to']} — check the inbox + app logs."))
