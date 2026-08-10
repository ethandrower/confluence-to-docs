from rest_framework import serializers
from .models import DocPage, PortalUser, Bucket, SharedFile, ChecklistItem


class DocPageTreeSerializer(serializers.ModelSerializer):
    children = serializers.SerializerMethodField()

    class Meta:
        model = DocPage
        fields = ['id', 'confluence_id', 'title', 'slug', 'parent', 'children', 'position', 'is_folder', 'last_synced']

    def get_children(self, obj):
        # Drop excluded pages here too (not just top-level roots), so an
        # excluded page nested under a published parent doesn't slip through.
        from portal.views.docs import is_doc_excluded
        children = [
            c for c in obj.children.filter(is_published=True).order_by('position', 'title')
            if not is_doc_excluded(c.title)
        ]
        return DocPageTreeSerializer(children, many=True).data


class DocPageDetailSerializer(serializers.ModelSerializer):
    breadcrumbs = serializers.SerializerMethodField()
    siblings = serializers.SerializerMethodField()

    class Meta:
        model = DocPage
        fields = ['id', 'confluence_id', 'title', 'slug', 'rendered_html', 'breadcrumbs', 'siblings', 'last_synced', 'confluence_version']

    def get_breadcrumbs(self, obj):
        crumbs = []
        current = obj
        while current.parent:
            current = current.parent
            crumbs.insert(0, {'title': current.title, 'slug': current.slug})
        return crumbs

    def get_siblings(self, obj):
        if obj.parent:
            siblings = obj.parent.children.filter(is_published=True).exclude(pk=obj.pk)
        else:
            siblings = DocPage.objects.filter(parent__isnull=True, is_published=True).exclude(pk=obj.pk)
        return [{'title': s.title, 'slug': s.slug} for s in siblings[:5]]


class PortalUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = PortalUser
        fields = ['id', 'email', 'name']


class SharedFileSerializer(serializers.ModelSerializer):
    uploaded_by_name = serializers.SerializerMethodField()
    comment_count = serializers.SerializerMethodField()
    seen = serializers.SerializerMethodField()

    class Meta:
        model = SharedFile
        # No review_status / review_notes: the approve-or-reject loop is
        # retired (see the SharedFile docstring). A customer's file list is
        # now just their files.
        fields = [
            'id', 'original_name', 'size_bytes', 'mime_type', 'state',
            'uploaded_at', 'uploaded_by_name', 'comment_count', 'seen',
        ]

    def get_comment_count(self, obj):
        # Internal comments — only meaningful (and only counted) for staff.
        return obj.comments.count() if self.context.get('staff') else 0

    def get_uploaded_by_name(self, obj):
        u = obj.uploaded_by
        return (u.name or u.email) if u else None

    def get_seen(self, obj):
        """Staff-only: has anyone here looked at this yet. Absent for
        customers — whether we've opened their file is our business, and
        surfacing it would recreate the review badge we just removed."""
        if not self.context.get('staff'):
            return None
        return obj.processed


class ChecklistItemSerializer(serializers.ModelSerializer):
    linked_file_name = serializers.SerializerMethodField()

    class Meta:
        model = ChecklistItem
        fields = ['id', 'text', 'position', 'linked_file', 'linked_file_name']

    def get_linked_file_name(self, obj):
        return obj.linked_file.original_name if obj.linked_file else None


class BucketSerializer(serializers.ModelSerializer):
    files = serializers.SerializerMethodField()
    requested_by_name = serializers.SerializerMethodField()
    checklist = serializers.SerializerMethodField()

    class Meta:
        model = Bucket
        fields = [
            'id', 'kind', 'title', 'description', 'due_at', 'status',
            'requested_by_name', 'created_at', 'files', 'checklist',
            # The client builds the tree from a flat list — one request, and
            # re-parenting a folder doesn't invalidate a nested payload.
            'parent', 'required',
        ]

    def get_files(self, obj):
        qs = obj.files.filter(deleted_at__isnull=True, state=SharedFile.STATE_READY)
        return SharedFileSerializer(qs, many=True, context=self.context).data

    def get_requested_by_name(self, obj):
        u = obj.requested_by
        return (u.name or u.email) if u else None

    def get_checklist(self, obj):
        if obj.kind != Bucket.KIND_REQUEST:
            return []
        return ChecklistItemSerializer(obj.checklist.all(), many=True).data
