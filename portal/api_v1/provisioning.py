"""The ONE write surface on /api/v1/ — company and user provisioning.

Deliberately its own module, mounted under its own `/api/v1/provisioning/`
prefix, rather than POST handlers bolted onto the read views. `views.py`
promises in its first paragraph that every view in it is a read-only generic
with no unsafe verb available to add by accident; that promise is worth more
than REST tidiness, so the writes live here where they are impossible to miss
and can be reviewed as one unit.

WHY THIS EXISTS. RevenueHub owns the customer relationship and already holds the
roster — who works for the customer, their email, and what they will do in the
product — captured during handover. Re-typing that roster into the portal by
hand is the CONFIG step of every activation, and hand-typing an email address is
how somebody ends up unable to log in on day one.

THREE PROPERTIES THIS API GUARANTEES, because the caller depends on all three:

  1. UPSERT, NEVER PLAIN CREATE. `Company.name` and `PortalUser.email` are both
     unique, and the caller's sync is at-least-once by design. A create-only
     endpoint would make re-running provisioning unsafe, which is the same as
     not being able to run it twice — so a repeat is a 200 with the existing
     row, never a 409, and never a duplicate.

  2. NOTHING IS SENT. Creating a PortalUser writes a row and does nothing else:
     the model has no save() override and no post_save receiver (the only one in
     portal/models.py is on DocPage), and a magic link is a separate, explicit
     act. Provisioning eight people the week before kickoff must not put eight
     emails in front of a customer who has not been introduced yet. There is a
     test asserting the mailbox stays empty.

  3. A USER IS NEVER SILENTLY MOVED BETWEEN COMPANIES. `PortalUser.email` is
     unique GLOBALLY, not per company, so an address already registered to
     another customer is a genuine conflict — one person cannot see two
     companies' tickets. That is a 409 for a human to resolve, not something to
     paper over by reassigning the FK.

WRITES ARE A SEPARATE CAPABILITY. `IsApiClient` is not enough here: the existing
read token would otherwise gain the ability to create users the moment this file
shipped. `CanProvision` additionally requires `ApiClient.can_provision`, which
is off by default and granted per client.

CSRF does not apply: the only authenticator is the bearer token, and DRF
enforces CSRF for SessionAuthentication alone. There is no cookie path in here.
"""
import logging

from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status
from rest_framework.generics import GenericAPIView
from rest_framework.response import Response

from portal.models import Company, PortalUser

from .auth import ApiClientAuthentication, CanProvision

log = logging.getLogger(__name__)


class ProvisioningApiV1View(GenericAPIView):
    """Shared policy for the write endpoints.

    `authentication_classes` is pinned for the same reason the read views pin
    it: so that no future change to the project's DRF defaults can quietly give
    this namespace a session-shaped second door.
    """

    authentication_classes = [ApiClientAuthentication]
    permission_classes = [CanProvision]
    http_method_names = ['get', 'post', 'head', 'options']


# --- input allowlists ---------------------------------------------------------
#
# Plain Serializers, not ModelSerializers, for the same reason serializers.py
# gives for the output side: a ModelSerializer's field set follows the model, so
# a column added to PortalUser next month would become remotely settable without
# anyone deciding that it should. `is_demo` is exactly that hazard — it lets an
# account sign in WITHOUT a magic link, and it must never be reachable from here.


class CompanyInSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=256, trim_whitespace=True)
    contract_end_date = serializers.DateField(required=False, allow_null=True)


class CompanyOutSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    name = serializers.CharField(read_only=True)
    contract_end_date = serializers.DateField(read_only=True, allow_null=True)
    created_at = serializers.DateTimeField(read_only=True)


class PortalUserInSerializer(serializers.Serializer):
    email = serializers.EmailField()
    name = serializers.CharField(max_length=256, required=False, allow_blank=True,
                                 trim_whitespace=True)
    # Constrained to the model's own choices rather than a copy of the list, so
    # a new role cannot be accepted here before the model knows about it.
    role = serializers.ChoiceField(choices=PortalUser.ROLE_CHOICES,
                                   default=PortalUser.ROLE_CUSTOMER)
    access_enabled = serializers.BooleanField(default=True)

    def validate_email(self, value):
        # Stored lowercase so the unique index actually prevents the duplicate a
        # caller would create by sending the same address differently cased.
        return value.strip().lower()


class PortalUserOutSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    email = serializers.CharField(read_only=True)
    name = serializers.CharField(read_only=True)
    role = serializers.CharField(read_only=True)
    company_id = serializers.IntegerField(read_only=True, allow_null=True)
    access_enabled = serializers.BooleanField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)
    last_login = serializers.DateTimeField(read_only=True, allow_null=True)


# --- endpoints ----------------------------------------------------------------


class CompanyProvisionView(ProvisioningApiV1View):
    """POST /api/v1/provisioning/companies/ — create a company, or return it."""

    serializer_class = CompanyInSerializer

    @extend_schema(
        request=CompanyInSerializer,
        responses={200: CompanyOutSerializer, 201: CompanyOutSerializer},
        description='Upsert a company by name. 201 when created, 200 when it '
                    'already existed.',
    )
    def post(self, request):
        data = self.get_serializer(data=request.data)
        data.is_valid(raise_exception=True)
        payload = data.validated_data

        company = Company.objects.filter(name=payload['name']).first()
        if company is None:
            company = Company.objects.create(
                name=payload['name'],
                contract_end_date=payload.get('contract_end_date'),
            )
            log.info('api_v1 provisioning: created company %s (%s) for client %s',
                     company.pk, company.name, request.auth)
            code = status.HTTP_201_CREATED
        else:
            # Only touched when the caller actually sent one: the contract date
            # comes from the system that holds the contract, but a caller that
            # omits it is saying nothing about it, not saying "clear it".
            if 'contract_end_date' in payload:
                if company.contract_end_date != payload['contract_end_date']:
                    company.contract_end_date = payload['contract_end_date']
                    company.save(update_fields=['contract_end_date'])
            code = status.HTTP_200_OK

        return Response(CompanyOutSerializer(company).data, status=code)


class CompanyUserProvisionView(ProvisioningApiV1View):
    """/api/v1/provisioning/companies/<id>/users/ — list, and upsert by email.

    The GET is here rather than on the read side because it exists to serve this
    endpoint: a caller reconciling its roster needs to see what is already there
    before deciding what to send, and that read is part of provisioning rather
    than part of the cross-customer dashboard the read API is for.
    """

    serializer_class = PortalUserInSerializer

    def _company(self, company_id):
        return get_object_or_404(Company, pk=company_id)

    @extend_schema(responses={200: PortalUserOutSerializer(many=True)},
                   description="Every portal user attached to this company.")
    def get(self, request, company_id):
        company = self._company(company_id)
        users = company.users.order_by('email')
        return Response(PortalUserOutSerializer(users, many=True).data)

    @extend_schema(
        request=PortalUserInSerializer,
        responses={200: PortalUserOutSerializer, 201: PortalUserOutSerializer,
                   409: None},
        description='Upsert a user by email within this company. 201 when '
                    'created, 200 when it already existed, 409 when the address '
                    'belongs to a different company.',
    )
    def post(self, request, company_id):
        company = self._company(company_id)
        data = self.get_serializer(data=request.data)
        data.is_valid(raise_exception=True)
        payload = data.validated_data

        user = PortalUser.objects.filter(email=payload['email']).first()

        if user is None:
            user = PortalUser.objects.create(
                email=payload['email'], name=payload.get('name', ''),
                role=payload['role'], company=company,
                access_enabled=payload['access_enabled'],
            )
            log.info('api_v1 provisioning: created user %s (%s) on company %s '
                     'for client %s', user.pk, user.email, company.pk, request.auth)
            return Response(PortalUserOutSerializer(user).data,
                            status=status.HTTP_201_CREATED)

        if user.company_id is not None and user.company_id != company.pk:
            # One address cannot belong to two customers: whichever company it
            # ends up on, that person can read that company's tickets. Reassigning
            # silently would move somebody's access on the strength of a typo.
            return Response(
                {'detail': f'{user.email} is already registered to company '
                           f'{user.company_id}. Move or remove that user first.'},
                status=status.HTTP_409_CONFLICT)

        # Same company (or previously unattached): bring the row up to date. This
        # is the path a re-run takes, and the path that re-enables somebody who
        # was offboarded and has come back.
        user.company = company
        user.name = payload.get('name', '') or user.name
        user.role = payload['role']
        user.access_enabled = payload['access_enabled']
        user.save(update_fields=['company', 'name', 'role', 'access_enabled'])
        return Response(PortalUserOutSerializer(user).data, status=status.HTTP_200_OK)
