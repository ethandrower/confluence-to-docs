from django.urls import path
from portal.views import docs, auth, tickets

urlpatterns = [
    # Docs
    path('docs/', docs.page_tree, name='page-tree'),
    path('docs/search/', docs.search_docs, name='search-docs'),
    path('docs/<slug:slug>/', docs.page_detail, name='page-detail'),

    # Auth
    path('auth/request-magic-link/', auth.request_magic_link, name='request-magic-link'),
    path('auth/verify/', auth.verify_magic_link, name='verify-magic-link'),
    path('auth/me/', auth.me, name='auth-me'),
    path('auth/logout/', auth.logout, name='auth-logout'),

    # Tickets
    path('tickets/', tickets.tickets, name='tickets'),
    path('tickets/request-types/', tickets.request_types, name='request-types'),
    path('tickets/<str:ticket_id>/', tickets.ticket_detail, name='ticket-detail'),
]
