"""Tests for the multipart upload path.

Multipart exists less for the 5 GB single-PUT ceiling than for retry: a
whole-object PUT has nothing to resume from, so a dropped connection at 90%
costs the whole transfer. These tests pin the part arithmetic (S3's 10,000
part limit is easy to breach silently), the threshold that decides which path
a file takes, and that an abandoned upload is *aborted* rather than deleted —
orphaned parts keep being billed and never appear in a bucket listing.
"""
import json
from unittest.mock import patch

from django.test import TestCase, Client, override_settings

from portal import file_storage
from portal.models import Bucket, Company, PortalUser, SharedFile

MB = 1024 ** 2
GB = 1024 ** 3


class PartPlanTest(TestCase):
    def test_small_multipart_file_uses_the_configured_floor(self):
        part, count = file_storage.part_plan(200 * MB)
        self.assertEqual(part, 16 * MB)
        self.assertEqual(count, 13)  # ceil(200/16)

    def test_part_size_grows_to_stay_under_the_10000_part_limit(self):
        # A fixed 16 MB part would need 320 parts here — fine — but the rule
        # has to hold at the ceiling too.
        part, count = file_storage.part_plan(5 * GB)
        self.assertLessEqual(count, 10000)
        self.assertGreaterEqual(part, 16 * MB)

    def test_a_huge_file_still_fits_in_10000_parts(self):
        for size in (10 * GB, 100 * GB, 1000 * GB):
            _, count = file_storage.part_plan(size)
            self.assertLessEqual(count, 10000, f'{size} produced {count} parts')

    def test_parts_are_never_below_the_s3_minimum_of_5mib(self):
        for size in (101 * MB, 500 * MB, 5 * GB):
            part, _ = file_storage.part_plan(size)
            self.assertGreaterEqual(part, 5 * MB)

    def test_parts_cover_the_whole_file(self):
        for size in (101 * MB, 333 * MB, 2 * GB):
            part, count = file_storage.part_plan(size)
            self.assertGreaterEqual(part * count, size)
            # ...and not with a whole wasted part on the end.
            self.assertLess(part * (count - 1), size)


class MultipartBase(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name='Acme')
        self.user = PortalUser.objects.create(
            email='jane@acme.test', name='Jane', role=PortalUser.ROLE_CUSTOMER,
            company=self.company, access_enabled=True)
        self.bucket = Bucket.objects.create(
            company=self.company, kind=Bucket.KIND_GENERAL,
            title='General uploads', status='general')
        self.client = Client()
        s = self.client.session
        s['portal_user_id'] = self.user.id
        s.save()

    def post(self, path, payload):
        return self.client.post(path, data=json.dumps(payload),
                                content_type='application/json')


class UploadInitRoutingTest(MultipartBase):
    @patch('portal.file_storage.presign_put', return_value='https://s3/put')
    def test_a_small_file_keeps_the_single_put_shape(self, _):
        r = self.post('/api/files/upload-init',
                      {'name': 'a.pdf', 'size': 1024, 'mime': 'application/pdf'})
        body = r.json()
        self.assertEqual(r.status_code, 200)
        self.assertIn('upload_url', body)
        self.assertNotIn('multipart', body)
        self.assertEqual(SharedFile.objects.get(id=body['file_id']).upload_id, '')

    @patch('portal.file_storage.create_multipart', return_value='UP-123')
    def test_a_large_file_switches_to_multipart(self, mock_create):
        r = self.post('/api/files/upload-init',
                      {'name': 'big.pdf', 'size': 200 * MB, 'mime': 'application/pdf'})
        body = r.json()
        self.assertTrue(body['multipart'])
        self.assertEqual(body['part_size'], 16 * MB)
        self.assertEqual(body['part_count'], 13)
        self.assertNotIn('upload_url', body)
        mock_create.assert_called_once()
        self.assertEqual(SharedFile.objects.get(id=body['file_id']).upload_id, 'UP-123')

    @override_settings(FILESHARE_MULTIPART_THRESHOLD=1024)
    @patch('portal.file_storage.create_multipart', return_value='UP-1')
    def test_the_threshold_is_configurable(self, _):
        r = self.post('/api/files/upload-init',
                      {'name': 'a.pdf', 'size': 4096, 'mime': 'application/pdf'})
        self.assertTrue(r.json()['multipart'])

    @patch('portal.file_storage.presign_put', return_value='https://s3/put')
    def test_a_file_exactly_at_the_threshold_stays_single_put(self, _):
        r = self.post('/api/files/upload-init',
                      {'name': 'a.pdf', 'size': 100 * MB, 'mime': 'application/pdf'})
        self.assertIn('upload_url', r.json())


class UploadPartsTest(MultipartBase):
    def make_file(self, upload_id='UP-1'):
        return SharedFile.objects.create(
            bucket=self.bucket, company=self.company, uploaded_by=self.user,
            original_name='big.pdf', storage_key='k', upload_id=upload_id,
            state=SharedFile.STATE_UPLOADING)

    @patch('portal.file_storage.presign_part', side_effect=lambda k, u, n: f'https://s3/{n}')
    def test_presigns_the_requested_parts(self, _):
        f = self.make_file()
        r = self.post('/api/files/upload-parts',
                      {'file_id': f.id, 'part_numbers': [1, 2, 3]})
        self.assertEqual(r.json()['urls'], {
            '1': 'https://s3/1', '2': 'https://s3/2', '3': 'https://s3/3'})

    def test_refuses_a_batch_over_the_cap(self):
        f = self.make_file()
        r = self.post('/api/files/upload-parts',
                      {'file_id': f.id, 'part_numbers': list(range(1, 60))})
        self.assertEqual(r.status_code, 400)

    def test_refuses_part_numbers_outside_the_s3_range(self):
        f = self.make_file()
        for bad in ([0], [-1], [10001]):
            r = self.post('/api/files/upload-parts', {'file_id': f.id, 'part_numbers': bad})
            self.assertEqual(r.status_code, 400, bad)

    def test_refuses_an_empty_list(self):
        f = self.make_file()
        r = self.post('/api/files/upload-parts', {'file_id': f.id, 'part_numbers': []})
        self.assertEqual(r.status_code, 400)

    def test_a_file_without_a_multipart_upload_is_not_found(self):
        f = self.make_file(upload_id='')
        r = self.post('/api/files/upload-parts', {'file_id': f.id, 'part_numbers': [1]})
        self.assertEqual(r.status_code, 404)

    def test_another_company_cannot_presign_parts(self):
        other = Company.objects.create(name='Other')
        theirs = SharedFile.objects.create(
            bucket=Bucket.objects.create(company=other, kind=Bucket.KIND_GENERAL,
                                         title='G', status='general'),
            company=other, original_name='x.pdf', storage_key='k',
            upload_id='UP-9', state=SharedFile.STATE_UPLOADING)
        r = self.post('/api/files/upload-parts', {'file_id': theirs.id, 'part_numbers': [1]})
        self.assertEqual(r.status_code, 404)


class UploadCompleteMultipartTest(MultipartBase):
    def make_file(self):
        return SharedFile.objects.create(
            bucket=self.bucket, company=self.company, uploaded_by=self.user,
            original_name='big.pdf', storage_key='k', upload_id='UP-1',
            state=SharedFile.STATE_UPLOADING)

    @patch('portal.file_storage.head_size', return_value=200 * MB)
    @patch('portal.file_storage.complete_multipart')
    def test_assembles_the_parts_then_marks_ready(self, mock_complete, _):
        f = self.make_file()
        r = self.post('/api/files/upload-complete', {
            'file_id': f.id,
            'parts': [{'PartNumber': 2, 'ETag': '"b"'}, {'PartNumber': 1, 'ETag': '"a"'}],
        })
        self.assertEqual(r.status_code, 200)
        mock_complete.assert_called_once()
        f.refresh_from_db()
        self.assertEqual(f.state, SharedFile.STATE_READY)
        # Cleared, so the nightly purge won't try to abort a finished upload.
        self.assertEqual(f.upload_id, '')

    def test_refuses_completion_without_a_part_list(self):
        f = self.make_file()
        r = self.post('/api/files/upload-complete', {'file_id': f.id})
        self.assertEqual(r.status_code, 400)
        f.refresh_from_db()
        self.assertEqual(f.state, SharedFile.STATE_UPLOADING)

    @patch('portal.file_storage.complete_multipart')
    def test_a_malformed_part_list_is_rejected_not_crashed(self, _):
        f = self.make_file()
        r = self.post('/api/files/upload-complete',
                      {'file_id': f.id, 'parts': [{'nope': 1}]})
        self.assertEqual(r.status_code, 400)

    @patch('portal.file_storage.complete_multipart', side_effect=Exception('boom'))
    def test_a_storage_failure_is_reported_not_swallowed(self, _):
        f = self.make_file()
        r = self.post('/api/files/upload-complete',
                      {'file_id': f.id, 'parts': [{'PartNumber': 1, 'ETag': '"a"'}]})
        self.assertEqual(r.status_code, 400)
        f.refresh_from_db()
        self.assertEqual(f.state, SharedFile.STATE_UPLOADING)


class UploadAbortTest(MultipartBase):
    @patch('portal.file_storage.abort_multipart', return_value=True)
    def test_aborts_the_multipart_upload_and_drops_the_row(self, mock_abort):
        f = SharedFile.objects.create(
            bucket=self.bucket, company=self.company, original_name='big.pdf',
            storage_key='k', upload_id='UP-1', state=SharedFile.STATE_UPLOADING)
        r = self.post('/api/files/upload-abort', {'file_id': f.id})
        self.assertEqual(r.status_code, 200)
        mock_abort.assert_called_once_with('k', 'UP-1')
        self.assertFalse(SharedFile.objects.filter(id=f.id).exists())

    @patch('portal.file_storage.delete_object', return_value=True)
    @patch('portal.file_storage.abort_multipart')
    def test_a_single_put_upload_is_deleted_not_aborted(self, mock_abort, mock_delete):
        f = SharedFile.objects.create(
            bucket=self.bucket, company=self.company, original_name='a.pdf',
            storage_key='k', state=SharedFile.STATE_UPLOADING)
        self.post('/api/files/upload-abort', {'file_id': f.id})
        mock_abort.assert_not_called()
        mock_delete.assert_called_once_with('k')

    def test_a_ready_file_cannot_be_aborted(self):
        f = SharedFile.objects.create(
            bucket=self.bucket, company=self.company, original_name='a.pdf',
            storage_key='k', state=SharedFile.STATE_READY, size_bytes=10)
        r = self.post('/api/files/upload-abort', {'file_id': f.id})
        self.assertEqual(r.status_code, 404)
        self.assertTrue(SharedFile.objects.filter(id=f.id).exists())


class PurgeAbortsMultipartTest(MultipartBase):
    """An abandoned multipart upload is not an object, so deleting its key is
    a no-op — its parts stay stored and billed until explicitly aborted."""

    @patch('portal.file_storage.abort_multipart', return_value=True)
    @patch('portal.file_storage.delete_object', return_value=True)
    def test_purge_aborts_rather_than_deletes(self, mock_delete, mock_abort):
        from datetime import timedelta
        from django.utils import timezone
        from django.core.management import call_command

        f = SharedFile.objects.create(
            bucket=self.bucket, company=self.company, original_name='big.pdf',
            storage_key='k', upload_id='UP-1', state=SharedFile.STATE_UPLOADING)
        SharedFile.objects.filter(id=f.id).update(
            uploaded_at=timezone.now() - timedelta(hours=48))

        call_command('purge_stale_uploads', '--hours', '24')
        mock_abort.assert_called_once_with('k', 'UP-1')
        mock_delete.assert_not_called()
        self.assertFalse(SharedFile.objects.filter(id=f.id).exists())
