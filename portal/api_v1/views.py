"""Read-only views for /api/v1/.

Every view here is a DRF read-only generic (`ListAPIView` / `RetrieveAPIView`)
with `http_method_names` narrowed to safe verbs. Not a ViewSet: a router-driven
`ModelViewSet` is one `mixins` line away from a write path, and this namespace
must not have one available to add by accident.

These querysets use `Ticket.objects` directly, bypassing `Ticket.for_user`.
That is intentional and is the reason this namespace exists — RevenueHub is a
cross-customer dashboard — but it means the ONLY thing standing between this
data and the internet is the bearer token in `auth.py`. Treat any change here
as security-relevant.
"""
import datetime
import re

from django.db.models import Count, Max, Q, TextField
from django.db.models.functions import Cast
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import generics
from rest_framework.exceptions import ValidationError

from portal.models import Company, Ticket

from .auth import ApiClientAuthentication, IsApiClient
from .pagination import CompanyCursorPagination, TicketCursorPagination
from .serializers import CompanySerializer, TicketSerializer

# Statuses the portal considers still in play. Used only for the discovery
# endpoint's `open` count — the ticket payload itself returns the portal's
# five-status vocabulary unmapped.
OPEN_STATUSES = (
    Ticket.STATUS_OPEN,
    Ticket.STATUS_WAITING_ON_CUSTOMER,
    Ticket.STATUS_WAITING_ON_SUPPORT,
)

VALID_STATUSES = {value for value, _ in Ticket.STATUS_CHOICES}
VALID_PRIORITIES = {value for value, _ in Ticket.PRIORITY_CHOICES}


class ReadOnlyApiV1View:
    """Shared policy for the data endpoints. Mixed into every view below.

    `authentication_classes` is set explicitly rather than inherited from
    `REST_FRAMEWORK['DEFAULT_AUTHENTICATION_CLASSES']` (which is
    SessionAuthentication) so that no future change to the project default can
    quietly give this namespace a second door.
    """

    authentication_classes = [ApiClientAuthentication]
    permission_classes = [IsApiClient]
    http_method_names = ['get', 'head', 'options']


def _parse_since(raw, param):
    """Parse an ISO-8601 datetime (or bare date) into an aware datetime."""
    value = parse_datetime(raw)
    if value is None:
        # A '+' in an unencoded query string arrives as a space, so a correctly
        # formatted '...T00:00:00+02:00' reaches us as '...T00:00:00 02:00'.
        # Repairing that one specific shape is friendlier than answering 400 to
        # a caller whose timestamp was in fact valid — and it can't rescue any
        # other malformed input, because the whole parse has to have failed
        # first.
        repaired = re.sub(r' (\d{2}:\d{2})$', r'+\1', raw)
        value = parse_datetime(repaired) if repaired != raw else None
    if value is None:
        as_date = parse_date(raw)
        if as_date is None:
            raise ValidationError(
                {param: 'Expected an ISO-8601 datetime, e.g. 2026-08-06T14:02:11Z.'})
        value = datetime.datetime(as_date.year, as_date.month, as_date.day)
    if timezone.is_naive(value):
        # Naive input is read as UTC, which is what the portal stores.
        value = timezone.make_aware(value, datetime.timezone.utc)
    return value


def _parse_ids(raw_values, param):
    ids = []
    for raw in raw_values:
        try:
            ids.append(int(raw))
        except (TypeError, ValueError):
            raise ValidationError({param: f'Expected an integer, got {raw!r}.'})
    return ids


def _parse_choices(raw_values, allowed, param):
    unknown = [v for v in raw_values if v not in allowed]
    if unknown:
        raise ValidationError({
            param: f'Unknown value(s): {", ".join(sorted(unknown))}. '
                   f'Allowed: {", ".join(sorted(allowed))}.'
        })
    return list(raw_values)


def _parse_bool(raw, param):
    if raw is None:
        return False
    lowered = str(raw).strip().lower()
    if lowered in ('1', 'true', 'yes'):
        return True
    if lowered in ('', '0', 'false', 'no'):
        return False
    raise ValidationError({param: 'Expected true or false.'})


TICKET_PARAMS = [
    OpenApiParameter(
        'company_id', OpenApiTypes.INT, many=True,
        description='Repeatable. Portal Company id.'),
    OpenApiParameter(
        'email', OpenApiTypes.STR,
        description='Match the ticket requester or its creator. Add '
                    'include_cc=true to widen to CC\'d addresses.'),
    OpenApiParameter(
        'include_cc', OpenApiTypes.BOOL,
        description='Widen the `email` filter to cc_emails. Default false: '
                    'being copied on a colleague\'s ticket is not the same as '
                    'having raised one.'),
    OpenApiParameter(
        'status', OpenApiTypes.STR, many=True, enum=sorted(VALID_STATUSES),
        description='Repeatable. Portal vocabulary, returned unmapped.'),
    OpenApiParameter(
        'priority', OpenApiTypes.STR, many=True, enum=sorted(VALID_PRIORITIES),
        description='Repeatable. Portal vocabulary, returned unmapped.'),
    OpenApiParameter(
        'created_since', OpenApiTypes.DATETIME,
        description='ISO-8601. Tickets created strictly after this instant.'),
    OpenApiParameter(
        'updated_since', OpenApiTypes.DATETIME,
        description='ISO-8601. Tickets updated strictly after this instant — '
                    'the incremental-sync filter.'),
]


class TicketQuerysetMixin:
    """The one place a ticket queryset is built for this API."""

    def base_queryset(self):
        # Counts exclude internal notes, so neither the count nor
        # `last_message_at` can betray staff-private discussion. distinct=True
        # keeps the two aggregates from inflating each other's join.
        customer_visible = Q(messages__is_internal=False)
        return (
            Ticket.objects
            .select_related('company', 'created_by')
            .annotate(
                message_count=Count('messages', filter=customer_visible, distinct=True),
                last_message_at=Max('messages__created_at', filter=customer_visible),
            )
        )

    def apply_filters(self, queryset):
        params = self.request.query_params

        company_ids = _parse_ids(params.getlist('company_id'), 'company_id')
        if company_ids:
            queryset = queryset.filter(company_id__in=company_ids)

        statuses = _parse_choices(params.getlist('status'), VALID_STATUSES, 'status')
        if statuses:
            queryset = queryset.filter(status__in=statuses)

        priorities = _parse_choices(
            params.getlist('priority'), VALID_PRIORITIES, 'priority')
        if priorities:
            queryset = queryset.filter(priority__in=priorities)

        created_since = params.get('created_since')
        if created_since:
            queryset = queryset.filter(
                created_at__gt=_parse_since(created_since, 'created_since'))

        updated_since = params.get('updated_since')
        if updated_since:
            queryset = queryset.filter(
                updated_at__gt=_parse_since(updated_since, 'updated_since'))

        email = (params.get('email') or '').strip()
        if email:
            queryset = self._filter_by_email(
                queryset, email, _parse_bool(params.get('include_cc'), 'include_cc'))

        return queryset

    @staticmethod
    def _filter_by_email(queryset, email, include_cc):
        """Requester-or-creator by default; CC only when asked for.

        "What has Jane raised?" is not answered by tickets Jane was copied on,
        so widening is opt-in rather than the silent default.
        """
        match = (
            Q(created_by__email__iexact=email)
            | Q(requester_email__iexact=email)
            | Q(requester__email__iexact=email)
        )

        if include_cc:
            # cc_emails is a JSON list. Cast to text and look for the address
            # WITH its surrounding JSON quotes, so "ana@x.com" cannot match an
            # entry for "joana@x.com" the way a bare substring search would.
            queryset = queryset.annotate(
                cc_text=Cast('cc_emails', output_field=TextField()))
            match |= Q(cc_text__icontains=f'"{email}"')

        return queryset.filter(match)


@extend_schema(
    parameters=TICKET_PARAMS,
    summary='List support tickets',
    description=(
        'Ticket metadata across all companies, ordered by `updated_at` '
        'ascending so that `updated_since` + `cursor` is a resumable, '
        'at-least-once incremental sync. Carries no conversation content: '
        '`message_count` counts customer-visible messages only, and no '
        'message body or internal note is ever returned.'
    ),
)
class TicketListView(ReadOnlyApiV1View, TicketQuerysetMixin, generics.ListAPIView):
    serializer_class = TicketSerializer
    pagination_class = TicketCursorPagination

    def get_queryset(self):
        return self.apply_filters(self.base_queryset())


@extend_schema(
    summary='Retrieve one support ticket',
    description='Keyed on `number` (the CS-N identifier), not the database id.',
)
class TicketDetailView(ReadOnlyApiV1View, TicketQuerysetMixin, generics.RetrieveAPIView):
    serializer_class = TicketSerializer
    lookup_field = 'number'
    lookup_url_kwarg = 'number'

    def get_queryset(self):
        return self.base_queryset()


@extend_schema(
    summary='List companies',
    description=(
        'Discovery endpoint. Exists so an operator can populate a consumer\'s '
        'account-id mapping once and never match on names again. `open` counts '
        'tickets that are neither resolved nor closed.'
    ),
)
class CompanyListView(ReadOnlyApiV1View, generics.ListAPIView):
    serializer_class = CompanySerializer
    pagination_class = CompanyCursorPagination

    def get_queryset(self):
        return Company.objects.annotate(
            total_ticket_count=Count('tickets', distinct=True),
            open_ticket_count=Count(
                'tickets', filter=Q(tickets__status__in=OPEN_STATUSES), distinct=True),
            last_ticket_at=Max('tickets__created_at'),
        ).prefetch_related('users')
