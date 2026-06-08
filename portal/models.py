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


class Company(models.Model):
    """A customer organisation whose people may be granted portal access."""
    name = models.CharField(max_length=256, unique=True)
    contract_end_date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = 'companies'
        ordering = ['name']

    def __str__(self):
        return self.name


class PortalUser(models.Model):
    ROLE_OWNER = 'owner'
    ROLE_ADMIN = 'admin'
    ROLE_CUSTOMER = 'customer'
    ROLE_CHOICES = [(ROLE_OWNER, 'Owner'), (ROLE_ADMIN, 'Admin'), (ROLE_CUSTOMER, 'Customer')]

    email = models.EmailField(unique=True)
    name = models.CharField(max_length=256, blank=True)
    # Access control (TG-672): only enabled users already in the DB can sign in.
    role = models.CharField(max_length=16, choices=ROLE_CHOICES, default=ROLE_CUSTOMER)
    company = models.ForeignKey(
        'Company', null=True, blank=True, on_delete=models.SET_NULL, related_name='users'
    )
    access_enabled = models.BooleanField(default=True)
    jsm_customer_id = models.CharField(max_length=64, blank=True)
    is_jsm_customer = models.BooleanField(default=False)
    jsm_checked_at = models.DateTimeField(null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_login = models.DateTimeField(null=True)

    @property
    def is_owner_role(self):
        return self.role == self.ROLE_OWNER

    @property
    def is_admin_role(self):
        # Owners are also admin-privileged.
        return self.role in (self.ROLE_OWNER, self.ROLE_ADMIN)

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


class ContactSubmission(models.Model):
    STATUS_PENDING = 'pending'
    STATUS_SENT = 'sent'
    STATUS_FAILED = 'failed'
    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_SENT, 'Sent'),
        (STATUS_FAILED, 'Failed'),
    ]

    name = models.CharField(max_length=256)
    email = models.EmailField()
    category = models.CharField(max_length=32)
    subject = models.CharField(max_length=512)
    message = models.TextField()
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=STATUS_PENDING)
    error = models.TextField(blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['-created_at']),
            models.Index(fields=['status']),
        ]

    def __str__(self):
        return f'{self.email} — {self.subject} ({self.status})'


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


# ── Customer file sharing ───────────────────────────────────────────────
class Bucket(models.Model):
    """A flat grouping of shared files for one company. Either a staff-created
    'request' (asking the customer for specific docs) or the customer's
    'general' uploads bucket. Explicitly NOT a folder tree — no nesting."""
    KIND_REQUEST = 'request'
    KIND_GENERAL = 'general'
    KIND_CHOICES = [(KIND_REQUEST, 'Request'), (KIND_GENERAL, 'General')]
    STATUS_CHOICES = [
        ('open', 'Open'), ('partial', 'Partial'),
        ('complete', 'Complete'), ('general', 'General'),
    ]

    company = models.ForeignKey('Company', on_delete=models.CASCADE, related_name='buckets')
    kind = models.CharField(max_length=16, choices=KIND_CHOICES, default=KIND_GENERAL)
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    requested_by = models.ForeignKey(
        'PortalUser', null=True, blank=True, on_delete=models.SET_NULL,
        related_name='requested_buckets',
    )
    due_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default='general')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['kind', '-created_at']

    def __str__(self):
        return f'{self.company.name} — {self.title}'


class SharedFile(models.Model):
    STATE_UPLOADING = 'uploading'
    STATE_READY = 'ready'
    REVIEW_CHOICES = [
        ('pending', 'Pending'), ('review', 'In review'),
        ('approved', 'Approved'), ('revision', 'Needs revision'),
    ]

    bucket = models.ForeignKey(Bucket, on_delete=models.CASCADE, related_name='files')
    company = models.ForeignKey('Company', on_delete=models.CASCADE, related_name='shared_files')
    uploaded_by = models.ForeignKey(
        'PortalUser', null=True, blank=True, on_delete=models.SET_NULL,
        related_name='uploaded_files',
    )
    original_name = models.CharField(max_length=512)
    storage_key = models.CharField(max_length=1024)
    size_bytes = models.BigIntegerField(null=True, blank=True)
    mime_type = models.CharField(max_length=255, blank=True)
    state = models.CharField(max_length=16, default=STATE_UPLOADING)
    review_status = models.CharField(max_length=16, choices=REVIEW_CHOICES, default='pending')
    review_notes = models.TextField(blank=True)
    reviewed_by = models.ForeignKey(
        'PortalUser', null=True, blank=True, on_delete=models.SET_NULL,
        related_name='reviewed_files',
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-uploaded_at']
        indexes = [
            models.Index(fields=['company', 'deleted_at']),
        ]

    def __str__(self):
        return self.original_name


class ChecklistItem(models.Model):
    """A required-document slot on a request bucket (Phase 3). The model lands
    now to avoid a later migration; endpoints come in Phase 3."""
    bucket = models.ForeignKey(Bucket, on_delete=models.CASCADE, related_name='checklist')
    text = models.CharField(max_length=512)
    position = models.IntegerField(default=0)
    linked_file = models.ForeignKey(
        SharedFile, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='satisfies',
    )
    created_by = models.ForeignKey('PortalUser', null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['position', 'id']


class FileActivity(models.Model):
    """Append-only audit trail for every file-sharing action. Never deleted."""
    company = models.ForeignKey('Company', on_delete=models.CASCADE, related_name='file_activity')
    file = models.ForeignKey(SharedFile, null=True, blank=True, on_delete=models.SET_NULL)
    bucket = models.ForeignKey(Bucket, null=True, blank=True, on_delete=models.SET_NULL)
    actor = models.ForeignKey('PortalUser', null=True, blank=True, on_delete=models.SET_NULL)
    action = models.CharField(max_length=32)  # upload|download|rename|delete|status_change|request_created|note
    detail = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['company', '-created_at']),
        ]
