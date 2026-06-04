from django.urls import path
from portal.views import docs, auth, tickets, admin_api

urlpatterns = [
    # Admin (manage users + companies) — gated to portal admins
    path('admin/companies/', admin_api.companies, name='admin-companies'),
    path('admin/companies/<int:company_id>/', admin_api.company_detail, name='admin-company-detail'),
    path('admin/users/', admin_api.users, name='admin-users'),
    path('admin/users/<int:user_id>/', admin_api.user_detail, name='admin-user-detail'),
    path('admin/sync/', admin_api.sync_docs, name='admin-sync'),

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
