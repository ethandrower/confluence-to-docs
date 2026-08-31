"""The outbound half of file activity at /api/v1/share-events/.

Two things are under test here, and the second is the reason the endpoint
needed a new model field rather than just a new view.

**The tenant boundary.** Like the rest of `portal.api_v1` this queryset uses
`ShareNotice.objects` directly and crosses between customers on purpose, so
the bearer token is the only thing guarding it. The token cases are asserted
here rather than assumed from test_api_v1.py, because a namespace that grew a
second door would still pass that file.

**The sync contract.** A share event's interesting moments arrive *after* the
row is written: the push is the boring half, the open is what a health score
turns on, and it lands days later. A consumer polls with `updated_since` and
walks an ascending cursor, so a change that does not move the row's ordering
key is a change the consumer never sees — its cursor is already past it.

`ShareNotice.updated_at` exists for that, and keeping it correct is not
automatic: `auto_now` fires on `save()`, and the two ways this row actually
changes are a queryset `.update()` (`mark_opened`) and a
`save(update_fields=[...])` (`send_share_reminders`), neither of which triggers
it by default. `test_an_open_is_visible_to_a_consumer_that_already_synced_the_push`
is the regression guard: it fails if either of those write sites stops setting
the column, and it fails in the way the bug would actually be noticed — as a
delivery that looks permanently unopened.
"""
import json
from datetime import timedelta

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from portal.models import (
    ApiClient, Bucket, Company, PortalUser, ShareNotice, SharedFile,
)


class ShareEventTestCase(TestCase):
    URL = '/api/v1/share-events/'

    def setUp(self):
        self.client_obj, self.token = ApiClient.issue('RevenueHub')

        self.acme = Company.objects.create(name='Acme Medical')
        self.globex = Company.objects.create(name='Globex Devices')

        self.jane = PortalUser.objects.create(email='jane@acme.com', company=self.acme)
        self.bob = PortalUser.objects.create(email='bob@acme.com', company=self.acme)
        self.zed = PortalUser.objects.create(email='zed@globex.com', company=self.globex)
        self.agent = PortalUser.objects.create(
            email='csm@citemed.com', role=PortalUser.ROLE_ADMIN)

        # A folder we pushed to Acme, holding one real file and one link.
        self.folder = Bucket.objects.create(
            company=self.acme, kind=Bucket.KIND_FOLDER,
            origin=Bucket.ORIGIN_STAFF, title='Q3 audit pack', status='open')
        self.report = SharedFile.objects.create(
            bucket=self.folder, company=self.acme, original_name='audit-report.pdf',
            storage_key='k/audit-report.pdf', state=SharedFile.STATE_READY)
        self.link = SharedFile.objects.create(
            bucket=self.folder, company=self.acme, original_name='QA dashboard',
            storage_key='', state=SharedFile.STATE_READY,
            item_type=SharedFile.ITEM_LINK,
            external_url='https://internal.example.com/secret-dashboard')

    # ── helpers ──────────────────────────────────────────────────────────

    def auth(self, token=None):
        return {'HTTP_AUTHORIZATION': f'Bearer {token or self.token}'}

    def get(self, path=None, token=None):
        return self.client.get(path or self.URL, **self.auth(token))

    def rows(self, path=None, token=None):
        r = self.get(path, token)
        self.assertEqual(r.status_code, 200, r.content)
        return json.loads(r.content)['results']

    def push(self, recipient, file=None, folder=None, remind=True):
        return ShareNotice.objects.create(
            bucket=folder or self.folder, file=file, recipient=recipient,
            sent_by=self.agent, remind=remind)

    @staticmethod
    def age(notice, **delta):
        """Backdate a notice's timestamps as if the push were older."""
        when = timezone.now() - timedelta(**delta)
        ShareNotice.objects.filter(pk=notice.pk).update(sent_at=when, updated_at=when)
        notice.refresh_from_db()
        return notice

    # ── the token is the only guard ──────────────────────────────────────

    def test_no_token_is_rejected(self):
        self.assertEqual(self.client.get(self.URL).status_code, 401)

    def test_a_bad_token_is_rejected(self):
        self.assertEqual(self.get(token='not-a-real-token').status_code, 401)

    def test_a_revoked_token_is_rejected(self):
        self.client_obj.enabled = False
        self.client_obj.save(update_fields=['enabled'])
        self.assertEqual(self.get().status_code, 401)

    def test_a_session_login_is_not_a_second_door(self):
        """The customer session must not authenticate a cross-tenant API."""
        s = self.client.session
        s['portal_user_id'] = self.jane.id
        s.save()
        self.assertEqual(self.client.get(self.URL).status_code, 401)

    def test_the_endpoint_is_read_only(self):
        for method in (self.client.post, self.client.put, self.client.delete):
            self.assertEqual(method(self.URL, **self.auth()).status_code, 405)

    # ── payload shape ────────────────────────────────────────────────────

    def test_a_folder_push_reports_the_folder_and_no_item(self):
        self.push(self.jane)
        (row,) = self.rows()
        self.assertEqual(row['company'], {'id': self.acme.id, 'name': 'Acme Medical'})
        self.assertEqual(row['folder'],
                         {'id': self.folder.id, 'title': 'Q3 audit pack'})
        # Null item is the payload's way of saying "we sent the whole folder",
        # which stays true as staff add to it afterwards.
        self.assertIsNone(row['item'])
        self.assertEqual(row['recipient_email'], 'jane@acme.com')
        self.assertEqual(row['sent_by_email'], 'csm@citemed.com')
        self.assertFalse(row['opened'])
        self.assertIsNone(row['first_opened_at'])
        self.assertEqual(row['reminder_count'], 0)
        self.assertTrue(row['remind'])

    def test_a_single_item_push_names_the_item(self):
        self.push(self.jane, file=self.report)
        (row,) = self.rows()
        self.assertEqual(row['item'], {
            'id': self.report.id,
            'name': 'audit-report.pdf',
            'item_type': 'file',
        })

    def test_a_pushed_link_is_reported_without_its_target(self):
        """A link's URL points outside the portal and a health dashboard has
        no use for it, so it stays out on the same principle as message
        bodies. Asserted against the raw bytes, so a future field carrying it
        would still trip this."""
        self.push(self.jane, file=self.link)
        r = self.get()
        self.assertNotIn(b'secret-dashboard', r.content)
        self.assertEqual(json.loads(r.content)['results'][0]['item']['item_type'],
                         'link')

    def test_no_storage_key_or_download_url_leaks(self):
        self.push(self.jane, file=self.report)
        body = self.get().content
        self.assertNotIn(b'storage_key', body)
        self.assertNotIn(b'k/audit-report.pdf', body)

    def test_a_deleted_staff_account_leaves_an_empty_sender_not_a_null(self):
        n = self.push(self.jane)
        self.agent.delete()  # sent_by is SET_NULL
        n.refresh_from_db()
        (row,) = self.rows()
        self.assertEqual(row['sent_by_email'], '')

    # ── the sync contract ────────────────────────────────────────────────

    def test_an_open_is_visible_to_a_consumer_that_already_synced_the_push(self):
        """The regression guard for the whole design.

        A consumer syncs the push, stores a watermark, and only then does the
        customer open it. If an open did not move `updated_at`, the row would
        sit behind the consumer's cursor for good and RevenueHub would show a
        delivery that is opened as permanently unopened.
        """
        notice = self.age(self.push(self.jane), days=2)
        watermark = timezone.now()  # consumer has synced everything so far
        self.assertEqual(self.rows(f'{self.URL}?updated_since={watermark.isoformat()}'), [])

        ShareNotice.mark_opened(self.jane, self.report)

        (row,) = self.rows(f'{self.URL}?updated_since={watermark.isoformat()}')
        self.assertEqual(row['id'], notice.id)
        self.assertTrue(row['opened'])

        # And the contrast that makes the point: the push itself is still old,
        # so a feed keyed on when we sent it would have shown nothing here.
        self.assertEqual(
            self.rows(f'{self.URL}?sent_since={watermark.isoformat()}'), [])

    def test_mark_opened_moves_updated_at_despite_being_a_queryset_update(self):
        """mark_opened never calls save(), so auto_now cannot fire for it and
        the column has to be written by hand. This fails if that is dropped."""
        notice = self.age(self.push(self.jane), days=2)
        before = notice.updated_at
        ShareNotice.mark_opened(self.jane, self.report)
        notice.refresh_from_db()
        self.assertGreater(notice.updated_at, before)

    def test_a_reminder_moves_updated_at_despite_update_fields(self):
        """send_share_reminders saves with update_fields, which writes only the
        names it is given — so updated_at has to be one of them."""
        notice = self.age(self.push(self.jane), days=4)  # first nudge is due at 3
        before = notice.updated_at
        call_command('send_share_reminders')
        notice.refresh_from_db()
        self.assertEqual(notice.reminder_count, 1)
        self.assertGreater(notice.updated_at, before)

    def test_a_reminder_reaches_a_consumer_that_had_already_synced(self):
        notice = self.age(self.push(self.jane), days=4)
        watermark = timezone.now()
        call_command('send_share_reminders')
        (row,) = self.rows(f'{self.URL}?updated_since={watermark.isoformat()}')
        self.assertEqual(row['id'], notice.id)
        self.assertEqual(row['reminder_count'], 1)

    def test_rows_come_back_oldest_change_first(self):
        """Ascending is what makes the cursor resumable; asserting it here
        stops a future 'newest first' tidy-up from silently breaking sync."""
        first = self.age(self.push(self.jane), days=5)
        second = self.age(self.push(self.bob), days=1)
        self.assertEqual([r['id'] for r in self.rows()], [first.id, second.id])

    # ── filters ──────────────────────────────────────────────────────────

    def test_company_id_filters_across_the_tenant_boundary(self):
        self.push(self.jane)
        other = Bucket.objects.create(
            company=self.globex, kind=Bucket.KIND_FOLDER,
            origin=Bucket.ORIGIN_STAFF, title='Globex pack', status='open')
        self.push(self.zed, folder=other)

        self.assertEqual(len(self.rows()), 2)  # both, by design
        rows = self.rows(f'{self.URL}?company_id={self.globex.id}')
        self.assertEqual([r['recipient_email'] for r in rows], ['zed@globex.com'])

    def test_opened_filter_has_three_states(self):
        opened = self.push(self.jane)
        unopened = self.push(self.bob)
        ShareNotice.mark_opened(self.jane, self.report)

        self.assertEqual(len(self.rows()), 2)
        self.assertEqual([r['id'] for r in self.rows(f'{self.URL}?opened=true')],
                         [opened.id])
        self.assertEqual([r['id'] for r in self.rows(f'{self.URL}?opened=false')],
                         [unopened.id])

    def test_an_absent_opened_filter_does_not_mean_false(self):
        """The bug this guards: defaulting the flag to False would turn every
        unfiltered poll into 'unopened only' and hide successful deliveries."""
        self.push(self.jane)
        ShareNotice.mark_opened(self.jane, self.report)
        self.assertEqual(len(self.rows()), 1)

    def test_recipient_email_is_matched_case_insensitively(self):
        self.push(self.jane)
        self.push(self.bob)
        rows = self.rows(f'{self.URL}?recipient_email=JANE@ACME.COM')
        self.assertEqual([r['recipient_email'] for r in rows], ['jane@acme.com'])

    def test_a_malformed_timestamp_is_a_400_not_a_500(self):
        self.assertEqual(self.get(f'{self.URL}?updated_since=yesterday').status_code, 400)

    # ── query cost ───────────────────────────────────────────────────────

    def test_a_page_does_not_issue_a_query_per_row(self):
        """Every traversal the serializer makes is select_related, so adding
        rows must not add queries. Without that a 100-row page is 401."""
        for i in range(6):
            u = PortalUser.objects.create(email=f'u{i}@acme.com', company=self.acme)
            self.push(u, file=self.report)
        with self.assertNumQueries(3):  # auth, count/page, rows
            self.get()
