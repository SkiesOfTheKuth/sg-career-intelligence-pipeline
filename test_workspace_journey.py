"""Isolated integration journey. Run against a disposable database only.

CAREER_QA_URL and CAREER_QA_PASSWORD are required. The runner mutates one
application. The default authenticated local test server is never inferred.
"""
import json
import os
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright, expect
def main():
    base=os.environ.get('CAREER_QA_URL')
    password=os.environ.get('CAREER_QA_PASSWORD')
    if not base or not password or os.environ.get('CAREER_QA_ISOLATED') != '1':
     print('Requires CAREER_QA_URL, CAREER_QA_PASSWORD, and CAREER_QA_ISOLATED=1 for disposable storage.');sys.exit(2)
    out=Path('output/playwright/v2');out.mkdir(parents=True,exist_ok=True)
    with sync_playwright() as p:
     browser=p.chromium.launch(headless=True)
     opts={'http_credentials':{'username':os.environ.get('CAREER_QA_USERNAME','Kawa'),'password':password},'viewport':{'width':1440,'height':1000}}
     a=browser.new_context(**opts); b=browser.new_context(**opts)
     page=a.new_page(); errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
     page.goto(base+'/');page.locator('#job-list .role-title').first.click();page.locator('#application-notes').wait_for()
     role=page.url.split('role=')[1].split('&')[0]
     page.locator('#application-stage').select_option('Preparing')
     page.locator('#draft-cover_letter').wait_for();page.wait_for_timeout(800)
     page.locator('#draft-cover_letter').fill('Isolated QA user draft. No invented achievements.')
     page.locator('#application-notes').fill('Isolated QA application notes.')
     page.locator('#application-next_action').fill('Review listing and follow up')
     page.locator('#application-follow_up_date').fill('2026-10-28')
     page.wait_for_timeout(800)
     expect(page.locator('#save-feedback > .save-status')).to_have_text('Saved', timeout=10000)
     page.context.grant_permissions(['clipboard-write'])
     page.evaluate('Object.defineProperty(navigator, "clipboard", {value:{writeText:()=>Promise.reject(new Error("blocked"))}})')
     page.get_by_role('button',name='Copy cover letter',exact=True).click()
     assert 'Clipboard access failed' in page.locator('#toast').inner_text()
     with page.expect_popup() as popup: page.get_by_role('link',name='View original listing (opens in a new tab)',exact=True).click()
     popup.value.close()
     assert page.locator('#application-stage').input_value()=='Preparing'
     page.get_by_role('button',name='Mark applied',exact=True).click();page.wait_for_timeout(800)
     assert page.locator('#application-stage').input_value()=='Applied'
     other=b.new_page();other.goto(base+'/?view=applications&role='+role);other.locator('#application-notes').wait_for()
     assert other.locator('#application-notes').input_value()=='Isolated QA application notes.'
     assert other.locator('#draft-cover_letter').input_value()=='Isolated QA user draft. No invented achievements.'
     other.locator('#application-notes').fill('Other authenticated context notes.');other.wait_for_timeout(400);expect(other.locator('#save-feedback > .save-status')).to_have_text('Saved', timeout=10000)
     page.locator('#application-notes').fill('First context competing notes.');page.wait_for_timeout(800)
     page.get_by_role('button',name='Save my edits over this version').wait_for(timeout=15000)
     page.screenshot(path=str(out/'conflict-1440.png'),full_page=True)
     page.get_by_role('button',name='Save my edits over this version').click();page.wait_for_timeout(800)
     page.locator('#application-stage').select_option('Closed');page.locator('#application-outcome').fill('Isolated QA closed');page.wait_for_timeout(800)
     page.get_by_role('button',name='Back to roles',exact=False).click()
     page.locator('#nav-applications').click();page.locator('#application-list [data-role-id="'+role+'"]').first.click()
     page.locator('#application-history > summary').click();page.wait_for_timeout(500)
     assert 'application updated' in page.locator('#application-history').inner_text().lower() or 'updated' in page.locator('#application-history').inner_text().lower()
     page.screenshot(path=str(out/'application-history-1440.png'),full_page=True)
     page.wait_for_timeout(6600) # Let transient confirmation finish before layout evidence.
     for width in [390,768]:
      page.set_viewport_size({'width':width,'height':844 if width==390 else 1000})
      page.locator('#role-detail').evaluate('(node) => node.scrollTop = 0')
      page.screenshot(path=str(out/f'detail-{width}.png'),full_page=False)
      assert not page.evaluate('document.documentElement.scrollWidth > innerWidth')
      page.keyboard.press('Escape');assert page.locator('#role-detail').is_hidden()
      page.locator('#application-list [data-role-id="'+role+'"]').first.focus();page.keyboard.press('Enter');page.locator('#application-notes').wait_for()
     # 200% zoom uses equivalent CSS viewport (1440 physical / 2 = 720 CSS pixels).
     page.set_viewport_size({'width':720,'height':500});page.screenshot(path=str(out/'detail-200-percent.png'),full_page=False)
     assert not page.evaluate('document.documentElement.scrollWidth > innerWidth')
     page.keyboard.press('Escape');page.screenshot(path=str(out/'applications-200-percent.png'),full_page=True)
     print(json.dumps({'role':role,'journey':'passed','separate_context_conflict':'passed','clipboard_failure':'passed','keyboard_escape_return':'passed','errors':errors}))
     browser.close()
    
    

if __name__ == "__main__":
    main()
