import json
from unittest.mock import patch

from django.test import TestCase
from django.core import mail

from portal.models import Company, PortalUser, Ticket, TicketMessage


def make_co_user(name='Acme', email='a@acme.com', role='customer'):
    co = Company.objects.create(name=name)
    u = PortalUser.objects.create(email=email, company=co, role=role)
    return co, u


class TicketModelTests(TestCase):
    def setUp(self):
        self.acme, self.cust = make_co_user()
        self.globex, self.other = make_co_user('Globex', 'g@globex.com')
        self.staff = PortalUser.objects.create(email='s@citemed.com', role='admin')

    def test_numbers_are_sequential_and_display_formatted(self):
        t1 = Ticket.objects.create(company=self.acme, created_by=self.cust, subject='A')
        t2 = Ticket.objects.create(company=self.globex, created_by=self.other, subject='B')
        self.assertEqual(t2.number, t1.number + 1)
        self.assertEqual(t1.display_number, f'CS-{t1.number}')

    def test_for_user_scopes_to_own_company(self):
        t = Ticket.objects.create(company=self.acme, created_by=self.cust, subject='A')
        Ticket.objects.create(company=self.globex, created_by=self.other, subject='B')
        ids = list(Ticket.for_user(self.cust).values_list('id', flat=True))
        self.assertEqual(ids, [t.id])

    def test_for_user_without_company_sees_nothing(self):
        loner = PortalUser.objects.create(email='x@x.com', role='customer')
        Ticket.objects.create(company=self.acme, created_by=self.cust, subject='A')
        self.assertEqual(Ticket.for_user(loner).count(), 0)

    def test_default_status_is_waiting_on_support(self):
        t = Ticket.objects.create(company=self.acme, created_by=self.cust, subject='A')
        self.assertEqual(t.status, Ticket.STATUS_WAITING_ON_SUPPORT)
