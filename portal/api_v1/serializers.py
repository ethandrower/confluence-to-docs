"""Output allowlists for /api/v1/.

These are plain `serializers.Serializer` classes, not ModelSerializers, and
that is a security decision rather than a stylistic one: a ModelSerializer's
field set follows the model, so a column added to Ticket next month would start
appearing in a cross-tenant payload with nobody deciding that it should. Here
every field is named, and anything unnamed is absent by construction.

Never add here: `TicketMessage.body` (customer conversation text), anything
derived from an `is_internal` message (staff-private notes), `Ticket.watchers`
(internal staff), or JiraTicketLink keys (internal by the model's own
docstring). If a consumer ever needs message bodies that is a deliberate
follow-up with its own argument, not a default.
"""
from rest_framework import serializers

from portal.models import Ticket

# This file was written against a Ticket that had no requester/assignee yet
# and probed for them at import time. Those fields landed with the ticket
# assignment work, so the probing is gone — but the ORDER it encoded is kept
# in get_requester_email below, because that part was a real decision.


class TicketCountsSerializer(serializers.Serializer):
    open = serializers.IntegerField()
    total = serializers.IntegerField()


class CompanySerializer(serializers.Serializer):
    """Discovery payload: enough for an operator to match this company against
    a RevenueHub Account once and store the id."""

    id = serializers.IntegerField(read_only=True)
    name = serializers.CharField(read_only=True)
    contract_end_date = serializers.DateField(read_only=True, allow_null=True)
    ticket_counts = serializers.SerializerMethodField()
    last_ticket_at = serializers.DateTimeField(read_only=True, allow_null=True)
    user_email_domains = serializers.SerializerMethodField()

    @staticmethod
    def get_ticket_counts(obj) -> dict:
        # Annotated by the view. "open" is the portal's own reading of open —
        # anything not resolved and not closed — and is the only place this API
        # collapses its vocabulary, because a count has to pick a line.
        return {
            'open': getattr(obj, 'open_ticket_count', 0) or 0,
            'total': getattr(obj, 'total_ticket_count', 0) or 0,
        }

    @staticmethod
    def get_user_email_domains(obj) -> list:
        """Evidence for the one-time account match, sorted, most-common first.

        `Company` has only a unique name, so a consumer matching its own
        accounts against this list has nothing but the name to go on — and
        names genuinely collide (two "Abiomed" rows is a real thing in
        RevenueHub today). The domains of a company's own portal users
        disambiguate that without anyone having to enter and maintain a
        `domain` field on every customer: this is derived from data that
        already exists and is already correct.

        Domains ONLY, never addresses. Which company a domain belongs to is
        the fact being established; who works there is not, and this endpoint
        has no business publishing a customer's staff list.

        Staff domains are excluded — our own people are attached to companies
        as agents on on-behalf tickets, and 'citemed.com' appearing under
        every customer would be noise that matches everything.
        """
        from django.conf import settings

        staff = {d.lower() for d in getattr(settings, 'STAFF_EMAIL_DOMAINS', [])}
        counts = {}
        for user in obj.users.all():
            if not user.email or '@' not in user.email:
                continue
            domain = user.email.rsplit('@', 1)[1].lower()
            if domain in staff:
                continue
            counts[domain] = counts.get(domain, 0) + 1
        return [d for d, _ in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))]


class TicketCompanySerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    name = serializers.CharField(read_only=True)


class TicketSerializer(serializers.Serializer):
    """Ticket metadata and counts. Deliberately no conversation content.

    `status` and `priority` are returned in the PORTAL's vocabulary, unmapped
    (statuses: open / waiting_on_customer / waiting_on_support / resolved /
    closed; priorities: urgent / high / standard / csm_direct). Baking a
    consumer's smaller enum into the producer would make the next consumer
    inherit the first one's lossy model, so the mapping belongs on ingest.
    Note `csm_direct` is a routing origin rather than a severity, so it has no
    clean severity equivalent downstream.
    """

    id = serializers.IntegerField(read_only=True)
    # The stable, human-quotable identifier — this is what a consumer should
    # store as its foreign key, not `id`.
    number = serializers.IntegerField(read_only=True)
    display_number = serializers.CharField(read_only=True)
    company = TicketCompanySerializer(read_only=True)
    subject = serializers.CharField(read_only=True)
    status = serializers.CharField(read_only=True)
    priority = serializers.CharField(read_only=True)
    category = serializers.CharField(read_only=True)
    requester_email = serializers.SerializerMethodField()
    assignee_email = serializers.SerializerMethodField()
    url = serializers.SerializerMethodField()
    # A count, never the messages. Internal notes are excluded from it as well
    # as from the payload: a count that moved when staff added a private note
    # would leak the fact (and the timing) of internal discussion.
    message_count = serializers.IntegerField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)
    updated_at = serializers.DateTimeField(read_only=True)
    last_message_at = serializers.DateTimeField(read_only=True, allow_null=True)

    @staticmethod
    def get_requester_email(obj) -> str:
        """Who the ticket is FOR, which is not always who opened it.

        Three sources in descending order of directness: the address a staff
        on-behalf ticket names, the linked PortalUser, then whoever opened it.
        The last is the common case — a customer filing their own ticket is
        both requester and creator.
        """
        if obj.requester_email:
            return obj.requester_email
        if obj.requester_id:
            return obj.requester.email
        return obj.created_by.email if obj.created_by_id else ''

    @staticmethod
    def get_assignee_email(obj) -> str:
        """Empty string, not null: unassigned is a real state and RevenueHub
        shouldn't have to distinguish "nobody owns this" from "field absent"."""
        return obj.assignee.email if obj.assignee_id else ''

    @staticmethod
    def get_url(obj) -> str:
        """Deep link into the STAFF view of this ticket.

        Consumers of this API are internal CS tools, so the useful destination
        is the agent's ticket page, not the customer's. Without it a CSM
        looking at a mirrored ticket has to retype "CS-5" into the portal's
        search to get back to the thing they're reading about.

        Built from FRONTEND_URL (the origin people actually type) rather than
        the request Host, which behind the dev proxy is an internal service
        name. Empty string when FRONTEND_URL is unset, so a misconfigured
        deployment yields no link rather than a broken one.
        """
        from portal.views.tickets_admin import _portal_ticket_url
        return _portal_ticket_url(obj)


class ShareItemSerializer(serializers.Serializer):
    """The one file or link a push named, when it named one."""

    id = serializers.IntegerField(read_only=True)
    name = serializers.CharField(source='original_name', read_only=True)
    # 'file' or 'link'. A link's target URL is deliberately NOT here: it points
    # at something outside the portal, a health dashboard has no use for it,
    # and this namespace crosses the tenant boundary — so it stays out on the
    # same principle that keeps message bodies out.
    item_type = serializers.CharField(read_only=True)


class ShareFolderSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    title = serializers.CharField(read_only=True)


class ShareEventSerializer(serializers.Serializer):
    """One (push, person) pair: something staff sent a customer, and what
    became of it.

    This is the finest grain the portal records, and it stays that way rather
    than being pre-aggregated per push. "Two of the four people we sent this to
    have opened it" is a fact a consumer can compute from these rows; it is not
    one it could recover from a summary that had already collapsed them.

    Titles and filenames appear here because staff wrote them when pushing —
    they are our own outbound material, not customer content. The recipient's
    address appears on the same footing as `requester_email` on a ticket: it
    names the participant in one interaction. That is a different question from
    CompanySerializer's, which deliberately publishes email DOMAINS only,
    because a discovery endpoint listing every customer's whole staff roster is
    a roster leak — one interaction is not.
    """

    id = serializers.IntegerField(read_only=True)
    company = TicketCompanySerializer(source='bucket.company', read_only=True)
    folder = ShareFolderSerializer(source='bucket', read_only=True)
    # Null when the whole folder was pushed rather than one item in it. That
    # distinction is the payload's own: a folder push means "here is everything
    # in here", and it stays true as staff add to it afterwards.
    item = ShareItemSerializer(read_only=True, source='file', allow_null=True)

    sent_by_email = serializers.SerializerMethodField()
    recipient_email = serializers.CharField(source='recipient.email', read_only=True)

    sent_at = serializers.DateTimeField(read_only=True)
    # When an email for this row last actually reached the recipient. Null
    # means the push is recorded but nothing was sent — the per-recipient rate
    # limit held it because they had already heard about this folder today.
    # Worth publishing rather than inferring from sent_at: a row that has sat
    # unopened for a week reads very differently once you know whether anyone
    # ever told them, and a consumer scoring engagement would otherwise count
    # an email we never sent as one they ignored.
    last_email_at = serializers.DateTimeField(read_only=True, allow_null=True)
    first_opened_at = serializers.DateTimeField(read_only=True, allow_null=True)
    # Derivable from first_opened_at, and included anyway: every consumer of
    # this endpoint wants the boolean, and each one deriving it separately is
    # each one getting a chance to derive it differently.
    opened = serializers.BooleanField(read_only=True)

    reminder_count = serializers.IntegerField(read_only=True)
    last_reminder_at = serializers.DateTimeField(read_only=True, allow_null=True)
    # Whether the nudge loop is still armed. False means nobody will chase this
    # automatically again — either staff switched it off at push time or both
    # nudges are spent — which is exactly when a health dashboard should start
    # caring that it is still unopened.
    remind = serializers.BooleanField(read_only=True)

    updated_at = serializers.DateTimeField(read_only=True)

    # No `url`, unlike TicketSerializer, and not by oversight: the admin files
    # view is a tab held in local component state inside /manage, so there is
    # no address that opens one company's folders. Any link built here would
    # be guessed, and a guessed link that lands on the users tab — or on the
    # SPA's catch-all — is worse than none. Making that tab deep-linkable is
    # the prerequisite, and it belongs with the frontend, not here.

    @staticmethod
    def get_sent_by_email(obj) -> str:
        """The staff member who pushed it. Empty string when the account has
        since been deleted (`sent_by` is SET_NULL), on the same reasoning as
        `assignee_email`: a consumer should not have to tell "no longer with
        us" apart from "field absent"."""
        return obj.sent_by.email if obj.sent_by_id else ''
