"""Backfill first_response_at for tickets answered before the column existed.

0025 added the field with no data migration, so every historical ticket read as
never-answered and therefore breached its SLA — in production that mislabelled
4 of 9 tickets as Overdue, three of them already resolved.

Uses the same rule as portal.sla.record_first_response (first non-internal
staff message that isn't the ticket's opening message) so backfilled and
live-recorded values mean the same thing. Idempotent — only fills NULLs — so
re-running is harmless.
"""
from django.db import migrations


def backfill(apps, schema_editor):
    # Historical models: don't import portal.sla here, since its logic could
    # drift from what this migration assumed. The rule is inlined deliberately.
    Ticket = apps.get_model('portal', 'Ticket')
    for ticket in Ticket.objects.filter(first_response_at__isnull=True).prefetch_related('messages'):
        msgs = sorted(ticket.messages.all(), key=lambda m: (m.created_at, m.pk))
        if not msgs:
            continue
        opening = msgs[0]
        reply = next(
            (m for m in msgs
             if m.origin == 'staff' and not m.is_internal and m.pk != opening.pk),
            None)
        if reply:
            Ticket.objects.filter(pk=ticket.pk).update(
                first_response_at=reply.created_at)


def noop(apps, schema_editor):
    """Reverse is a no-op: the column stays, and clearing it would throw away
    values legitimately recorded since."""


class Migration(migrations.Migration):

    dependencies = [
        ('portal', '0025_ticket_first_response_at'),
    ]

    operations = [
        migrations.RunPython(backfill, noop),
    ]
