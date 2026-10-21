"""Browser regressions; API fixtures mutate only isolated in-memory records."""
import copy
import json
import unittest
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).parent
JOB = {'id':'role-1','title':'Marketing Executive','company':'Example','description':'Manage social media campaigns.', 'employment_types':['Full Time'], 'salary':{'display':'S$3,000 / month'}, 'assessment':{'fit':'Relevant','reasons':['Supported campaign work.']}, 'verification':{}}

class EditorRegression(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pw = sync_playwright().start()
        cls.browser = cls.pw.chromium.launch(headless=True)
    @classmethod
    def tearDownClass(cls):
        cls.browser.close(); cls.pw.stop()
    def setUp(self):
        self.app = {'job_id':'role-1','stage':'Saved','notes':'original','revision':1,'drafts':{},'job':JOB}
        self.fail_requests = False
        self.history_items = []
        self.context = self.browser.new_context()
        self.context.route('https://workspace.test/**', self.route)
    def tearDown(self): self.context.close()
    def route(self, route):
        path = route.request.url.split('workspace.test',1)[1].split('?',1)[0]
        if path.startswith('/api/'):
            data = {}
            if path == '/api/jobs': data = {'items':[JOB], 'total':1}
            elif path == '/api/jobs/role-1': data = JOB
            elif path == '/api/applications': data = {'items':[copy.deepcopy(self.app)]}
            elif path.endswith('/history'): data = {'items':self.history_items, 'total':len(self.history_items), 'offset':0, 'limit':25}
            elif path == '/api/applications/role-1':
                if self.fail_requests: return route.fulfill(status=503,json={'detail':'Offline fixture'})
                patch = route.request.post_data_json
                if patch.pop('expected_revision') != self.app['revision']:
                    return route.fulfill(status=409,json={'detail':{'current':copy.deepcopy(self.app)}})
                self.app.update(patch); self.app['revision'] += 1
                data = copy.deepcopy(self.app)
            route.fulfill(json=data); return
        file = ROOT / ('templates/index.html' if path == '/' else path.lstrip('/'))
        route.fulfill(body=file.read_bytes(),content_type='text/html' if file.suffix == '.html' else 'text/css' if file.suffix == '.css' else 'text/javascript')
    def page(self):
        page = self.context.new_page(); page.goto('https://workspace.test/?view=applications&role=role-1')
        page.locator('#application-notes').wait_for(); return page
    def test_documented_incompatibility_is_never_labelled_supported(self):
        page = self.page()
        page.evaluate('''() => {
            const row = {quote: 'Singapore citizens only', status:'incompatible', candidate_evidence:[], reason:'The listing excludes permanent residents.'};
            const score = {value:39, provisional:true, gates:[{...row, evidence_state:'documented_incompatibility'}],
                components:[], limits:[], requirements:[row], duties:[], preferred:[], version:'documented-fit-v2'};
            const output = window.FitScore.detail({assessment:{score}}); output.id='eligibility-fixture'; document.body.append(output);
        }''')
        text = page.locator('#eligibility-fixture').text_content()
        self.assertIn('Documented incompatibility', text)
        self.assertIn('eligibility conflict', text)
        self.assertNotIn('Supported by CV', text)
    def test_acknowledgement_does_not_remove_newer_pending_version(self):
        page = self.page(); held = []
        page.route('**/api/applications/role-1', lambda route: held.append(route))
        page.locator('#application-notes').fill('first version'); page.wait_for_timeout(400)
        page.locator('#application-notes').fill('newer version')
        self.app['notes'] = 'first version'; self.app['revision'] = 2
        held[0].fulfill(json=copy.deepcopy(self.app)); page.wait_for_timeout(100)
        records = page.evaluate("Object.keys(localStorage).filter(k => k.startsWith('sg_career_recovery_v2:')).map(k => JSON.parse(localStorage.getItem(k)))")
        self.assertTrue(any(record['patch'].get('notes') == 'newer version' and record['expected_revision'] == 2 for record in records))
        for pending in held[1:]: pending.fulfill(status=503, json={'detail':'Offline fixture'})
    def test_timeout_keeps_draft_and_offers_retry(self):
        page = self.page()
        page.evaluate("""() => {const native = window.fetch; window.fetch = (path, options) => path === '/api/applications/role-1' ? Promise.reject(new DOMException('Request timed out', 'TimeoutError')) : native(path, options);}""")
        page.locator('#application-notes').fill('timeout draft'); page.wait_for_timeout(450)
        self.assertTrue(page.get_by_role('button', name='Retry save', exact=True).is_visible())
        self.assertEqual(page.locator('#application-notes').input_value(), 'timeout draft')
        page.reload(); page.locator('#application-notes').wait_for()
        self.assertIn('timeout draft', page.locator('body').inner_text())
    def test_recovery_menu_includes_every_job(self):
        page = self.page()
        page.evaluate("""() => {for (const id of ['missing-one','missing-two']) localStorage.setItem('sg_career_recovery_v2:fixture:'+id, JSON.stringify({job_id:id,editor_id:'fixture',expected_revision:0,patch:{notes:'draft '+id},job_snapshot:{id,title:id}}));}""")
        page.reload(); page.locator('#application-notes').wait_for()
        page.get_by_text('Choose a role to recover', exact=True).click()
        page.get_by_role('button', name='missing-two', exact=True).click()
        self.assertIn('draft missing-two', page.locator('#role-detail').inner_text())
    def test_reversed_search_responses_cannot_replace_newer_results(self):
        page = self.context.new_page(); held = []
        def searches(route):
            if 'q=older' in route.request.url: held.append(route)
            elif 'q=newer' in route.request.url:
                route.fulfill(json={'items':[{**JOB,'title':'Newer result'}], 'total':1})
                for old in held: old.fulfill(json={'items':[{**JOB,'title':'Obsolete result'}], 'total':1})
            else: route.fulfill(json={'items':[JOB], 'total':1})
        page.route('**/api/jobs?*', searches)
        page.goto('https://workspace.test/'); page.locator('#job-list .role-row').wait_for()
        page.locator('#search-query').fill('older'); page.wait_for_timeout(350)
        page.locator('#search-query').fill('newer'); page.wait_for_timeout(450)
        self.assertIn('Newer result', page.locator('#job-list').inner_text())
        self.assertNotIn('Obsolete result', page.locator('#job-list').inner_text())
    def test_unauthorized_save_retains_text_for_recovery(self):
        page = self.page()
        page.route('**/api/applications/role-1', lambda route: route.fulfill(status=401,json={'detail':'Sign in'}))
        page.locator('#application-notes').fill('text survives authentication failure'); page.wait_for_timeout(450)
        self.assertIn('authentication', page.locator('#save-feedback').inner_text())
        page.reload(); page.locator('#application-notes').wait_for()
        self.assertIn('text survives authentication failure', page.locator('body').inner_text())
    def test_resolved_import_history_exposes_original_and_resolution(self):
        self.history_items = [{'type':'import_version','created_at':'2026-10-20','at':'2026-10-21','resolved_at':'2026-10-21','resolution_status':'resolved','incoming':{'application':{'notes':'original imported notes','stage':'Applied'}},'resolution':{'notes':'retained resolution','stage':'Preparing'}}]
        page = self.page(); page.locator('#application-history > summary').click()
        page.get_by_text('Original browser notes and stage', exact=True).click()
        page.get_by_text('Resolution saved to application', exact=True).click()
        self.assertIn('original imported notes', page.locator('#application-history').inner_text())
        self.assertIn('retained resolution', page.locator('#application-history').inner_text())
        self.assertIn('Applied', page.locator('#application-history').inner_text())
    def test_refresh_keeps_display_and_base_revision_together(self):
        page = self.page()
        self.app['notes'] = 'other browser'; self.app['revision'] = 2
        page.locator('#refresh-applications').click()
        page.wait_for_timeout(100)
        self.assertEqual(page.locator('#application-notes').input_value(),'other browser')
        page.locator('#application-notes').fill('edited fresh copy'); page.wait_for_timeout(500)
        self.assertEqual(self.app['notes'],'edited fresh copy')
    def test_dirty_refresh_retains_base_and_requires_resolution(self):
        page = self.page(); self.fail_requests = True
        page.locator('#application-notes').fill('unsaved draft'); page.wait_for_timeout(450)
        self.app['notes'] = 'other browser'; self.app['revision'] = 2
        page.locator('#refresh-applications').click(); page.wait_for_timeout(100)
        self.assertEqual(page.locator('#application-notes').input_value(), 'unsaved draft')
        self.assertTrue(page.get_by_role('button', name='Save my edits over this version').is_visible())
        self.assertEqual(self.app['notes'], 'other browser')
        self.fail_requests = False
        page.get_by_role('button', name='Save my edits over this version').click(); page.wait_for_timeout(300)
        self.assertEqual(self.app['notes'], 'unsaved draft')
    def test_legacy_recovery_is_retained_and_converted_once(self):
        page = self.page()
        legacy = {'role-1': {'patch': {'notes':'legacy draft'}, 'expected_revision':1}}
        page.evaluate('(value) => localStorage.setItem("sg_career_recovery_v1", JSON.stringify(value))', legacy)
        page.reload(); page.locator('#application-notes').wait_for()
        self.assertIn('legacy draft', page.locator('body').inner_text())
        self.assertEqual(page.evaluate('JSON.parse(localStorage.getItem("sg_career_recovery_v1"))'), legacy)
        count = page.evaluate('Object.keys(localStorage).filter(key => key.startsWith("sg_career_recovery_v2:")).length')
        page.reload(); page.locator('#application-notes').wait_for()
        self.assertEqual(page.evaluate('Object.keys(localStorage).filter(key => key.startsWith("sg_career_recovery_v2:")).length'), count)
    def test_immediate_close_preserves_latest_keystrokes(self):
        page = self.page(); self.fail_requests = True
        page.locator('#application-notes').fill('last keystrokes'); page.close()
        recovered = self.page()
        self.assertIn('last keystrokes', recovered.locator('body').inner_text())
    def test_failed_edits_in_two_tabs_survive_a_save_and_reload(self):
        a, b = self.page(), self.page(); self.fail_requests = True
        a.locator('#application-notes').fill('tab A draft'); a.wait_for_timeout(450)
        b.locator('#application-notes').fill('tab B draft'); b.wait_for_timeout(450)
        self.fail_requests = False
        a.get_by_role('button',name='Retry save',exact=True).click(); a.wait_for_timeout(450)
        b.reload(); b.locator('#application-notes').wait_for()
        self.assertIn('tab B draft', b.locator('body').inner_text() + b.locator('#application-notes').input_value())

if __name__ == '__main__': unittest.main()


