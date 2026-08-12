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


def notify_notice(notice, event, also_companies=None):
    """Nudge whoever a notice applies to, so a banner appears (or clears)
    without a reload — during an incident nobody thinks to refresh.

    Carries no message text, matching notify_ticket: the client refetches
    through /api/notices/, which is where tenant scoping is enforced. Putting
    the body on the wire would route around that.

    Fan-out mirrors SiteNotice.for_user: a scoped notice goes only to the
    companies it names, an unscoped one to everybody. The arrival of even a
    content-free nudge signals that something happened, so scoping has to hold
    here too and not just in REST.

    `also_companies` covers an edit that CHANGED the scope. Nudging only where a
    notice now applies leaves the audience it was withdrawn from still showing a
    banner that no longer concerns them, so the caller passes the previous scope
    and both sides are told.

    None (the default) means "there is no previous scope" — a create or a
    retire. An empty LIST is different: it means the notice was platform-wide
    before this edit, so the far side is everyone. Collapsing those two is how
    an earlier version of this leaked every newly-created scoped notice to the
    global group; the tenant-scoping test caught it.
    """
    layer = get_channel_layer()
    if layer is None:
        return
    payload = {'type': 'notice.changed', 'event': event}

    scopes = [set(notice.companies.values_list('id', flat=True))]
    if also_companies is not None:
        scopes.append(set(also_companies))

    groups = set()
    for scope in scopes:
        if scope:
            groups.update(notice_group_for_company(cid) for cid in scope)
        else:
            groups.add(NOTICE_GROUP_ALL)

    for group in groups:
        async_to_sync(layer.group_send)(group, payload)
