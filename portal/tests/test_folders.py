"""Customer-created folder tree (GitHub #41).

The interesting tests here are the tenant-isolation ones. A file's `company`
does not change when it moves between folders, so a naive check on the object
being moved would still pass while the object lands under another customer's
folder. Both the folder re-parent and the file move must resolve their
DESTINATION through the scoped manager, and that's what these assert.
"""
import json

from django.core import mail
from django.test import TestCase, override_settings

from portal.models import Bucket, Company, PortalUser, SharedFile


class FolderTestBase(TestCase):
    def setUp(self):
        self.acme = Company.objects.create(name='Acme')
        self.rival = Company.objects.create(name='Rival')
        self.jane = PortalUser.objects.create(
            email='jane@acme.com', company=self.acme, role=PortalUser.ROLE_CUSTOMER)
        self.rival_user = PortalUser.objects.create(
            email='bob@rival.com', company=self.rival, role=PortalUser.ROLE_CUSTOMER)
        self.general = Bucket.objects.create(
            company=self.acme, kind=Bucket.KIND_GENERAL,
            title='General uploads', status='general')
        self.login(self.jane)

    def login(self, user):
        s = self.client.session
        s['portal_user_id'] = user.id
        s.save()

    def mkfolder(self, title, parent=None, company=None):
        return Bucket.objects.create(
            company=company or self.acme, kind=Bucket.KIND_FOLDER,
            title=title, parent=parent, status='general')

    def create(self, title, parent_id=None):
        return self.client.post(
            '/api/files/folders/',
            data=json.dumps({'title': title, 'parent_id': parent_id}),
            content_type='application/json')

    def patch(self, folder_id, **body):
        return self.client.patch(
            f'/api/files/folders/{folder_id}/',
            data=json.dumps(body), content_type='application/json')


class FolderCreateTest(FolderTestBase):
    def test_creates_a_top_level_folder(self):
        r = self.create('Clinical Data')
        self.assertEqual(r.status_code, 201)
        f = Bucket.objects.get(title='Clinical Data')
        self.assertEqual(f.kind, Bucket.KIND_FOLDER)
        self.assertIsNone(f.parent)
        self.assertEqual(f.company, self.acme)
        self.assertEqual(f.created_by, self.jane)

    def test_creates_a_subfolder(self):
        parent = self.mkfolder('Clinical Data')
        r = self.create('2026', parent_id=parent.id)
        self.assertEqual(r.status_code, 201)
        self.assertEqual(Bucket.objects.get(title='2026').parent, parent)

    def test_a_request_bucket_cannot_be_a_parent(self):
        """Requests are tasks with due dates. Nesting one inside a customer's
        folder tree is how a request gets buried and missed."""
        req = Bucket.objects.create(
            company=self.acme, kind=Bucket.KIND_REQUEST, title='Send us the DoC')
        r = self.create('Hidden', parent_id=req.id)
        self.assertEqual(r.status_code, 400)
        self.assertFalse(Bucket.objects.filter(title='Hidden').exists())

    def test_the_general_bucket_cannot_be_a_parent(self):
        r = self.create('Nested', parent_id=self.general.id)
        self.assertEqual(r.status_code, 400)

    def test_duplicate_sibling_names_are_refused(self):
        self.mkfolder('Reports')
        r = self.create('Reports')
        self.assertEqual(r.status_code, 409)

    def test_the_same_name_is_fine_under_a_different_parent(self):
        a = self.mkfolder('2025')
        self.mkfolder('Reports', parent=a)
        b = self.mkfolder('2026')
        r = self.create('Reports', parent_id=b.id)
        self.assertEqual(r.status_code, 201)

    def test_a_blank_name_is_refused(self):
        self.assertEqual(self.create('   ').status_code, 400)

    def test_depth_is_capped(self):
        parent = None
        for i in range(Bucket.MAX_DEPTH):
            parent = self.mkfolder(f'L{i}', parent=parent)
        r = self.create('too deep', parent_id=parent.id)
        self.assertEqual(r.status_code, 400)


class FolderTenantIsolationTest(FolderTestBase):
    def test_cannot_create_a_folder_under_another_companys_folder(self):
        theirs = self.mkfolder('Their Files', company=self.rival)
        r = self.create('Mine', parent_id=theirs.id)
        # 404, not 403: a folder they can't see shouldn't be confirmed to exist.
        self.assertEqual(r.status_code, 404)
        self.assertFalse(Bucket.objects.filter(title='Mine').exists())

    def test_cannot_rename_another_companys_folder(self):
        theirs = self.mkfolder('Their Files', company=self.rival)
        r = self.patch(theirs.id, title='Pwned')
        self.assertEqual(r.status_code, 404)
        theirs.refresh_from_db()
        self.assertEqual(theirs.title, 'Their Files')

    def test_cannot_move_a_folder_into_another_companys_tree(self):
        mine = self.mkfolder('Mine')
        theirs = self.mkfolder('Theirs', company=self.rival)
        r = self.patch(mine.id, parent_id=theirs.id)
        self.assertEqual(r.status_code, 404)
        mine.refresh_from_db()
        self.assertIsNone(mine.parent)

    def test_cannot_delete_another_companys_folder(self):
        theirs = self.mkfolder('Theirs', company=self.rival)
        r = self.client.delete(f'/api/files/folders/{theirs.id}/')
        self.assertEqual(r.status_code, 404)
        self.assertTrue(Bucket.objects.filter(id=theirs.id).exists())


class FolderMoveTest(FolderTestBase):
    def test_moves_a_folder_under_a_new_parent(self):
        a, b = self.mkfolder('A'), self.mkfolder('B')
        r = self.patch(a.id, parent_id=b.id)
        self.assertEqual(r.status_code, 200)
        a.refresh_from_db()
        self.assertEqual(a.parent, b)

    def test_moves_a_folder_back_to_the_top_level(self):
        b = self.mkfolder('B')
        a = self.mkfolder('A', parent=b)
        r = self.patch(a.id, parent_id=None)
        self.assertEqual(r.status_code, 200)
        a.refresh_from_db()
        self.assertIsNone(a.parent)

    def test_a_folder_cannot_be_moved_into_itself(self):
        a = self.mkfolder('A')
        r = self.patch(a.id, parent_id=a.id)
        self.assertEqual(r.status_code, 400)

    def test_a_folder_cannot_be_moved_into_its_own_descendant(self):
        """The subtree would be detached from every root — still in the
        database, holding files, reachable from nothing."""
        a = self.mkfolder('A')
        b = self.mkfolder('B', parent=a)
        c = self.mkfolder('C', parent=b)
        r = self.patch(a.id, parent_id=c.id)
        self.assertEqual(r.status_code, 400)
        a.refresh_from_db()
        self.assertIsNone(a.parent)

    def test_a_move_that_would_bust_the_depth_limit_is_refused(self):
        # A three-level branch dropped under a chain that leaves no room.
        branch = self.mkfolder('root')
        node = branch
        for i in range(3):
            node = self.mkfolder(f'child{i}', parent=node)
        deep = None
        for i in range(Bucket.MAX_DEPTH - 2):
            deep = self.mkfolder(f'D{i}', parent=deep)
        r = self.patch(branch.id, parent_id=deep.id)
        self.assertEqual(r.status_code, 400)

    def test_renaming_into_an_existing_sibling_name_is_refused(self):
        self.mkfolder('Reports')
        other = self.mkfolder('Drafts')
        r = self.patch(other.id, title='reports')
        self.assertEqual(r.status_code, 409)

    def test_only_folders_can_be_renamed(self):
        r = self.patch(self.general.id, title='Renamed')
        self.assertEqual(r.status_code, 400)


class FolderDeleteTest(FolderTestBase):
    def test_deletes_an_empty_folder(self):
        f = self.mkfolder('Empty')
        r = self.client.delete(f'/api/files/folders/{f.id}/')
        self.assertEqual(r.status_code, 200)
        self.assertFalse(Bucket.objects.filter(id=f.id).exists())

    def test_refuses_to_delete_a_folder_with_subfolders(self):
        f = self.mkfolder('Parent')
        self.mkfolder('Child', parent=f)
        r = self.client.delete(f'/api/files/folders/{f.id}/')
        self.assertEqual(r.status_code, 409)
        self.assertTrue(Bucket.objects.filter(id=f.id).exists())

    def test_refuses_to_delete_a_folder_holding_files(self):
        """The FK cascades, so an unguarded delete would take the files with
        it — silently, and with no way back."""
        f = self.mkfolder('Has files')
        SharedFile.objects.create(
            bucket=f, company=self.acme, original_name='a.pdf',
            storage_key='k', state=SharedFile.STATE_READY)
        r = self.client.delete(f'/api/files/folders/{f.id}/')
        self.assertEqual(r.status_code, 409)
        self.assertTrue(SharedFile.objects.filter(bucket=f).exists())

    def test_a_soft_deleted_file_does_not_block_deletion(self):
        from django.utils import timezone
        f = self.mkfolder('Has bin')
        SharedFile.objects.create(
            bucket=f, company=self.acme, original_name='a.pdf',
            storage_key='k', state=SharedFile.STATE_READY,
            deleted_at=timezone.now())
        self.assertEqual(self.client.delete(f'/api/files/folders/{f.id}/').status_code, 200)

    def test_the_general_bucket_cannot_be_deleted(self):
        r = self.client.delete(f'/api/files/folders/{self.general.id}/')
        self.assertEqual(r.status_code, 400)
        self.assertTrue(Bucket.objects.filter(id=self.general.id).exists())


class FileMoveTest(FolderTestBase):
    def mkfile(self, name, bucket=None, company=None):
        return SharedFile.objects.create(
            bucket=bucket or self.general, company=company or self.acme,
            original_name=name, storage_key=f'k/{name}',
            state=SharedFile.STATE_READY)

    def move(self, file_ids, bucket_id):
        return self.client.post(
            '/api/files/move/',
            data=json.dumps({'file_ids': file_ids, 'bucket_id': bucket_id}),
            content_type='application/json')

    def test_moves_files_into_a_folder(self):
        dest = self.mkfolder('Reports')
        a, b = self.mkfile('a.pdf'), self.mkfile('b.pdf')
        r = self.move([a.id, b.id], dest.id)
        self.assertEqual(r.status_code, 200)
        a.refresh_from_db(); b.refresh_from_db()
        self.assertEqual(a.bucket, dest)
        self.assertEqual(b.bucket, dest)

    def test_cannot_move_a_file_into_another_companys_folder(self):
        """The file is legitimately ours and the folder is legitimately
        theirs — only resolving the DESTINATION through the scoped manager
        catches this."""
        theirs = self.mkfolder('Theirs', company=self.rival)
        a = self.mkfile('a.pdf')
        r = self.move([a.id], theirs.id)
        self.assertEqual(r.status_code, 404)
        a.refresh_from_db()
        self.assertEqual(a.bucket, self.general)

    def test_cannot_move_another_companys_file(self):
        dest = self.mkfolder('Mine')
        theirs_bucket = self.mkfolder('Theirs', company=self.rival)
        theirs = self.mkfile('secret.pdf', bucket=theirs_bucket, company=self.rival)
        r = self.move([theirs.id], dest.id)
        self.assertEqual(r.status_code, 404)
        theirs.refresh_from_db()
        self.assertEqual(theirs.bucket, theirs_bucket)

    def test_a_batch_containing_one_bad_id_moves_nothing(self):
        """Half-applying a multi-select move leaves the customer with files
        scattered across two folders and no indication which."""
        dest = self.mkfolder('Reports')
        a = self.mkfile('a.pdf')
        r = self.move([a.id, 999999], dest.id)
        self.assertEqual(r.status_code, 404)
        a.refresh_from_db()
        self.assertEqual(a.bucket, self.general)

    def test_files_can_be_moved_back_to_general(self):
        dest = self.mkfolder('Reports')
        a = self.mkfile('a.pdf', bucket=dest)
        self.assertEqual(self.move([a.id], self.general.id).status_code, 200)
        a.refresh_from_db()
        self.assertEqual(a.bucket, self.general)

    def test_an_empty_batch_is_refused(self):
        dest = self.mkfolder('Reports')
        self.assertEqual(self.move([], dest.id).status_code, 400)


class BucketListingTest(FolderTestBase):
    def test_the_listing_carries_parent_so_the_client_can_build_the_tree(self):
        a = self.mkfolder('A')
        self.mkfolder('B', parent=a)
        r = self.client.get('/api/files/buckets/')
        self.assertEqual(r.status_code, 200)
        by_title = {b['title']: b for b in r.json()['buckets']}
        self.assertIsNone(by_title['A']['parent'])
        self.assertEqual(by_title['B']['parent'], a.id)

    def test_another_companys_folders_are_not_listed(self):
        self.mkfolder('Theirs', company=self.rival)
        titles = [b['title'] for b in self.client.get('/api/files/buckets/').json()['buckets']]
        self.assertNotIn('Theirs', titles)


class RequiredRequestTest(FolderTestBase):
    """Most requests are useful-to-have. Only the ones marked required belong
    in the customer's "you must do this" list."""

    def test_a_request_is_not_required_by_default(self):
        b = Bucket.objects.create(
            company=self.acme, kind=Bucket.KIND_REQUEST, title='Nice to have')
        self.assertFalse(b.required)

    def test_the_listing_exposes_required_so_the_client_can_split(self):
        Bucket.objects.create(
            company=self.acme, kind=Bucket.KIND_REQUEST, title='Blocking',
            required=True, status='open')
        Bucket.objects.create(
            company=self.acme, kind=Bucket.KIND_REQUEST, title='Optional', status='open')
        rows = {b['title']: b for b in self.client.get('/api/files/buckets/').json()['buckets']}
        self.assertTrue(rows['Blocking']['required'])
        self.assertFalse(rows['Optional']['required'])


class AgentInboxPathTest(FolderTestBase):
    """An agent scanning "what did they send me" needs to know where it
    landed; a nested folder name alone is ambiguous."""

    def setUp(self):
        super().setUp()
        self.staff = PortalUser.objects.create(
            email='agent@citemed.com', role=PortalUser.ROLE_ADMIN)
        self.login(self.staff)

    def test_inbox_reports_the_folder_path(self):
        a = self.mkfolder('Clinical Data')
        b = self.mkfolder('Site 04', parent=a)
        SharedFile.objects.create(
            bucket=b, company=self.acme, original_name='enrolment.pdf',
            storage_key='k', state=SharedFile.STATE_READY)
        r = self.client.get('/api/admin/files/inbox/')
        self.assertEqual(r.status_code, 200)
        row = next(i for i in r.json()['items'] if i['original_name'] == 'enrolment.pdf')
        self.assertEqual(row['bucket']['title'], 'Site 04')
        self.assertEqual(row['bucket']['path'], 'Clinical Data')

    def test_a_top_level_folder_has_an_empty_path(self):
        a = self.mkfolder('Reports')
        SharedFile.objects.create(
            bucket=a, company=self.acme, original_name='r.pdf',
            storage_key='k', state=SharedFile.STATE_READY)
        r = self.client.get('/api/admin/files/inbox/')
        row = next(i for i in r.json()['items'] if i['original_name'] == 'r.pdf')
        self.assertEqual(row['bucket']['path'], '')


@override_settings(SUPPORT_EMAIL='support@citemed.com')
class UploadNotificationTest(TestCase):
    """Regression: uploads into 'General uploads' notified nobody, because the
    bucket has no `requested_by` and the function returned early."""

    def setUp(self):
        self.company = Company.objects.create(name='Acme')
        self.agent = PortalUser.objects.create(
            email='alice@citemed.com', role=PortalUser.ROLE_ADMIN)
        self.csm = PortalUser.objects.create(
            email='csm@citemed.com', role=PortalUser.ROLE_ADMIN)
        self.general = Bucket.objects.create(
            company=self.company, kind=Bucket.KIND_GENERAL,
            title='General uploads', status='general')

    def _upload_to(self, bucket):
        return SharedFile.objects.create(
            bucket=bucket, company=self.company, original_name='report.pdf',
            storage_key='k', state=SharedFile.STATE_READY)

    def test_a_general_upload_notifies_every_agent(self):
        from portal import file_notify
        file_notify.notify_upload(self._upload_to(self.general))
        self.assertEqual(len(mail.outbox), 1)
        to = mail.outbox[0].to
        self.assertIn('alice@citemed.com', to)
        self.assertIn('support@citemed.com', to)

    def test_a_folder_upload_notifies_every_agent(self):
        from portal import file_notify
        folder = Bucket.objects.create(
            company=self.company, kind=Bucket.KIND_FOLDER, title='Reports')
        file_notify.notify_upload(self._upload_to(folder))
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('alice@citemed.com', mail.outbox[0].to)

    def test_a_request_upload_still_goes_to_the_csm_who_asked(self):
        """Narrower on purpose: someone asked for this specific document, so
        it's theirs to chase rather than everyone's to ignore."""
        from portal import file_notify
        req = Bucket.objects.create(
            company=self.company, kind=Bucket.KIND_REQUEST,
            title='Send us the DoC', requested_by=self.csm)
        file_notify.notify_upload(self._upload_to(req))
        self.assertEqual(len(mail.outbox), 1)
        to = mail.outbox[0].to
        self.assertIn('csm@citemed.com', to)
        self.assertNotIn('alice@citemed.com', to)
