"""
Delete MagicLinkToken rows that have been expired for a while.

Tokens are time-bounded (15-60 min) and one-shot-use, so once a row is
either `used=True` or `expires_at < now()`, it can never authenticate
anyone again. Keeping them around is harmless but unnecessary.

This command prunes rows where `expires_at` is older than the configured
retention window (default 7 days), leaving recent ones for audit / debug.
Designed to be run as a daily cron via Dokku's `cron` plugin
(see app.json) — idempotent and fast.
"""
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from portal.models import MagicLinkToken


class Command(BaseCommand):
    help = 'Delete expired magic-link tokens older than --days days.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--days',
            type=int,
            default=7,
            help='Delete tokens whose expires_at is older than this many days. Default: 7.',
        )

    def handle(self, *args, **options):
        cutoff = timezone.now() - timedelta(days=options['days'])
        qs = MagicLinkToken.objects.filter(expires_at__lt=cutoff)
        count = qs.count()
        qs.delete()
        self.stdout.write(
            self.style.SUCCESS(
                f'Pruned {count} magic-link token(s) older than {options["days"]} day(s).'
            )
        )
