"""Pushing files the other way: staff → customer.

Two things are being asserted here that the customer-upload tests can't cover.

The first is that a delivered folder is genuinely read-only to the customer.
"Read-only" is not one check — it's four separate write paths (rename/delete,
move-in, move-out, upload-into) that each have to refuse independently, and a
guard on only the obvious one leaves the folder dismantlable a file at a time.

The second is that "who never opened this" is answerable. That question needs
the intended audience recorded at push time, which is what ShareNotice is for;
FileActivity records who DID act and so can never answer its negative.
"""
import json
from datetime import timedelta
from unittest.mock import patch

from django.core import mail
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from portal.models import Bucket, Company, PortalUser, SharedFile, ShareNotice


class PushTestBase(TestCase):
    def setUp(self):
        self.acme = Company.objects.create(name='Acme')
        self.rival = Company.objects.create(name='Rival')
        self.jane = PortalUser.objects.create(
            email='jane@acme.com', name='Jane', company=self.acme,
            role=PortalUser.ROLE_CUSTOMER)
        self.raj = PortalUser.objects.create(
            email='raj@acme.com', name='Raj', company=self.acme,
            role=PortalUser.ROLE_CUSTOMER)
        self.outsider = PortalUser.objects.create(
            email='bob@rival.com', company=self.rival, role=PortalUser.ROLE_CUSTOMER)
        self.staff = PortalUser.objects.create(
            email='csm@citemed.com', name='Ana', company=None,
            role=PortalUser.ROLE_ADMIN)
        self.general = Bucket.objects.create(
            company=self.acme, kind=Bucket.KIND_GENERAL,
            title='General uploads', status='general')
        # A folder we pushed, with one delivered file in it.
        self.shared = Bucket.objects.create(
            company=self.acme, kind=Bucket.KIND_FOLDER, title='Deliverables',
            status='general', origin=Bucket.ORIGIN_STAFF, created_by=self.staff)
        self.delivered = SharedFile.objects.create(
            bucket=self.shared, company=self.acme, uploaded_by=self.staff,
            original_name='CER.pdf', storage_key='k/cer.pdf',
            state=SharedFile.STATE_READY, size_bytes=10)

    def login(self, user):
        s = self.client.session
        s['portal_user_id'] = user.id
        s.save()

    def post(self, path, **body):
        # Named `path`, not `url` — link payloads carry a 'url' key of their own.
        return self.client.post(path, data=json.dumps(body),
                                content_type='application/json')


class StaffFolderIsReadOnlyToCustomerTest(PushTestBase):
    """Every write path into a delivered folder has to refuse separately."""

    def setUp(self):
        super().setUp()
        self.login(self.jane)

    def test_customer_cannot_rename_a_delivered_folder(self):
        r = self.client.patch(
            f'/api/files/folders/{self.shared.id}/',
            data=json.dumps({'title': 'Mine now'}), content_type='application/json')
        self.assertEqual(r.status_code, 403)
        self.shared.refresh_from_db()
        self.assertEqual(self.shared.title, 'Deliverables')

    def test_customer_cannot_delete_a_delivered_folder(self):
        r = self.client.delete(f'/api/files/folders/{self.shared.id}/')
        self.assertEqual(r.status_code, 403)
        self.assertTrue(Bucket.objects.filter(id=self.shared.id).exists())

    def test_customer_cannot_rename_or_delete_a_delivered_file(self):
        r = self.client.patch(
            f'/api/files/{self.delivered.id}',
            data=json.dumps({'name': 'whatever.pdf'}), content_type='application/json')
        self.assertEqual(r.status_code, 403)
        r = self.client.delete(f'/api/files/{self.delivered.id}')
        self.assertEqual(r.status_code, 403)
        self.delivered.refresh_from_db()
        self.assertIsNone(self.delivered.deleted_at)
        self.assertEqual(self.delivered.original_name, 'CER.pdf')

    @patch('portal.file_storage.presign_put', return_value='https://s3/put')
    def test_customer_cannot_upload_into_a_delivered_folder(self, _mock):
        r = self.post('/api/files/upload-init', name='mine.pdf', size=10,
                      bucket_id=self.shared.id)
        self.assertEqual(r.status_code, 403)

    def test_customer_cannot_move_files_into_a_delivered_folder(self):
        mine = SharedFile.objects.create(
            bucket=self.general, company=self.acme, uploaded_by=self.jane,
            original_name='mine.pdf', storage_key='k/mine.pdf',
            state=SharedFile.STATE_READY)
        r = self.post('/api/files/move/', file_ids=[mine.id], bucket_id=self.shared.id)
        self.assertEqual(r.status_code, 403)
        mine.refresh_from_db()
        self.assertEqual(mine.bucket_id, self.general.id)

    def test_customer_cannot_move_a_delivered_file_out(self):
        """The destination check alone doesn't stop this — without a guard on
        the SOURCE a customer could empty the folder we sent them one file at
        a time and the share would quietly cease to exist."""
        r = self.post('/api/files/move/', file_ids=[self.delivered.id],
                      bucket_id=self.general.id)
        self.assertEqual(r.status_code, 403)
        self.delivered.refresh_from_db()
        self.assertEqual(self.delivered.bucket_id, self.shared.id)

    def test_customer_cannot_nest_their_own_folder_inside_a_delivered_one(self):
        r = self.post('/api/files/folders/', title='Mine', parent_id=self.shared.id)
        self.assertEqual(r.status_code, 403)

    def test_customer_can_still_see_and_download_what_was_delivered(self):
        """Read-only must not mean invisible — the whole point is access."""
        r = self.client.get('/api/files/buckets/')
        titles = {b['title']: b for b in r.json()['buckets']}
        self.assertIn('Deliverables', titles)
        self.assertEqual(titles['Deliverables']['origin'], 'staff')
        self.assertEqual(
            [f['original_name'] for f in titles['Deliverables']['files']], ['CER.pdf'])

        with patch('portal.file_storage.presign_get', return_value='https://s3/get') as m:
            r = self.client.get(f'/api/files/{self.delivered.id}/download')
        self.assertEqual(r.status_code, 302)
        m.assert_called_once()


class LinkItemTest(PushTestBase):
    def setUp(self):
        super().setUp()
        self.login(self.staff)

    def test_staff_can_add_a_link_and_the_customer_sees_it(self):
        r = self.post('/api/admin/files/links/', bucket_id=self.shared.id,
                      name='QA results', url='https://qa.example.com/run/12')
        self.assertEqual(r.status_code, 201)
        body = r.json()['file']
        self.assertEqual(body['item_type'], 'link')
        self.assertEqual(body['external_url'], 'https://qa.example.com/run/12')
        self.assertIsNone(body['size_bytes'])

        self.login(self.jane)
        r = self.client.get('/api/files/buckets/')
        folder = next(b for b in r.json()['buckets'] if b['id'] == self.shared.id)
        link = next(f for f in folder['files'] if f['item_type'] == 'link')
        self.assertEqual(link['external_url'], 'https://qa.example.com/run/12')

    def test_non_http_schemes_are_refused(self):
        """Allowlist, not blocklist. These are rendered as something the
        customer clicks, so anything the browser handles specially is a
        hazard — enumerating those is a losing game."""
        for bad in ('javascript:alert(1)', 'data:text/html;base64,x',
                    'file:///etc/passwd', 'ftp://x.com/a', 'notaurl'):
            r = self.post('/api/admin/files/links/', bucket_id=self.shared.id,
                          name='bad', url=bad)
            self.assertEqual(r.status_code, 400, f'{bad} should be refused')
        self.assertFalse(
            SharedFile.objects.filter(item_type=SharedFile.ITEM_LINK).exists())

    def test_download_and_view_refuse_a_link_without_presigning(self):
        """A link row has an empty storage_key. Presigning it would hand back
        a signed URL to a key that doesn't exist, so both paths must branch
        BEFORE they reach storage."""
        r = self.post('/api/admin/files/links/', bucket_id=self.shared.id,
                      name='QA', url='https://qa.example.com/run/12')
        link_id = r.json()['file']['id']
        self.login(self.jane)
        with patch('portal.file_storage.presign_get') as pget, \
             patch('portal.file_storage.presign_view') as pview:
            self.assertEqual(
                self.client.get(f'/api/files/{link_id}/download').status_code, 400)
            self.assertEqual(
                self.client.get(f'/api/files/{link_id}/view').status_code, 400)
        pget.assert_not_called()
        pview.assert_not_called()


class SharePushTest(PushTestBase):
    def setUp(self):
        super().setUp()
        self.login(self.staff)

    def test_push_notifies_each_person_separately(self):
        r = self.post('/api/admin/files/share/', bucket_id=self.shared.id,
                      recipient_ids=[self.jane.id, self.raj.id])
        self.assertEqual(r.status_code, 201)
        self.assertEqual(ShareNotice.objects.count(), 2)
        # One message each, not one addressed to both: who else was notified
        # isn't the customer's business, and the reminder loop needs to be
        # able to follow up with just one of them later.
        self.assertEqual(len(mail.outbox), 2)
        self.assertEqual(
            sorted(to for m in mail.outbox for to in m.to),
            ['jane@acme.com', 'raj@acme.com'])

    def test_push_refuses_someone_from_another_company(self):
        r = self.post('/api/admin/files/share/', bucket_id=self.shared.id,
                      recipient_ids=[self.jane.id, self.outsider.id])
        self.assertEqual(r.status_code, 400)
        # Refused wholesale rather than silently notifying the valid subset —
        # a partial push looks identical to a working one until a customer
        # says they never heard.
        self.assertEqual(ShareNotice.objects.count(), 0)
        self.assertEqual(len(mail.outbox), 0)

    def test_push_refuses_a_disabled_account(self):
        self.raj.access_enabled = False
        self.raj.save(update_fields=['access_enabled'])
        r = self.post('/api/admin/files/share/', bucket_id=self.shared.id,
                      recipient_ids=[self.raj.id])
        self.assertEqual(r.status_code, 400)
        self.assertEqual(ShareNotice.objects.count(), 0)

    def test_members_endpoint_lists_only_that_company(self):
        r = self.client.get(f'/api/admin/files/companies/{self.acme.id}/members')
        emails = {m['email'] for m in r.json()['members']}
        self.assertEqual(emails, {'jane@acme.com', 'raj@acme.com'})

    def test_status_reports_each_person(self):
        self.post('/api/admin/files/share/', bucket_id=self.shared.id,
                  recipient_ids=[self.jane.id, self.raj.id])
        ShareNotice.objects.filter(recipient=self.jane).update(
            first_opened_at=timezone.now())
        r = self.client.get(f'/api/admin/files/share/{self.shared.id}/')
        body = r.json()
        self.assertEqual(body['total'], 2)
        self.assertEqual(body['opened'], 1)
        by_email = {p['email']: p for p in body['recipients']}
        self.assertIsNotNone(by_email['jane@acme.com']['opened_at'])
        self.assertIsNone(by_email['raj@acme.com']['opened_at'])


class OpenTrackingTest(PushTestBase):
    def test_downloading_marks_the_notice_opened_once(self):
        n = ShareNotice.objects.create(
            bucket=self.shared, recipient=self.jane, sent_by=self.staff)
        self.login(self.jane)
        with patch('portal.file_storage.presign_get', return_value='https://s3/get'):
            self.client.get(f'/api/files/{self.delivered.id}/download')
        n.refresh_from_db()
        self.assertIsNotNone(n.first_opened_at)

        first = n.first_opened_at
        with patch('portal.file_storage.presign_get', return_value='https://s3/get'):
            self.client.get(f'/api/files/{self.delivered.id}/download')
        n.refresh_from_db()
        self.assertEqual(n.first_opened_at, first, 'only the first open counts')

    def test_opening_a_file_in_a_subfolder_satisfies_the_parent_notice(self):
        """We push a folder; they open something two levels down inside it.
        That is plainly them having opened what we sent."""
        sub = Bucket.objects.create(
            company=self.acme, kind=Bucket.KIND_FOLDER, title='Round 2',
            parent=self.shared, status='general', origin=Bucket.ORIGIN_STAFF)
        deep = SharedFile.objects.create(
            bucket=sub, company=self.acme, original_name='v2.pdf',
            storage_key='k/v2.pdf', state=SharedFile.STATE_READY)
        n = ShareNotice.objects.create(
            bucket=self.shared, recipient=self.jane, sent_by=self.staff)
        self.login(self.jane)
        with patch('portal.file_storage.presign_get', return_value='https://s3/get'):
            self.client.get(f'/api/files/{deep.id}/download')
        n.refresh_from_db()
        self.assertIsNotNone(n.first_opened_at)

    def test_another_persons_open_does_not_clear_your_notice(self):
        jane_n = ShareNotice.objects.create(
            bucket=self.shared, recipient=self.jane, sent_by=self.staff)
        raj_n = ShareNotice.objects.create(
            bucket=self.shared, recipient=self.raj, sent_by=self.staff)
        self.login(self.jane)
        with patch('portal.file_storage.presign_get', return_value='https://s3/get'):
            self.client.get(f'/api/files/{self.delivered.id}/download')
        jane_n.refresh_from_db()
        raj_n.refresh_from_db()
        self.assertIsNotNone(jane_n.first_opened_at)
        self.assertIsNone(raj_n.first_opened_at)

    def test_clicking_a_link_reports_the_open(self):
        """Nothing hits Django when a browser follows an external link, so the
        client reports it — and the endpoint is deliberately not a redirect,
        which would make the portal an authenticated open-redirector."""
        link = SharedFile.objects.create(
            bucket=self.shared, company=self.acme, original_name='QA',
            item_type=SharedFile.ITEM_LINK, external_url='https://qa.example.com/1',
            storage_key='', state=SharedFile.STATE_READY)
        n = ShareNotice.objects.create(
            bucket=self.shared, file=link, recipient=self.jane, sent_by=self.staff)
        self.login(self.jane)
        r = self.post(f'/api/files/{link.id}/opened')
        self.assertEqual(r.status_code, 200)
        n.refresh_from_db()
        self.assertIsNotNone(n.first_opened_at)


class ReminderCadenceTest(PushTestBase):
    """Two nudges, at 3 and 7 days, then silent for good."""

    def _notice(self, days_ago, **kw):
        n = ShareNotice.objects.create(
            bucket=self.shared, recipient=self.jane, sent_by=self.staff, **kw)
        # sent_at is auto_now_add, so age it explicitly.
        ShareNotice.objects.filter(pk=n.pk).update(
            sent_at=timezone.now() - timedelta(days=days_ago))
        n.refresh_from_db()
        return n

    def test_nothing_before_the_first_threshold(self):
        self._notice(days_ago=2)
        call_command('send_share_reminders')
        self.assertEqual(len(mail.outbox), 0)

    def test_first_nudge_at_three_days(self):
        n = self._notice(days_ago=3)
        call_command('send_share_reminders')
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('jane@acme.com', mail.outbox[0].to)
        n.refresh_from_db()
        self.assertEqual(n.reminder_count, 1)

    def test_second_nudge_waits_for_seven_days(self):
        """Both thresholds are measured from the push, not from the previous
        nudge — otherwise a late first reminder drags the second one out."""
        n = self._notice(days_ago=4, reminder_count=1)
        ShareNotice.objects.filter(pk=n.pk).update(
            last_reminder_at=timezone.now() - timedelta(days=1))
        call_command('send_share_reminders')
        self.assertEqual(len(mail.outbox), 0)

        ShareNotice.objects.filter(pk=n.pk).update(
            sent_at=timezone.now() - timedelta(days=7))
        call_command('send_share_reminders')
        self.assertEqual(len(mail.outbox), 1)
        n.refresh_from_db()
        self.assertEqual(n.reminder_count, 2)

    def test_it_stops_after_two_and_never_speaks_again(self):
        self._notice(days_ago=90, reminder_count=ShareNotice.MAX_REMINDERS)
        call_command('send_share_reminders')
        self.assertEqual(len(mail.outbox), 0)

    def test_an_opened_share_is_never_nudged(self):
        self._notice(days_ago=30, first_opened_at=timezone.now())
        call_command('send_share_reminders')
        self.assertEqual(len(mail.outbox), 0)

    def test_push_can_opt_out_of_nudging_entirely(self):
        self._notice(days_ago=30, remind=False)
        call_command('send_share_reminders')
        self.assertEqual(len(mail.outbox), 0)

    def test_running_twice_in_a_day_sends_one_email(self):
        self._notice(days_ago=3)
        call_command('send_share_reminders')
        call_command('send_share_reminders')
        self.assertEqual(len(mail.outbox), 1)

    def test_dry_run_sends_nothing_and_records_nothing(self):
        n = self._notice(days_ago=3)
        call_command('send_share_reminders', '--dry-run')
        self.assertEqual(len(mail.outbox), 0)
        n.refresh_from_db()
        self.assertEqual(n.reminder_count, 0)


class StaffFolderCreationTest(PushTestBase):
    def setUp(self):
        super().setUp()
        self.login(self.staff)

    def test_staff_folder_lands_in_the_customers_tree_as_ours(self):
        r = self.post('/api/admin/files/folders/', company_id=self.acme.id,
                      title='Q3 CER')
        self.assertEqual(r.status_code, 201)
        folder = Bucket.objects.get(id=r.json()['folder']['id'])
        self.assertEqual(folder.company_id, self.acme.id)
        self.assertEqual(folder.origin, Bucket.ORIGIN_STAFF)
        self.assertTrue(folder.is_staff_origin)

    def test_a_staff_folder_cannot_be_nested_under_a_customer_folder(self):
        """It would become deletable by them via a parent they do control."""
        theirs = Bucket.objects.create(
            company=self.acme, kind=Bucket.KIND_FOLDER, title='Theirs',
            status='general', origin=Bucket.ORIGIN_CUSTOMER)
        r = self.post('/api/admin/files/folders/', company_id=self.acme.id,
                      title='Ours', parent_id=theirs.id)
        self.assertEqual(r.status_code, 400)

    def test_same_name_on_both_sides_is_allowed(self):
        """A customer "Reports" and a CiteMed "Reports" render in separate
        sections, so they are not siblings on screen and refusing the second
        would be an error about a folder the user may not be able to see."""
        Bucket.objects.create(
            company=self.acme, kind=Bucket.KIND_FOLDER, title='Reports',
            status='general', origin=Bucket.ORIGIN_CUSTOMER)
        r = self.post('/api/admin/files/folders/', company_id=self.acme.id,
                      title='Reports')
        self.assertEqual(r.status_code, 201)

    def test_deleting_a_staff_folder_with_files_is_refused(self):
        r = self.client.delete(f'/api/admin/files/folders/{self.shared.id}/')
        self.assertEqual(r.status_code, 409)
        self.assertTrue(Bucket.objects.filter(id=self.shared.id).exists())

    def test_staff_endpoints_refuse_a_customers_own_folder(self):
        theirs = Bucket.objects.create(
            company=self.acme, kind=Bucket.KIND_FOLDER, title='Theirs',
            status='general', origin=Bucket.ORIGIN_CUSTOMER)
        r = self.client.patch(
            f'/api/admin/files/folders/{theirs.id}/',
            data=json.dumps({'title': 'Renamed'}), content_type='application/json')
        self.assertEqual(r.status_code, 404)
        theirs.refresh_from_db()
        self.assertEqual(theirs.title, 'Theirs')
