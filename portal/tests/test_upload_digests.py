"""Upload notifications are batched, not one email per file.

The bug these guard: `upload_complete` called `notify_upload(f)` inline, once
per file. A customer dragging in a 150-file folder sent 150 emails to every
agent and the shared inbox, and made 150 blocking mail calls on the request
path — four at a time, since uploads run concurrently. Folder upload made that
trivially reachable.
"""
from datetime import timedelta
from unittest.mock import patch

from django.core import mail
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone

from portal.models import Bucket, Company, PortalUser, SharedFile


@override_settings(SUPPORT_EMAIL='support@citemed.com')
class UploadDigestTest(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name='Acme')
        self.agent = PortalUser.objects.create(
            email='alice@citemed.com', role=PortalUser.ROLE_ADMIN)
        self.csm = PortalUser.objects.create(
            email='csm@citemed.com', role=PortalUser.ROLE_ADMIN)
        self.general = Bucket.objects.create(
            company=self.company, kind=Bucket.KIND_GENERAL,
            title='General uploads', status='general')

    def mkfile(self, name, bucket=None, *, age_seconds=600, state=None, deleted=False):
        """A settled upload by default — old enough for the sweep to pick up."""
        f = SharedFile.objects.create(
            bucket=bucket or self.general, company=self.company, original_name=name,
            storage_key=f'k/{name}', state=state or SharedFile.STATE_READY,
            deleted_at=timezone.now() if deleted else None)
        SharedFile.objects.filter(id=f.id).update(
            uploaded_at=timezone.now() - timedelta(seconds=age_seconds))
        return f

    # ── The batching itself ──────────────────────────────────────────────

    def test_a_folder_upload_sends_one_email_not_one_per_file(self):
        for i in range(150):
            self.mkfile(f'report-{i}.pdf')
        call_command('send_upload_digests')
        self.assertEqual(len(mail.outbox), 1)

    def test_the_email_counts_the_batch_and_names_a_few(self):
        for i in range(5):
            self.mkfile(f'report-{i}.pdf')
        call_command('send_upload_digests')
        body = mail.outbox[0].body
        self.assertIn('5 files', body)
        self.assertIn('report-0.pdf', body)
        self.assertIn('and 2 more', body)  # 5 files, 3 shown

    def test_a_lone_upload_still_reads_as_one_file(self):
        self.mkfile('solo.pdf')
        call_command('send_upload_digests')
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('solo.pdf', mail.outbox[0].body)
        self.assertNotIn('and 0 more', mail.outbox[0].body)

    def test_uploads_are_reported_once(self):
        self.mkfile('a.pdf')
        call_command('send_upload_digests')
        call_command('send_upload_digests')
        self.assertEqual(len(mail.outbox), 1)

    # ── The settle window ────────────────────────────────────────────────

    def test_a_still_arriving_batch_is_left_for_the_next_pass(self):
        # Splitting a batch across two emails is the thing the window exists to
        # avoid, so anything younger than it is deliberately skipped.
        self.mkfile('fresh.pdf', age_seconds=5)
        call_command('send_upload_digests')
        self.assertEqual(len(mail.outbox), 0)

    def test_the_window_is_adjustable_so_a_burst_can_be_flushed(self):
        self.mkfile('fresh.pdf', age_seconds=5)
        call_command('send_upload_digests', '--settle', '1')
        self.assertEqual(len(mail.outbox), 1)

    # ── Routing is unchanged, only the number of messages ────────────────

    def test_request_uploads_still_go_to_the_csm_and_not_the_whole_team(self):
        req = Bucket.objects.create(
            company=self.company, kind=Bucket.KIND_REQUEST,
            title='Send us the DoC', requested_by=self.csm, status='open')
        self.mkfile('doc.pdf', req)
        call_command('send_upload_digests')
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('csm@citemed.com', mail.outbox[0].to)
        self.assertNotIn('alice@citemed.com', mail.outbox[0].to)

    def test_two_audiences_get_two_emails_rather_than_one_merged_one(self):
        """Collapsing per company would either leak a CSM's request files to
        the whole team or hide them from it. Grouping on the resolved
        recipients keeps who-hears-what exactly as it was."""
        req = Bucket.objects.create(
            company=self.company, kind=Bucket.KIND_REQUEST,
            title='Send us the DoC', requested_by=self.csm, status='open')
        self.mkfile('for-csm.pdf', req)
        self.mkfile('for-everyone.pdf')
        call_command('send_upload_digests')
        self.assertEqual(len(mail.outbox), 2)
        by_to = {tuple(sorted(m.to)): m for m in mail.outbox}
        csm_mail = [m for k, m in by_to.items() if 'csm@citemed.com' in k][0]
        self.assertNotIn('alice@citemed.com', csm_mail.to)

    def test_two_companies_are_never_mentioned_in_the_same_email(self):
        other = Company.objects.create(name='Rival')
        SharedFile.objects.create(
            bucket=Bucket.objects.create(
                company=other, kind=Bucket.KIND_GENERAL,
                title='General uploads', status='general'),
            company=other, original_name='theirs.pdf', storage_key='k/theirs',
            state=SharedFile.STATE_READY)
        SharedFile.objects.update(uploaded_at=timezone.now() - timedelta(seconds=600))
        self.mkfile('ours.pdf')
        call_command('send_upload_digests')
        self.assertEqual(len(mail.outbox), 2)
        for m in mail.outbox:
            self.assertFalse('theirs.pdf' in m.body and 'ours.pdf' in m.body)

    # ── What must never be reported ──────────────────────────────────────

    def test_an_unfinished_upload_is_not_announced(self):
        self.mkfile('half.pdf', state=SharedFile.STATE_UPLOADING)
        call_command('send_upload_digests')
        self.assertEqual(len(mail.outbox), 0)

    def test_a_deleted_file_is_not_announced(self):
        self.mkfile('gone.pdf', deleted=True)
        call_command('send_upload_digests')
        self.assertEqual(len(mail.outbox), 0)

    # ── Failure and dry-run behaviour ────────────────────────────────────

    def test_a_failed_send_is_retried_rather_than_silently_dropped(self):
        f = self.mkfile('a.pdf')
        with patch('portal.file_notify.notify_upload_batch', side_effect=Exception('smtp down')):
            call_command('send_upload_digests')
        f.refresh_from_db()
        self.assertIsNone(f.notified_at)
        call_command('send_upload_digests')
        self.assertEqual(len(mail.outbox), 1)

    def test_one_bad_company_does_not_strand_the_others(self):
        other = Company.objects.create(name='Rival')
        Bucket.objects.create(company=other, kind=Bucket.KIND_GENERAL,
                              title='General uploads', status='general')
        self.mkfile('ours.pdf')
        calls = {'n': 0}

        def flaky(company, files, recipients):
            calls['n'] += 1
            if calls['n'] == 1:
                raise Exception('bad address')

        with patch('portal.file_notify.notify_upload_batch', side_effect=flaky):
            call_command('send_upload_digests')
        self.assertEqual(calls['n'], 1)  # only one group existed; it failed cleanly

    def test_dry_run_neither_sends_nor_marks(self):
        f = self.mkfile('a.pdf')
        call_command('send_upload_digests', '--dry-run')
        f.refresh_from_db()
        self.assertEqual(len(mail.outbox), 0)
        self.assertIsNone(f.notified_at)


@override_settings(SUPPORT_EMAIL='support@citemed.com')
class UploadCompleteDoesNotEmailTest(TestCase):
    """The regression guard: completing an upload must not send mail on the
    request path, however many files are in flight."""

    def setUp(self):
        self.company = Company.objects.create(name='Acme')
        PortalUser.objects.create(email='alice@citemed.com', role=PortalUser.ROLE_ADMIN)
        self.jane = PortalUser.objects.create(
            email='jane@acme.com', company=self.company, role=PortalUser.ROLE_CUSTOMER)
        self.general = Bucket.objects.create(
            company=self.company, kind=Bucket.KIND_GENERAL,
            title='General uploads', status='general')
        s = self.client.session
        s['portal_user_id'] = self.jane.id
        s.save()

    @patch('portal.file_storage.signature_ok', return_value=True)
    @patch('portal.file_storage.head_size', return_value=10)
    def test_completing_an_upload_sends_no_mail(self, _size, _sig):
        f = SharedFile.objects.create(
            bucket=self.general, company=self.company, original_name='a.pdf',
            storage_key='k/a', state=SharedFile.STATE_UPLOADING)
        r = self.client.post(
            '/api/files/upload-complete',
            data={'file_id': f.id}, content_type='application/json')
        self.assertEqual(r.status_code, 200)
        f.refresh_from_db()
        self.assertEqual(f.state, SharedFile.STATE_READY)
        self.assertEqual(len(mail.outbox), 0)
        # Left for the sweep rather than dropped entirely.
        self.assertIsNone(f.notified_at)
