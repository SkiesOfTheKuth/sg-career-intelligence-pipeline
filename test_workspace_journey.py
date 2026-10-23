"""Mutating real-data journey: explicitly configured disposable storage only.

CAREER_QA_ISOLATED=1, CAREER_QA_URL and CAREER_QA_PASSWORD are required.
CAREER_QA_OUTPUT optionally selects the private screenshot/report directory.
Never run against production. All browser external-listing requests are blocked;
opening a listing tests navigation and does not contact an employer.
"""
import csv
import io
import json
import os
from uuid import uuid4
from pathlib import Path
from urllib.parse import urlparse, parse_qs
from playwright.sync_api import sync_playwright, expect


def main():
    base = os.environ.get('CAREER_QA_URL', '').rstrip('/')
    password = os.environ.get('CAREER_QA_PASSWORD')
    if not base or not password or os.environ.get('CAREER_QA_ISOLATED') != '1':
        raise SystemExit('Requires CAREER_QA_URL, CAREER_QA_PASSWORD and CAREER_QA_ISOLATED=1 for disposable storage.')
    if urlparse(base).hostname not in {'127.0.0.1', 'localhost', '::1'}:
        raise SystemExit('This mutating journey requires a local disposable server.')
    out = Path(os.environ.get('CAREER_QA_OUTPUT', 'output/playwright/isolated-journey'))
    out.mkdir(parents=True, exist_ok=True)
    evidence = []
    errors = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        options = {'http_credentials': {'username': os.environ.get('CAREER_QA_USERNAME', 'Kawa'), 'password': password}, 'viewport': {'width': 1440, 'height': 1000}}
        first, second = browser.new_context(**options), browser.new_context(**options)
        for context in (first, second):
            context.route('**/*', lambda route: route.continue_() if route.request.url.startswith(base + '/') else route.abort())
        page = first.new_page()
        page.on('pageerror', lambda error: errors.append(str(error)))

        def current(role):
            response = first.request.get(base + '/api/applications')
            assert response.ok, response.status
            return next(item for item in response.json()['items'] if str(item['job_id']) == role)

        def saved(page, role, expected, label):
            expect(page.locator('#save-feedback > .save-status')).to_have_text('Saved', timeout=15000)
            actual = current(role)
            for key, value in expected.items():
                if key == 'drafts':
                    for name, text in value.items(): assert actual[key][name] == text, (label, name)
                else: assert actual[key] == value, (label, key)
            evidence.append({'step': label, 'revision': actual['revision'], 'expected_fields': list(expected), 'result': 'passed'})
            return actual

        page.goto(base + '/')
        page.locator('#job-list .role-title').first.click()
        page.locator('#application-notes').wait_for()
        role = parse_qs(urlparse(page.url).query)['role'][0]
        # Source quotation and specific CV evidence are available in the detail.
        page.get_by_role('button', name='Fit score & evidence', exact=True).click()
        page.get_by_text('Compare responsibilities', exact=False).first.click()
        assert page.locator('.score-evidence').count()
        page.screenshot(path=str(out / 'evidence-1440.png'))
        page.locator('#application-stage').select_option('Preparing')
        page.locator('#draft-cover_letter').wait_for()
        draft = 'Isolated QA user draft. No invented achievements.'
        page.locator('#draft-cover_letter').fill(draft)
        page.locator('#application-notes').fill('Isolated QA application notes.')
        page.locator('#application-next_action').fill('Review listing and follow up')
        page.locator('#application-follow_up_date').fill('2026-10-28')
        saved(page, role, {'stage':'Preparing', 'notes':'Isolated QA application notes.', 'next_action':'Review listing and follow up', 'follow_up_date':'2026-10-28', 'drafts':{'cover_letter':draft}}, 'prepare and edit')
        page.evaluate("Object.defineProperty(navigator, 'clipboard', {value:{writeText:()=>Promise.reject(new Error('blocked'))}})")
        page.get_by_role('button', name='Copy cover letter', exact=True).click()
        expect(page.locator('#toast')).to_contain_text('Clipboard access failed')
        assert page.locator('#draft-cover_letter').evaluate('(node) => node.selectionStart === 0 && node.selectionEnd === node.value.length')
        with page.expect_popup() as popup:
            page.get_by_role('link', name='View original listing (opens in a new tab)', exact=True).click()
        popup.value.close()
        assert current(role)['stage'] == 'Preparing'
        page.get_by_role('button', name='Mark applied', exact=True).click()
        applied = saved(page, role, {'stage':'Applied'}, 'explicit mark applied')
        assert applied['applied_at']

        other = second.new_page()
        other.on('pageerror', lambda error: errors.append(str(error)))
        other.goto(base + '/?view=applications&role=' + role)
        expect(other.locator('#application-notes')).to_have_value('Isolated QA application notes.')
        expect(other.locator('#draft-cover_letter')).to_have_value(draft)
        other.locator('#application-notes').fill('Other authenticated context notes.')
        saved(other, role, {'notes':'Other authenticated context notes.'}, 'second authenticated browser')
        page.locator('#application-notes').fill('First context competing notes.')
        page.get_by_role('button', name='Save my edits over this version', exact=True).wait_for()
        assert current(role)['notes'] == 'Other authenticated context notes.'
        page.screenshot(path=str(out / 'conflict-1440.png'))
        page.get_by_role('button', name='Save my edits over this version', exact=True).click()
        saved(page, role, {'notes':'First context competing notes.'}, 'explicit concurrency resolution')
        page.locator('#application-stage').select_option('Closed')
        page.locator('#application-outcome').fill('Isolated QA closed')
        saved(page, role, {'stage':'Closed','outcome':'Isolated QA closed','drafts':{'cover_letter':draft}}, 'close and retain draft')

        # A conflicting browser import must retain original and resolution.
        imported_note = 'Original imported notes for QA history ' + uuid4().hex
        imported = first.request.post(base + '/api/applications/import', data={'records': {role: {'stage':'Applied','notes':imported_note}}})
        assert imported.ok and not imported.json()['errors']
        page.goto(base + '/?view=applications&role=' + role)
        page.get_by_role('button', name='Keep current version', exact=True).first.click()
        saved(page, role, {'stage':'Closed','notes':'First context competing notes.'}, 'resolve browser import')
        page.locator('#application-history > summary').click()
        page.get_by_text('Original browser notes and stage', exact=True).first.click()
        page.get_by_text('Resolution saved to application', exact=True).first.click()
        expect(page.locator('#application-history')).to_contain_text(imported_note)
        history = first.request.get(base + f'/api/applications/{role}/history?offset=0&limit=100').json()
        assert any(item.get('type') == 'import_version' and item.get('resolution_status') == 'resolved' and item.get('resolution', {}).get('notes') == 'First context competing notes.' for item in history['items'])
        assert any(item.get('stage') == 'Applied' for item in history['items'])
        page.locator('#application-history').scroll_into_view_if_needed()
        page.screenshot(path=str(out / 'application-history-1440.png'))

        page.get_by_role('button', name='Back to applications', exact=False).click()
        page.locator('#application-list .application-select input').first.check()
        with page.expect_download() as download:
            page.get_by_role('button', name='Export selected (1)', exact=True).click()
        rows = list(csv.DictReader(Path(download.value.path()).read_text(encoding='utf-8-sig').splitlines()))
        assert len(rows) == 1 and rows[0]['ID'] == role and rows[0]['Notes'] == 'First context competing notes.'
        assert imported_note in rows[0]['History']
        assert rows[0]['Cover letter'] == draft
        evidence.append({'step':'selected export and resolved import history', 'records':1,'result':'passed'})
        opener = page.locator('#application-list [data-role-id="' + role + '"]').first
        opener.focus();page.keyboard.press('Enter')
        for width, height in [(390,844),(768,1000),(1440,1000)]:
            page.set_viewport_size({'width':width,'height':height})
            page.locator('#role-detail').evaluate('(node) => node.scrollTop=0')
            page.screenshot(path=str(out / f'detail-{width}.png'))
            assert not page.evaluate('document.documentElement.scrollWidth > innerWidth')
            page.keyboard.press('Escape')
            assert page.locator('#role-detail').is_hidden()
            assert opener.evaluate('(node) => document.activeElement === node')
            page.keyboard.press('Enter');page.locator('#application-notes').wait_for()

        page.goto(base + '/sources')
        page.locator('#records button').first.wait_for()
        page.locator('#records button').first.focus();page.keyboard.press('Enter')
        page.locator('.evidence-version summary').first.wait_for()
        page.locator('.evidence-version summary').first.focus();page.keyboard.press('Enter')
        assert page.locator('.evidence-version pre').first.is_visible()
        page.screenshot(path=str(out / 'source-payload-keyboard-1440.png'))
        page.keyboard.press('Escape')
        assert not page.locator('#record-inspector').is_visible()
        assert not errors, errors
        report = {'environment':base,'role':role,'journey':'passed','steps':evidence,'page_errors':errors,'zoom':'Not tested by this runner; viewport screenshots are not native zoom evidence.'}
        (out / 'journey-report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        print(json.dumps(report))
        browser.close()


if __name__ == '__main__':
    main()
