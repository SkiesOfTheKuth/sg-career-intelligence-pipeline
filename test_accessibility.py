"""Browser-measured accessibility contracts; fixtures make no external calls."""
import unittest
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).parent


def source_audit_fixture():
    """A complete retained-source response exercises the production renderer."""
    source = {'id': 'mcf', 'name': 'MyCareersFuture', 'state': 'scheduled',
              'count': 2, 'scope': 'Four bounded searches.', 'method': 'Free API',
              'mode': 'scheduled', 'home': 'https://example.test/source',
              'needs_recheck': 2, 'latest_errors': [], 'coverage': []}
    return {'sources': [source], 'total': 2, 'discovery_count': 2,
            'applications_count': 0, 'excluded_count': 0, 'coverage': [],
            'history': [], 'generated_at': 1792600000, 'explanation': 'Retained source evidence.',
            'scheduler': {'running': False, 'enabled': True, 'interval_hours': 12,
                          'limit_per_query': 10, 'queries': ['Thai', 'Marketing Executive',
                          'Social Media Executive', 'Public Relations']}}


class AccessibilityContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pw = sync_playwright().start()
        cls.browser = cls.pw.chromium.launch()

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()

    def setUp(self):
        self.context = self.browser.new_context()
        self.audit = source_audit_fixture()
        def route(request):
            path = request.request.url.split('workspace.test', 1)[1].split('?', 1)[0]
            if path == '/api/audit/sources':
                return request.fulfill(json=self.audit)
            if path.startswith('/api/'):
                return request.fulfill(json={'items': [], 'total': 0, 'limit': 20})
            file = ROOT / ('templates/index.html' if path == '/' else 'templates/sources.html' if path == '/sources' else path.lstrip('/'))
            request.fulfill(body=file.read_bytes(), content_type='text/html' if file.suffix == '.html' else 'text/css' if file.suffix == '.css' else 'text/javascript')
        self.context.route('https://workspace.test/**', route)
        self.page = self.context.new_page()

    def tearDown(self):
        self.context.close()

    def test_input_boundaries_have_three_to_one_contrast(self):
        self.page.goto('https://workspace.test/')
        ratio = self.page.locator('#search-query').evaluate(r'''n => {
            const css = getComputedStyle(n);
            const lum = value => {const c = value.match(/[\d.]+/g).slice(0,3).map(v => {v=Number(v)/255;return v<=.04045?v/12.92:Math.pow((v+.055)/1.055,2.4)});return c[0]*.2126+c[1]*.7152+c[2]*.0722};
            const a=lum(css.borderTopColor),b=lum(css.backgroundColor);
            return (Math.max(a,b)+.05)/(Math.min(a,b)+.05);
        }''')
        self.assertGreaterEqual(ratio, 3, 'A white input needs a visible boundary against its white surroundings.')

    def test_mobile_detail_uses_an_element_supporting_dialog_role(self):
        self.page.goto('https://workspace.test/')
        self.assertEqual(self.page.locator('#role-detail').evaluate('(n)=>n.tagName'), 'DIV')

    def test_source_disclosure_has_a_section_heading(self):
        self.page.goto('https://workspace.test/sources')
        self.assertEqual(self.page.locator('#flow-heading h2').count(), 1)

    def test_source_standalone_links_have_touch_sized_targets(self):
        self.page.goto('https://workspace.test/sources')
        self.page.locator('#record-source').select_option('mcf')
        box = self.page.locator('#selected-detail > a').bounding_box()
        self.assertGreaterEqual(box['height'], 44)

    def test_mobile_sources_keyboard_order_matches_health_then_search(self):
        self.page.set_viewport_size({'width': 390, 'height': 844})
        self.page.goto('https://workspace.test/sources')
        self.page.locator('#audit-content').wait_for(state='visible')
        self.page.locator('#refresh-overview').focus()
        self.page.keyboard.press('Tab')
        self.assertEqual(self.page.locator(':focus').inner_text(), 'Check schedule and scope')
        self.page.keyboard.press('Tab')
        self.assertEqual(self.page.locator(':focus').get_attribute('id'), 'record-source')
        self.page.keyboard.press('Tab')
        self.assertEqual(self.page.locator(':focus').get_attribute('id'), 'record-query')
        order = self.page.locator('#audit-content > *').evaluate_all('(nodes)=>nodes.map(n=>n.classList[0])')
        self.assertEqual(order, ['collection-status', 'records-section', 'flow-section', 'audit-detail-disclosure', 'history-section'])

    def test_desktop_sources_keep_flow_first_in_reading_and_keyboard_order(self):
        self.page.set_viewport_size({'width': 1440, 'height': 900})
        self.page.goto('https://workspace.test/sources')
        self.page.locator('#audit-content').wait_for(state='visible')
        self.page.locator('#refresh-overview').focus()
        self.page.keyboard.press('Tab')
        self.assertEqual(self.page.locator(':focus').get_attribute('id'), 'flow-heading')
        self.page.keyboard.press('Tab')
        self.assertEqual(self.page.locator(':focus').get_attribute('data-source'), 'mcf')

    def test_selecting_source_keeps_keyboard_focus_on_the_filter(self):
        for width in (390, 1440):
            with self.subTest(width=width):
                self.page.set_viewport_size({'width': width, 'height': 900})
                self.page.goto('https://workspace.test/sources')
                source = self.page.locator('#record-source')
                source.focus()
                source.select_option('mcf')
                self.assertEqual(self.page.locator(':focus').get_attribute('id'), 'record-source')
                self.page.keyboard.press('Tab')
                self.assertEqual(self.page.locator(':focus').get_attribute('id'), 'record-query')

    def test_responsive_reordering_preserves_focus_and_handles_collapsed_content(self):
        self.page.set_viewport_size({'width': 1440, 'height': 900})
        self.page.goto('https://workspace.test/sources')
        self.page.locator('#audit-content').wait_for(state='visible')
        query = self.page.locator('#record-query')
        query.fill('marketing')
        query.focus()
        self.page.set_viewport_size({'width': 390, 'height': 844})
        self.page.wait_for_function("document.querySelector('#audit-content').firstElementChild.classList.contains('collection-status')")
        self.assertEqual(self.page.locator(':focus').get_attribute('id'), 'record-query')
        self.assertEqual(query.input_value(), 'marketing')
        self.page.set_viewport_size({'width': 1440, 'height': 900})
        self.page.wait_for_function("document.querySelector('.flow-section').open")
        self.page.locator('.source-node').focus()
        self.page.set_viewport_size({'width': 390, 'height': 844})
        self.page.wait_for_function("!document.querySelector('.flow-section').open")
        self.assertEqual(self.page.locator(':focus').get_attribute('id'), 'flow-heading')

    def test_source_loading_and_failure_offer_a_keyboard_retry(self):
        pending = []
        self.page.route('**/api/audit/sources', lambda route: pending.append(route))
        self.page.goto('https://workspace.test/sources')
        self.page.wait_for_function("document.querySelector('#refresh-overview').disabled")
        self.assertIn('Loading source records', self.page.locator('#load-feedback').inner_text())
        self.assertFalse(self.page.locator('#audit-content').is_visible())
        self.page.wait_for_timeout(20)
        self.assertEqual(len(pending), 1)
        pending.pop().fulfill(status=503, json={'error': 'Unavailable'})
        retry = self.page.locator('#load-feedback').get_by_role('button', name='Retry')
        retry.wait_for()
        retry.focus()
        self.page.keyboard.press('Enter')
        self.page.wait_for_timeout(20)
        self.assertEqual(len(pending), 1)
        pending.pop().fulfill(json=self.audit)
        self.page.locator('#audit-content').wait_for(state='visible')
        self.assertFalse(self.page.locator('#load-feedback').is_visible())

    def test_record_failure_keeps_filters_and_keyboard_retry(self):
        pending = []
        self.page.route('**/api/audit/records?**', lambda route: pending.append(route))
        self.page.goto('https://workspace.test/sources?source=mcf&q=marketing')
        self.page.locator('#audit-content').wait_for(state='visible')
        self.assertEqual(self.page.locator('#records').get_attribute('aria-busy'), 'true')
        self.assertIn('Loading records', self.page.locator('#record-count').inner_text())
        self.page.wait_for_timeout(20)
        pending.pop().fulfill(status=503, json={})
        retry = self.page.locator('#records').get_by_role('button', name='Retry')
        retry.wait_for()
        self.assertEqual(self.page.locator('#records').get_attribute('aria-busy'), 'false')
        self.assertEqual(self.page.locator('#record-query').input_value(), 'marketing')
        self.assertEqual(self.page.locator('#record-source').input_value(), 'mcf')
        retry.focus()
        self.page.keyboard.press('Enter')
        self.page.wait_for_timeout(20)
        pending.pop().fulfill(json={'items': [], 'total': 0, 'limit': 20})
        self.page.get_by_role('button', name='Clear search and filters').wait_for()
        self.assertEqual(self.page.locator('#record-query').input_value(), 'marketing')

    def test_failed_overview_reload_keeps_available_records_and_filters(self):
        self.page.goto('https://workspace.test/sources?q=marketing')
        self.page.locator('#audit-content').wait_for(state='visible')
        self.page.route('**/api/audit/sources', lambda route: route.fulfill(status=503, json={}))
        self.page.locator('#refresh-overview').click()
        self.page.locator('#load-feedback').get_by_role('button', name='Retry').wait_for()
        self.assertTrue(self.page.locator('#audit-content').is_visible())
        self.assertEqual(self.page.locator('#record-query').input_value(), 'marketing')
        self.assertEqual(self.page.locator('#refresh-overview').is_enabled(), True)


if __name__ == '__main__':
    unittest.main()
