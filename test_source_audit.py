"""Audit and score regressions use small source fixtures, never live scraping."""
import asyncio
from datetime import datetime, timezone
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import app as web
from evidence import build_job, present_job, sort_key
from source_audit import build_audit, audit_records, inspect_record
from storage import Store


def role(jid='one', **changes):
    raw = dict(title='Social Media Executive', company='Employer', source='LinkedIn Jobs',
               url='https://example.com/jobs/'+jid, description="Responsibilities\nManage social media accounts.\nCreate content for social media.\nRequirements\nBachelor's degree in Marketing\nExperience in social media")
    raw.update(changes)
    return build_job(raw, jid)


class ScoreTests(unittest.TestCase):
    def score(self, **changes): return role(**changes)['assessment']['score']

    def test_supported_role_has_traceable_components_and_outscores_specialist(self):
        supported = role()
        finance = role('finance',title='Accounts Receivable Specialist')
        a,b = supported['assessment']['score'], finance['assessment']['score']
        self.assertEqual(a['value'],100)
        self.assertEqual(supported['assessment']['fit'],'Relevant')
        self.assertEqual(sum(part['earned'] for part in a['components']),a['value'])
        self.assertTrue(all(row['quote'] and row['candidate_evidence'] for row in a['duties']))
        self.assertLess(b['value'],40)
        self.assertLess(sort_key(supported), sort_key(finance))

    def test_partial_missing_or_company_only_descriptions_withhold_score(self):
        for changes in [dict(description_incomplete=True),dict(description=''),dict(description='We are a company specialising in social media, content creation and marketing analytics.')]:
            self.assertIsNone(self.score(**changes)['value'])

    def test_missing_requirements_are_not_assumed_met(self):
        score = self.score(description='Responsibilities\nManage social media accounts.')
        self.assertLess(score['value'],60)
        self.assertTrue(score['provisional'])
        self.assertEqual(score['components'][2]['earned'],0)

    def test_unknown_requirements_reduce_score_and_do_not_mean_incapable(self):
        score = self.score(requirements='Excellent writing skills\nMust use Python')
        self.assertLess(score['value'],60)
        self.assertEqual(score['unknown_requirements'],2)
        self.assertTrue(any('not a claim' in row['reason'] for row in score['requirements']))

    def test_languages_and_required_duration_cap_score(self):
        for req in ['Fluent Japanese or Vietnamese required','Fluent English and Japanese or Vietnamese required','Minimum 5 years of marketing experience']:
            score = self.score(requirements=req)
            self.assertTrue(score['gates'],req)
            self.assertLess(score['value'],40)

    def test_supported_language_alternative_does_not_make_false_gate(self):
        for req in ['Fluent Japanese or English required','Japanese proficiency preferred','Japanese is not required']:
            score = self.score(requirements=req)
            self.assertFalse(any(g['kind']=='language' for g in score['gates']),req)

    def test_mixed_language_alternatives_do_not_waive_independent_requirement(self):
        score = self.score(requirements='Fluent Japanese or English and Vietnamese required')
        gate = next(g for g in score['gates'] if g['kind']=='language')
        self.assertIn('Vietnamese',gate['reason']);self.assertNotIn('Japanese,',gate['reason'])

    def test_specialist_tools_and_video_skills_cannot_earn_duty_points(self):
        for duty in ['Analyse content analytics using SQL.']:
            score = self.score(description=f'Responsibilities\n{duty}\nRequirements\nExperience in social media')
            self.assertEqual(score['components'][1]['earned'],0,duty)
            self.assertTrue(all(row['status']=='check' for row in score['duties']))
        mixed = self.score(description='Responsibilities\nManage social media and paid advertising budgets.\nRequirements\nExperience in social media')
        self.assertEqual(mixed['duties'][0]['status'], 'partial')
        self.assertFalse(mixed['duties'][0]['clauses'][1]['candidate_evidence'])
        score = self.score(description='Responsibilities\nCreate content and edit videos with Adobe Premiere.\nRequirements\nExperience in social media')
        self.assertEqual(score['duties'][0]['status'], 'partial')
        self.assertEqual(score['components'][1]['earned'], 25)
        self.assertFalse(score['duties'][0]['clauses'][1]['candidate_evidence'])

    def test_repeating_supported_duty_cannot_dilute_unknowns(self):
        base = 'Responsibilities\nManage social media accounts.\nEdit videos.\nRequirements\nExperience in social media'
        first=self.score(description=base)
        repeated=self.score(description=base.replace('Manage social media accounts.','Manage social media accounts.\nManage social media channels.\nManage social media campaigns.'))
        self.assertEqual(first['value'],repeated['value'])

    def test_company_prestige_salary_thailand_and_queries_add_no_points(self):
        first=self.score()
        second=role(company='PropertyGuru',advertised_salary='SGD 90000 /month',query_matched='Thai speaking',description=role()['description']+'\nAbout us\nWe have offices in Thailand.')['assessment']['score']
        self.assertEqual(first['value'],second['value'])
        j=role(company='PropertyGuru',description='We operate in Thailand.\nResponsibilities\nManage social media accounts.')
        self.assertEqual(j['thai_relevance'],'Thailand market context')

    def test_nonstandard_headings_and_noun_bullets_do_not_hide_specialist_duties(self):
        description = 'Job Responsibilities including but not limited to:\n- Develop creative marketing content\n- Product photography\n- Graphic design\n- Knowledge on video production\nRequirements:\nExperience in social media'
        score=self.score(description=description)
        self.assertEqual(len(score['duties']),4)
        self.assertLess(score['components'][1]['earned'],20)
        description='1. Conducting market research to identify customer needs\n2. Actively seeking out sales opportunities through cold calling and social media\n3. Setting up client meetings\n4. Discovering new sales prospects'
        score=self.score(description=description)
        self.assertEqual(len(score['duties']),4)
        self.assertLess(score['value'],40)

    def test_curly_apostrophe_heading_retains_actual_mandatory_language(self):
        job=role(description='What You’ll Do\nManage social media.\nWhat We’re Looking For\nFluent Japanese or Vietnamese required')
        self.assertTrue(job['requirements']['mandatory'])
        self.assertLess(job['assessment']['score']['value'],40)

    def test_read_time_reassessment_upgrades_stored_jobs_without_mutating_evidence(self):
        old=role();old['assessment']={'fit':'Relevant','score':{'value':99,'version':'old'}}
        original=old['raw_evidence'].copy()
        current=present_job(old)
        self.assertEqual(current['assessment']['score']['version'],'documented-fit-v2')
        self.assertEqual(old['assessment']['score']['version'],'old')
        self.assertEqual(current['raw_evidence'],original)


class SourceAuditTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.store=Store(Path(self.temp.name)/'career.sqlite3').initialize()
        self.store.seed_jobs([role(),role('mcf',source='MyCareersFuture (Singapore Govt)'),role('expired',expiry_date='2000-01-01')])
    def tearDown(self): self.temp.cleanup()
    def overview(self): return build_audit(self.store,scheduler_enabled=True,running=False,interval_seconds=43200)

    def test_counts_coverage_and_modes_come_from_store(self):
        self.store.put_application('one',{'expected_revision':0,'notes':'Saved'})
        audit=self.overview()
        self.assertEqual(sum(s['count'] for s in audit['sources']),3)
        self.assertEqual(audit['discovery_count'],2);self.assertEqual(audit['excluded_count'],1)
        self.assertEqual(audit['applications_count'],1)
        self.assertEqual(audit['coverage'][0]['count'],3)
        self.assertEqual(audit['coverage'][3]['count'],0)
        self.assertEqual(audit['scheduler']['limit_per_query'],10)
        self.assertEqual(len(audit['scheduler']['queries']),4)
        self.assertEqual(next(s for s in audit['sources'] if s['id']=='linkedin')['state'],'retained')

    def test_degraded_historical_date_is_not_successful_verification(self):
        job=self.store.get_job('mcf');job['verification'].update(status='degraded',checked_at='2026-10-21T01:00:00Z',last_error='timeout')
        self.store.upsert_jobs([job]);self.store.record_sync({'status':'error','started_at':'2026-10-21T02:00:00Z','errors':[{'message':'timeout'}]})
        source=next(s for s in self.overview()['sources'] if s['id']=='mycareersfuture')
        self.assertIsNone(source['last_success']);self.assertEqual(source['state'],'error')
        self.assertEqual(source['latest_record_date'],'2026-10-21T01:00:00Z')

    def test_failed_run_preserves_previous_successful_response_and_date(self):
        now=datetime.now(timezone.utc).isoformat()
        job=role('mcf',source='MyCareersFuture (Singapore Govt)',verified_at=now)
        job['verification'].update(status='degraded',last_error='timeout')
        self.store.upsert_jobs([job]);self.store.record_sync({'status':'error','errors':[{'message':'timeout'}]})
        source=next(s for s in self.overview()['sources'] if s['id']=='mycareersfuture')
        self.assertEqual(source['last_success'],now);self.assertEqual(source['coverage'][3]['count'],0)

    def test_records_filter_search_and_paginate_consistently(self):
        self.assertEqual(audit_records(self.store,source='mycareersfuture')['total'],1)
        self.assertEqual(audit_records(self.store,q='Employer social')['total'],3)
        self.assertEqual(audit_records(self.store,status='excluded')['items'][0]['id'],'expired')
        self.assertEqual(audit_records(self.store,status='recent')['total'],0)
        first=audit_records(self.store,limit=1);second=audit_records(self.store,offset=1,limit=1)
        self.assertNotEqual(first['items'][0]['id'],second['items'][0]['id'])

    def test_evidence_versions_preserve_payload_and_redact_nested_credentials(self):
        for index in range(3): self.store.record_source_evidence('one','LinkedIn',{'description':'<script>source text</script>','version':index,'nested':{'api_key':'secret'},'record':{'query_matched':'Thai speaking'}})
        page=inspect_record(self.store,'one',limit=2)
        self.assertEqual(page['evidence']['total'],3)
        self.assertEqual([x['payload']['version'] for x in page['evidence']['items']],[2,1])
        self.assertEqual(page['evidence']['items'][0]['payload']['nested']['api_key'],'[redacted]')
        self.assertEqual(page['collector_context']['query_matched'],'Thai speaking')
        self.assertIsNone(inspect_record(self.store,'absent'))

    def test_cancelled_request_does_not_abandon_running_collector_or_release_lock(self):
        app=SimpleNamespace(state=SimpleNamespace(store=self.store,sync_run_task=None))
        started=threading.Event();finish=threading.Event()
        def collect(**kwargs): started.set();finish.wait(3);return {'status':'success'}
        async def exercise():
            app.state.sync_lock=asyncio.Lock()
            with patch.object(web,'synchronize_upstream_jobs',side_effect=collect),patch.object(web,'verified_backup'):
                request=asyncio.create_task(web.run_sync(app))
                for _ in range(100):
                    if started.is_set():break
                    await asyncio.sleep(.005)
                self.assertTrue(started.is_set());request.cancel()
                with self.assertRaises(asyncio.CancelledError):await request
                self.assertTrue(app.state.sync_lock.locked())
                self.assertEqual((await web.run_sync(app))['status'],'in_progress')
                finish.set();await app.state.sync_run_task
                self.assertFalse(app.state.sync_lock.locked())
                self.assertIsNone(self.store.get_meta('active_sync'))
                self.assertIsNotNone(self.store.get_meta('next_sync_at'))
        asyncio.run(exercise())

    def test_backup_failure_does_not_relabel_source_success_as_failure(self):
        app=SimpleNamespace(state=SimpleNamespace(store=self.store,sync_run_task=None))
        async def exercise():
            app.state.sync_lock=asyncio.Lock()
            with patch.object(web,'synchronize_upstream_jobs',return_value={'status':'success'}),patch.object(web,'verified_backup',side_effect=OSError('Disk error')),self.assertLogs(web.logger,level='ERROR'):
                result=await web.run_sync(app)
                self.assertEqual(result['status'],'success')
                self.assertIn('storage_warning',result)
                self.assertEqual(self.store.get_sync_history(),[])
                self.assertIsNotNone(self.store.get_meta('last_backup_error'))
        asyncio.run(exercise())


if __name__ == '__main__':unittest.main()
