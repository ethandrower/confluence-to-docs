"""Pull recent delivery events from the Mailgun Events API and apply them to
ticket messages — the same updates the webhook does, but by polling instead of
being pushed to.

Use it where Mailgun can't reach us (local dev, no public webhook URL) and as a
prod backstop for missed webhook events:

    python manage.py poll_mailgun_events            # last 1 hour
    python manage.py poll_mailgun_events --hours 24

Auth + domain come from the same MAILGUN_ACCESS_KEY / MAILGUN_SERVER_NAME the
send path uses.
"""
import time

import requests
from django.conf import settings
from django.core.management.base import BaseCommand

from portal.webhook_handlers import apply_delivery_event

# Mailgun event names we care about (maps 1:1 to apply_delivery_event).
EVENTS = ['delivered', 'failed', 'complained']
US_BASE = 'https://api.mailgun.net/v3'


class Command(BaseCommand):
    help = 'Reconcile ticket delivery_status from the Mailgun Events API.'

    def add_arguments(self, parser):
        parser.add_argument('--hours', type=float, default=1.0,
                            help='How far back to pull events (default 1h).')

    def handle(self, *args, **opts):
        key = getattr(settings, 'MAILGUN_ACCESS_KEY', '')
        domain = getattr(settings, 'MAILGUN_SERVER_NAME', '')
        if not (key and domain):
            self.stderr.write('MAILGUN_ACCESS_KEY / MAILGUN_SERVER_NAME not set.')
            return

        begin = time.time() - opts['hours'] * 3600
        url = f'{US_BASE}/{domain}/events'
        params = {'event': ' OR '.join(EVENTS), 'begin': begin,
                  'ascending': 'yes', 'limit': 300}
        updated = seen = 0
        try:
            while url:
                r = requests.get(url, auth=('api', key), params=params, timeout=15)
                params = None  # paging URLs are fully-formed
                if r.status_code != 200:
                    self.stderr.write(f'Mailgun events HTTP {r.status_code}: {r.text[:200]}')
                    return
                body = r.json()
                items = body.get('items', [])
                for ev in items:
                    seen += 1
                    mid = (ev.get('message', {}).get('headers', {}) or {}).get('message-id', '')
                    etype = ev.get('event', '')
                    reason = ev.get('reason') or ev.get('delivery-status', {}).get('description', '')
                    if apply_delivery_event(mid, etype, reason):
                        updated += 1
                url = (body.get('paging', {}) or {}).get('next')
                if not items:
                    break
        except Exception as e:
            self.stderr.write(f'poll failed: {e}')
            return
        self.stdout.write(self.style.SUCCESS(
            f'Mailgun events: {seen} scanned, {updated} ticket messages updated.'))
