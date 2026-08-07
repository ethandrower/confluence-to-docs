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

# `requester`/`requester_email`/`assignee` are being added to Ticket on a
# separate branch (ticket assignment). The API contract promises those fields
# now, so they are resolved defensively: RevenueHub's payload shape does not
# change when that branch lands, it just starts carrying better data.
_TICKET_FIELDS = {f.name for f in Ticket._meta.get_fields()}
HAS_REQUESTER_EMAIL = 'requester_email' in _TICKET_FIELDS
HAS_REQUESTER = 'requester' in _TICKET_FIELDS
HAS_ASSIGNEE = 'assignee' in _TICKET_FIELDS


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

    @staticmethod
    def get_ticket_counts(obj) -> dict:
        # Annotated by the view. "open" is the portal's own reading of open —
        # anything not resolved and not closed — and is the only place this API
        # collapses its vocabulary, because a count has to pick a line.
        return {
            'open': getattr(obj, 'open_ticket_count', 0) or 0,
            'total': getattr(obj, 'total_ticket_count', 0) or 0,
        }


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
    # A count, never the messages. Internal notes are excluded from it as well
    # as from the payload: a count that moved when staff added a private note
    # would leak the fact (and the timing) of internal discussion.
    message_count = serializers.IntegerField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)
    updated_at = serializers.DateTimeField(read_only=True)
    last_message_at = serializers.DateTimeField(read_only=True, allow_null=True)

    @staticmethod
    def get_requester_email(obj) -> str:
        if HAS_REQUESTER_EMAIL:
            email = getattr(obj, 'requester_email', '')
            if email:
                return email
        if HAS_REQUESTER:
            requester = getattr(obj, 'requester', None)
            if requester is not None:
                return requester.email
        # Pre-assignment-branch fallback: whoever opened it is the requester.
        return obj.created_by.email if obj.created_by_id else ''

    @staticmethod
    def get_assignee_email(obj) -> str:
        if HAS_ASSIGNEE:
            assignee = getattr(obj, 'assignee', None)
            if assignee is not None:
                return assignee.email
        return ''
