import json
from unittest.mock import patch

from django.test import TestCase
from django.core import mail

from portal.models import Company, PortalUser, Bucket, SharedFile, FileActivity, ChecklistItem


class ModelScopingTests(TestCase):
    def setUp(self):
        self.acme = Company.objects.create(name='Acme')
        self.globex = Company.objects.create(name='Globex')
        self.cust = PortalUser.objects.create(email='a@acme.com', company=self.acme, role='customer')

    def test_general_bucket_helper_is_per_company_and_idempotent(self):
        from portal.views.files import get_general_bucket
        b1 = get_general_bucket(self.acme)
        b2 = get_general_bucket(self.acme)
        self.assertEqual(b1.id, b2.id)
        self.assertEqual(b1.kind, Bucket.KIND_GENERAL)
        b3 = get_general_bucket(self.globex)
        self.assertNotEqual(b1.id, b3.id)


class UploadFlowTests(TestCase):
    def setUp(self):
        self.acme = Company.objects.create(name='Acme')
        self.cust = PortalUser.objects.create(email='a@acme.com', company=self.acme, role='customer')

    def _login(self):
        s = self.client.session
        s['portal_user_id'] = self.cust.id
        s.save()

    @patch('portal.file_storage.presign_put', return_value='https://s3/put')
    def test_upload_init_creates_file_and_returns_url(self, _mock):
        self._login()
        r = self.client.post('/api/files/upload-init', data=json.dumps(
            {'name': 'refs.ris', 'size': 1234, 'mime': 'text/plain'}),
            content_type='application/json')
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertIn('file_id', body)
        self.assertEqual(body['upload_url'], 'https://s3/put')
        f = SharedFile.objects.get(id=body['file_id'])
        self.assertEqual(f.state, 'uploading')
        self.assertEqual(f.company_id, self.acme.id)
        self.assertTrue(f.storage_key)

    def test_upload_init_rejects_bad_extension(self):
        self._login()
        r = self.client.post('/api/files/upload-init', data=json.dumps(
            {'name': 'evil.exe', 'size': 10, 'mime': 'application/octet-stream'}),
            content_type='application/json')
        self.assertEqual(r.status_code, 400)

    def test_upload_init_requires_company(self):
        nocompany = PortalUser.objects.create(email='x@nowhere.com', role='customer')
        s = self.client.session
        s['portal_user_id'] = nocompany.id
        s.save()
        r = self.client.post('/api/files/upload-init', data=json.dumps(
            {'name': 'refs.ris', 'size': 1, 'mime': 'text/plain'}),
            content_type='application/json')
        self.assertEqual(r.status_code, 403)

    @patch('portal.file_storage.head_size', return_value=1234)
    @patch('portal.file_storage.presign_put', return_value='https://s3/put')
    def test_upload_complete_marks_ready_and_audits(self, _p, _h):
        self._login()
        init = self.client.post('/api/files/upload-init', data=json.dumps(
            {'name': 'refs.ris', 'size': 1234, 'mime': 'text/plain'}),
            content_type='application/json').json()
        r = self.client.post('/api/files/upload-complete', data=json.dumps(
            {'file_id': init['file_id']}), content_type='application/json')
        self.assertEqual(r.status_code, 200)
        f = SharedFile.objects.get(id=init['file_id'])
        self.assertEqual(f.state, 'ready')
        self.assertEqual(f.size_bytes, 1234)
        self.assertTrue(FileActivity.objects.filter(file=f, action='upload').exists())


class ListAndManageTests(TestCase):
    def setUp(self):
        self.acme = Company.objects.create(name='Acme')
        self.globex = Company.objects.create(name='Globex')
        self.a = PortalUser.objects.create(email='a@acme.com', company=self.acme, role='customer')
        self.g = PortalUser.objects.create(email='g@globex.com', company=self.globex, role='customer')
        from portal.views.files import get_general_bucket
        self.afile = SharedFile.objects.create(
            bucket=get_general_bucket(self.acme), company=self.acme, uploaded_by=self.a,
            original_name='a.pdf', storage_key='k', state='ready', size_bytes=10)

    def _login(self, u):
        s = self.client.session
        s['portal_user_id'] = u.id
        s.save()

    def test_customer_lists_only_own_company(self):
        self._login(self.g)
        r = self.client.get('/api/files/buckets/')
        self.assertEqual(r.status_code, 200)
        files = [f for b in r.json()['buckets'] for f in b['files']]
        self.assertEqual(files, [])

    def test_customer_cannot_delete_other_company_file(self):
        self._login(self.g)
        r = self.client.delete(f'/api/files/{self.afile.id}')
        self.assertIn(r.status_code, (403, 404))
        self.afile.refresh_from_db()
        self.assertIsNone(self.afile.deleted_at)

    def test_rename_and_soft_delete(self):
        self._login(self.a)
        r = self.client.patch(f'/api/files/{self.afile.id}', data=json.dumps({'name': 'b.pdf'}),
                              content_type='application/json')
        self.assertEqual(r.status_code, 200)
        self.afile.refresh_from_db()
        self.assertEqual(self.afile.original_name, 'b.pdf')
        r = self.client.delete(f'/api/files/{self.afile.id}')
        self.assertEqual(r.status_code, 200)
        self.afile.refresh_from_db()
        self.assertIsNotNone(self.afile.deleted_at)
        r = self.client.get('/api/files/buckets/')
        ids = [f['id'] for b in r.json()['buckets'] for f in b['files']]
        self.assertNotIn(self.afile.id, ids)

    @patch('portal.file_storage.presign_get', return_value='https://s3/get')
    def test_download_redirects_and_audits(self, _m):
        self._login(self.a)
        r = self.client.get(f'/api/files/{self.afile.id}/download')
        self.assertEqual(r.status_code, 302)
        self.assertEqual(r['Location'], 'https://s3/get')
        self.assertTrue(FileActivity.objects.filter(file=self.afile, action='download').exists())

    @patch('portal.file_storage.presign_view', return_value='https://s3/inline')
    def test_view_redirects_inline(self, _m):
        self._login(self.a)
        r = self.client.get(f'/api/files/{self.afile.id}/view')
        self.assertEqual(r.status_code, 302)
        self.assertEqual(r['Location'], 'https://s3/inline')

    def test_view_blocked_cross_company(self):
        self._login(self.g)
        r = self.client.get(f'/api/files/{self.afile.id}/view')
        self.assertIn(r.status_code, (403, 404))

    @patch('portal.file_storage.presign_view', return_value='https://s3/inline')
    @patch('portal.file_storage.presign_get', return_value='https://s3/download')
    def test_view_non_previewable_falls_back_to_download(self, _get, _view):
        # A non-PDF/image (even if uploaded with a spoofed mime) must NOT be
        # served inline — it should redirect to a plain download instead.
        evil = SharedFile.objects.create(
            bucket=self.afile.bucket, company=self.acme, uploaded_by=self.a,
            original_name='note.txt', storage_key='k2', state='ready',
            size_bytes=10, mime_type='text/html')
        self._login(self.a)
        r = self.client.get(f'/api/files/{evil.id}/view')
        self.assertEqual(r.status_code, 302)
        self.assertEqual(r['Location'], 'https://s3/download')  # not the inline URL


class AdminFilesTests(TestCase):
    def setUp(self):
        self.acme = Company.objects.create(name='Acme')
        self.admin = PortalUser.objects.create(email='p@citemed.com', role='admin')
        self.cust = PortalUser.objects.create(email='a@acme.com', company=self.acme, role='customer')
        from portal.views.files import get_general_bucket
        SharedFile.objects.create(bucket=get_general_bucket(self.acme), company=self.acme,
                                  original_name='a.pdf', storage_key='k', state='ready', size_bytes=10)

    def _login(self, u):
        s = self.client.session
        s['portal_user_id'] = u.id
        s.save()

    def test_customer_blocked_from_admin_files(self):
        self._login(self.cust)
        self.assertEqual(self.client.get('/api/admin/files/companies/').status_code, 403)

    def test_admin_lists_companies_with_counts(self):
        self._login(self.admin)
        r = self.client.get('/api/admin/files/companies/')
        self.assertEqual(r.status_code, 200)
        acme = next(c for c in r.json()['companies'] if c['id'] == self.acme.id)
        self.assertEqual(acme['file_count'], 1)

    def test_admin_views_company_files(self):
        self._login(self.admin)
        r = self.client.get(f'/api/admin/files/companies/{self.acme.id}/')
        self.assertEqual(r.status_code, 200)
        files = [f for b in r.json()['buckets'] for f in b['files']]
        self.assertEqual(len(files), 1)


class ClientListTests(TestCase):
    def setUp(self):
        self.acme = Company.objects.create(name='Acme')
        self.globex = Company.objects.create(name='Globex')
        self.admin = PortalUser.objects.create(email='p@citemed.com', role='admin')
        self.cust = PortalUser.objects.create(email='a@acme.com', company=self.acme, role='customer')
        from portal.views.files import get_general_bucket
        self.f1 = SharedFile.objects.create(bucket=get_general_bucket(self.acme), company=self.acme,
                                            original_name='a.pdf', storage_key='k1', state='ready', size_bytes=10)
        self.f2 = SharedFile.objects.create(bucket=get_general_bucket(self.globex), company=self.globex,
                                            original_name='b.pdf', storage_key='k2', state='ready', size_bytes=20)

    def _login(self, u):
        s = self.client.session
        s['portal_user_id'] = u.id
        s.save()

    def test_the_client_list_carries_the_unseen_count(self):
        """With the cross-client inbox gone, this list is the ONLY place
        "who sent us something new" is answered. If it stops counting, an
        agent has to open every client to find the one that uploaded."""
        self._login(self.admin)
        rows = {c['name']: c for c in
                self.client.get('/api/admin/files/companies/').json()['companies']}
        self.assertEqual(rows['Acme']['unseen_count'], 1)
        self.assertEqual(rows['Globex']['unseen_count'], 1)

    def test_marking_a_file_seen_clears_it_from_the_count(self):
        self._login(self.admin)
        r = self.client.patch(f'/api/admin/files/{self.f1.id}/processed',
                              data=json.dumps({'processed': True}),
                              content_type='application/json')
        self.assertEqual(r.status_code, 200)
        rows = {c['name']: c for c in
                self.client.get('/api/admin/files/companies/').json()['companies']}
        self.assertEqual(rows['Acme']['unseen_count'], 0)
        self.assertEqual(rows['Acme']['file_count'], 1)  # still there, just seen

    def test_the_retired_review_endpoints_are_gone(self):
        """Both were removed with the approve/reject loop. Asserting they 404
        stops them being quietly reinstated by a merge."""
        self._login(self.admin)
        self.assertEqual(self.client.get('/api/admin/files/inbox/').status_code, 404)
        self.assertEqual(
            self.client.patch(f'/api/admin/files/{self.f1.id}/review',
                              data='{}', content_type='application/json').status_code, 404)

    def test_activity_feed_admin_only_and_lists_events(self):
        from portal.views.files import log_activity
        log_activity(self.acme, 'upload', actor=self.cust, name='a.pdf')
        # customer blocked
        self._login(self.cust)
        self.assertEqual(self.client.get('/api/admin/files/activity/').status_code, 403)
        # admin sees it
        self._login(self.admin)
        r = self.client.get('/api/admin/files/activity/')
        self.assertEqual(r.status_code, 200)
        actions = [a['action'] for a in r.json()['items']]
        self.assertIn('upload', actions)


class DemoLoginTests(TestCase):
    def setUp(self):
        # Seeded by migration 0013 (is_demo=True). Use it directly.
        self.demo = PortalUser.objects.get(email='demo@citemed.com')
        self.real = PortalUser.objects.create(email='real@acme.com', role='customer',
                                             access_enabled=True, is_demo=False)

    def test_seeded_demo_user_is_flagged(self):
        self.assertTrue(self.demo.is_demo)
        self.assertEqual(self.demo.role, 'customer')

    def test_demo_user_logs_in_without_magic_link(self):
        r = self.client.get('/api/auth/demo-login/', {'email': 'demo@citemed.com'})
        self.assertEqual(r.status_code, 302)
        me = self.client.get('/api/auth/me/')
        self.assertEqual(me.status_code, 200)
        self.assertEqual(me.json()['user']['email'], 'demo@citemed.com')

    def test_real_user_cannot_use_demo_login(self):
        r = self.client.get('/api/auth/demo-login/', {'email': 'real@acme.com'})
        self.assertEqual(r.status_code, 404)
        self.assertEqual(self.client.get('/api/auth/me/').status_code, 401)

    def test_unknown_email_404(self):
        self.assertEqual(self.client.get('/api/auth/demo-login/', {'email': 'nobody@x.com'}).status_code, 404)

    def test_login_form_signs_in_demo_directly(self):
        # Entering a demo email on the normal login form skips the magic link.
        r = self.client.post('/api/auth/request-magic-link/',
                             data=json.dumps({'email': 'demo@citemed.com'}),
                             content_type='application/json')
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json().get('demo'))
        self.assertEqual(self.client.get('/api/auth/me/').json()['user']['email'], 'demo@citemed.com')

    def test_login_form_real_user_gets_link_not_session(self):
        r = self.client.post('/api/auth/request-magic-link/',
                             data=json.dumps({'email': 'real@acme.com'}),
                             content_type='application/json')
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.json().get('demo'))
        self.assertEqual(self.client.get('/api/auth/me/').status_code, 401)  # not logged in


class ReviewAndChecklistTests(TestCase):
    def setUp(self):
        self.acme = Company.objects.create(name='Acme')
        self.admin = PortalUser.objects.create(email='p@citemed.com', role='admin')
        self.cust = PortalUser.objects.create(email='a@acme.com', company=self.acme, role='customer')
        from portal.views.files import get_general_bucket
        self.req = Bucket.objects.create(company=self.acme, kind='request', title='Q3 PMS', status='open')
        self.f = SharedFile.objects.create(bucket=self.req, company=self.acme, uploaded_by=self.cust,
                                           original_name='a.pdf', storage_key='k', state='ready', size_bytes=10)

    def _login(self, u):
        s = self.client.session
        s['portal_user_id'] = u.id
        s.save()

    def _customer_file(self):
        data = self.client.get('/api/files/buckets/').json()
        return next(x for b in data['buckets'] for x in b['files'] if x['id'] == self.f.id)

    def test_no_review_state_reaches_the_customer(self):
        """The approve/reject loop is retired. Any leak of these keys puts a
        permanent "AWAITING REVIEW" badge back on the customer's files for a
        review that is never coming."""
        self.f.review_status = 'pending'
        self.f.review_notes = 'internal scribble'
        self.f.save()
        self._login(self.cust)
        f = self._customer_file()
        for key in ('review_status', 'review_notes'):
            self.assertNotIn(key, f)
        self.assertNotIn('internal scribble', json.dumps(f))

    def test_the_seen_flag_is_staff_only(self):
        """Whether we've opened their file is our business — surfacing it
        would recreate the badge we just removed."""
        self._login(self.cust)
        self.assertIsNone(self._customer_file()['seen'])
        self._login(self.admin)
        r = self.client.get(f'/api/admin/files/companies/{self.acme.id}/').json()
        f = next(x for b in r['buckets'] for x in b['files'] if x['id'] == self.f.id)
        self.assertIs(f['seen'], False)

    def test_internal_comments_add_list_and_hidden_from_customer(self):
        self._login(self.admin)
        # add a comment
        r = self.client.post(f'/api/admin/files/{self.f.id}/comments',
                            data=json.dumps({'body': 'Is page 2 the latest?'}), content_type='application/json')
        self.assertEqual(r.status_code, 201)
        # list shows it
        items = self.client.get(f'/api/admin/files/{self.f.id}/comments').json()['comments']
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]['body'], 'Is page 2 the latest?')
        self.assertTrue(FileActivity.objects.filter(file=self.f, action='comment').exists())
        # customer can't touch the comments endpoint, and comment_count is 0 (staff-only)
        self._login(self.cust)
        self.assertIn(self.client.get(f'/api/admin/files/{self.f.id}/comments').status_code, (401, 403))
        data = self.client.get('/api/files/buckets/').json()
        f = next(x for b in data['buckets'] for x in b['files'] if x['id'] == self.f.id)
        self.assertEqual(f['comment_count'], 0)

    def test_checklist_create_link_and_visible(self):
        self._login(self.admin)
        item = self.client.post('/api/admin/files/checklist/', data=json.dumps({
            'bucket_id': self.req.id, 'text': 'Signed PMS report'}), content_type='application/json').json()
        self.assertEqual(item['text'], 'Signed PMS report')
        # link the file to the checklist slot
        r = self.client.patch(f"/api/admin/files/checklist/{item['id']}/",
                             data=json.dumps({'linked_file_id': self.f.id}), content_type='application/json')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()['linked_file_name'], 'a.pdf')
        # checklist surfaces in the customer bucket view
        self._login(self.cust)
        data = self.client.get('/api/files/buckets/').json()
        b = next(x for x in data['buckets'] if x['id'] == self.req.id)
        self.assertEqual(len(b['checklist']), 1)


class RequestAuthoringTests(TestCase):
    def setUp(self):
        self.acme = Company.objects.create(name='Acme')
        self.admin = PortalUser.objects.create(email='p@citemed.com', role='admin')
        self.cust = PortalUser.objects.create(email='a@acme.com', company=self.acme, role='customer')

    def _login(self, u):
        s = self.client.session
        s['portal_user_id'] = u.id
        s.save()

    def test_admin_creates_request_and_customer_sees_it(self):
        self._login(self.admin)
        r = self.client.post('/api/admin/files/requests/', data=json.dumps({
            'company_id': self.acme.id, 'title': 'Q3 PMS Report',
            'description': 'Upload your PMS report.', 'due_at': '2026-07-01', 'status': 'open',
        }), content_type='application/json')
        self.assertEqual(r.status_code, 201)
        b = r.json()
        self.assertEqual(b['kind'], 'request')
        self.assertEqual(b['requested_by_name'], 'p@citemed.com')
        self.assertTrue(FileActivity.objects.filter(bucket_id=b['id'], action='request_created').exists())
        # customer sees the request in their bucket list
        self._login(self.cust)
        r2 = self.client.get('/api/files/buckets/')
        titles = [x['title'] for x in r2.json()['buckets']]
        self.assertIn('Q3 PMS Report', titles)

    def test_customer_cannot_create_request(self):
        self._login(self.cust)
        r = self.client.post('/api/admin/files/requests/', data=json.dumps({
            'company_id': self.acme.id, 'title': 'X'}), content_type='application/json')
        self.assertEqual(r.status_code, 403)

    def test_admin_edits_request(self):
        self._login(self.admin)
        b = self.client.post('/api/admin/files/requests/', data=json.dumps({
            'company_id': self.acme.id, 'title': 'Orig'}), content_type='application/json').json()
        r = self.client.patch(f"/api/admin/files/requests/{b['id']}/", data=json.dumps({
            'title': 'Updated', 'status': 'complete'}), content_type='application/json')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()['title'], 'Updated')
        self.assertEqual(r.json()['status'], 'complete')
