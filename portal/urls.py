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
    path('tickets/submit/', tickets.submit_ticket, name='submit-ticket'),
]
