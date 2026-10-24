"""Local browser fixtures for the campaign controls; all requests are intercepted."""
import unittest
from pathlib import Path
from playwright.sync_api import sync_playwright, expect
from test_accessibility import source_audit_fixture

ROOT=Path(__file__).parent


class CampaignBrowserTests(unittest.TestCase):
    def test_status_pause_and_responsive_discovery_controls(self):
        out=ROOT/'output'/'playwright'/'campaign';out.mkdir(parents=True,exist_ok=True)
        with sync_playwright() as pw:
            browser=pw.chromium.launch()
            for width in (390,768,1440):
                context=browser.new_context(viewport={'width':width,'height':900})
                audit=source_audit_fixture()
                audit['campaign']={'state':'active','stops_at':1793360000,'heartbeat':1792760000,
                    'reported_run_charges_usd':.06,'observed_account_usage_usd':.061,
                    'actor_committed_usd':.2,'rolling_actor_committed_usd':.2,
                    'accounting_note':'Caps remain committed after completion.',
                    'burst':{'id':'one-day-20261024','local_day':'2026-10-24','state':'capacity',
                        'reason':'Verified capacity is committed.','target_usd':150,'soft_cap_usd':200,
                        'charged_usd':38.2,'reserved_exposure_usd':60.5,'observed_ancillary_usd':.04,
                        'capacity_ceiling_usd':60.5,'shortfall_usd':111.8,'window_end':1792857600,
                        'baseline_campaign_charged_usd':19.08,'pending_imports':0,'recurring_policy_restored':False,
                        'accounting_note':'Completed caps stay committed; shared usage is separate.',
                        'sources':[{'source':'indeed','charged_usd':28,'reserved_usd':40,'new_count':200,'duplicate_count':12,
                            'target_allocation_usd':70,'soft_allocation_usd':95,'state':'active','tranches':[], 'failures':0}]},
                    'sources':[{'source':'indeed','new_count':4,'updated_count':0,'duplicate_count':6,'lead_count':0,'due_at':1792780000},
                               {'source':'linkedin','blocked_reason':'Source robots directives disallow this path'}]}
                pauses=[];errors=[]
                def route(request):
                    path=request.request.url.split('workspace.test',1)[1].split('?',1)[0]
                    if path=='/api/audit/sources':return request.fulfill(json=audit)
                    if path=='/api/campaign/pause':
                        pauses.append(True);audit['campaign']['state']='paused';return request.fulfill(json=audit['campaign'])
                    if path.startswith('/api/'):
                        return request.fulfill(json={'items':[],'total':0,'limit':20})
                    file=ROOT/('templates/index.html' if path=='/' else 'templates/sources.html' if path=='/sources' else path.lstrip('/'))
                    request.fulfill(body=file.read_bytes(),content_type='text/html' if file.suffix=='.html' else 'text/css' if file.suffix=='.css' else 'text/javascript')
                context.route('https://workspace.test/**',route)
                page=context.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
                page.goto('https://workspace.test/sources');page.locator('#audit-content').wait_for(state='visible')
                if width<=650:page.locator('.audit-detail-disclosure > summary').click()
                page.locator('#campaign-summary').click()
                expect(page.locator('#campaign-detail')).to_contain_text('One-day burst limits below')
                expect(page.locator('#campaign-detail')).to_contain_text('Verified capacity ceiling')
                expect(page.locator('#campaign-detail')).to_contain_text('$111.80')
                expect(page.locator('#campaign-detail')).to_contain_text('robots directives')
                self.assertLessEqual(page.evaluate('document.documentElement.scrollWidth'),width)
                page.locator('#campaign-summary').scroll_into_view_if_needed()
                page.screenshot(path=str(out/f'status-fixture-{width}.png'),full_page=True)
                page.locator('#pause-campaign').click()
                expect(page.locator('#campaign-feedback')).to_contain_text('Paid collection paused')
                expect(page.locator('#pause-campaign')).to_be_hidden()
                self.assertEqual(pauses,[True]);self.assertFalse(errors)
                page.goto('https://workspace.test/')
                self.assertEqual(page.locator('#sort-filter option[value=discovered]').inner_text(),'Newly discovered')
                context.close()
            browser.close()


if __name__=='__main__':unittest.main()
