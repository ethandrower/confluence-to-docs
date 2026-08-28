"""Tests for POST /api/files/folders/ensure-path — the folder-tree upload.

The endpoint exists because resolving a dropped tree client-side is racy: two
files in the same new subfolder each try to create it. These tests pin the
behaviour that makes the server-side version worth having — reuse rather than
fork, one folder per path regardless of how many files share it, and a clean
refusal rather than a constraint error at the depth limit.
"""
import json

from django.test import TestCase, Client

from portal.models import Bucket, Company, PortalUser


class EnsurePathTest(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name='Acme')
        self.user = PortalUser.objects.create(
            email='jane@acme.test', name='Jane', role=PortalUser.ROLE_CUSTOMER,
            company=self.company, access_enabled=True,
        )
        self.client = Client()
        session = self.client.session
        session['portal_user_id'] = self.user.id
        session.save()

    def post(self, paths, root_id=None):
        return self.client.post(
            '/api/files/folders/ensure-path',
            data=json.dumps({'paths': paths, 'root_id': root_id}),
            content_type='application/json',
        )

    def folders(self):
        return Bucket.objects.filter(company=self.company, kind=Bucket.KIND_FOLDER)

    # ── creation ──────────────────────────────────────────────────────────
    def test_creates_the_whole_chain_and_returns_every_level(self):
        r = self.post(['2024/q1'])
        self.assertEqual(r.status_code, 200)
        got = r.json()['folders']
        # Intermediate levels are returned too, so a file sitting at "2024"
        # resolves without a second call.
        self.assertIn('2024', got)
        self.assertIn('2024/q1', got)
        q1 = Bucket.objects.get(id=got['2024/q1'])
        self.assertEqual(q1.title, 'q1')
        self.assertEqual(q1.parent.title, '2024')
        self.assertIsNone(q1.parent.parent)

    def test_shared_prefixes_create_each_folder_once(self):
        # This is the race the endpoint exists to prevent: three paths under
        # one parent must yield ONE parent, not three.
        r = self.post(['2024/q1', '2024/q2', '2024/q3'])
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.folders().filter(title='2024').count(), 1)
        self.assertEqual(self.folders().count(), 4)  # 2024 + three quarters

    def test_reuses_an_existing_folder_rather_than_forking_it(self):
        existing = Bucket.objects.create(
            company=self.company, kind=Bucket.KIND_FOLDER, title='2024', status='general')
        r = self.post(['2024/q1'])
        self.assertEqual(r.json()['folders']['2024'], existing.id)
        self.assertEqual(self.folders().filter(title='2024').count(), 1)

    def test_reuse_is_case_insensitive(self):
        # Re-uploading a tree from a case-insensitive filesystem must merge
        # into the folder already there, not sit beside it.
        Bucket.objects.create(
            company=self.company, kind=Bucket.KIND_FOLDER, title='Reports', status='general')
        self.post(['reports/q1'])
        self.assertEqual(self.folders().filter(title__iexact='reports').count(), 1)

    def test_is_idempotent_across_calls(self):
        first = self.post(['a/b/c']).json()['folders']
        second = self.post(['a/b/c']).json()['folders']
        self.assertEqual(first, second)
        self.assertEqual(self.folders().count(), 3)

    # ── rooting ───────────────────────────────────────────────────────────
    def test_paths_are_created_under_the_given_root(self):
        root = Bucket.objects.create(
            company=self.company, kind=Bucket.KIND_FOLDER, title='Root', status='general')
        got = self.post(['sub'], root_id=root.id).json()['folders']
        self.assertEqual(got[''], root.id)
        self.assertEqual(Bucket.objects.get(id=got['sub']).parent_id, root.id)

    def test_empty_path_maps_to_the_root_so_loose_files_resolve(self):
        got = self.post([]).json()['folders']
        self.assertEqual(got, {'': None})

    # ── normalising ───────────────────────────────────────────────────────
    def test_ignores_empty_dot_and_parent_segments(self):
        got = self.post(['a//b', './c', 'd/../e']).json()['folders']
        self.assertIn('a/b', got)
        self.assertIn('c', got)
        # '..' is dropped rather than escaping upward.
        self.assertIn('d/e', got)
        self.assertFalse(any('..' in k for k in got))

    # ── limits ────────────────────────────────────────────────────────────
    def test_refuses_a_path_deeper_than_max_depth(self):
        deep = '/'.join(f'l{i}' for i in range(Bucket.MAX_DEPTH + 1))
        r = self.post([deep])
        self.assertEqual(r.status_code, 400)
        self.assertIn('deeper', r.json()['error'])
        # Nothing partially created — the transaction rolled back.
        self.assertEqual(self.folders().count(), 0)

    def test_depth_is_measured_from_the_root_not_from_zero(self):
        root = Bucket.objects.create(
            company=self.company, kind=Bucket.KIND_FOLDER, title='Root', status='general')
        deep = '/'.join(f'l{i}' for i in range(Bucket.MAX_DEPTH))
        r = self.post([deep], root_id=root.id)
        self.assertEqual(r.status_code, 400)

    def test_accepts_a_path_exactly_at_the_limit(self):
        exact = '/'.join(f'l{i}' for i in range(Bucket.MAX_DEPTH))
        self.assertEqual(self.post([exact]).status_code, 200)
        self.assertEqual(self.folders().count(), Bucket.MAX_DEPTH)

    def test_refuses_an_oversized_batch(self):
        r = self.post([f'f{i}' for i in range(501)])
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self.folders().count(), 0)

    # ── isolation ─────────────────────────────────────────────────────────
    def test_a_root_from_another_company_is_not_found(self):
        other = Company.objects.create(name='Other')
        theirs = Bucket.objects.create(
            company=other, kind=Bucket.KIND_FOLDER, title='Theirs', status='general')
        r = self.post(['sub'], root_id=theirs.id)
        self.assertEqual(r.status_code, 404)
        self.assertEqual(self.folders().count(), 0)

    def test_a_request_bucket_cannot_be_used_as_a_root(self):
        req = Bucket.objects.create(
            company=self.company, kind=Bucket.KIND_REQUEST, title='Send us X', status='open')
        r = self.post(['sub'], root_id=req.id)
        self.assertEqual(r.status_code, 400)

    def test_requires_a_company(self):
        loner = PortalUser.objects.create(
            email='no@one.test', name='No One', role=PortalUser.ROLE_CUSTOMER,
            access_enabled=True)
        c = Client()
        s = c.session
        s['portal_user_id'] = loner.id
        s.save()
        r = c.post('/api/files/folders/ensure-path',
                   data=json.dumps({'paths': ['a']}), content_type='application/json')
        self.assertEqual(r.status_code, 403)


class AllowedExtensionsTest(TestCase):
    """The uploader reports what a dropped folder will skip before uploading,
    so the list has to travel with the listing rather than be duplicated."""

    def test_buckets_listing_advertises_the_allowlist(self):
        company = Company.objects.create(name='Acme')
        user = PortalUser.objects.create(
            email='j@acme.test', name='J', role=PortalUser.ROLE_CUSTOMER,
            company=company, access_enabled=True)
        c = Client()
        s = c.session
        s['portal_user_id'] = user.id
        s.save()
        body = c.get('/api/files/buckets/').json()
        self.assertIn('pdf', body['allowed_ext'])
        self.assertNotIn('exe', body['allowed_ext'])
