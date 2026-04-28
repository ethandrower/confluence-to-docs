from django.db import models, connection
from django.db.models.signals import post_save
from django.dispatch import receiver


def _is_postgres():
    return connection.vendor == 'postgresql'


class DocPage(models.Model):
    confluence_id = models.CharField(max_length=64, unique=True)
    slug = models.SlugField(max_length=255, unique=True)
    title = models.CharField(max_length=512)
    parent = models.ForeignKey('self', null=True, blank=True, on_delete=models.SET_NULL, related_name='children')
    rendered_html = models.TextField()
    raw_storage = models.TextField()
    version = models.IntegerField(default=1)
    confluence_version = models.IntegerField(default=1)
    space_key = models.CharField(max_length=64)
    last_synced = models.DateTimeField(auto_now=True)
    is_published = models.BooleanField(default=True)
    is_folder = models.BooleanField(default=False)
    position = models.IntegerField(default=0)
    # TextField works on both SQLite and Postgres.
    # On Postgres the signal populates it via SearchVector; on SQLite it's plain text.
    search_vector = models.TextField(null=True, blank=True)

    class Meta:
        ordering = ['position', 'title']

    def __str__(self):
        return self.title


class DocImage(models.Model):
    confluence_id = models.CharField(max_length=256, unique=True)
    page = models.ForeignKey(DocPage, on_delete=models.CASCADE, related_name='images')
    local_path = models.CharField(max_length=512)
    original_filename = models.CharField(max_length=256)
    content_type = models.CharField(max_length=64)

    def __str__(self):
        return self.original_filename


class PortalUser(models.Model):
    email = models.EmailField(unique=True)
    name = models.CharField(max_length=256, blank=True)
    jsm_customer_id = models.CharField(max_length=64, blank=True)
    is_jsm_customer = models.BooleanField(default=False)
    jsm_checked_at = models.DateTimeField(null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_login = models.DateTimeField(null=True)

    def __str__(self):
        return self.email


class MagicLinkToken(models.Model):
    user = models.ForeignKey(PortalUser, on_delete=models.CASCADE)
    token = models.CharField(max_length=128, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    used = models.BooleanField(default=False)
    expires_at = models.DateTimeField()

    def is_valid(self):
        from django.utils import timezone
        return not self.used and self.expires_at > timezone.now()


@receiver(post_save, sender=DocPage)
def update_search_vector(sender, instance, **kwargs):
    if _is_postgres():
        from django.contrib.postgres.search import SearchVector
        DocPage.objects.filter(pk=instance.pk).update(
            search_vector=SearchVector('title', weight='A') + SearchVector('raw_storage', weight='B')
        )
    else:
        # SQLite fallback: store concatenated text for icontains search
        DocPage.objects.filter(pk=instance.pk).update(
            search_vector=f"{instance.title} {instance.raw_storage}"
        )
