from django.urls import path
from portal.views import docs, auth, tickets, admin_api, files, files_admin

urlpatterns = [
    # Admin (manage users + companies) — gated to portal admins
    path('admin/companies/', admin_api.companies, name='admin-companies'),
    path('admin/companies/<int:company_id>/', admin_api.company_detail, name='admin-company-detail'),
    path('admin/users/', admin_api.users, name='admin-users'),
    path('admin/users/<int:user_id>/', admin_api.user_detail, name='admin-user-detail'),
    path('admin/sync/', admin_api.sync_docs, name='admin-sync'),
    path('admin/add-page/', admin_api.add_page, name='admin-add-page'),

    # Admin — file sharing
    path('admin/files/inbox/', files_admin.inbox, name='admin-files-inbox'),
    path('admin/files/activity/', files_admin.activity, name='admin-files-activity'),
    path('admin/files/<int:file_id>/processed', files_admin.set_processed, name='admin-files-processed'),
    path('admin/files/companies/', files_admin.companies, name='admin-files-companies'),
    path('admin/files/companies/<int:company_id>/', files_admin.company_files, name='admin-files-company'),
    path('admin/files/companies/<int:company_id>/download-all', files_admin.company_download_all, name='admin-files-zip'),
    path('admin/files/requests/', files_admin.create_request, name='admin-files-create-request'),
    path('admin/files/requests/<int:bucket_id>/', files_admin.update_request, name='admin-files-update-request'),
    path('admin/files/<int:file_id>/review', files_admin.set_review, name='admin-files-review'),
    path('admin/files/checklist/', files_admin.create_checklist_item, name='admin-files-checklist-create'),
    path('admin/files/checklist/<int:item_id>/', files_admin.checklist_item, name='admin-files-checklist-item'),
    path('admin/files/<int:file_id>/download', files_admin.admin_file_download, name='admin-files-download'),
    path('admin/files/<int:file_id>/view', files_admin.admin_file_view, name='admin-files-view'),

    # File sharing (customer + shared)
    path('files/buckets/', files.buckets_list, name='files-buckets'),
    path('files/upload-init', files.upload_init, name='files-upload-init'),
    path('files/upload-complete', files.upload_complete, name='files-upload-complete'),
    path('files/<int:file_id>', files.file_detail, name='files-file'),
    path('files/<int:file_id>/download', files.file_download, name='files-download'),
    path('files/<int:file_id>/view', files.file_view, name='files-view'),

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
