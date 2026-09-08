"""Apply roster spreadsheets a customer has confirmed (REV-45).

WHY A CRON COMMAND AND NOT A TASK QUEUE. The Procfile disables the Celery
worker for this app — "worker / beat disabled for v1 — sync runs via `dokku run`
cron, no Redis dependency" — and every other background job here is an app.json
cron entry. Carrying one spreadsheet import would mean adding an always-on
process type, a Redis dependency in the deploy path, and a second way for a
release to fail. The trade is latency: an import waits up to a minute instead of
starting instantly, which nobody notices behind a screen that already says the
import is being processed.

WHY NOT JUST DO IT IN THE REQUEST. A 2,000-row roster is a few thousand
queries. On a request that is a proxy timeout with half a roster written and no
record of where it stopped; here a failure leaves the job row saying `failed`
with the reason on it.

Claiming is a conditional UPDATE rather than a read-then-write, so two runs
overlapping — which is what happens the moment one import takes longer than the
cron interval — cannot both pick up the same job.
"""
import logging
import traceback

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from portal import roster
from portal.models import RequestedUser, RosterImport

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Apply confirmed roster imports to their user request.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--limit', type=int, default=5,
            help='Most imports to apply in one run (default: 5).')
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Report what would be applied without writing anything.')

    def handle(self, *args, **opts):
        pending = RosterImport.objects.filter(
            state=RosterImport.STATE_CONFIRMED
        ).order_by('confirmed_at')[:opts['limit']]

        if not pending:
            self.stdout.write('Nothing to apply.')
            return

        applied = 0
        for job in pending:
            if opts['dry_run']:
                preview = roster.build_preview(
                    job.headers, job.rows, job.mapping,
                    job.request.licensed_modules())
                usable = sum(1 for r in preview if r['importable'])
                self.stdout.write(
                    f'[dry-run] import {job.pk} ({job.filename}): '
                    f'{usable} of {len(preview)} row(s) importable')
                continue

            # Claim it. If another run got there first the update touches no
            # rows and this one moves on.
            claimed = RosterImport.objects.filter(
                pk=job.pk, state=RosterImport.STATE_CONFIRMED
            ).update(state=RosterImport.STATE_APPLYING)
            if not claimed:
                continue

            try:
                self._apply(job)
                applied += 1
            except Exception as exc:
                logger.error('roster import %s failed: %s', job.pk, exc,
                             exc_info=True)
                RosterImport.objects.filter(pk=job.pk).update(
                    state=RosterImport.STATE_FAILED,
                    error=f'{exc}\n{traceback.format_exc()}'[:4000],
                    applied_at=timezone.now())
                self.stderr.write(self.style.ERROR(
                    f'Import {job.pk} failed: {exc}'))

        if applied:
            self.stdout.write(self.style.SUCCESS(
                f'Applied {applied} roster import(s).'))

    def _apply(self, job):
        """Write one import's rows onto its request.

        Uses the SAME build_preview the confirmation screen used, against the
        same stored mapping — so what is written is what the customer was shown.
        If this re-derived the mapping the preview would be decoration.
        """
        job.refresh_from_db()
        request = job.request
        preview = roster.build_preview(
            job.headers, job.rows, job.mapping, request.licensed_modules())

        created = updated = skipped = 0
        problems = []

        # One transaction for the whole file: a roster half-applied is worse
        # than one not applied, because nobody can tell which half.
        with transaction.atomic():
            for row in preview:
                if not row['importable']:
                    skipped += 1
                    for problem in row['problems']:
                        problems.append({'row': row['line'], **problem})
                    continue

                # Non-blocking problems (an unknown module, a missing role)
                # travel with the row so the customer still sees them after the
                # import, rather than only in the preview they have now left.
                for problem in row['problems']:
                    problems.append({'row': row['line'], **problem})

                _, was_created = RequestedUser.objects.update_or_create(
                    request=request,
                    email=row['email'],
                    defaults={
                        'first_name': row['first_name'][:128],
                        'last_name': row['last_name'][:128],
                        'modules': row['modules'],
                        'role_type': row['role_type'],
                        'note': row['note'],
                        'source': RequestedUser.SOURCE_IMPORT,
                    },
                )
                if was_created:
                    created += 1
                else:
                    updated += 1

            RosterImport.objects.filter(pk=job.pk).update(
                state=RosterImport.STATE_DONE,
                created_count=created,
                updated_count=updated,
                skipped_count=skipped,
                # Bounded: a 2,000-row file of nothing but bad rows should not
                # write a multi-megabyte JSON blob nobody will read past the
                # first screenful.
                problems=problems[:200],
                applied_at=timezone.now(),
            )

        logger.info('roster import %s applied: created=%s updated=%s skipped=%s',
                    job.pk, created, updated, skipped)
        self.stdout.write(
            f'Import {job.pk} ({job.filename}): {created} added, '
            f'{updated} updated, {skipped} skipped')
