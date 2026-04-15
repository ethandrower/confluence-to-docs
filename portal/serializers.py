from rest_framework import serializers
from .models import DocPage, PortalUser


class DocPageTreeSerializer(serializers.ModelSerializer):
    children = serializers.SerializerMethodField()

    class Meta:
        model = DocPage
        fields = ['id', 'confluence_id', 'title', 'slug', 'parent', 'children', 'position']

    def get_children(self, obj):
        children = obj.children.filter(is_published=True).order_by('position', 'title')
        return DocPageTreeSerializer(children, many=True).data


class DocPageDetailSerializer(serializers.ModelSerializer):
    breadcrumbs = serializers.SerializerMethodField()
    siblings = serializers.SerializerMethodField()

    class Meta:
        model = DocPage
        fields = ['id', 'confluence_id', 'title', 'slug', 'rendered_html', 'breadcrumbs', 'siblings', 'last_synced']

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
