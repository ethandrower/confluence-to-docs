from django.test import TestCase, override_settings

from portal.models import DocPage, PortalUser


@override_settings(DOCS_ALLOWED_SPACES=[])  # no space restriction in tests
class DocsSearchMatchAnyTests(TestCase):
    """The docs search backs both ⌘K (default: literal phrase) and ticket
    deflection (match=any: per-word), so a realistic multi-word subject can
    surface docs even when the exact phrase never appears verbatim."""

    def setUp(self):
        self.user = PortalUser.objects.create(email='u@x.com', role='customer')
        DocPage.objects.create(
            confluence_id='c1', slug='device-families',
            title='Managing Device Families', rendered_html='',
            raw_storage='body about hardware', space_key='SP')
        DocPage.objects.create(
            confluence_id='c2', slug='outcome-measures',
            title='Reporting Outcome Measures', rendered_html='',
            raw_storage='outcome text', space_key='SP')

    def _login(self):
        s = self.client.session
        s['portal_user_id'] = self.user.id
        s.save()

    def test_default_full_phrase_misses_multiword_subject(self):
        # Current ⌘K behavior: the whole query is one literal substring.
        self._login()
        r = self.client.get('/api/docs/search/?q=device+family+reporting')
        self.assertEqual(len(r.json()['results']), 0)

    def test_match_any_finds_pages_by_individual_word(self):
        self._login()
        r = self.client.get('/api/docs/search/?q=device+family+reporting&match=any')
        titles = [x['title'] for x in r.json()['results']]
        self.assertIn('Managing Device Families', titles)   # 'device'
        self.assertIn('Reporting Outcome Measures', titles)  # 'reporting'

    def test_match_any_ignores_short_noise_words(self):
        # Short stopword-ish tokens (<=2 chars) must not match everything.
        self._login()
        r = self.client.get('/api/docs/search/?q=to+be+device&match=any')
        titles = [x['title'] for x in r.json()['results']]
        self.assertEqual(titles, ['Managing Device Families'])
