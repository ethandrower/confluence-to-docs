from django.contrib import admin
from .models import DocPage, DocImage, PortalUser, MagicLinkToken, ContactSubmission


@admin.register(DocPage)
class DocPageAdmin(admin.ModelAdmin):
    list_display = ['title', 'slug', 'confluence_version', 'last_synced', 'is_published']
    list_filter = ['is_published', 'space_key']
    search_fields = ['title', 'slug']
    readonly_fields = ['confluence_id', 'confluence_version', 'last_synced', 'raw_storage', 'search_vector']
    actions = ['force_resync', 'unpublish', 'publish']

    def force_resync(self, request, queryset):
        from .tasks import sync_page
        for page in queryset:
            sync_page.delay(page.confluence_id)
    force_resync.short_description = 'Force re-sync from Confluence'

    def unpublish(self, request, queryset):
        queryset.update(is_published=False)
    unpublish.short_description = 'Unpublish selected pages'

    def publish(self, request, queryset):
        queryset.update(is_published=True)
    publish.short_description = 'Publish selected pages'


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
