import json

from django.test import TestCase

from portal.models import Company, PortalUser


class AdminCompanyDateTests(TestCase):
    """Regression: assigning a raw 'YYYY-MM-DD' string to Company.contract_end_date
    (a DateField) then serializing it 500'd on .isoformat(). Parse to a date."""

    def setUp(self):
        self.admin = PortalUser.objects.create(email='admin@citemed.com', role='admin')

    def _login(self):
        s = self.client.session
        s['portal_user_id'] = self.admin.id
        s.save()

    def test_create_company_with_date_string(self):
        self._login()
        r = self.client.post('/api/admin/companies/', data=json.dumps(
            {'name': 'Acme', 'contract_end_date': '2026-12-31'}),
            content_type='application/json')
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.json()['company']['contract_end_date'], '2026-12-31')

    def test_update_company_date_string_no_500(self):
        self._login()
        c = Company.objects.create(name='Beta')
        r = self.client.patch(f'/api/admin/companies/{c.id}/', data=json.dumps(
            {'contract_end_date': '2027-01-15'}), content_type='application/json')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()['company']['contract_end_date'], '2027-01-15')

    def test_clearing_date_works(self):
        self._login()
        c = Company.objects.create(name='Delta')
        r = self.client.patch(f'/api/admin/companies/{c.id}/', data=json.dumps(
            {'contract_end_date': ''}), content_type='application/json')
        self.assertEqual(r.status_code, 200)
        self.assertIsNone(r.json()['company']['contract_end_date'])

    def test_invalid_date_returns_400_not_500(self):
        self._login()
        c = Company.objects.create(name='Gamma')
        r = self.client.patch(f'/api/admin/companies/{c.id}/', data=json.dumps(
            {'contract_end_date': 'not-a-date'}), content_type='application/json')
        self.assertEqual(r.status_code, 400)
