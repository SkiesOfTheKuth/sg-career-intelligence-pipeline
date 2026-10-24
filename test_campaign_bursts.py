"""Isolated burst admission, recovery and value regressions. Network is forbidden."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from campaign import CampaignWorker
from campaign_apify import ApiError
from campaign_bursts import Bursts, SGT, account_headroom, batch_queries, day_window, expansion_candidates, identity
from campaign_sources import input_for, validate_input
from campaign_store import DAY, units
from storage import Store
from test_campaign_scheduler_v2 import Api


class BurstTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.store=Store(Path(self.temp.name)/'burst.sqlite3').initialize()
        self.now=datetime(2026,10,24,12,tzinfo=SGT).timestamp()
        self.api=Api()
        self.worker=CampaignWorker(self.store,self.api,clock=lambda:self.now)
        self.j=self.worker.journal;self.b=self.worker.bursts
        self.j.create(self.now)
        with self.store._connection(write=True) as c:
            c.execute("UPDATE campaigns SET state='active',mode='production',started_at=?,stops_at=?",(self.now-1000,self.now+6*DAY))
            c.execute('UPDATE campaign_sources SET due_at=?',(self.now+DAY,))
        self.worker.refresh_accounts(self.now)
        self.store.set_meta('last_backup',{'verified':True})
        self.store.set_meta('campaign_validated_sources',['indeed','linkedin','google','careers'])
        self.j.claim(self.worker.owner,self.now)
        self.network=patch('requests.request',side_effect=AssertionError('Live network forbidden'));self.network.start()

    def tearDown(self):
        self.network.stop();self.temp.cleanup()

    def start(self):
        return self.worker.start_burst('one-day-20261024')

    def batch(self,source='indeed',query='unused query',tranche=1):
        self.b.enqueue_searches(source,[query],tranche,self.now)
        return next(b for b in self.j.batches() if query in batch_queries(b))

    def complete(self,batch,new=0,duplicates=0,leads=0,cost=.1,cap=.6875):
        with self.store._connection(write=True) as c:
            c.execute("UPDATE campaign_batches SET state='done',reserved_at=?,finished_at=?,account_id='one',reserved_units=?,charge_units=?,new_count=?,duplicate_count=?,lead_count=? WHERE id=?",
                      (self.now,self.now,units(cap),units(cost),new,duplicates,leads,batch['id']))

    def test_incremental_idempotent_endpoint_preserves_clock_and_prior_cost(self):
        self.j.enqueue('indeed','old',input_for('indeed','old'),{'cap_usd':2},self.now)
        old=self.j.batches()[0];self.complete(old,new=3,cost=1.4,cap=2)
        before=self.j.current();first=self.start();again=self.start()
        self.assertEqual(first['id'],again['id']);self.assertEqual(first['baseline_campaign_charged_usd'],1.4)
        self.assertEqual(first['charged_usd'],0);self.assertEqual(first['target_usd'],150)
        self.assertEqual((before['id'],before['started_at'],before['stops_at']),tuple(self.j.current()[k] for k in ('id','started_at','stops_at')))
        with self.assertRaises(ValueError):self.worker.start_burst('different-burst')

    def test_sgt_calendar_window(self):
        self.start();row=self.b.current()
        self.assertEqual(row['local_day'],'2026-10-24')
        self.assertEqual(datetime.fromtimestamp(row['window_end'],SGT).isoformat(),'2026-10-25T00:00:00+08:00')

    def test_accounts_deduplicated_and_capacity_underfill(self):
        self.api.snapshots=lambda:[{**self.api.snapshot('one'),'limit_usd':5}]*2
        # Remove old fixture accounts to model one configured account.
        with self.store._connection(write=True) as c:c.execute('DELETE FROM campaign_accounts')
        report=self.start()
        self.assertAlmostEqual(report['capacity_ceiling_usd'],4.85)
        self.assertAlmostEqual(report['capacity_shortfall_usd'],145.15)
        self.assertEqual(len(self.j.accounts()),1)

    def test_account_ancillary_cannot_recycle_completed_caps(self):
        self.start();batch=self.batch();self.complete(batch,cost=.1,cap=2)
        self.now+=1
        self.j.account({**self.api.snapshot('one'),'usage_usd':.5},self.now)
        with self.store._connection() as c:
            headroom=account_headroom(c,self.j.current()['id'],self.j.accounts()[0])
        self.assertEqual(headroom,units(97.45))
        report=self.b.report(self.now)
        self.assertEqual(report['reserved_exposure_usd'],2)
        self.assertEqual(report['charged_usd'],.1)
        self.assertEqual(report['observed_ancillary_usd'],.4)

    def test_no_duplicate_queries_across_history_and_restarts(self):
        self.j.enqueue('indeed','old',input_for('indeed','Marketing Executive hospitality'),{'cap_usd':.5},self.now)
        self.start()
        self.assertEqual(self.b.enqueue_searches('indeed',['marketing  executive Hospitality'],1,self.now),0)
        self.assertEqual(self.b.enqueue_searches('indeed',['unique',' Unique '],1,self.now),1)
        restarted=CampaignWorker(Store(self.store.path).initialize(),self.api,clock=lambda:self.now)
        self.assertEqual(restarted.bursts.enqueue_searches('indeed',['UNIQUE'],2,self.now),0)
        self.assertEqual(restarted.bursts.current()['id'],self.b.current()['id'])

    def test_expansion_dimensions_and_payload_contracts(self):
        for source in ('indeed','linkedin','google'):
            queries=list(expansion_candidates(source,[{'company':'Acme'}]))
            self.assertTrue(any('Acme' in q for q in queries))
            self.assertTrue(any('Adecco' in q for q in queries))
            for query in queries[:30]:
                payload=input_for(source,query);validate_input(source,payload)
                if source=='indeed':self.assertEqual(payload['maxItemsPerSearch'],100);self.assertFalse(payload['parseCompanyDetails']);self.assertFalse(payload['followApplyRedirects'])
                if source=='linkedin':self.assertEqual(payload['limitPerSource'],100);self.assertFalse(payload['scrapeCompany'])

    def test_tranches_stop_and_transfer_only_unused_allocation_once(self):
        self.start()
        for n in (1,2):
            self.complete(self.batch(query=f'q{n}',tranche=n),duplicates=9,leads=1,cap=1)
            self.b.reconcile(self.now)
        report=self.b.report(self.now);sources={s['source']:s for s in report['sources']}
        self.assertEqual(sources['indeed']['state'],'value_stopped')
        self.assertEqual(sources['indeed']['soft_allocation_usd'],2)
        self.assertEqual(sources['linkedin']['soft_allocation_usd'],177)
        self.assertEqual(sources['google']['soft_allocation_usd'],1)
        self.assertEqual(sources['careers']['soft_allocation_usd'],20)
        self.b.reconcile(self.now)
        self.assertEqual(len([e for e in self.b.report(self.now)['events'] if e['kind']=='reallocation']),1)

    def test_value_streak_resets_and_rank_uses_charges(self):
        self.start()
        for n,new in ((1,0),(2,2),(3,0)):
            self.complete(self.batch(query=f'i{n}',tranche=n),new=new,duplicates=20)
        self.complete(self.batch('linkedin','l1'),new=3,duplicates=1,cost=.05,cap=.25)
        self.b.reconcile(self.now)
        report=self.b.report(self.now)
        self.assertEqual(report['ranking'][0],'linkedin')
        self.assertEqual(next(s for s in report['sources'] if s['source']=='indeed')['state'],'active')

    def test_unfinished_import_does_not_complete_a_tranche(self):
        self.start();one=self.batch(query='one');two=self.batch(query='two')
        self.complete(one,duplicates=10)
        self.j.update_batch(two['id'],state='importing',charge_units=units(.1))
        self.b.reconcile(self.now)
        self.assertFalse(next(s for s in self.b.report(self.now)['sources'] if s['source']=='indeed')['tranches'])

    def test_transactional_two_global_one_per_account_and_rotation(self):
        self.start();batches=[self.batch(query=f'q{n}') for n in range(5)]
        with ThreadPoolExecutor(max_workers=5) as pool:
            results=list(pool.map(lambda p:self.j.reserve(p[1]['id'],['one','two','three'][p[0]%3],.6875,self.worker.owner,self.now),enumerate(batches)))
        self.assertEqual(sum(r[0] for r in results),2)
        self.assertEqual(len({r['account_id'] for r in self.j.batches(('launching',))}),2)

    def test_incremental_soft_cap_at_two_hundred_not_old_rolling_fifty(self):
        self.start();batch=self.batch()
        self.assertTrue(self.j.reserve(batch['id'],'one',.6875,self.worker.owner,self.now)[0])
        self.complete(batch,new=1,cap=199.75,cost=150)
        with self.store._connection(write=True) as c:
            c.execute('UPDATE campaign_bursts SET initial_capacity_units=?,capacity_units=?',(units(200),units(200)))
            c.execute('UPDATE campaign_burst_sources SET target_units=?,soft_units=? WHERE source=?',(units(200),units(200),'indeed'))
            c.execute('UPDATE campaign_accounts SET limit_units=?',(units(1000),))
        self.b.reconcile(self.now)
        queued=self.batch(query='beyond-soft',tranche=2)
        self.assertIn('US$200',self.j.budget_reason(queued['id'],.6875,self.now))
        self.assertEqual(self.b.report(self.now)['state'],'target_reached')

    def test_completed_caps_limit_capacity_and_fragmented_accounts_stop(self):
        self.start()
        with self.store._connection(write=True) as c:
            c.execute('UPDATE campaign_accounts SET limit_units=?',(units(.35),))
        self.b.reconcile(self.now)
        self.assertEqual(self.b.current()['state'],'capacity')

    def test_campaign_total_ceiling_still_applies(self):
        self.start();batch=self.batch(query='old');self.complete(batch,new=1,cap=314.9,cost=10)
        with self.store._connection(write=True) as c:
            c.execute('UPDATE campaign_batches SET burst_id=NULL WHERE id=?',(batch['id'],))
            c.execute('UPDATE campaign_accounts SET limit_units=?',(units(1000),))
        new=self.batch(query='new')
        self.assertIn('Campaign budget',self.j.budget_reason(new['id'],.6875,self.now))

    def test_google_daily_production_limit_includes_prior_campaign_batches(self):
        for n in (1,2):
            payload=input_for('google','\n'.join(f'old {n} {i}' for i in range(20)))
            self.j.enqueue('google',f'g{n}',payload,{'cap_usd':.5},self.now)
            batch=next(r for r in self.j.batches() if r['batch_key']==f'g{n}');self.complete(batch,cap=.5,cost=.5)
        self.start();self.b.schedule(self.worker,self.now)
        self.assertFalse([r for r in self.j.batches() if r['source']=='google' and r['burst_id']])
        google=self.batch('google','new official careers')
        self.assertIn('Google daily',self.j.budget_reason(google['id'],.5,self.now))

    def test_google_leads_and_career_recursion_preserve_parent_payload(self):
        self.start();batch=self.batch('google','official jobs')
        item={'organicResults':[{'url':'https://acme.example/careers','title':'Acme careers'}]}
        self.worker.import_page(batch,[item],self.now)
        self.worker.import_page(batch,[item],self.now)
        self.assertEqual(self.store.count_jobs(),0)
        with self.store._connection() as c:
            row=c.execute('SELECT * FROM campaign_discovery').fetchone()
            self.assertEqual(json.loads(row['evidence_json'])['parent_batch_id'],batch['id'])
            self.assertEqual(c.execute('SELECT COUNT(*) FROM campaign_items').fetchone()[0],1)
        self.worker.schedule_careers(self.now,0,False,burst_id=self.b.current()['id'],batch_limit=1)
        career=next(r for r in self.j.batches() if r['source']=='careers')
        self.assertEqual(json.loads(career['context_json'])['depth'],0)
        self.assertLessEqual(len(json.loads(career['context_json'])['urls']),50)
        self.assertEqual(career['burst_id'],self.b.current()['id'])

    def test_duplicate_import_is_checkpointed_and_preserves_applications(self):
        self.start();batch=self.batch()
        item={'jobKey':'fresh','positionName':'Marketing Executive','company':'Acme','url':'https://sg.indeed.com/viewjob?jk=fresh',
              'location':'Singapore','description':'Responsibilities: Manage social media content. Requirements: Marketing degree.'}
        self.worker.import_page(batch,[item,item],self.now)
        self.worker.import_page(batch,[item,item],self.now)
        self.assertEqual(self.store.count_jobs(),1)
        current=next(r for r in self.j.batches() if r['id']==batch['id'])
        self.assertEqual((current['new_count'],current['duplicate_count'],current['checkpoint']),(1,1,2))

    def test_window_expiry_cancels_unlaunched_and_restores_recurring_admission(self):
        self.start();burst=self.b.current();batch=self.batch()
        self.j.enqueue('linkedin','recurring',input_for('linkedin','ordinary'),{'cap_usd':.25},self.now)
        recurring=next(r for r in self.j.batches() if r['batch_key']=='recurring')
        self.assertIn('wait until',self.j.budget_reason(recurring['id'],.25,self.now))
        self.now=burst['window_end']+1;self.b.reconcile(self.now);self.b.close_queued(self.now)
        self.assertIsNone(self.j.budget_reason(recurring['id'],.25,self.now))
        self.assertEqual(next(r for r in self.j.batches() if r['id']==batch['id'])['state'],'superseded')
        self.assertTrue(self.b.report(self.now)['recurring_policy_restored'])

    def test_auth_failure_stops_new_paid_work_but_retains_import(self):
        self.start();batch=self.batch();self.j.update_batch(batch['id'],state='importing',charge_units=units(.1))
        self.b.reconcile(self.now,'Apify authentication (HTTP 401)')
        self.assertEqual(self.b.current()['state'],'account_error')
        self.assertEqual(self.j.batches(('importing',))[0]['id'],batch['id'])
        self.assertIn('stopped',self.j.budget_reason(self.batch(query='next')['id'],.6875,self.now))

    def test_api_authentication_idempotency_and_fixed_parameters(self):
        import app as web
        from fastapi.testclient import TestClient
        old=web.app.state.database_path;web.app.state.database_path=self.store.path
        self.store.set_meta('seed_version',2)
        try:
            with patch.dict(os.environ,{'DISABLE_BACKGROUND_SYNC':'1','APIFY_TOKENS_JSON':'[]'}),TestClient(web.app) as client:
                web.app.state.campaign_worker=self.worker
                auth=(web.AUTH_USERNAME,web.AUTH_PASSWORD);payload={'burst_id':'one-day-20261024'}
                self.assertEqual(client.post('/api/campaign/burst',json=payload).status_code,401)
                self.assertEqual(client.post('/api/campaign/burst',json=payload,auth=auth,headers={'Origin':'https://evil.example'}).status_code,403)
                self.assertEqual(client.post('/api/campaign/burst',json={**payload,'target':999},auth=auth).status_code,422)
                a=client.post('/api/campaign/burst',json=payload,auth=auth);self.assertEqual(a.status_code,200,a.text)
                b=client.post('/api/campaign/burst',json=payload,auth=auth);self.assertEqual(a.json()['id'],b.json()['id'])
                self.assertEqual(len(self.api.launched),0)
        finally:web.app.state.database_path=old

    def test_restart_restoration_keeps_all_burst_content(self):
        self.start();batch=self.batch();self.complete(batch,new=2)
        self.b.reconcile(self.now)
        backup=Path(self.temp.name)/'backup.sqlite3';self.store.backup(backup)
        result=Store.restore_backup(backup,Path(self.temp.name)/'restored.sqlite3')
        self.assertEqual(result['counts']['campaign_bursts'],1)
        self.assertEqual(result['counts']['campaign_burst_tranches'],1)
        before=Store.verify_database(self.store.path);Store(self.store.path).initialize()
        self.assertEqual(before,Store.verify_database(self.store.path))

    def test_nonempty_application_snapshot_notes_drafts_and_history_survive(self):
        job={'id':'saved','title':'Marketing Executive','company':'Acme','url':'https://acme.example/careers/1',
             'verification':{'last_success_at':'2026-10-22T00:00:00+00:00'}}
        self.store.seed_jobs([job])
        self.store.put_application('saved',{'expected_revision':0,'notes':'Exact user notes','drafts':{'cover_letter':'Exact user draft'},'stage':'Preparing'})
        before=self.store.get_application('saved')
        self.start();self.worker.schedule_careers(self.now,0,True,burst_id=self.b.current()['id'])
        self.assertEqual(self.store.get_application('saved'),before)
        backup=Path(self.temp.name)/'nonempty.sqlite3';self.store.backup(backup)
        target=Path(self.temp.name)/'restored-nonempty.sqlite3';Store.restore_backup(backup,target)
        self.assertEqual(Store(target).initialize().get_application('saved'),before)

    def test_worker_obeys_burst_run_deadline_and_retains_obtained_imports(self):
        self.start();self.b.schedule(self.worker,self.now)
        self.worker.tick()
        self.assertLessEqual(len(self.api.launched),2)
        self.assertTrue(all(r['burst_id']==self.b.current()['id'] for r in self.api.launched))
        # The native launch receives the burst end, earlier than campaign end.
        calls=[]
        self.api.launch=lambda ref,batch,stop,now:(calls.append(stop) or {'id':'another'+str(len(calls)),'status':'RUNNING'})
        for batch in self.j.batches(('running',)):
            self.j.update_batch(batch['id'],state='done',finished_at=self.now,charge_units=0)
        self.worker.tick()
        self.assertTrue(calls);self.assertTrue(all(stop==self.b.current()['window_end'] for stop in calls))
        self.now=self.b.current()['window_end']+1
        self.worker.tick()
        self.assertTrue(self.api.aborted)
        self.assertTrue(self.b.report(self.now)['recurring_policy_restored'])

    def test_google_minimum_slice_and_career_slice_are_not_reallocated(self):
        self.start()
        with self.store._connection(write=True) as c:
            c.execute('UPDATE campaign_bursts SET initial_capacity_units=?,capacity_units=?',(units(1),units(1)))
        self.batch('google','official careers')
        batch=self.batch()
        self.assertIn('protects discovery',self.j.budget_reason(batch['id'],.6875,self.now))

    def test_source_exhaustion_closes_burst_without_repeating_queries(self):
        self.start()
        with self.store._connection(write=True) as c:
            c.execute("UPDATE campaign_burst_sources SET state='value_stopped' WHERE source IN ('indeed','linkedin')")
            c.execute("UPDATE campaign_burst_sources SET soft_units=0 WHERE source IN ('google','careers')")
        # Model the already-consumed Google daily limit.
        for n in range(2):
            self.j.enqueue('google',f'daily{n}',input_for('google',f'daily{n}'),{'cap_usd':.5},self.now)
            batch=next(b for b in self.j.batches() if b['batch_key']==f'daily{n}');self.complete(batch,cap=.5)
        self.b.schedule(self.worker,self.now)
        self.assertEqual(self.b.current()['state'],'value_exhausted')


if __name__=='__main__':unittest.main()
