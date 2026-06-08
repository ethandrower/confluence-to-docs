import json
from unittest.mock import patch

from django.test import TestCase

from portal.models import Company, PortalUser, Bucket, SharedFile, FileActivity


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
