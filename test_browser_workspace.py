"""Browser regressions; API fixtures mutate only isolated in-memory records."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from playwright.sync_api import sync_playwright
from storage import Conflict, Store

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
            elif path == '/api/drafts/role-1': data = {'recruiter_message':'Supported recruiter prompt', 'cover_letter':'Supported cover prompt', 'supported_pairs':[{'quote':'Manage social campaigns','candidate_evidence':['CV: led social campaign planning.']}], 'requirements_to_check':['Confirm language requirement']}
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
    def test_closed_application_keeps_existing_draft_reviewable(self):
        self.app.update(stage='Closed',drafts={'cover_letter':'Retained user draft'})
        page=self.page()
        self.assertEqual(page.locator('#draft-cover_letter').count(),1)
        page.get_by_text('Application preparation',exact=True).click()
        self.assertEqual(page.locator('#draft-cover_letter').input_value(),'Retained user draft')
    def test_first_save_exposes_history_without_reopening_role(self):
        self.app.update(notes='', revision=0)
        page = self.context.new_page()
        page.route('**/api/applications', lambda route: route.fulfill(json={'items':[]}))
        page.goto('https://workspace.test/?role=role-1')
        page.locator('#application-notes').fill('First saved note')
        page.wait_for_timeout(450)
        self.assertEqual(self.app['notes'], 'First saved note')
        self.assertEqual(page.locator('#application-history > summary').count(), 1)

    def test_successful_import_resolution_updates_feedback_and_closed_outcome(self):
        self.app['import_conflicts'] = [{'id':7,'incoming':{'application':{'notes':'imported notes','stage':'Closed'}}}]
        page = self.page()
        def resolve(route):
            patch = route.request.post_data_json
            self.assertEqual(patch.pop('expected_revision'), self.app['revision'])
            self.assertEqual(patch.pop('resolve_import_conflicts'), [7])
            self.app.update(patch, import_conflicts=[], revision=self.app['revision'] + 1)
            route.fulfill(json=copy.deepcopy(self.app))
        page.route('**/api/applications/role-1', resolve)
        page.get_by_role('button', name='Use previous notes and stage', exact=True).click()
        page.wait_for_timeout(150)
        self.assertEqual(page.locator('#save-feedback > .save-status').inner_text(), 'Saved')
        self.assertNotIn('Saving…', page.locator('#role-detail').inner_text())
        self.assertTrue(page.locator('#application-outcome').is_visible())
    def test_import_resolution_acknowledgement_must_confirm_resolved_ids(self):
        for index, conflicts in enumerate(([{'id':7}], None, [None], {'id':7})):
            with self.subTest(import_conflicts=conflicts):
                notes = f'Keep import choice {index}'
                self.app.update(notes='original', stage='Saved', revision=1,
                                import_conflicts=[{'id':7,'incoming':{'application':{'notes':notes,'stage':'Closed'}}}])
                page = self.page(); requests = []
                def invalid_ack(route):
                    requests.append(route.request.post_data_json)
                    acknowledgement = {**copy.deepcopy(self.app),'notes':notes,'stage':'Closed','revision':2}
                    if conflicts is None: acknowledgement.pop('import_conflicts')
                    else: acknowledgement['import_conflicts'] = conflicts
                    route.fulfill(json=acknowledgement)
                page.route('**/api/applications/role-1', invalid_ack)
                page.get_by_role('button', name='Use previous notes and stage', exact=True).click()
                page.wait_for_timeout(100)
                self.assertTrue(page.get_by_role('button', name='Retry save', exact=True).is_visible())
                self.assertNotIn('Review saved.', page.locator('#role-detail').inner_text())
                self.assertEqual(page.locator('#application-notes').input_value(), notes)
                records = page.evaluate("Object.keys(localStorage).filter(key=>key.startsWith('sg_career_recovery_v2:')).map(key=>JSON.parse(localStorage.getItem(key)))")
                retained = [record for record in records if record['patch'].get('notes') == notes]
                self.assertEqual(len(retained), 1)
                self.assertEqual(retained[0]['expected_revision'], 1)
                self.assertEqual(retained[0]['patch']['resolve_import_conflicts'], [7])
                def valid_ack(route):
                    patch = route.request.post_data_json
                    self.assertEqual(patch.pop('expected_revision'), 1)
                    self.assertEqual(patch.pop('resolve_import_conflicts'), [7])
                    self.app.update(patch, import_conflicts=[], revision=2)
                    route.fulfill(json=copy.deepcopy(self.app))
                page.route('**/api/applications/role-1', valid_ack)
                page.get_by_role('button', name='Retry save', exact=True).click()
                page.wait_for_timeout(100)
                self.assertEqual(page.locator('#save-feedback > .save-status').inner_text(), 'Saved')
                self.assertIn('Review saved.', page.locator('#role-detail').inner_text())
                self.assertEqual(len(requests), 1)
                page.close()
    def test_save_refreshes_open_history_and_ignores_older_history_response(self):
        page = self.page(); held = []
        page.route('**/api/applications/role-1/history?*', lambda route: held.append(route))
        page.locator('#application-history > summary').click()
        page.wait_for_timeout(50)
        page.locator('#application-notes').fill('Update while history loads')
        page.wait_for_timeout(450)
        self.assertEqual(len(held), 2)
        held[1].fulfill(json={'items':[{'type':'updated','stage':'Preparing'}], 'total':1})
        held[0].fulfill(json={'items':[{'type':'created','stage':'Saved'}], 'total':1})
        page.wait_for_timeout(100)
        self.assertIn('Preparing', page.locator('#application-history').inner_text())
        self.assertNotIn('created', page.locator('#application-history').inner_text())
        self.assertTrue(page.locator('#application-notes').evaluate('(node) => node === document.activeElement'))
        self.assertEqual(page.locator('#application-notes').input_value(), 'Update while history loads')
    def test_import_resolution_rebase_does_not_resubmit_already_resolved_ids(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory) / 'isolated.sqlite3').initialize()
            store.seed_jobs([JOB])
            store.put_application('role-1', {'expected_revision':0,'notes':'original'})
            store.import_applications({'role-1':{'notes':'Retain my import choice','stage':'Preparing'}})
            self.app = store.get_application('role-1')
            page = self.page()
            # A different editor has already resolved this import before this editor saves.
            conflict_id = self.app['import_conflicts'][0]['id']
            store.put_application('role-1', {'expected_revision':self.app['revision'],'resolve_import_conflicts':[conflict_id]})
            def save(route):
                try:
                    route.fulfill(json=store.put_application('role-1', route.request.post_data_json))
                except Conflict as error:
                    route.fulfill(status=409, json={'detail':{'current':error.current}})
                except ValueError as error:
                    route.fulfill(status=400, json={'detail':str(error)})
            page.route('**/api/applications/role-1', save)
            page.get_by_role('button', name='Use previous notes and stage', exact=True).click()
            page.get_by_role('button', name='Save my edits over this version', exact=True).click()
            page.wait_for_timeout(150)
            self.assertEqual(page.locator('#save-feedback > .save-status').inner_text(), 'Saved')
            actual = store.get_application('role-1')
            self.assertEqual(actual['notes'], 'Retain my import choice')
            self.assertEqual(actual['stage'], 'Preparing')
            retained = [event for event in store.get_application_history('role-1')['items'] if event['type'] == 'import_version']
            self.assertEqual(len(retained), 1)
            self.assertEqual(retained[0]['resolution']['notes'], 'original')
            page.close()
    def test_failed_inflight_write_exposes_already_observed_server_conflict(self):
        page=self.page();held=[]
        page.route('**/api/applications/role-1',lambda route:held.append(route))
        page.locator('#application-notes').fill('pending old base');page.wait_for_timeout(400)
        self.app.update(notes='new server revision',revision=2)
        page.locator('#refresh-applications').click();page.wait_for_timeout(100)
        held[0].fulfill(status=503,json={'detail':'request unavailable'});page.wait_for_timeout(100)
        self.assertTrue(page.get_by_role('button',name='Save my edits over this version',exact=True).is_visible())
        self.assertEqual(page.locator('#application-notes').input_value(),'pending old base')
    def test_append_retry_label_resets_after_success(self):
        page=self.context.new_page();attempts=[]
        def search(route):
            if 'offset=1' in route.request.url:
                attempts.append(1)
                if len(attempts)==1: route.fulfill(status=503,json={'detail':'try again'})
                else: route.fulfill(json={'items':[{**JOB,'id':'role-2'}],'total':3})
            else: route.fulfill(json={'items':[JOB],'total':3})
        page.route('**/api/jobs?*',search);page.goto('https://workspace.test/')
        page.locator('#job-list .role-row').wait_for();page.locator('#load-more').click();page.wait_for_timeout(100)
        self.assertEqual(page.locator('#load-more').inner_text(),'Retry loading more')
        page.locator('#load-more').click();page.wait_for_timeout(100)
        self.assertEqual(page.locator('#load-more').inner_text(),'Load more roles')
    def test_failed_export_retains_selected_application(self):
        page=self.page();page.get_by_role('button',name='Back to applications',exact=False).click()
        page.locator('#application-list input[type=checkbox]').check()
        page.route('**/api/export/applications?*',lambda route:route.fulfill(status=503,body='unavailable'))
        page.get_by_role('button',name='Export selected (1)',exact=True).click();page.wait_for_timeout(100)
        self.assertTrue(page.locator('#application-list input[type=checkbox]').is_checked())
        self.assertFalse(page.get_by_role('button',name='Export selected (1)',exact=True).is_disabled())
        self.assertIn('Export failed',page.locator('#toast').inner_text())
    def test_unavailable_storage_still_saves_server_and_retains_failure_warning(self):
        page = self.context.new_page()
        page.add_init_script("Object.defineProperty(window,'localStorage',{get(){throw new DOMException('Blocked','SecurityError')}})")
        page.goto('https://workspace.test/?view=applications&role=role-1');page.locator('#application-notes').wait_for()
        page.locator('#application-notes').fill('server remains available');page.wait_for_timeout(450)
        self.assertEqual(self.app['notes'],'server remains available')
        self.assertEqual(page.locator('#save-feedback > .save-status').inner_text(),'Saved')
        self.fail_requests=True
        page.locator('#application-notes').fill('keep page open');page.wait_for_timeout(450)
        self.assertIn('only on this page',page.locator('#save-feedback').inner_text())
        self.assertTrue(page.evaluate("(() => {const e=new Event('beforeunload',{cancelable:true});window.dispatchEvent(e);return e.defaultPrevented;})()"))
    def test_earlier_ack_with_newer_keystrokes_and_refreshed_revision_conflicts(self):
        page=self.page();held=[]
        page.route('**/api/applications/role-1',lambda route:held.append(route))
        page.locator('#application-notes').fill('submitted');page.wait_for_timeout(400)
        acknowledged={**copy.deepcopy(self.app),'notes':'submitted','revision':2}
        page.locator('#application-notes').fill('newer keystrokes')
        self.app.update(notes='remote revision 3',revision=3)
        page.locator('#refresh-applications').click();page.wait_for_timeout(100)
        held[0].fulfill(json=acknowledged);page.wait_for_timeout(150)
        self.assertEqual(page.locator('#application-notes').input_value(),'newer keystrokes')
        self.assertTrue(page.get_by_role('button',name='Save my edits over this version',exact=True).is_visible())
        self.assertEqual(len(held),1)
        records=page.evaluate("Object.keys(localStorage).filter(k=>k.startsWith('sg_career_recovery_v2:')).map(k=>JSON.parse(localStorage.getItem(k)))")
        self.assertTrue(any(r['expected_revision']==2 and r['patch'].get('notes')=='newer keystrokes' for r in records))
    def test_user_draft_edit_wins_over_late_generation(self):
        page=self.page();held=[]
        page.route('**/api/drafts/role-1',lambda route:held.append(route))
        page.get_by_role('button',name='Prepare application',exact=True).click()
        page.locator('#draft-cover_letter').fill('my truthful draft')
        held[0].fulfill(json={'cover_letter':'generated suggestion','recruiter_message':'message'});page.wait_for_timeout(450)
        self.assertEqual(page.locator('#draft-cover_letter').input_value(),'my truthful draft')
        self.assertEqual(self.app['drafts']['cover_letter'],'my truthful draft')

    def test_preparation_shows_supported_pairs_separately_from_checklist(self):
        page=self.page()
        page.get_by_role('button',name='Prepare application',exact=True).click()
        page.locator('.supported-pairs').wait_for()
        self.assertIn('Manage social campaigns',page.locator('.supported-pairs').inner_text())
        self.assertNotIn('Confirm language requirement',page.locator('.supported-pairs').inner_text())
        page.locator('#preparation-checklist').click()
        self.assertIn('Confirm language requirement',page.locator('#preparation-checklist').inner_text())
    def test_mobile_detail_excludes_background_skip_link_and_restores_it(self):
        page = self.page();page.set_viewport_size({'width':390,'height':844})
        # MatchMedia change dispatch is asynchronous after viewport resizing.
        # Assert the resulting modal state, not the first synchronous frame.
        page.wait_for_function("document.querySelector('.skip-link').inert")
        self.assertTrue(page.locator('.skip-link').evaluate('(node) => node.inert'))
        page.locator('#application-notes').focus();page.keyboard.press('Escape')
        self.assertFalse(page.locator('.skip-link').evaluate('(node) => node.inert'))
    def test_recovery_delete_failure_preserves_version_and_explains_retry(self):
        page = self.page()
        page.evaluate("""() => localStorage.setItem('sg_career_recovery_v2:fixture',JSON.stringify({job_id:'role-1',editor_id:'other',expected_revision:1,patch:{notes:'keep recoverable'}}))""")
        page.reload();page.locator('#application-notes').wait_for(); errors=[];page.on('pageerror',lambda error: errors.append(str(error)))
        page.evaluate("() => {Storage.prototype.removeItem = () => {throw new DOMException('Denied', 'SecurityError')};}")
        page.get_by_role('button',name='Discard this recovery copy',exact=True).click()
        self.assertEqual(errors, [])
        self.assertIn('could not be removed',page.locator('#role-detail').inner_text())
        self.assertIn('keep recoverable',page.locator('#role-detail').inner_text())
    def test_focused_unedited_draft_matches_generated_saved_value(self):
        page = self.page(); held=[]
        page.route('**/api/drafts/role-1',lambda route: held.append(route))
        page.get_by_role('button',name='Prepare application',exact=True).click()
        page.locator('#draft-cover_letter').focus();page.wait_for_timeout(100)
        held[0].fulfill(json={'cover_letter':'Supported generated draft','recruiter_message':'Supported message'})
        page.wait_for_timeout(450)
        self.assertEqual(page.locator('#draft-cover_letter').input_value(),'Supported generated draft')
        self.assertEqual(self.app['drafts']['cover_letter'],'Supported generated draft')
    def test_late_save_acknowledgement_keeps_newer_refreshed_server_copy(self):
        page = self.page(); held=[]
        page.route('**/api/applications/role-1',lambda route: held.append(route))
        page.locator('#application-notes').fill('my submitted version'); page.wait_for_timeout(400)
        acknowledged={**copy.deepcopy(self.app),'notes':'my submitted version','revision':2}
        self.app.update(notes='later other browser version',revision=3)
        page.locator('#refresh-applications').click();page.wait_for_timeout(100)
        self.assertEqual(page.locator('#application-notes').input_value(),'my submitted version')
        held[0].fulfill(json=acknowledged);page.wait_for_timeout(150)
        self.assertEqual(page.locator('#application-notes').input_value(),'later other browser version')
        self.assertIn('later other browser version',page.locator('#application-list').inner_text())
    def test_invalid_success_acknowledgement_never_discards_pending_text(self):
        page = self.page()
        page.route('**/api/applications/role-1', lambda route: route.fulfill(json={}))
        page.locator('#application-notes').fill('must survive malformed acknowledgement'); page.wait_for_timeout(450)
        self.assertTrue(page.get_by_role('button', name='Retry save', exact=True).is_visible())
        records = page.evaluate("Object.keys(localStorage).filter(k => k.startsWith('sg_career_recovery_v2:')).map(k => JSON.parse(localStorage.getItem(k)))")
        self.assertTrue(any(record['patch'].get('notes') == 'must survive malformed acknowledgement' for record in records))
    def test_one_malformed_recovery_record_does_not_hide_valid_versions(self):
        page = self.page()
        page.evaluate("""() => {
          localStorage.setItem('sg_career_recovery_v2:broken', '{');
          localStorage.setItem('sg_career_recovery_v2:valid', JSON.stringify({job_id:'role-1',editor_id:'fixture',expected_revision:1,patch:{notes:'valid independent draft'}}));
        }""")
        page.reload(); page.locator('#application-notes').wait_for()
        self.assertIn('valid independent draft', page.locator('#role-detail').inner_text())
        self.assertEqual(page.evaluate("localStorage.getItem('sg_career_recovery_v2:broken')"), '{')
    def test_storage_failure_is_not_reported_as_durable_browser_recovery(self):
        page = self.page(); self.fail_requests = True
        page.evaluate("""() => {const native = Storage.prototype.setItem; Storage.prototype.setItem = function(key,value) {if (key.startsWith('sg_career_recovery_v2:')) throw new DOMException('Full', 'QuotaExceededError');return native.call(this,key,value);};}""")
        page.locator('#application-notes').fill('only on this page'); page.wait_for_timeout(450)
        self.assertIn('only on this page', page.locator('#save-feedback').inner_text())
        self.assertNotIn('Your text is retained in this browser', page.locator('#global-notices').inner_text())
        self.assertTrue(page.get_by_role('button',name='Download unsaved edits',exact=True).is_visible())
    def test_failed_mark_applied_never_announces_success(self):
        page = self.page(); self.fail_requests = True
        page.get_by_role('button', name='Mark applied',exact=True).click(); page.wait_for_timeout(400)
        self.assertNotIn('Application marked applied.',page.locator('#toast').text_content())
        self.assertEqual(self.app['stage'],'Saved')
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


