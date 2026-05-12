import subprocess
import sys
from pathlib import Path

from django.contrib import admin, messages
from django.http import HttpResponseRedirect
from django.urls import path, reverse

from .models import DocPage, DocImage, PortalUser, MagicLinkToken, ContactSubmission


@admin.register(DocPage)
class DocPageAdmin(admin.ModelAdmin):
    list_display = ['title', 'slug', 'confluence_version', 'last_synced', 'is_published']
    list_filter = ['is_published', 'space_key']
    search_fields = ['title', 'slug']
    readonly_fields = ['confluence_id', 'confluence_version', 'last_synced', 'raw_storage', 'search_vector']
    actions = ['unpublish', 'publish']
    change_list_template = 'admin/portal/docpage/change_list.html'

    def unpublish(self, request, queryset):
        queryset.update(is_published=False)
    unpublish.short_description = 'Unpublish selected pages'

    def publish(self, request, queryset):
        queryset.update(is_published=True)
    publish.short_description = 'Publish selected pages'

    # ---- Custom admin views: "Sync from Confluence" button -----------------
    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path(
                'sync-confluence/',
                self.admin_site.admin_view(self.sync_confluence_view),
                name='portal_docpage_sync_confluence',
            ),
        ]
        return custom + urls

    def sync_confluence_view(self, request):
        """
        Kick off `manage.py sync_from_mcp` as a detached background process.
        Returns immediately — sync runs to completion in the background and
        logs to Dokku's stdout. We don't block the admin request because a
        full sync can take minutes.
        """
        try:
            # Use sys.executable so we run inside the same venv as Django.
            # cwd = repo root (BASE_DIR is the parent of this app's dir).
            repo_root = Path(__file__).resolve().parent.parent
            subprocess.Popen(
                [sys.executable, 'manage.py', 'sync_from_mcp'],
                cwd=str(repo_root),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            messages.success(
                request,
                'Confluence sync started in the background. '
                'Refresh this page in a few minutes — page rows will update as the sync progresses.',
            )
        except Exception as e:
            messages.error(request, f'Failed to start sync: {e}')

        return HttpResponseRedirect(reverse('admin:portal_docpage_changelist'))


@admin.register(DocImage)
class DocImageAdmin(admin.ModelAdmin):
    list_display = ['original_filename', 'page', 'content_type', 'local_path']
    search_fields = ['original_filename']


@admin.register(PortalUser)
class PortalUserAdmin(admin.ModelAdmin):
    list_display = ['email', 'name', 'is_jsm_customer', 'created_at', 'last_login']
    list_filter = ['is_jsm_customer']
    search_fields = ['email', 'name']
    readonly_fields = ['created_at', 'last_login', 'jsm_checked_at']


@admin.register(MagicLinkToken)
class MagicLinkTokenAdmin(admin.ModelAdmin):
    list_display = ['user', 'created_at', 'expires_at', 'used']
    list_filter = ['used']
    readonly_fields = ['token', 'created_at']


@admin.register(ContactSubmission)
class ContactSubmissionAdmin(admin.ModelAdmin):
    list_display = ['created_at', 'email', 'category', 'subject', 'status']
    list_filter = ['status', 'category', 'created_at']
    search_fields = ['email', 'name', 'subject', 'message']
    readonly_fields = ['name', 'email', 'category', 'subject', 'message', 'ip_address', 'created_at', 'sent_at', 'status', 'error']
