from django.contrib.auth import get_user_model
from django.test import TestCase

from portal.decorators import is_portal_admin
from portal.models import Company, PortalUser


class IsPortalAdminTest(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name='Acme')

    def _user(self, role, email='u@acme.com'):
        return PortalUser.objects.create(email=email, company=self.company, role=role)

    def test_owner_is_admin(self):
        self.assertTrue(is_portal_admin(self._user(PortalUser.ROLE_OWNER)))

    def test_admin_role_is_admin(self):
        self.assertTrue(is_portal_admin(self._user(PortalUser.ROLE_ADMIN)))

    def test_plain_customer_is_not_admin(self):
        self.assertFalse(is_portal_admin(self._user(PortalUser.ROLE_CUSTOMER)))

    def test_superuser_by_email_is_admin(self):
        get_user_model().objects.create_superuser(
            username='su', email='boss@acme.com', password='x')
        self.assertFalse(is_portal_admin(self._user(PortalUser.ROLE_CUSTOMER, 'nope@acme.com')))
        self.assertTrue(is_portal_admin(self._user(PortalUser.ROLE_CUSTOMER, 'boss@acme.com')))

    def test_none_is_not_admin(self):
        self.assertFalse(is_portal_admin(None))
