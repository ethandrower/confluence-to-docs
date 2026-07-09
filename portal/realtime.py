"""Fan a tiny 'ticket changed' nudge to the relevant Channels groups. Carries
NO ticket content — clients refetch via REST. Safe no-op if no channel layer."""
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer


def notify_ticket(ticket, event, *, to_ticket=True, to_admins=True, to_company=True):
    layer = get_channel_layer()
    if layer is None:
        return
    number, company_id = ticket.number, ticket.company_id
    if to_ticket:
        async_to_sync(layer.group_send)(
            f'ticket-{number}', {'type': 'ticket.changed', 'number': number, 'event': event})
    if to_admins:
        async_to_sync(layer.group_send)(
            'admins', {'type': 'inbox.changed', 'number': number, 'event': event})
    if to_company and company_id:
        async_to_sync(layer.group_send)(
            f'co-{company_id}', {'type': 'list.changed', 'number': number, 'event': event})
