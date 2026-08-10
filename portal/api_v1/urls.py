"""URLconf for the read-only integration API.

Mounted at `/api/v1/` from citemed/urls.py, ahead of the session-authenticated
`/api/` include. Every route is a GET; there is no unsafe verb in this file,
which is why the CSRF sweep in test_auth_hardening.py has nothing to say about
it and why test_api_v1.py has to assert the token boundary itself.
"""
from django.urls import path

from .schema import GuardedSchemaView, GuardedSwaggerView
from .views import CompanyListView, TicketDetailView, TicketListView

app_name = 'api_v1'

urlpatterns = [
    path('companies/', CompanyListView.as_view(), name='companies'),
    path('tickets/', TicketListView.as_view(), name='tickets'),
    path('tickets/<int:number>/', TicketDetailView.as_view(), name='ticket-detail'),

    path('schema/', GuardedSchemaView.as_view(), name='schema'),
    path('docs/', GuardedSwaggerView.as_view(url_name='api_v1:schema'), name='docs'),
]
