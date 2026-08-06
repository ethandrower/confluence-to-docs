"""SLA-driven triage (EC-SOP-07 §4.1, requested by Priscilla 2026-08-06).

The Inbox previously ordered strictly oldest-first, so an URGENT filed this
morning sat below a Standard from last week — which defeats the point of
having a priority at all. These cover ordering and filtering by priority.
"""
import json
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from portal.models import Company, PortalUser, Ticket


class InboxPriorityOrderingTest(TestCase):
    def setUp(self):
        self.co = Company.objects.create(name='Acme')
        self.staff = PortalUser.objects.create(
            email='s@citemed.com', role=PortalUser.ROLE_ADMIN)
        s = self.client.session
        s['portal_user_id'] = self.staff.id
        s.save()

    def _ticket(self, subject, priority, days_old):
        t = Ticket.objects.create(
            company=self.co, subject=subject, priority=priority,
            status=Ticket.STATUS_WAITING_ON_SUPPORT)
        # updated_at is auto_now, so set it explicitly past the save.
        Ticket.objects.filter(pk=t.pk).update(
            updated_at=timezone.now() - timedelta(days=days_old))
        return t

    def test_urgent_outranks_an_older_standard(self):
        old_standard = self._ticket('week-old standard', 'standard', days_old=7)
        new_urgent = self._ticket('urgent today', 'urgent', days_old=0)
        r = self.client.get('/api/admin/tickets/inbox/')
        nums = [x['number'] for x in r.json()['tickets']]
        self.assertEqual(nums, [new_urgent.number, old_standard.number])

    def test_full_priority_order(self):
        # Rank follows the response commitments in EC-SOP-07 §4.1.
        made = {p: self._ticket(p, p, days_old=0)
                for p in ('standard', 'csm_direct', 'high', 'urgent')}
        r = self.client.get('/api/admin/tickets/inbox/')
        nums = [x['number'] for x in r.json()['tickets']]
        self.assertEqual(nums, [made['urgent'].number, made['high'].number,
                                made['csm_direct'].number, made['standard'].number])

    def test_oldest_first_still_breaks_ties_within_a_priority(self):
        newer = self._ticket('newer high', 'high', days_old=1)
        older = self._ticket('older high', 'high', days_old=5)
        r = self.client.get('/api/admin/tickets/inbox/')
        nums = [x['number'] for x in r.json()['tickets']]
        self.assertEqual(nums, [older.number, newer.number])


class AdminListPriorityFilterTest(TestCase):
    def setUp(self):
        self.co = Company.objects.create(name='Acme')
        staff = PortalUser.objects.create(
            email='s@citemed.com', role=PortalUser.ROLE_ADMIN)
        s = self.client.session
        s['portal_user_id'] = staff.id
        s.save()
        self.urgent = Ticket.objects.create(
            company=self.co, subject='u', priority='urgent')
        self.standard = Ticket.objects.create(
            company=self.co, subject='s', priority='standard')

    def test_filters_to_one_priority(self):
        r = self.client.get('/api/admin/tickets/?priority=urgent')
        nums = [x['number'] for x in r.json()['tickets']]
        self.assertEqual(nums, [self.urgent.number])

    def test_no_filter_returns_everything(self):
        r = self.client.get('/api/admin/tickets/')
        self.assertEqual(len(r.json()['tickets']), 2)

    def test_unknown_priority_is_ignored_rather_than_returning_nothing(self):
        # A bad querystring value should not silently look like "no tickets".
        r = self.client.get('/api/admin/tickets/?priority=bogus')
        self.assertEqual(len(r.json()['tickets']), 2)
