from rest_framework import serializers
from .models import DocPage, PortalUser, Bucket, SharedFile


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

    class Meta:
        model = SharedFile
        fields = [
            'id', 'original_name', 'size_bytes', 'mime_type', 'state',
            'review_status', 'review_notes', 'uploaded_at', 'uploaded_by_name',
        ]

    def get_uploaded_by_name(self, obj):
        u = obj.uploaded_by
        return (u.name or u.email) if u else None


class BucketSerializer(serializers.ModelSerializer):
    files = serializers.SerializerMethodField()

    class Meta:
        model = Bucket
        fields = ['id', 'kind', 'title', 'description', 'due_at', 'status', 'files']

    def get_files(self, obj):
        qs = obj.files.filter(deleted_at__isnull=True, state=SharedFile.STATE_READY)
        return SharedFileSerializer(qs, many=True).data
