import hashlib
import secrets
from datetime import timedelta

from django.db import models, connection
from django.db.models.signals import post_save
from django.dispatch import receiver
# Module-level because SiteNotice.starts_at uses `timezone.now` as a field
# default, which is evaluated at class-definition time.
from django.utils import timezone


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
    # Demo/sandbox accounts may sign in WITHOUT a magic link (see
    # auth.demo_login) so staff can open the customer portal in a second
    # browser. Only ever set on throwaway sandbox accounts — never real users.
    is_demo = models.BooleanField(default=False)
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
    """A grouping of shared files for one company.

    Three kinds, and the difference matters:

      - 'general' — the single auto-created "General uploads" root. One per
        company, never nested, never deleted.
      - 'request' — staff asking the customer for specific documents, with a
        due date and optionally a checklist. Deliberately NOT part of the
        folder tree: a request is a task with a deadline, and letting a
        customer drag one into a subfolder would let them bury or lose it.
        Pinned above the tree in the UI.
      - 'folder'  — customer-created, nestable, the actual document structure.

    Nesting is an adjacency list (`parent`) rather than a materialised path:
    depth here is single digits, and this keeps the existing serializer and
    queries intact. Only 'folder' rows may have a parent or be one.
    """
    KIND_REQUEST = 'request'
    KIND_GENERAL = 'general'
    KIND_FOLDER = 'folder'
    KIND_CHOICES = [
        (KIND_REQUEST, 'Request'), (KIND_GENERAL, 'General'), (KIND_FOLDER, 'Folder'),
    ]
    ORIGIN_CUSTOMER = 'customer'
    ORIGIN_STAFF = 'staff'
    ORIGIN_CHOICES = [(ORIGIN_CUSTOMER, 'Customer'), (ORIGIN_STAFF, 'CiteMed')]
    STATUS_CHOICES = [
        ('open', 'Open'), ('partial', 'Partial'),
        ('complete', 'Complete'), ('general', 'General'),
    ]
    # Deep enough for any real document set, shallow enough that a recursive
    # walk stays cheap and a UI can still show the path.
    MAX_DEPTH = 8

    company = models.ForeignKey('Company', on_delete=models.CASCADE, related_name='buckets')
    kind = models.CharField(max_length=16, choices=KIND_CHOICES, default=KIND_GENERAL)
    # WHO the folder belongs to, which is a different question from `kind`.
    # A 'folder' the customer made is theirs to rename, move and delete; a
    # 'folder' we pushed to them is a deliverable they may read but must not
    # reorganise or destroy. Defaulting to 'customer' makes every existing
    # row correct at migration time with no data pass.
    origin = models.CharField(max_length=16, choices=ORIGIN_CHOICES, default=ORIGIN_CUSTOMER)
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    # CASCADE, not PROTECT: a company delete must be able to take its whole
    # tree with it in one collector pass. Deleting a folder that still holds
    # anything is refused at the API layer instead (see views.files), which is
    # where a human-readable error can be returned.
    parent = models.ForeignKey(
        'self', null=True, blank=True, on_delete=models.CASCADE, related_name='children',
    )
    created_by = models.ForeignKey(
        'PortalUser', null=True, blank=True, on_delete=models.SET_NULL,
        related_name='created_buckets',
    )
    requested_by = models.ForeignKey(
        'PortalUser', null=True, blank=True, on_delete=models.SET_NULL,
        related_name='requested_buckets',
    )
    due_at = models.DateTimeField(null=True, blank=True)
    # Only meaningful on a 'request'. Most requests are useful-to-have rather
    # than genuinely gating, and a customer shown ten equally-urgent demands
    # reads the whole list as noise and does none of them. Marking the few
    # that actually block progress lets the UI put those in front of them and
    # leave the rest sitting quietly alongside their own folders.
    required = models.BooleanField(default=False)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default='general')
    last_reminder_at = models.DateTimeField(null=True, blank=True)  # due-date reminder throttle
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['kind', '-created_at']
        constraints = [
            # At most one 'general' bucket per company (guards the get_or_create
            # race in get_general_bucket). Requests are unconstrained.
            models.UniqueConstraint(
                fields=['company'], condition=models.Q(kind='general'),
                name='uniq_general_bucket_per_company',
            ),
            # Only folders nest. Enforced in the database because the API is
            # not the only writer — the admin and the shell reach this too.
            models.CheckConstraint(
                check=models.Q(parent__isnull=True) | models.Q(kind='folder'),
                name='only_folders_may_be_nested',
            ),
        ]

    def __str__(self):
        return f'{self.company.name} — {self.title}'

    @classmethod
    def for_company(cls, company_id):
        """Every bucket belonging to one company.

        Staff endpoints scope through here with a company_id taken from the
        request: choosing which client to act on IS the staff job, so that is
        a legitimate parameter rather than a leak. Customer endpoints must go
        through for_user() instead, which pins the company to the session.
        """
        if not company_id:
            return cls.objects.none()
        return cls.objects.filter(company_id=company_id)

    @classmethod
    def for_user(cls, user):
        """Tenant-isolation chokepoint for buckets — the same rule as
        SharedFile.for_user. Folder endpoints must query through here so a
        re-parent can never reach across companies.

        This matters more for a tree than it did for a flat list: moving a
        folder or a file changes its parent but NOT its `company`, so a
        target picked from another tenant would still pass a naive
        `company_id` check on the object being moved. The target has to be
        resolved through this method too.
        """
        return cls.for_company(getattr(user, 'company_id', None))

    @property
    def is_staff_origin(self):
        """Pushed to the customer by us. Read-only on the customer side: they
        may open and download what is inside, but not rename, move, delete or
        upload into it. One field answers every permission question about a
        folder, which is why customer uploads are kept out of these rather
        than tracked per-file."""
        return self.origin == self.ORIGIN_STAFF

    @property
    def level(self):
        """1-based depth, so it reads the way the limit is worded: a top-level
        folder is level 1 and MAX_DEPTH = 8 means eight levels, not nine."""
        return self.depth + 1

    @property
    def depth(self):
        """0 for a top-level bucket. Walks parents, bounded by MAX_DEPTH + 1 so
        a cycle introduced outside the API can't hang a request."""
        d, node, seen = 0, self.parent, {self.pk}
        while node is not None and d <= self.MAX_DEPTH + 1:
            if node.pk in seen:
                break
            seen.add(node.pk)
            d += 1
            node = node.parent
        return d

    def subtree_height(self):
        """How many levels sit below this bucket (0 if it has no children).
        A move must fit the whole subtree under MAX_DEPTH, not just the folder
        being dragged — otherwise dropping a deep branch one level down
        silently exceeds the limit."""
        children = list(self.children.all())
        if not children:
            return 0
        return 1 + max(c.subtree_height() for c in children)

    def is_descendant_of(self, other):
        """True if `other` is this bucket, or anywhere above it. Used to refuse
        a move that would detach a subtree into its own cycle."""
        node, seen = self, set()
        while node is not None and node.pk not in seen:
            if node.pk == other.pk:
                return True
            seen.add(node.pk)
            node = node.parent
        return False


class SharedFile(models.Model):
    """A customer-shared file living in S3 (reached only via presigned URLs).

    Two states that matter:
      - `state`     : upload lifecycle — 'uploading' until the browser→S3 PUT
                      is confirmed, then 'ready'. Only 'ready' files are
                      listed/downloadable.
      - `processed` : INTERNAL "someone has looked at this". Drives the unseen
                      dot in the staff view and nothing else. Never shown to
                      customers, and it is not an approval — see below.

    RETIRED: the customer-facing review loop (`review_status`, `review_notes`,
    `reviewed_by`, `reviewed_at`). It modelled staff approving or rejecting
    each uploaded document, which is not what actually happens — documents get
    collected and ticked off a checklist, not adjudicated one by one. Leaving
    it in place meant every customer's file list showed a permanent "AWAITING
    REVIEW" badge for a review that was never coming.

    The columns are kept rather than dropped so existing rows aren't
    destroyed, but nothing reads or writes them: they are absent from every
    serializer and there is no endpoint that sets them. Whether a document is
    accounted for is now expressed by ChecklistItem.linked_file — a fact about
    the request it satisfies, not a verdict on the file.
    """
    STATE_UPLOADING = 'uploading'
    STATE_READY = 'ready'
    ITEM_FILE = 'file'
    ITEM_LINK = 'link'
    ITEM_TYPE_CHOICES = [(ITEM_FILE, 'File'), (ITEM_LINK, 'Link')]
    # Retained only so the retired columns keep valid choices; unused.
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
    # A 'link' is a first-class row with no bytes behind it: an external URL
    # (QA results, a dashboard) that lives in the folder tree beside real
    # files so it sorts, moves, renames and permissions identically.
    # `storage_key` is empty and size/mime are null for these, so every
    # download path must branch on item_type before it presigns anything.
    item_type = models.CharField(max_length=8, choices=ITEM_TYPE_CHOICES, default=ITEM_FILE)
    external_url = models.URLField(max_length=2048, blank=True)
    storage_key = models.CharField(max_length=1024)
    # S3 multipart UploadId, set only while a large upload is in flight.
    # Completion needs it to assemble the object from its parts, and an
    # abandoned upload needs it to be *aborted*: orphaned parts keep being
    # billed and never show up in a listing of the bucket's objects.
    upload_id = models.CharField(max_length=255, blank=True)
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
    # Internal "we've handled / integrated this" flag for the staff inbox.
    # Distinct from review_status (which is the customer-facing approve/revise loop).
    processed = models.BooleanField(default=False)
    processed_at = models.DateTimeField(null=True, blank=True)
    processed_by = models.ForeignKey(
        'PortalUser', null=True, blank=True, on_delete=models.SET_NULL,
        related_name='processed_files',
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-uploaded_at']
        indexes = [
            models.Index(fields=['company', 'deleted_at']),
            # Powers the cross-client inbox list + unprocessed count.
            models.Index(fields=['state', 'processed', 'deleted_at', '-uploaded_at']),
        ]

    def __str__(self):
        return self.original_name

    @classmethod
    def for_company(cls, company_id):
        """Non-deleted files belonging to one company. The staff-side entry
        point; see Bucket.for_company for why a company_id parameter is
        legitimate there and not on the customer side."""
        if not company_id:
            return cls.objects.none()
        return cls.objects.filter(company_id=company_id, deleted_at__isnull=True)

    @classmethod
    def for_user(cls, user):
        """Non-deleted files the given portal user may access — scoped to THEIR
        company only. The single chokepoint for customer-side tenant isolation:
        customer endpoints must query through here, never `objects` directly,
        so a forgotten `.filter(company_id=...)` can't leak across clients."""
        return cls.for_company(getattr(user, 'company_id', None))

    @property
    def is_link(self):
        return self.item_type == self.ITEM_LINK


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


class FileComment(models.Model):
    """Internal CiteMed-staff discussion on a shared file. NEVER exposed to the
    customer — only the admin API returns these."""
    file = models.ForeignKey(SharedFile, on_delete=models.CASCADE, related_name='comments')
    author = models.ForeignKey('PortalUser', null=True, blank=True, on_delete=models.SET_NULL)
    body = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']


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


class ShareNotice(models.Model):
    """One row per (push, person): who we told about a folder or file we
    pushed to a customer, and whether they ever opened it.

    FileActivity cannot answer this. It is an append-only record of who DID
    act, and the question a reminder loop has to ask is who did NOT — which
    needs the intended audience recorded at push time. Nothing else stores
    that, so "notified but never opened" is unanswerable without this table.

    Recipients are PortalUser rows rather than free-text addresses on purpose:
    a share notification is a link into the portal, so notifying somebody who
    cannot sign in there is a dead email by construction. If staff want to
    reach a new person, the answer is to provision them, not to email past
    the access model.

    Pushing the same folder again creates NEW rows rather than resetting the
    old ones. A second push is a second thing to have missed, and it should
    get its own nudge cycle instead of quietly rearming the first.
    """
    # Two nudges, then it stays quiet for good. A third automated email was
    # never going to be the thing that worked; past that point staff chase it
    # themselves, which is what the per-person status panel exists for.
    MAX_REMINDERS = 2
    # Days after the push, measured from sent_at, at which each nudge fires.
    # Indexed by reminder_count, so it must hold exactly MAX_REMINDERS entries.
    REMINDER_AFTER_DAYS = [3, 7]

    # ── How much mail one person can receive about shared files ──────────
    #
    # The per-notice reminder cap above is not by itself a limit on what a
    # human receives, because pushing a folder twice makes two notices and
    # each one nudges on its own schedule. Staff re-notifying a folder as they
    # add to it is the normal workflow, not misuse, so the cadence has to
    # survive it: three pushes of one folder to one person who never opens it
    # produced NINE emails — three sends plus six reminders, several landing
    # on the same day with an identical subject line.
    #
    # Two rules fix that, and they are deliberately about the person rather
    # than the row, because "spam" is a fact about an inbox:
    #
    #   1. One email per person per folder per day. A second push of the same
    #      folder says the same sentence and points at the same link, so a
    #      second email adds nothing the first did not already say.
    #   2. A hard ceiling per person per day across all folders, as a backstop
    #      for any path that gets added later without reading this comment.
    SAME_FOLDER_COOLDOWN = timedelta(hours=24)
    MAX_EMAILS_PER_DAY = 4

    bucket = models.ForeignKey(Bucket, on_delete=models.CASCADE, related_name='notices')
    # Set when a single file or link was pushed; null when the whole folder was.
    file = models.ForeignKey(
        SharedFile, null=True, blank=True, on_delete=models.CASCADE,
        related_name='notices',
    )
    recipient = models.ForeignKey(
        'PortalUser', on_delete=models.CASCADE, related_name='share_notices')
    sent_by = models.ForeignKey(
        'PortalUser', null=True, blank=True, on_delete=models.SET_NULL,
        related_name='sent_share_notices',
    )
    sent_at = models.DateTimeField(auto_now_add=True)
    # Part of the /api/v1/share-events/ contract, not bookkeeping.
    #
    # That endpoint is polled, and its cursor walks an ASCENDING ordering, so a
    # row that changes must move to the END of the ordering or the consumer's
    # cursor has already passed it and the change is lost. Ordering on sent_at
    # would do exactly that: an open — the event most worth syncing — never
    # moves the row, so RevenueHub would learn about every push and none of the
    # responses to them.
    #
    # auto_now covers an ordinary save(). It fires on NEITHER of the two other
    # ways this row is written: a queryset .update() (mark_opened) skips save()
    # altogether, and save(update_fields=[...]) omitting this name skips it too.
    # Both of those sites therefore set this column explicitly, and
    # test_api_v1_share_events.py holds them to it.
    updated_at = models.DateTimeField(auto_now=True, db_index=True)
    first_opened_at = models.DateTimeField(null=True, blank=True)
    last_reminder_at = models.DateTimeField(null=True, blank=True)
    reminder_count = models.IntegerField(default=0)
    # Staff can push without arming the nudge loop at all.
    remind = models.BooleanField(default=True)
    # When an email for THIS notice last actually reached the recipient —
    # push or reminder, whichever came last. Distinct from sent_at, which
    # records when staff pushed: the two differ exactly when a send was
    # suppressed, and that gap is the thing the rate limit is made of.
    # Counting sent_at instead would count suppressed sends as delivered and
    # let the ceiling drift up every time it did its job.
    last_email_at = models.DateTimeField(null=True, blank=True, db_index=True)

    class Meta:
        ordering = ['-sent_at']
        indexes = [
            # Powers the reminder sweep: unopened, still armed, under the cap.
            models.Index(fields=['first_opened_at', 'remind', 'reminder_count', 'sent_at']),
            # Powers the per-person status panel on one folder.
            models.Index(fields=['bucket', 'recipient']),
        ]

    def __str__(self):
        return f'{self.bucket.title} → {self.recipient.email}'

    @property
    def opened(self):
        return self.first_opened_at is not None

    @property
    def exhausted(self):
        return self.reminder_count >= self.MAX_REMINDERS

    def due_for_reminder(self, now=None):
        """Whether this notice has earned its next nudge.

        Both thresholds are measured from `sent_at`, not from the previous
        reminder: the question is how long this has gone unopened in total,
        and chaining off last_reminder_at would let a late first nudge drag
        the second one out indefinitely.
        """
        now = now or timezone.now()
        if self.opened or not self.remind or self.exhausted:
            return False
        return (now - self.sent_at) >= timedelta(
            days=self.REMINDER_AFTER_DAYS[self.reminder_count])

    def suppressed_reason(self, now=None):
        """Why this notice must not be emailed right now, or None to send.

        Consulted by both senders — the push view and the reminder sweep — so
        the two cannot come to different conclusions about the same inbox. A
        reason string rather than a bool because it gets logged and returned
        to staff: "we didn't email them" is a much less useful thing to be
        told than which rule stopped it.

        Both windows are rolling rather than calendar days. A calendar rule
        would let a push at 23:50 and another at 00:10 both go, which is the
        one case a reader of "once a day" would be most surprised by.
        """
        now = now or timezone.now()
        recent = self.__class__.objects.filter(
            recipient_id=self.recipient_id, last_email_at__isnull=False)
        if self.pk:
            recent = recent.exclude(pk=self.pk)

        if recent.filter(bucket_id=self.bucket_id,
                         last_email_at__gt=now - self.SAME_FOLDER_COOLDOWN).exists():
            return 'already emailed about this folder today'
        if recent.filter(
                last_email_at__gt=now - timedelta(days=1)
        ).count() >= self.MAX_EMAILS_PER_DAY:
            return 'daily email limit for this recipient reached'
        return None

    def record_email_sent(self, now=None):
        """Stamp an email that actually went out.

        Writes updated_at by hand for the reason the field's own comment
        gives: this is a save(update_fields=...), so the column's auto_now
        does not fire for names the caller leaves out, and a send that never
        moved updated_at would be invisible to /api/v1/share-events/.
        """
        self.last_email_at = now or timezone.now()
        self.updated_at = self.last_email_at
        self.save(update_fields=['last_email_at', 'updated_at'])

    @classmethod
    def supersede_open_notices(cls, recipient_id, bucket_id, now=None):
        """Disarm this person's earlier unopened notices for the same folder.

        A second push of a folder is not a second thing to open — it is the
        same folder, behind the same link — so the older notice's nudge cycle
        would spend its two reminders saying what the new one is about to say
        again. Left alone they interleave: with pushes on three consecutive
        days the recipient gets a reminder on days 4, 5, 6 and again on 8, 9,
        10, all with one subject line.

        Only `remind` is cleared. The rows stay, unopened and readable, so the
        per-person status panel and the RevenueHub feed still show every push
        that was made rather than quietly losing the history.
        """
        now = now or timezone.now()
        return (cls.objects
                .filter(recipient_id=recipient_id, bucket_id=bucket_id,
                        first_opened_at__isnull=True, remind=True)
                .update(remind=False, updated_at=now))

    @classmethod
    def mark_opened(cls, user, file, now=None):
        """Record that `user` opened `file`, satisfying every notice covering
        it — the notice for that exact file, and any for a folder above it.

        Walking ancestors matters: we push a folder, they open something two
        levels down inside it, and that is plainly them having opened what we
        sent. Only the first open is kept; re-opening doesn't move the mark.

        `updated_at` is written by hand here because this is a queryset update:
        it never calls save(), so the field's auto_now would not fire and the
        open would stay invisible to /api/v1/share-events/.
        """
        now = now or timezone.now()
        bucket_ids, node, seen = [], file.bucket, set()
        # Bounded like Bucket.depth, so a cycle introduced outside the API
        # can't spin here on what is a read path.
        while node is not None and len(seen) <= Bucket.MAX_DEPTH + 1:
            if node.pk in seen:
                break
            seen.add(node.pk)
            bucket_ids.append(node.pk)
            node = node.parent
        return (
            cls.objects
            .filter(recipient=user, first_opened_at__isnull=True)
            .filter(models.Q(file=file)
                    | models.Q(file__isnull=True, bucket_id__in=bucket_ids))
            .update(first_opened_at=now, updated_at=now)
        )


class Ticket(models.Model):
    """A customer support conversation. Replaces Jira for customer comms —
    Jira remains internal-only via the (never customer-visible) jira_key."""
    STATUS_OPEN = 'open'
    STATUS_WAITING_ON_CUSTOMER = 'waiting_on_customer'
    STATUS_WAITING_ON_SUPPORT = 'waiting_on_support'
    STATUS_RESOLVED = 'resolved'
    STATUS_CLOSED = 'closed'
    STATUS_CHOICES = [
        (STATUS_OPEN, 'Open'),
        (STATUS_WAITING_ON_CUSTOMER, 'Waiting on customer'),
        (STATUS_WAITING_ON_SUPPORT, 'Waiting on support'),
        (STATUS_RESOLVED, 'Resolved'),
        (STATUS_CLOSED, 'Closed'),
    ]
    CATEGORY_CHOICES = [
        ('question', 'Question'), ('bug', 'Bug Report'),
        ('feature', 'Feature Request'), ('docs', 'Documentation Issue'),
        ('other', 'Other'),
    ]

    # SLA severity, per the SLA doc. Staff-assigned and staff-visible only:
    # a customer able to mark their own ticket Urgent would drain the field of
    # meaning, so it is absent from the customer serializer (_ticket_dict) and
    # writable solely through the admin endpoint.
    #
    # Note 'csm_direct' is a routing origin rather than a severity — it sits in
    # this list because the SLA doc treats the four as one set. If a ticket ever
    # needs to be both Urgent AND CSM-direct, this wants splitting into two
    # fields.
    PRIORITY_URGENT = 'urgent'
    PRIORITY_HIGH = 'high'
    PRIORITY_STANDARD = 'standard'
    PRIORITY_CSM_DIRECT = 'csm_direct'
    PRIORITY_CHOICES = [
        (PRIORITY_URGENT, 'Urgent'),
        (PRIORITY_HIGH, 'High'),
        (PRIORITY_STANDARD, 'Standard'),
        (PRIORITY_CSM_DIRECT, 'CSM Direct'),
    ]

    # Triage rank, lower = attend to first. Ordered by the first-response
    # commitments in EC-SOP-07 §4.1: URGENT is the only same-business-day
    # promise; High (1 business day) and CSM Direct (within 24 hours) are
    # effectively next-day, with High ahead because it denotes a platform
    # error blocking work rather than an account conversation; Standard
    # (1–2 business days) is the loosest. The High/CSM Direct order is the
    # one judgement call here — the doc doesn't rank them against each other.
    PRIORITY_RANK = {
        PRIORITY_URGENT: 0,
        PRIORITY_HIGH: 1,
        PRIORITY_CSM_DIRECT: 2,
        PRIORITY_STANDARD: 3,
    }

    # null=True so save() can assign it pre-INSERT; unique=True guards races.
    number = models.PositiveIntegerField(unique=True, editable=False, null=True, blank=True)
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='tickets')
    created_by = models.ForeignKey(
        'PortalUser', null=True, blank=True, on_delete=models.SET_NULL,
        related_name='tickets_created',
    )
    # Who the ticket is FOR, as opposed to `created_by` (who opened it). The
    # two differ only on the staff on-behalf path, where created_by is the
    # agent. Nullable because a customer opening their own ticket doesn't need
    # it, and because staff can name someone with no portal account at all —
    # see requester_email, which is recorded either way.
    requester = models.ForeignKey(
        'PortalUser', null=True, blank=True, on_delete=models.SET_NULL,
        related_name='tickets_requested',
    )
    requester_email = models.EmailField(blank=True)
    # The agent who picked the ticket up. Null means nobody owns it yet, which
    # is what keeps it in the shared queue.
    assignee = models.ForeignKey(
        'PortalUser', null=True, blank=True, on_delete=models.SET_NULL,
        related_name='tickets_assigned',
    )
    # Staff following the ticket for follow-up. Deliberately separate from
    # cc_emails, which is customer-facing: CC'd addresses receive the
    # customer-worded mail and are listed back to the customer. Watchers are
    # internal and must never be serialized to a customer.
    watchers = models.ManyToManyField(
        'PortalUser', blank=True, related_name='tickets_watching',
    )
    subject = models.CharField(max_length=512)
    category = models.CharField(max_length=32, choices=CATEGORY_CHOICES, default='question')
    status = models.CharField(max_length=32, choices=STATUS_CHOICES,
                              default=STATUS_WAITING_ON_SUPPORT)
    priority = models.CharField(max_length=16, choices=PRIORITY_CHOICES,
                                default=PRIORITY_STANDARD)
    # When we first replied to the customer — drives the SLA first-response
    # indicator (portal/sla.py). Denormalised rather than derived, because the
    # admin list needs it per row and deriving it would be a query per ticket.
    first_response_at = models.DateTimeField(null=True, blank=True)
    cc_emails = models.JSONField(default=list, blank=True)
    # Internal Jira references live in JiraTicketLink (admin-only, never
    # serialized to customers). Was a single `jira_key` CharField — migrated
    # to the link model in 0019 to support multiple keys + live status.
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']
        indexes = [
            models.Index(fields=['company', '-updated_at']),
            models.Index(fields=['status', 'updated_at']),  # admin inbox
        ]

    def __str__(self):
        return f'{self.display_number} {self.subject}'

    @property
    def display_number(self):
        return f'CS-{self.number}'

    def save(self, *args, **kwargs):
        if self.number is not None:
            super().save(*args, **kwargs)
            return

        # Max+1 is fine at our write volume; unique=True catches races. On a
        # collision (concurrent create landed between our aggregate read and
        # our INSERT) we re-aggregate and retry a bounded number of times
        # instead of letting IntegrityError escape to the caller. Avoids a
        # sequence table.
        from django.db import IntegrityError, transaction

        max_attempts = 5
        for attempt in range(max_attempts):
            last = Ticket.objects.aggregate(models.Max('number'))['number__max']
            self.number = (last or 0) + 1
            try:
                with transaction.atomic():
                    super().save(*args, **kwargs)
                return
            except IntegrityError:
                self.number = None
                if attempt == max_attempts - 1:
                    raise

    @classmethod
    def for_user(cls, user):
        """Tenant-isolation chokepoint — customer endpoints must query through
        here, never `objects` directly (same rule as SharedFile.for_user).

        Two ways in: the ticket belongs to your company, or it was opened
        specifically for you. The second exists so a staff on-behalf ticket
        reaches the person it names even when they sit outside the company it
        was filed under — without it, being the requester grants nothing and
        the customer can only ever follow the thread by email.

        It stays a tenant boundary: the match is on this exact user's primary
        key, so it widens access by precisely the tickets naming them and
        nothing else.
        """
        if user is None or getattr(user, 'pk', None) is None:
            return cls.objects.none()
        company_id = getattr(user, 'company_id', None)
        if company_id:
            return cls.objects.filter(
                models.Q(company_id=company_id) | models.Q(requester_id=user.pk)
            )
        return cls.objects.filter(requester_id=user.pk)


class TicketRead(models.Model):
    """Per-user read state for a ticket — drives the customer list's unread dot."""
    user = models.ForeignKey('PortalUser', on_delete=models.CASCADE, related_name='ticket_reads')
    ticket = models.ForeignKey('Ticket', on_delete=models.CASCADE, related_name='reads')
    last_read_at = models.DateTimeField()

    class Meta:
        unique_together = (('user', 'ticket'),)


class TicketMessage(models.Model):
    ORIGIN_PORTAL = 'portal'
    ORIGIN_STAFF = 'staff'
    ORIGIN_EMAIL = 'email'  # Phase 2 inbound

    # Delivery of the customer-facing email this message triggered (if any).
    # Tier A = synchronous submission truth only: 'sent' = the mail backend
    # accepted it, 'failed' = the send raised. 'not_applicable' = nothing was
    # emailed to a customer for this row (internal notes, customer's own
    # replies). 'queued' is reserved for Tier B (async webhook delivery truth).
    DELIVERY_NA = 'not_applicable'
    DELIVERY_QUEUED = 'queued'
    DELIVERY_SENT = 'sent'          # accepted by the ESP; awaiting a delivery event
    DELIVERY_DELIVERED = 'delivered'  # Tier B: Mailgun confirmed delivery
    DELIVERY_BOUNCED = 'bounced'    # Tier B: bounced / rejected / complained
    DELIVERY_FAILED = 'failed'      # submission to the ESP failed
    DELIVERY_CHOICES = [
        (DELIVERY_NA, 'Not applicable'),
        (DELIVERY_QUEUED, 'Queued'),
        (DELIVERY_SENT, 'Sent'),
        (DELIVERY_DELIVERED, 'Delivered'),
        (DELIVERY_BOUNCED, 'Bounced'),
        (DELIVERY_FAILED, 'Failed'),
    ]

    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name='messages')
    author = models.ForeignKey('PortalUser', null=True, blank=True, on_delete=models.SET_NULL)
    author_email = models.EmailField(blank=True)
    body = models.TextField()
    origin = models.CharField(max_length=16, default=ORIGIN_PORTAL)
    # Staff-only note: never customer-visible, never emailed to the customer.
    is_internal = models.BooleanField(default=False)
    delivery_status = models.CharField(max_length=16, choices=DELIVERY_CHOICES,
                                       default=DELIVERY_NA)
    delivery_detail = models.CharField(max_length=256, blank=True)  # admin-only
    delivery_attempted_at = models.DateTimeField(null=True, blank=True)
    # ESP (Mailgun) message-id captured at send, used to correlate delivery
    # webhook events back to this message (Tier B). Distinct from
    # email_message_id (our RFC-5322 Message-ID used for inbox threading).
    esp_message_id = models.CharField(max_length=256, blank=True, db_index=True)
    # Phase-2 email-threading plumbing, populated on outbound sends now.
    email_message_id = models.CharField(max_length=256, blank=True)
    reply_token = models.CharField(max_length=64, blank=True, db_index=True)
    # Jira comment id this message was ingested from (S1 Jira→portal sync).
    # Globally unique per Jira; used to dedupe so a comment syncs at most once.
    jira_comment_id = models.CharField(max_length=32, blank=True, default='',
                                       db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']
        constraints = [
            # A Jira comment syncs at most once per ticket (S1 dedup). Partial
            # constraint so the empty default on non-Jira messages is exempt.
            models.UniqueConstraint(
                fields=['ticket', 'jira_comment_id'],
                condition=~models.Q(jira_comment_id=''),
                name='uniq_jira_comment_per_ticket'),
        ]


class TicketActivity(models.Model):
    """Append-only audit trail for ticket actions. Never deleted."""
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name='activity')
    actor = models.ForeignKey('PortalUser', null=True, blank=True, on_delete=models.SET_NULL)
    action = models.CharField(max_length=32)
    detail = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']


class ApiClient(models.Model):
    """A machine consumer of the read-only integration API at /api/v1/.

    This is NOT a PortalUser and must never become one. The portal has exactly
    two authentication doors: the session (a human, scoped to their company by
    `Ticket.for_user`) and this token (a server, deliberately unscoped). The
    bearer authenticator returns an AnonymousUser and hands the ApiClient back
    only as `request.auth`, so nothing downstream can mistake a machine for a
    person and no code path can be authenticated by both doors at once.

    Only the SHA-256 of the token is stored. The raw token is shown once, by
    `manage.py create_api_client`, and is unrecoverable afterwards — a database
    dump therefore leaks nothing usable. A plain hash (not a slow KDF) is the
    right choice here precisely because the token is 256 bits of `secrets`
    entropy rather than a human-chosen password: there is nothing to brute
    force, and every request would otherwise pay the KDF cost.

    Revocation is a row edit (`enabled = False`) or a delete in the Django
    admin, so a leaked credential is cut off without a deploy.
    """

    TOKEN_PREFIX = 'csp_'  # helps secret scanners and humans recognise it

    name = models.CharField(max_length=128, unique=True)
    token_hash = models.CharField(max_length=64, unique=True, editable=False)
    enabled = models.BooleanField(default=True)
    # Write capability, off by default and granted per client. The /api/v1/
    # namespace was read-only for its whole life, so every token that exists
    # today was issued on that understanding; a shared permission would have
    # silently upgraded all of them the moment the provisioning endpoints
    # shipped. Read access and the ability to create customer logins are not
    # the same grant and should not be carried by the same flag.
    can_provision = models.BooleanField(
        default=False,
        help_text='Allow this client to POST to /api/v1/provisioning/ '
                  '(create companies and portal users).')
    created_at = models.DateTimeField(auto_now_add=True)
    # Last successful authentication. Its own justification: a sync that
    # silently stops is otherwise invisible from this side of the integration.
    last_used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return f'{self.name}{"" if self.enabled else " (disabled)"}'

    @staticmethod
    def hash_token(raw_token):
        return hashlib.sha256(raw_token.encode('utf-8')).hexdigest()

    @classmethod
    def issue(cls, name):
        """Create a client and return (client, raw_token). The raw token is
        returned exactly once — it is never stored and cannot be recovered."""
        raw = cls.TOKEN_PREFIX + secrets.token_urlsafe(32)
        client = cls.objects.create(name=name, token_hash=cls.hash_token(raw))
        return client, raw

    def touch(self, now=None):
        """Record a successful authentication.

        A queryset UPDATE rather than save(): one statement, no signals, and it
        cannot accidentally write back a stale copy of any other column.
        """
        from django.utils import timezone
        stamp = now or timezone.now()
        type(self).objects.filter(pk=self.pk).update(last_used_at=stamp)
        self.last_used_at = stamp


class JiraTicketLink(models.Model):
    """A link from a support ticket to an internal Jira issue. ADMIN-ONLY —
    never serialized to customers. Supports multiple issues per ticket and
    caches the issue's live status (refreshed on admin view)."""
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name='jira_links')
    key = models.CharField(max_length=32)  # e.g. ECD-123
    cached_status = models.CharField(max_length=64, blank=True)
    cached_status_category = models.CharField(max_length=32, blank=True)  # new/indeterminate/done
    cached_summary = models.CharField(max_length=512, blank=True)
    fetched_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']
        constraints = [
            models.UniqueConstraint(fields=['ticket', 'key'],
                                    name='uniq_jira_key_per_ticket'),
        ]

    def __str__(self):
        return f'{self.key} → {self.ticket.display_number}'


class SiteNotice(models.Model):
    """An incident or maintenance notice shown in the portal (#49).

    This SUPPLEMENTS the notification channel EC-SOP-07 §5.2 commits to
    (email to the designated account contact) — it does not replace it. The
    banner shares fate with the portal: one host, one web container, so it is
    unreachable exactly when a SEV-1 is happening. Raising a notice here is
    never sufficient on its own.

    Deliberately NOT a public status page. §5.2 states we don't operate one, so
    every read path is behind a portal session. If that decision is ever
    revisited (the Engineering incident guide assumes a Statuspage and
    contradicts the SLA — see #49), this model is compatible with either
    outcome; only the gate on the read endpoint would move.
    """
    LEVEL_INFO = 'info'
    LEVEL_WARNING = 'warning'
    LEVEL_CRITICAL = 'critical'
    LEVEL_CHOICES = [
        (LEVEL_INFO, 'Info'),
        (LEVEL_WARNING, 'Warning'),
        (LEVEL_CRITICAL, 'Critical'),
    ]

    level = models.CharField(max_length=16, choices=LEVEL_CHOICES, default=LEVEL_INFO)
    message = models.TextField()
    # Optional "more detail" target — a docs page or a ticket thread.
    link_url = models.URLField(blank=True)
    link_label = models.CharField(max_length=64, blank=True)

    # Active window. starts_at in the future schedules a notice, which is what
    # the 72-hour maintenance notice in §3.2 needs. A null ends_at means
    # open-ended: an incident has no known end when it is raised.
    starts_at = models.DateTimeField(default=timezone.now)
    ends_at = models.DateTimeField(null=True, blank=True)
    # Set instead of deleting, so the customer-visible history TG-421 asked for
    # survives the incident being resolved.
    retired_at = models.DateTimeField(null=True, blank=True)

    # Empty = everyone. A SEV-2 frequently affects a subset of clients, and
    # telling the rest they're affected is its own kind of incident.
    companies = models.ManyToManyField(Company, blank=True, related_name='site_notices')
    created_by = models.ForeignKey(
        'PortalUser', null=True, blank=True, on_delete=models.SET_NULL,
        related_name='site_notices_created',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-starts_at']
        indexes = [
            models.Index(fields=['retired_at', 'starts_at']),
        ]

    def __str__(self):
        return f'[{self.level}] {self.message[:60]}'

    @property
    def is_dismissible(self):
        """Critical notices stay put. Enforced server-side too (the dismiss
        endpoint refuses them) — a hidden button is not a rule."""
        return self.level != self.LEVEL_CRITICAL

    def retire(self):
        self.retired_at = timezone.now()
        self.save(update_fields=['retired_at', 'updated_at'])

    @classmethod
    def currently_visible(cls, now=None, queryset=None):
        """Live notices: window open, not retired.

        Takes an optional base queryset so callers can compose this with
        `for_user` without restating the window rules — "what counts as live"
        must have exactly one definition.
        """
        now = now or timezone.now()
        base = cls.objects.all() if queryset is None else queryset
        return base.filter(
            retired_at__isnull=True, starts_at__lte=now,
        ).filter(models.Q(ends_at__isnull=True) | models.Q(ends_at__gt=now))

    @classmethod
    def for_user(cls, user):
        """Tenant-isolation chokepoint — the same rule as Ticket.for_user and
        Bucket.for_user. Read endpoints must query through here.

        Two ways a notice reaches someone: it is unscoped (platform-wide), or it
        names their company. Note that a user with no company (our own agents)
        sees platform-wide notices only — a company-scoped notice is about that
        client's data and isn't theirs to be told about via the banner.

        distinct() matters: the OR spans an M2M join, so a notice naming several
        companies would otherwise come back once per row.
        """
        if user is None or getattr(user, 'pk', None) is None:
            return cls.objects.none()
        unscoped = models.Q(companies__isnull=True)
        company_id = getattr(user, 'company_id', None)
        if company_id:
            return cls.objects.filter(
                unscoped | models.Q(companies__id=company_id)
            ).distinct()
        return cls.objects.filter(unscoped).distinct()


class NoticeDismissal(models.Model):
    """Per-user dismissal of a notice. Per-user rather than per-company: one
    colleague clearing a banner must not clear it for everyone else."""
    notice = models.ForeignKey(SiteNotice, on_delete=models.CASCADE, related_name='dismissals')
    user = models.ForeignKey('PortalUser', on_delete=models.CASCADE, related_name='notice_dismissals')
    dismissed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = (('notice', 'user'),)

    def __str__(self):
        return f'{self.user.email} dismissed {self.notice_id}'
