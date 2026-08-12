"""In-portal incident and maintenance notices (#49).

Scope note: this banner SUPPLEMENTS the account-contact email that EC-SOP-07
§5.2 names as the notification channel — it does not satisfy it. The banner
shares fate with the portal (one host, one web container), so it is offline
exactly when a SEV-1 is happening. Tests here cover the portal surface only.
"""
import json
from datetime import timedelta

from django.test import Client, TestCase
from django.utils import timezone

from portal.models import Company, NoticeDismissal, PortalUser, SiteNotice


def make_notice(**kwargs):
    kwargs.setdefault('message', 'Sync is delayed while we work on it.')
    companies = kwargs.pop('companies', None)
    notice = SiteNotice.objects.create(**kwargs)
    if companies:
        notice.companies.set(companies)
    return notice


class ActiveWindowTests(TestCase):
    def test_a_notice_with_no_end_date_stays_visible(self):
        """An incident has no known end when it is raised."""
        notice = make_notice(ends_at=None)
        self.assertIn(notice, SiteNotice.currently_visible())

    def test_a_notice_scheduled_for_later_is_not_visible_yet(self):
        """Scheduled maintenance is announced 72 hours ahead (EC-SOP-07 §3.2)
        and must not appear until its window opens."""
        notice = make_notice(starts_at=timezone.now() + timedelta(hours=72))
        self.assertNotIn(notice, SiteNotice.currently_visible())

    def test_a_notice_past_its_end_date_is_not_visible(self):
        notice = make_notice(
            starts_at=timezone.now() - timedelta(hours=2),
            ends_at=timezone.now() - timedelta(hours=1),
        )
        self.assertNotIn(notice, SiteNotice.currently_visible())

    def test_a_retired_notice_is_not_visible(self):
        notice = make_notice(retired_at=timezone.now())
        self.assertNotIn(notice, SiteNotice.currently_visible())

    def test_retiring_keeps_the_row_so_history_survives(self):
        """TG-421 asked for a log of incidents and resolutions, so retiring a
        notice must not be a delete."""
        notice = make_notice()
        notice.retire()
        notice.refresh_from_db()
        self.assertIsNotNone(notice.retired_at)
        self.assertNotIn(notice, SiteNotice.currently_visible())


class TenantScopingTests(TestCase):
    def setUp(self):
        self.acme = Company.objects.create(name='Acme')
        self.globex = Company.objects.create(name='Globex')
        self.acme_user = PortalUser.objects.create(
            email='a@acme.com', company=self.acme, role='customer')
        self.globex_user = PortalUser.objects.create(
            email='g@globex.com', company=self.globex, role='customer')
        self.staff = PortalUser.objects.create(
            email='agent@citemed.com', company=None, role='admin')

    def test_an_unscoped_notice_reaches_everyone(self):
        notice = make_notice()
        self.assertIn(notice, SiteNotice.for_user(self.acme_user))
        self.assertIn(notice, SiteNotice.for_user(self.globex_user))

    def test_an_unscoped_notice_reaches_a_user_with_no_company(self):
        """Agents have no company row; a platform-wide notice still applies."""
        notice = make_notice()
        self.assertIn(notice, SiteNotice.for_user(self.staff))

    def test_a_scoped_notice_reaches_only_the_named_company(self):
        """A SEV-2 often affects a subset of clients."""
        notice = make_notice(companies=[self.acme])
        self.assertIn(notice, SiteNotice.for_user(self.acme_user))
        self.assertNotIn(notice, SiteNotice.for_user(self.globex_user))

    def test_a_scoped_notice_does_not_leak_to_a_user_with_no_company(self):
        notice = make_notice(companies=[self.acme])
        self.assertNotIn(notice, SiteNotice.for_user(self.staff))

    def test_an_anonymous_caller_gets_nothing(self):
        make_notice()
        self.assertEqual(list(SiteNotice.for_user(None)), [])

    def test_a_notice_is_not_returned_twice_when_scoped_to_several_companies(self):
        """The OR across an M2M join duplicates rows without a distinct()."""
        notice = make_notice(companies=[self.acme, self.globex])
        self.assertEqual(list(SiteNotice.for_user(self.acme_user)), [notice])


class DismissibilityTests(TestCase):
    def test_critical_notices_cannot_be_dismissed(self):
        self.assertFalse(make_notice(level=SiteNotice.LEVEL_CRITICAL).is_dismissible)

    def test_lower_levels_can_be_dismissed(self):
        self.assertTrue(make_notice(level=SiteNotice.LEVEL_INFO).is_dismissible)
        self.assertTrue(make_notice(level=SiteNotice.LEVEL_WARNING).is_dismissible)


class CustomerReadEndpointTests(TestCase):
    url = '/api/notices/'

    def setUp(self):
        self.acme = Company.objects.create(name='Acme')
        self.globex = Company.objects.create(name='Globex')
        self.user = PortalUser.objects.create(
            email='a@acme.com', company=self.acme, role='customer')

    def _login(self, user=None):
        session = self.client.session
        session['portal_user_id'] = (user or self.user).id
        session.save()

    def test_requires_a_session(self):
        """§5.2 says we do not operate a PUBLIC status page, so this endpoint
        must not become one."""
        make_notice()
        self.assertEqual(self.client.get(self.url).status_code, 401)

    def test_returns_a_live_notice(self):
        self._login()
        notice = make_notice(level=SiteNotice.LEVEL_WARNING, message='Sync delayed')
        body = self.client.get(self.url).json()
        self.assertEqual([n['id'] for n in body['notices']], [notice.id])
        self.assertEqual(body['notices'][0]['level'], 'warning')
        self.assertEqual(body['notices'][0]['message'], 'Sync delayed')

    def test_omits_a_notice_for_another_company(self):
        self._login()
        make_notice(companies=[self.globex])
        self.assertEqual(self.client.get(self.url).json()['notices'], [])

    def test_omits_a_scheduled_notice_until_its_window_opens(self):
        self._login()
        make_notice(starts_at=timezone.now() + timedelta(hours=72))
        self.assertEqual(self.client.get(self.url).json()['notices'], [])

    def test_omits_a_notice_this_user_has_dismissed(self):
        self._login()
        notice = make_notice()
        self.client.post(f'/api/notices/{notice.id}/dismiss')
        self.assertEqual(self.client.get(self.url).json()['notices'], [])

    def test_a_dismissal_by_one_colleague_does_not_clear_it_for_another(self):
        colleague = PortalUser.objects.create(
            email='b@acme.com', company=self.acme, role='customer')
        notice = make_notice()
        self._login()
        self.client.post(f'/api/notices/{notice.id}/dismiss')
        self._login(colleague)
        self.assertEqual(
            [n['id'] for n in self.client.get(self.url).json()['notices']], [notice.id])

    def test_tells_the_client_whether_a_notice_may_be_dismissed(self):
        self._login()
        make_notice(level=SiteNotice.LEVEL_CRITICAL)
        self.assertFalse(self.client.get(self.url).json()['notices'][0]['dismissible'])


class DismissEndpointTests(TestCase):
    def setUp(self):
        self.acme = Company.objects.create(name='Acme')
        self.user = PortalUser.objects.create(
            email='a@acme.com', company=self.acme, role='customer')
        session = self.client.session
        session['portal_user_id'] = self.user.id
        session.save()

    def test_refuses_to_dismiss_a_critical_notice(self):
        """Enforced here, not only by hiding the button — the endpoint is
        reachable directly."""
        notice = make_notice(level=SiteNotice.LEVEL_CRITICAL)
        response = self.client.post(f'/api/notices/{notice.id}/dismiss')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(NoticeDismissal.objects.count(), 0)

    def test_dismissing_twice_is_harmless(self):
        """The banner can be clicked twice, and a retry must not 500."""
        notice = make_notice()
        first = self.client.post(f'/api/notices/{notice.id}/dismiss')
        second = self.client.post(f'/api/notices/{notice.id}/dismiss')
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(NoticeDismissal.objects.count(), 1)

    def test_cannot_dismiss_another_companys_notice(self):
        """Not a real UI path, but the id is guessable and this is the tenant
        boundary, so it must be checked rather than assumed."""
        other = Company.objects.create(name='Globex')
        notice = make_notice(companies=[other])
        response = self.client.post(f'/api/notices/{notice.id}/dismiss')
        self.assertEqual(response.status_code, 404)
        self.assertEqual(NoticeDismissal.objects.count(), 0)

    def test_rejects_a_get(self):
        notice = make_notice()
        self.assertEqual(self.client.get(f'/api/notices/{notice.id}/dismiss').status_code, 405)


class NoticeHistoryTests(TestCase):
    """The "log of incidents and resolutions" TG-421 asked for."""
    url = '/api/notices/history/'

    def setUp(self):
        self.acme = Company.objects.create(name='Acme')
        self.user = PortalUser.objects.create(
            email='a@acme.com', company=self.acme, role='customer')
        session = self.client.session
        session['portal_user_id'] = self.user.id
        session.save()

    def test_includes_retired_notices(self):
        retired = make_notice(message='Resolved incident')
        retired.retire()
        self.assertEqual(
            [n['id'] for n in self.client.get(self.url).json()['notices']], [retired.id])

    def test_includes_a_dismissed_notice_that_is_still_live(self):
        """Dismissing hides the banner, not the record."""
        notice = make_notice()
        self.client.post(f'/api/notices/{notice.id}/dismiss')
        self.assertIn(notice.id, [n['id'] for n in self.client.get(self.url).json()['notices']])

    def test_still_excludes_another_companys_notices(self):
        make_notice(companies=[Company.objects.create(name='Globex')])
        self.assertEqual(self.client.get(self.url).json()['notices'], [])

    def test_requires_a_session(self):
        self.assertEqual(Client().get(self.url).status_code, 401)


class AdminNoticeEndpointTests(TestCase):
    url = '/api/admin/notices/'

    def setUp(self):
        self.acme = Company.objects.create(name='Acme')
        self.admin = PortalUser.objects.create(
            email='agent@citemed.com', role='admin')
        self.customer = PortalUser.objects.create(
            email='a@acme.com', company=self.acme, role='customer')
        self._login(self.admin)

    def _login(self, user):
        session = self.client.session
        session['portal_user_id'] = user.id
        session.save()

    def _post(self, payload, url=None):
        return self.client.post(
            url or self.url, data=json.dumps(payload), content_type='application/json')

    def test_a_customer_cannot_raise_a_notice(self):
        self._login(self.customer)
        self.assertEqual(self._post({'message': 'we are down'}).status_code, 403)

    def test_a_customer_cannot_list_notices_through_the_admin_endpoint(self):
        self._login(self.customer)
        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_raises_a_notice_without_a_deploy(self):
        response = self._post({
            'level': 'critical', 'message': 'Uploads are failing',
            'link_url': 'https://support.citemed.com/support', 'link_label': 'Open a ticket',
        })
        self.assertEqual(response.status_code, 201)
        notice = SiteNotice.objects.get(pk=response.json()['notice']['id'])
        self.assertEqual(notice.level, 'critical')
        self.assertEqual(notice.message, 'Uploads are failing')
        self.assertEqual(notice.created_by_id, self.admin.id)

    def test_records_company_scoping(self):
        response = self._post({'message': 'Your sync is delayed', 'company_ids': [self.acme.id]})
        notice = SiteNotice.objects.get(pk=response.json()['notice']['id'])
        self.assertEqual([c.id for c in notice.companies.all()], [self.acme.id])

    def test_rejects_an_empty_message(self):
        """A blank banner is worse than none."""
        self.assertEqual(self._post({'message': '   '}).status_code, 400)

    def test_rejects_an_unknown_level(self):
        self.assertEqual(self._post({'message': 'x', 'level': 'apocalyptic'}).status_code, 400)

    def test_refuses_a_javascript_url(self):
        """link_url is rendered into an href the customer clicks, and Vue does
        not sanitize a bound href. URLField's validators do NOT run on
        objects.create() — only full_clean() applies them — so without an
        explicit check an agent could store javascript: and run script in a
        customer's session. Agents are trusted with customer data, not with
        code execution in a customer's browser.
        """
        for hostile in ('javascript:alert(1)', 'JavaScript:alert(1)',
                        ' javascript:alert(1)', 'data:text/html,<script>alert(1)</script>',
                        'vbscript:msgbox(1)'):
            with self.subTest(url=hostile):
                response = self._post({'message': 'x', 'link_url': hostile})
                self.assertEqual(response.status_code, 400, hostile)
        self.assertEqual(SiteNotice.objects.count(), 0)

    def test_refuses_a_javascript_url_on_edit_too(self):
        """The create path is not the only way in."""
        notice = make_notice()
        response = self.client.patch(
            f'{self.url}{notice.id}/',
            data=json.dumps({'link_url': 'javascript:alert(1)'}),
            content_type='application/json')
        self.assertEqual(response.status_code, 400)
        notice.refresh_from_db()
        self.assertEqual(notice.link_url, '')

    def test_still_accepts_an_ordinary_link(self):
        response = self._post({
            'message': 'x', 'link_url': 'https://support.citemed.com/support'})
        self.assertEqual(response.status_code, 201)
        self.assertEqual(
            SiteNotice.objects.get(pk=response.json()['notice']['id']).link_url,
            'https://support.citemed.com/support')

    def test_still_accepts_no_link_at_all(self):
        self.assertEqual(self._post({'message': 'x', 'link_url': ''}).status_code, 201)

    def test_rejects_a_link_too_long_for_the_column(self):
        """URLField is 200 chars and create()/save() never call full_clean(),
        so an over-length paste reaches the database unchecked: a DataError 500
        on Postgres (production), silently truncated-free on SQLite. Either way
        the agent gets no useful answer."""
        response = self._post({
            'message': 'x', 'link_url': 'https://example.com/' + 'a' * 300})
        self.assertEqual(response.status_code, 400)

    def test_rejects_a_link_label_too_long_for_the_column(self):
        response = self._post({'message': 'x', 'link_label': 'l' * 100})
        self.assertEqual(response.status_code, 400)

    def test_records_an_explicit_maintenance_window(self):
        """§3.2 maintenance notices are written ahead of the window they describe."""
        starts = timezone.now() + timedelta(hours=72)
        ends = starts + timedelta(hours=4)
        response = self._post({
            'message': 'Planned maintenance, Saturday 02:00–06:00 ET',
            'starts_at': starts.isoformat(), 'ends_at': ends.isoformat(),
        })
        notice = SiteNotice.objects.get(pk=response.json()['notice']['id'])
        self.assertEqual(notice.starts_at.isoformat(), starts.isoformat())
        self.assertEqual(notice.ends_at.isoformat(), ends.isoformat())

    def test_rejects_a_window_that_ends_before_it_starts(self):
        """Silently accepting it would create a notice that can never show."""
        starts = timezone.now()
        response = self._post({
            'message': 'backwards',
            'starts_at': starts.isoformat(),
            'ends_at': (starts - timedelta(hours=1)).isoformat(),
        })
        self.assertEqual(response.status_code, 400)

    def test_edits_an_existing_notice(self):
        notice = make_notice(message='first wording')
        response = self.client.patch(
            f'{self.url}{notice.id}/', data=json.dumps({'message': 'clearer wording'}),
            content_type='application/json')
        self.assertEqual(response.status_code, 200)
        notice.refresh_from_db()
        self.assertEqual(notice.message, 'clearer wording')

    def test_retires_a_notice_without_deleting_it(self):
        notice = make_notice()
        response = self.client.delete(f'{self.url}{notice.id}/')
        self.assertEqual(response.status_code, 200)
        notice.refresh_from_db()
        self.assertIsNotNone(notice.retired_at)

    def test_lists_retired_notices_too_so_history_is_manageable(self):
        live = make_notice(message='live')
        retired = make_notice(message='retired')
        retired.retire()
        ids = [n['id'] for n in self.client.get(self.url).json()['notices']]
        self.assertIn(live.id, ids)
        self.assertIn(retired.id, ids)
