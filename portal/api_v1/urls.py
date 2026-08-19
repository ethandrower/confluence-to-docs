"""URLconf for the integration API.

Mounted at `/api/v1/` from citemed/urls.py, ahead of the session-authenticated
`/api/` include.

Every route here was a GET until provisioning shipped. The unsafe verbs are now
confined to the `provisioning/` prefix and to `provisioning.py`, and they are
gated by `CanProvision` — a capability off by default — rather than by the read
token. Everything outside that prefix is still read-only and still asserts its
own token boundary in test_api_v1.py.

The CSRF sweep in test_auth_hardening.py still has nothing to say about this
file: it walks `portal.urls` for `portal.views` callables, and DRF enforces CSRF
only for SessionAuthentication, which nothing in this namespace uses.
"""
from django.urls import path

from .provisioning import CompanyProvisionView, CompanyUserProvisionView
from .schema import GuardedSchemaView, GuardedSwaggerView
from .views import CompanyListView, TicketDetailView, TicketListView

app_name = 'api_v1'

urlpatterns = [
    path('companies/', CompanyListView.as_view(), name='companies'),
    path('tickets/', TicketListView.as_view(), name='tickets'),
    path('tickets/<int:number>/', TicketDetailView.as_view(), name='ticket-detail'),

    # The write surface. See provisioning.py for why it is a separate prefix.
    path('provisioning/companies/', CompanyProvisionView.as_view(),
         name='provision-companies'),
    path('provisioning/companies/<int:company_id>/users/',
         CompanyUserProvisionView.as_view(), name='provision-company-users'),

    path('schema/', GuardedSchemaView.as_view(), name='schema'),
    path('docs/', GuardedSwaggerView.as_view(url_name='api_v1:schema'), name='docs'),
]
