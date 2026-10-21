"""Behavioral regressions from the workspace audit; no fixed dataset counts."""
import asyncio
import csv
import io
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
import app as web
from evidence import build_job
from storage import Store


def vacancy(jid, **changes):
    raw=dict(title='Social media executive',company='Example employer',url='https://example.com/jobs/'+jid,
             source='Employer',description='Manage social media campaigns.\nRequirements\nDegree in Marketing\nEnglish proficiency',
             requirements='Degree in Marketing\nEnglish proficiency',advertised_salary='SGD 3,000 - 5,000 / month',
             employment_type='Full Time',employment_type_verified=True,verified_at='2026-10-21T01:00:00+00:00')
    raw.update(changes)
    return build_job(raw,jid)


class WorkspaceAPI(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.path=Path(self.temp.name)/'career.sqlite3'
        self.store=Store(self.path).initialize()
        self.jobs=[vacancy('monthly'),vacancy('annual',advertised_salary='SGD 60,000 - 72,000 /yr'),
                   vacancy('daily',advertised_salary='SGD 200 /day'),vacancy('hourly',advertised_salary='SGD 20 /hr'),
                   vacancy('unknown',advertised_salary='Not disclosed'),vacancy('expired',expiry_date='2020-01-01')]
        self.store.seed_jobs(self.jobs);self.store.set_meta('seed_version',2)
        self.previous=web.app.state.database_path;web.app.state.database_path=self.path
        self.env=patch.dict(os.environ,{'DISABLE_BACKGROUND_SYNC':'1'});self.env.start()
        self.context=TestClient(web.app);self.client=self.context.__enter__()
        self.auth=(web.AUTH_USERNAME,web.AUTH_PASSWORD)

    def tearDown(self):
        self.context.__exit__(None,None,None);web.app.state.database_path=self.previous
        self.env.stop();self.temp.cleanup()

    def get(self,url):return self.client.get(url,auth=self.auth)
    def put(self,jid,payload):return self.client.put('/api/applications/'+jid,json=payload,auth=self.auth)

    def test_every_data_interface_requires_auth(self):
        for path in ['/', '/api/jobs','/api/jobs/monthly','/api/jobs/batch?ids=monthly','/api/options',
                     '/api/applications','/api/drafts/monthly','/api/export/applications','/api/export/filtered',
                     '/download/excel','/download/csv','/api/stats','/api/backup','/sources',
                     '/api/audit/sources','/api/audit/records','/api/audit/records/monthly']:
            r=self.client.get(path);self.assertEqual(401,r.status_code,path)
        for method,url in [('put','/api/applications/monthly'),('post','/api/applications/import'),('post','/api/sync')]:
            self.assertEqual(getattr(self.client,method)(url,json={}).status_code,401)
        self.assertEqual(self.client.get('/healthz').status_code,200)
        self.assertEqual(self.client.get('/',auth=('bad','wrong')).status_code,401)

    def test_salary_disclosure_independent_of_threshold_and_units(self):
        ids=lambda query:{x['id'] for x in self.get('/api/jobs?'+query).json()['items']}
        self.assertEqual(ids('salary_only=true'),{'monthly','annual','daily','hourly'})
        self.assertEqual(ids('min_salary=4000'),{'annual'})
        self.assertIn('unknown',ids(''))
        self.assertNotIn('expired',ids(''))
        self.assertIn('expired',ids('include_closed=true'))

    def test_note_creates_application_and_survives_restart(self):
        r=self.put('monthly',{'expected_revision':0,'notes':'Call recruiter tomorrow'})
        self.assertEqual(r.status_code,200);self.assertEqual(r.json()['stage'],'Saved')
        self.assertEqual(Store(self.path).get_application('monthly')['notes'],'Call recruiter tomorrow')
        self.assertEqual(self.get('/api/applications').json()['items'][0]['notes'],'Call recruiter tomorrow')

    def test_two_browsers_cannot_silently_overwrite(self):
        self.put('monthly',{'expected_revision':0,'notes':'Original'})
        self.assertEqual(self.put('monthly',{'expected_revision':1,'notes':'First browser'}).status_code,200)
        r=self.put('monthly',{'expected_revision':1,'notes':'Second browser'})
        self.assertEqual(r.status_code,409);self.assertEqual(r.json()['current']['notes'],'First browser')
        self.assertEqual(self.store.get_application('monthly')['notes'],'First browser')

    def test_import_is_repeatable_and_conflicts_are_retained(self):
        self.put('monthly',{'expected_revision':0,'notes':'Server note'})
        payload={'records':{'monthly':{'id':'monthly','status':'Applied','notes':'Browser note'},'missing':{'id':'missing','status':'Ready','notes':'Unavailable vacancy'}}}
        first=self.client.post('/api/applications/import',json=payload,auth=self.auth).json()
        second=self.client.post('/api/applications/import',json=payload,auth=self.auth).json()
        self.assertTrue(first['conflicts']);self.assertEqual(second['imported'],0)
        saved=self.store.get_application('monthly');self.assertEqual(saved['notes'],'Server note');self.assertTrue(saved['import_conflicts'])
        missing=self.get('/api/jobs/missing').json()['job'];self.assertEqual(missing['status'],'unavailable')
        self.assertEqual(self.store.get_application('missing')['stage'],'Preparing')

    def test_application_export_respects_selection_and_injection(self):
        self.put('monthly',{'expected_revision':0,'notes':' =HYPERLINK("bad")','stage':'Applied'})
        self.put('annual',{'expected_revision':0,'notes':'Other note'})
        r=self.get('/api/export/applications?ids=monthly')
        rows=list(csv.DictReader(io.StringIO(r.content.decode('utf-8-sig'))))
        self.assertEqual(len(rows),1);self.assertEqual(rows[0]['Stage'],'Applied')
        self.assertTrue(rows[0]['Notes'].startswith("'"));self.assertEqual(rows[0]['Original URL'],'https://example.com/jobs/monthly')
        rows=list(csv.DictReader(io.StringIO(self.get('/api/export/applications?stage=Saved').content.decode('utf-8-sig'))))
        self.assertEqual([x['ID'] for x in rows],['annual'])

    def test_search_and_export_share_filters(self):
        query='salary_only=true&min_salary=4000&employment_type=Full%20Time'
        expected=[x['id'] for x in self.get('/api/jobs?'+query).json()['items']]
        self.assertEqual(expected,['annual'])
        rows=list(csv.DictReader(io.StringIO(self.get('/api/export/filtered?'+query).content.decode('utf-8-sig'))))
        self.assertEqual([x['ID'] for x in rows],expected)
        self.assertEqual(self.get('/api/jobs?q=nonexistentfoobar').json()['total'],0)
        self.assertEqual(self.get('/api/jobs?limit=251').status_code,422)
        self.assertEqual(self.get('/api/jobs?offset=-1').status_code,422)

    def test_details_and_search_have_identical_presentation(self):
        found=self.get('/api/jobs?q=social').json()['items']
        for job in found:self.assertEqual(job,self.get('/api/jobs/'+job['id']).json()['job'])
        self.assertEqual(found[0],self.get('/api/audit/records/'+found[0]['id']).json()['job'])

    def test_audit_pages_and_bounds(self):
        self.assertEqual(self.get('/sources').status_code,200)
        self.assertEqual(self.get('/api/audit/sources').json()['total'],len(self.jobs))
        self.assertEqual(self.get('/api/audit/records?status=excluded').json()['total'],1)
        self.assertEqual(self.get('/api/audit/records/missing').status_code,404)
        self.assertEqual(self.get('/api/audit/records?offset=-1').status_code,422)
        self.assertEqual(self.get('/api/audit/records/monthly?limit=51').status_code,422)

    def test_lifespan_records_interrupted_run_and_schedules_retry(self):
        self.store.set_meta('active_sync',{'started_at':'2026-10-20T01:00:00Z'})
        async def restart():
            async with web.lifespan(web.app):
                self.assertEqual(self.store.get_sync_history(1)[0]['status'],'interrupted')
                self.assertIsNone(self.store.get_meta('active_sync'))
                self.assertLessEqual(self.store.get_meta('next_sync_at'),time.time())
        asyncio.run(restart())

    def test_drafts_and_listing_reads_do_not_mark_applied(self):
        self.put('monthly',{'expected_revision':0})
        self.get('/api/jobs/monthly');r=self.get('/api/drafts/monthly');self.assertEqual(r.status_code,200)
        text=json.dumps(r.json()).lower()
        for banned in ['immediately available','immediate availability','@gmail','+65','i specialize in highlight']:
            self.assertNotIn(banned,text)
        self.assertEqual(self.store.get_application('monthly')['stage'],'Saved')

    def test_xlsx_is_a_real_workbook_with_sanitized_source(self):
        import openpyxl
        r=self.get('/download/excel');self.assertEqual(r.status_code,200)
        wb=openpyxl.load_workbook(io.BytesIO(r.content),read_only=True)
        self.assertIn('Title',next(wb.active.values));wb.close()
        self.assertEqual(web.sanitize_url('javascript:alert(1)'),'#')
        for text in ['=cmd',' @SUM(A1)','\t=SUM(A1)','\n+cmd']:
            self.assertTrue(web.safe_cell(text).startswith("'"))

    def test_cross_origin_writes_rejected(self):
        r=self.client.put('/api/applications/monthly',json={'expected_revision':0},auth=self.auth,headers={'Origin':'https://elsewhere.test'})
        self.assertEqual(r.status_code,403)

    def test_lifespan_resumes_overdue_refresh(self):
        self.store.set_meta('next_sync_at',time.time()-20)
        async def exercise():
            async def finish(application):
                application.state.store.set_meta('next_sync_at',time.time()+43200)
            with patch.object(web,'run_sync',side_effect=finish) as synced:
                task=asyncio.create_task(web.refresh_loop(web.app))
                await asyncio.sleep(.02);task.cancel()
                try:await task
                except asyncio.CancelledError:pass
                self.assertEqual(synced.call_count,1)
        asyncio.run(exercise())

    def test_downloadable_backup_restores_applications(self):
        self.put('monthly',{'expected_revision':0,'notes':'Backup restore check'})
        response=self.get('/api/backup');self.assertEqual(response.status_code,200)
        downloaded=Path(self.temp.name)/'downloaded.sqlite3';downloaded.write_bytes(response.content)
        restored=Path(self.temp.name)/'restored.sqlite3'
        self.assertTrue(Store.restore_backup(downloaded,restored)['restoration_verified'])
        self.assertEqual(Store(restored).get_application('monthly')['notes'],'Backup restore check')

    def test_freelance_separation_and_thai_filter(self):
        self.store.seed_jobs([vacancy('freelance',title='Freelance Thai interpreter',employment_type='Freelance',description='Must speak Thai. Interpretation assignments.')])
        ids=lambda query:{j['id'] for j in self.get('/api/jobs?'+query).json()['items']}
        self.assertNotIn('freelance',ids(''))
        self.assertEqual(ids('opportunity_type=freelance&thai_relevance=required'),{'freelance'})
        self.assertIn('freelance',ids('opportunity_type=all'))


if __name__=='__main__':unittest.main()
