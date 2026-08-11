"""Fan a tiny 'changed' nudge to the relevant Channels groups. Carries
NO content — clients refetch via REST. Safe no-op if no channel layer."""
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

#: Group every signed-in portal user joins — platform-wide notices land here.
NOTICE_GROUP_ALL = 'notices'


def notice_group_for_company(company_id):
    return f'notices-co-{company_id}'


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


def notify_notice(notice, event):
    """Nudge whoever a notice applies to, so a banner appears (or clears)
    without a reload — during an incident nobody thinks to refresh.

    Carries no message text, matching notify_ticket: the client refetches
    through /api/notices/, which is where tenant scoping is enforced. Putting
    the body on the wire would route around that.

    Fan-out mirrors SiteNotice.for_user: a scoped notice goes only to the
    companies it names, an unscoped one to everybody. The arrival of even a
    content-free nudge signals that something happened, so scoping has to hold
    here too and not just in REST.
    """
    layer = get_channel_layer()
    if layer is None:
        return
    payload = {'type': 'notice.changed', 'event': event}
    company_ids = list(notice.companies.values_list('id', flat=True))
    if company_ids:
        for company_id in company_ids:
            async_to_sync(layer.group_send)(notice_group_for_company(company_id), payload)
    else:
        async_to_sync(layer.group_send)(NOTICE_GROUP_ALL, payload)
