"""First-response SLA targets (EC-SOP-07 §4.1).

    Priority     First response      →  modelled as
    URGENT       Same business day      end of the business day it arrived
    High         1 business day         9 business hours
    Standard     1-2 business days      18 business hours (the outer bound)
    CSM Direct   Within 24 hours        24 CALENDAR hours (the doc says hours,
                                        not business days, for this one)

Business Hours per the doc: Mon-Fri 09:00-18:00, and a request arriving
outside them counts as received at the start of the next business day.
"""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from django.test import TestCase

from portal import sla
from portal.models import Company, PortalUser, Ticket, TicketMessage

TZ = ZoneInfo('America/New_York')


def at(y, m, d, hh, mm=0):
    return datetime(y, m, d, hh, mm, tzinfo=TZ)


class ReceiptTimeTest(TestCase):
    """The clock starts when the request is deemed received, not when it landed."""

    def test_inside_business_hours_is_received_immediately(self):
        t = at(2026, 8, 5, 10, 30)          # Wednesday 10:30
        self.assertEqual(sla.receipt_time(t), t)

    def test_before_opening_waits_for_opening(self):
        self.assertEqual(sla.receipt_time(at(2026, 8, 5, 6, 0)),
                         at(2026, 8, 5, 9, 0))

    def test_after_close_rolls_to_the_next_morning(self):
        self.assertEqual(sla.receipt_time(at(2026, 8, 5, 21, 0)),
                         at(2026, 8, 6, 9, 0))

    def test_saturday_rolls_to_monday(self):
        self.assertEqual(sla.receipt_time(at(2026, 8, 8, 11, 0)),   # Sat
                         at(2026, 8, 10, 9, 0))                     # Mon

    def test_friday_evening_rolls_to_monday(self):
        self.assertEqual(sla.receipt_time(at(2026, 8, 7, 19, 0)),   # Fri 19:00
                         at(2026, 8, 10, 9, 0))                     # Mon 09:00


class BusinessHoursArithmeticTest:
    pass


class FirstResponseDueTest(TestCase):
    def setUp(self):
        self.co = Company.objects.create(name='Acme')

    def _ticket(self, priority, created):
        t = Ticket.objects.create(company=self.co, subject='x', priority=priority)
        Ticket.objects.filter(pk=t.pk).update(created_at=created)
        t.refresh_from_db()
        return t

    def test_urgent_is_due_by_close_of_the_day_it_arrived(self):
        t = self._ticket('urgent', at(2026, 8, 5, 10, 0))    # Wed 10:00
        self.assertEqual(sla.first_response_due(t), at(2026, 8, 5, 18, 0))

    def test_urgent_arriving_at_night_is_due_end_of_the_next_business_day(self):
        t = self._ticket('urgent', at(2026, 8, 5, 22, 0))    # Wed 22:00
        self.assertEqual(sla.first_response_due(t), at(2026, 8, 6, 18, 0))

    def test_high_is_one_business_day_of_hours(self):
        # Wed 14:00 + 9 business hours -> Thu 14:00 (5h Wed, 4h Thu)
        t = self._ticket('high', at(2026, 8, 5, 14, 0))
        self.assertEqual(sla.first_response_due(t), at(2026, 8, 6, 14, 0))

    def test_high_over_a_weekend_skips_it(self):
        # Fri 14:00 + 9 business hours -> Mon 14:00
        t = self._ticket('high', at(2026, 8, 7, 14, 0))
        self.assertEqual(sla.first_response_due(t), at(2026, 8, 10, 14, 0))

    def test_standard_uses_the_outer_bound_of_two_business_days(self):
        # Wed 09:00 + 18 business hours = 9h Wed + 9h Thu -> close of Thursday.
        t = self._ticket('standard', at(2026, 8, 5, 9, 0))
        self.assertEqual(sla.first_response_due(t), at(2026, 8, 6, 18, 0))

    def test_standard_spanning_a_weekend(self):
        # Thu 14:00 + 18h: 4h Thu, 9h Fri, 5h Mon -> Mon 14:00.
        t = self._ticket('standard', at(2026, 8, 6, 14, 0))
        self.assertEqual(sla.first_response_due(t), at(2026, 8, 10, 14, 0))

    def test_csm_direct_is_calendar_hours_not_business_hours(self):
        # The doc says "within 24 hours" for this tier only — so a Friday
        # request is due Saturday, not Monday.
        t = self._ticket('csm_direct', at(2026, 8, 7, 14, 0))
        self.assertEqual(sla.first_response_due(t), at(2026, 8, 8, 14, 0))


class BreachTest(TestCase):
    def setUp(self):
        self.co = Company.objects.create(name='Acme')
        self.staff = PortalUser.objects.create(
            email='s@citemed.com', role=PortalUser.ROLE_ADMIN)

    def _ticket(self, created, priority='high'):
        t = Ticket.objects.create(company=self.co, subject='x', priority=priority)
        Ticket.objects.filter(pk=t.pk).update(created_at=created)
        t.refresh_from_db()
        return t

    def test_unanswered_and_past_due_is_breached(self):
        t = self._ticket(at(2026, 8, 5, 9, 0))
        self.assertTrue(sla.is_breached(t, now=at(2026, 8, 7, 12, 0)))

    def test_unanswered_but_still_within_target_is_not_breached(self):
        t = self._ticket(at(2026, 8, 5, 9, 0))
        self.assertFalse(sla.is_breached(t, now=at(2026, 8, 5, 12, 0)))

    def test_answered_in_time_is_never_breached_afterwards(self):
        t = self._ticket(at(2026, 8, 5, 9, 0))
        t.first_response_at = at(2026, 8, 5, 11, 0)
        t.save(update_fields=['first_response_at'])
        # Long past the deadline now, but it was answered in time.
        self.assertFalse(sla.is_breached(t, now=at(2026, 8, 20, 12, 0)))

    def test_answered_late_stays_breached(self):
        t = self._ticket(at(2026, 8, 5, 9, 0))
        t.first_response_at = at(2026, 8, 12, 9, 0)
        t.save(update_fields=['first_response_at'])
        self.assertTrue(sla.is_breached(t, now=at(2026, 8, 20, 12, 0)))


class FirstResponseTrackingTest(TestCase):
    def setUp(self):
        self.co = Company.objects.create(name='Acme')
        self.cust = PortalUser.objects.create(
            email='c@acme.com', company=self.co, role=PortalUser.ROLE_CUSTOMER)
        self.staff = PortalUser.objects.create(
            email='s@citemed.com', role=PortalUser.ROLE_ADMIN)
        self.t = Ticket.objects.create(
            company=self.co, created_by=self.cust, subject='Help')

    def _msg(self, origin, internal=False, author=None):
        return TicketMessage.objects.create(
            ticket=self.t, author=author, author_email='x@y.z', body='b',
            origin=origin, is_internal=internal)

    def test_a_staff_reply_records_the_first_response(self):
        self._msg(TicketMessage.ORIGIN_PORTAL, author=self.cust)
        msg = self._msg(TicketMessage.ORIGIN_STAFF, author=self.staff)
        sla.record_first_response(self.t, msg)
        self.t.refresh_from_db()
        self.assertIsNotNone(self.t.first_response_at)

    def test_an_internal_note_is_not_a_response_to_the_customer(self):
        self._msg(TicketMessage.ORIGIN_PORTAL, author=self.cust)
        note = self._msg(TicketMessage.ORIGIN_STAFF, internal=True, author=self.staff)
        sla.record_first_response(self.t, note)
        self.t.refresh_from_db()
        self.assertIsNone(self.t.first_response_at)

    def test_a_customer_message_is_not_a_response(self):
        msg = self._msg(TicketMessage.ORIGIN_PORTAL, author=self.cust)
        sla.record_first_response(self.t, msg)
        self.t.refresh_from_db()
        self.assertIsNone(self.t.first_response_at)

    def test_the_opening_message_of_an_on_behalf_ticket_is_not_a_response(self):
        # Staff-created tickets open with a staff message — that's the request
        # being recorded, not us answering it.
        opening = self._msg(TicketMessage.ORIGIN_STAFF, author=self.staff)
        sla.record_first_response(self.t, opening)
        self.t.refresh_from_db()
        self.assertIsNone(self.t.first_response_at)

    def test_only_the_first_response_counts(self):
        self._msg(TicketMessage.ORIGIN_PORTAL, author=self.cust)
        first = self._msg(TicketMessage.ORIGIN_STAFF, author=self.staff)
        sla.record_first_response(self.t, first)
        self.t.refresh_from_db()
        original = self.t.first_response_at

        later = self._msg(TicketMessage.ORIGIN_STAFF, author=self.staff)
        sla.record_first_response(self.t, later)
        self.t.refresh_from_db()
        self.assertEqual(self.t.first_response_at, original)
