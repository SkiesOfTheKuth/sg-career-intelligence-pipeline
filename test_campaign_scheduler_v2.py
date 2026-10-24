"""Offline regression evidence for the corrected campaign scheduler."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from campaign import CampaignWorker, iso
from campaign_apify import ApiError
from campaign_sources import input_for
from campaign_store import DAY, units
from storage import Store


class Api:
    def __init__(self):
        self.launched, self.aborted = [], []
        self.remote = {'id':'run1','status':'RUNNING','defaultDatasetId':'dataset1'}
        self.pages = {}
        self.match = None

    def snapshot(self, reference):
        return {'account_id':reference,'reference':reference,'usage_usd':0,'limit_usd':100,
                'cycle':{'start':'a','end':'b'},'available':True}

    def snapshots(self):
        return [self.snapshot('one'),self.snapshot('two'),self.snapshot('three')]

    def contract(self,*args):
        return {}

    def launch(self,ref,batch,*args):
        self.launched.append(batch)
        return {**self.remote,'id':'run'+str(len(self.launched))}

    def run(self,*args):
        return self.remote.copy()

    def reconcile(self,*args):
        return self.match

    def abort(self,ref,run):
        self.aborted.append(run)

    def items(self,ref,dataset,offset):
        return self.pages.get(offset,[])


class SchedulerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name)/'campaign.sqlite3').initialize()
        self.now = 1800000000.0
        self.api = Api()
        self.worker = CampaignWorker(self.store,self.api,access=lambda *_:self.fail('Removed access check ran'),clock=lambda:self.now)
        self.j = self.worker.journal
        self.j.create(self.now)
        self.worker.refresh_accounts(self.now)
        self.j.claim(self.worker.owner,self.now)
        self.network = patch('requests.request',side_effect=AssertionError('Live network forbidden'))
        self.network.start()

    def tearDown(self):
        self.network.stop()
        self.temp.cleanup()

    def production(self):
        with self.store._connection(write=True) as c:
            c.execute("UPDATE campaigns SET state='active',mode='production',started_at=?,stops_at=?",(self.now,self.now+7*DAY))
            c.execute('UPDATE campaign_sources SET due_at=?',(self.now+DAY,))
        self.store.set_meta('campaign_validated_sources',['indeed','linkedin','google','careers'])

    def queue(self,url,depth=0,evidence=None):
        with self.store._connection(write=True) as c:
            self.worker.discover(c,self.j.current()['id'],url,None,depth,url,evidence or {},self.now)

    def batch(self,source,payload,context=None,key='test'):
        self.j.enqueue(source,key,payload,context or {'cap_usd':.5},self.now)
        return next(b for b in self.j.batches() if b['batch_key']==key)

    def test_removed_access_checks_never_run_for_all_sources(self):
        for source in ('indeed','linkedin','google','careers'):
            with self.subTest(source=source):
                self.production()
                batch = self.batch(source,input_for(source,'http://127.0.0.1:8080/careers' if source=='careers' else 'Thai'),key=source)
                self.worker.tick()
                observed = next(b for b in self.j.batches() if b['id']==batch['id'])
                self.assertEqual(observed['state'],'running')
                self.j.update_batch(batch['id'],state='done',finished_at=self.now,charge_units=0)
        self.assertEqual(len(self.api.launched),4)

    def test_source_validation_isolated_and_preserves_active_campaign(self):
        self.production()
        before = self.j.current()
        self.store.set_meta('campaign_validated_sources',['indeed'])
        self.worker.pilot('google')
        batch = next(b for b in self.j.batches() if b['batch_key']=='pilot:google')
        self.assertEqual(json.loads(batch['context_json'])['cap_usd'],.5)
        self.worker.tick()
        batch = next(b for b in self.j.batches() if b['id']==batch['id'])
        self.assertEqual(batch['state'],'running')
        self.worker.import_page(batch,[{'url':'https://google.com/search?q=jobs','organicResults':[{'url':'https://employer.example/careers','title':'Careers'}]}],self.now)
        with self.store._connection() as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM campaign_discovery').fetchone()[0],0)
        after = self.j.current()
        self.assertEqual((after['state'],after['mode'],after['started_at'],after['stops_at']),
                         (before['state'],before['mode'],before['started_at'],before['stops_at']))

    def test_all_pilot_inputs_and_pilot_budget_are_bounded(self):
        self.production()
        for source in ('indeed','linkedin','google','careers'):
            self.worker.pilot(source,['https://employer.example/careers'] if source=='careers' else None)
        batches = self.j.batches()
        self.assertEqual(len(batches),4)
        self.assertEqual(sum(json.loads(b['context_json'])['cap_usd'] for b in batches),1.4)
        for batch in batches:
            self.assertTrue(json.loads(batch['context_json'])['pilot'])
        self.assertFalse(json.loads(next(b for b in batches if b['source']=='careers')['input_json'])['respectRobotsTxtFile'])
        self.worker.pilot('indeed')
        self.assertEqual(len(self.j.batches()),4)

    def test_search_cycles_google_minimum_and_source_allowance(self):
        self.production()
        self.store.upsert_jobs([{'id':'job'+str(i),'title':'Marketing','company':'Employer '+str(i),'url':'https://employer'+str(i)+'.example/careers'} for i in range(30)])
        for source in ('linkedin','indeed','google'):
            self.j.source(source,due_at=self.now)
        self.worker.schedule(self.now)
        for source in ('linkedin','indeed'):
            batches = [b for b in self.j.batches() if b['source']==source]
            self.assertEqual(len(batches),8)
            self.assertLessEqual(sum(json.loads(b['context_json'])['cap_usd'] for b in batches)*4,8 if source=='linkedin' else 22)
        batches = [b for b in self.j.batches() if b['source']=='google']
        self.assertEqual(len(batches),2)
        queries = [q for b in batches for q in json.loads(b['input_json'])['queries'].splitlines()]
        self.assertEqual(len(queries),40)
        self.assertEqual(len(set(queries)),40)
        for batch in batches:
            self.assertEqual(json.loads(batch['context_json'])['cap_usd'],.5)
            self.assertEqual(json.loads(batch['input_json'])['maxPagesPerQuery'],3)
        self.assertFalse(self.j.reserve(batches[0]['id'],'one',.49,self.worker.owner,self.now)[0])

    def test_career_queue_domain_depth_page_limits_survive_restart(self):
        self.production()
        for domain in range(22):
            for page in range(55 if domain==0 else 1):
                self.queue(f'https://employer{domain}.example/careers/{page}')
        self.queue('https://employer0.example/careers/deep',3)
        self.worker.schedule_careers(self.now,0,seed_rechecks=False)
        batches = [b for b in self.j.batches() if b['source']=='careers']
        self.assertEqual(len(batches),20)
        groups = [json.loads(b['context_json']) for b in batches]
        self.assertEqual(len({g['domain'] for g in groups}),20)
        self.assertEqual(max(len(g['urls']) for g in groups),50)
        self.assertTrue(all(g['cap_usd']==.5 for g in groups))
        restarted = CampaignWorker(self.store,self.api,clock=lambda:self.now)
        restarted.schedule_careers(self.now,0,seed_rechecks=False)
        self.assertEqual(len(self.j.batches()),20)
        with self.store._connection() as c:
            self.assertEqual(c.execute("SELECT state FROM campaign_discovery WHERE depth=3").fetchone()[0],'blocked')
        self.now += DAY+1
        restarted.schedule_careers(self.now,1,seed_rechecks=False)
        self.assertEqual(len(self.j.batches()),22)

    def test_saved_application_recheck_precedes_new_discovery(self):
        self.production()
        self.store.upsert_jobs([{'id':'saved','title':'Marketing Executive','company':'Employer','url':'https://zzz.example/open-position',
                                 'verification':{'last_success_at':'2026-10-23T00:00:00Z'}}])
        self.store.put_application('saved',{'expected_revision':0,'notes':'Keep application'})
        for domain in range(25):
            self.queue(f'https://aaa{domain}.example/careers')
        self.worker.schedule_careers(self.now,0)
        contexts = [json.loads(b['context_json']) for b in self.j.batches()]
        self.assertTrue(any('https://zzz.example/open-position' in c['urls'] for c in contexts))
        self.worker.tick()
        self.assertTrue(json.loads(self.api.launched[0]['context_json'])['priority'])

    def test_returned_links_parent_evidence_and_queue_transitions(self):
        self.production()
        self.queue('https://employer.example/careers')
        self.worker.schedule_careers(self.now,0,seed_rechecks=False)
        batch = self.j.batches()[0]
        item = {'url':'https://employer.example/careers','markdown':'[Vacancy](https://employer.example/jobs/one)',
                'text':'Careers opportunities','crawl':{'httpStatusCode':200}}
        self.worker.import_page(batch,[item],self.now)
        self.worker.import_page(batch,[item],self.now)
        with self.store._connection() as c:
            rows = {r['url']:dict(r) for r in c.execute('SELECT * FROM campaign_discovery')}
            self.assertEqual(rows[item['url']]['state'],'done')
            child = rows['https://employer.example/jobs/one']
            self.assertEqual(child['depth'],1)
            self.assertEqual(json.loads(child['evidence_json'])['parent_batch_id'],batch['id'])
            self.assertEqual(c.execute('SELECT COUNT(*) FROM campaign_items').fetchone()[0],1)
        self.worker.schedule_careers(self.now,0,seed_rechecks=False)
        depth = [json.loads(b['context_json'])['depth'] for b in self.j.batches()]
        self.assertEqual(sorted(depth),[0,1])

    def test_policy_migration_preserves_provider_failures_reservations_and_clock(self):
        self.production()
        before = self.j.current()
        blocked = self.batch('linkedin',input_for('linkedin','Thai'),key='blocked')
        genuine = self.batch('google',input_for('google','Thai'),key='provider')
        self.j.update_batch(blocked['id'],state='blocked',error='Source robots directives disallow this path')
        self.j.update_batch(genuine['id'],state='failed',error='Apify input (HTTP 400)')
        self.queue('https://employer.example/careers')
        with self.store._connection(write=True) as c:
            c.execute("UPDATE campaign_discovery SET state='blocked',reason='Official crawler redirect/private-network isolation is not verified.'")
        self.worker.repair_removed_policy(self.now)
        rows = {b['batch_key']:b for b in self.j.batches()}
        self.assertEqual(rows['blocked']['state'],'superseded')
        self.assertEqual(rows['provider']['state'],'failed')
        self.assertEqual(self.j.current()['stops_at'],before['stops_at'])
        with self.store._connection() as c:
            self.assertEqual(c.execute('SELECT state FROM campaign_discovery').fetchone()[0],'queued')
        self.assertEqual(len(self.store.get_meta('campaign_policy_correction_v2')['superseded_observations']),2)
        self.worker.repair_removed_policy(self.now+1)
        self.assertEqual(len(self.store.get_meta('campaign_policy_correction_v2')['superseded_observations']),2)

    def test_old_career_proxy_payload_is_preserved_and_corrected_replacement_is_durable(self):
        self.production()
        old = self.batch('careers',input_for('careers','https://example.org/jobs'),{'cap_usd':.5,'domain':'example.org','depth':0,'urls':['https://example.org/jobs']},key='old')
        with self.store._connection(write=True) as c:
            c.execute("UPDATE campaign_batches SET state='failed',reserved_units=?,reserved_at=?,error='Apify input (HTTP 400)' WHERE id=?",(units(.5),self.now,old['id']))
        # Recreate the legacy payload exactly as the earlier build emitted it.
        with self.store._connection(write=True) as c:
            payload=json.loads(old['input_json']);payload['proxyConfiguration']={'useApifyProxy':False}
            c.execute('UPDATE campaign_batches SET input_json=? WHERE id=?',(json.dumps(payload),old['id']))
        self.worker.repair_career_inputs(self.now)
        rows=self.j.batches();replacement=next(b for b in rows if b['batch_key']=='old:proxy-v1')
        self.assertEqual(next(b for b in rows if b['id']==old['id'])['state'],'failed')
        self.assertTrue(json.loads(replacement['input_json'])['proxyConfiguration']['useApifyProxy'])
        self.worker.repair_career_inputs(self.now+1)
        self.assertEqual(len([b for b in self.j.batches() if b['batch_key']=='old:proxy-v1']),1)

    def test_named_crawler_errors_are_checkpointed_and_classified(self):
        self.production()
        url = 'https://employer.example/careers'
        self.queue(url)
        self.worker.schedule_careers(self.now,0,seed_rechecks=False)
        batch = self.j.batches()[0]
        self.assertTrue(self.j.reserve(batch['id'],'one',.5,self.worker.owner,self.now)[0])
        self.j.update_batch(batch['id'],state='running',run_id='run1',dataset_id='dataset1')
        self.api.remote.update(status='SUCCEEDED',usageTotalUsd=.03,storageIds={'datasets':{'errors':'errors1'}})
        raw = {'url':url,'httpStatus':403,'errorCode':'HTTP_STATUS_403','errorExplanation':'Provider denied this page','debug':{'rawErrorMessage':'Exact raw response'}}
        self.api.items = lambda ref,dataset,offset:[raw] if dataset=='errors1' and offset==0 else []
        self.worker.poll(self.j.batches()[0],self.now)
        self.assertEqual(self.j.batches()[0]['state'],'importing')
        restarted = CampaignWorker(self.store,self.api,clock=lambda:self.now)
        restarted.poll(self.j.batches()[0],self.now)
        batch = self.j.batches()[0]
        self.assertEqual(batch['state'],'done')
        self.assertEqual(batch['error_category'],'source_access')
        self.assertEqual(batch['checkpoint'],0)
        with self.store._connection() as c:
            row = c.execute('SELECT * FROM campaign_items').fetchone()
            self.assertEqual(row['item_index'],-1)
            self.assertEqual(json.loads(row['payload_json']),raw)
            self.assertEqual(c.execute('SELECT state FROM campaign_discovery').fetchone()[0],'failed')

    def test_deadline_stops_paid_work_and_finishes_imports_after_restart(self):
        self.production()
        batch = self.batch('indeed',input_for('indeed','Thai'))
        self.assertTrue(self.j.reserve(batch['id'],'one',.5,self.worker.owner,self.now)[0])
        self.j.update_batch(batch['id'],state='running',run_id='run1',dataset_id='dataset1')
        self.now += 7*DAY+1
        worker = CampaignWorker(self.store,self.api,clock=lambda:self.now)
        worker.tick()
        self.assertEqual(self.api.aborted,['run1'])
        self.api.remote.update(status='ABORTED',usageTotalUsd=.1,finishedAt=iso(self.now))
        worker.tick()
        self.assertEqual(self.j.current()['state'],'stopped')
        self.assertEqual(self.j.batches()[0]['state'],'failed')
        self.assertEqual(self.j.status(self.now)['reported_run_charges_usd'],.1)
        self.assertEqual(self.api.launched,[])


if __name__=='__main__':
    unittest.main()
