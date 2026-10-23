"""Explicit isolated campaign regressions. No credential or live API access."""
import copy
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from campaign import CampaignWorker, iso
from campaign_apify import ApiError
from campaign_apify import Apify
from campaign_sources import (AccessBlocked, canonical_url, public_addresses, check_robots,
    input_for, validate_input, queries)
from campaign_store import CampaignStore, DAY, units
from storage import Store


class FakeApi:
    def __init__(self):
        self.launched=[]; self.aborted=[]; self.match=None; self.launch_error=None
        self.remote={'id':'run1','status':'RUNNING','defaultDatasetId':'data1'}
        self.pages={0:[{'jobKey':'abc','positionName':'Marketing Executive','company':'Employer',
            'url':'https://sg.indeed.com/viewjob?jk=abc','location':'Singapore',
            'description':'Responsibilities\nManage social media content.\nRequirements\nDegree in Marketing.'}]}
    def snapshot(self,ref):
        return {'account_id':ref,'reference':ref,'usage_usd':0,'limit_usd':100,'cycle':{'start':'a','end':'b'},'available':True}
    def snapshots(self): return [self.snapshot('one'),self.snapshot('two'),self.snapshot('three')]
    def contract(self,*args): return {}
    def launch(self,ref,batch,stops,now):
        self.launched.append((ref,batch,stops,now))
        if self.launch_error: raise self.launch_error
        return self.remote.copy()
    def reconcile(self,*args): return self.match
    def run(self,*args): return self.remote.copy()
    def abort(self,ref,rid): self.aborted.append(rid)
    def items(self,ref,dataset,offset): return copy.deepcopy(self.pages.get(offset,[]))


class CampaignTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.store=Store(Path(self.temp.name)/'test.sqlite3').initialize()
        self.now=1800000000.0
        self.api=FakeApi()
        self.worker=CampaignWorker(self.store,self.api,access=lambda u:{'allowed':True},clock=lambda:self.now)
        self.j=self.worker.journal
        self.j.create(self.now);self.worker.refresh_accounts(self.now);self.j.state('pilot')
        self.j.claim(self.worker.owner,self.now)
        self.network=patch('requests.request',side_effect=AssertionError('Live network forbidden'));self.network.start()

    def tearDown(self):
        self.network.stop();self.temp.cleanup()

    def enqueue(self,key='q',amount=.2,source='indeed'):
        self.j.enqueue(source,key,input_for(source,'Marketing Executive',10),{'cap_usd':amount},self.now)
        return next(b for b in self.j.batches() if b['batch_key']==key)

    def reserve(self,b,account='one',amount=.2):
        return self.j.reserve(b['id'],account,amount,self.worker.owner,self.now)

    def production(self):
        with self.store._connection(write=True) as c:
            c.execute("UPDATE campaigns SET mode='production',state='active',started_at=?,stops_at=?",(self.now,self.now+7*DAY))
        self.store.set_meta('campaign_validated_sources',['indeed'])

    def test_clock_starts_at_first_committed_launch_not_preparation(self):
        self.assertIsNone(self.j.current()['stops_at'])
        b=self.enqueue();self.assertTrue(self.reserve(b)[0])
        first=self.j.current()['started_at'];self.now+=60
        self.j.state('paused');self.j.state('pilot')
        self.assertEqual(self.j.current()['started_at'],first)
        self.assertEqual(self.j.current()['stops_at'],first+7*DAY)
        with self.assertRaises(ValueError):self.j.create(self.now)

    def test_concurrent_reservations_cannot_exceed_global_or_account_limits(self):
        batches=[self.enqueue(str(n)) for n in range(12)]
        with ThreadPoolExecutor(max_workers=12) as pool:
            results=list(pool.map(lambda pair:self.reserve(pair[1],['one','two','three'][pair[0]%3]),enumerate(batches)))
        self.assertEqual(sum(r[0] for r in results),2)
        self.assertEqual(len({b['account_id'] for b in self.j.batches(('launching',))}),2)

    def test_pilot_cap_includes_reservations_and_ancillary(self):
        b=self.enqueue(amount=2);self.assertTrue(self.reserve(b,amount=2)[0])
        self.j.update_batch(b['id'],state='done',finished_at=self.now,charge_units=units(.1))
        b=self.enqueue('second',amount=1)
        self.assertFalse(self.reserve(b,amount=1)[0])
        s=self.api.snapshot('one');s['usage_usd']=3;self.j.account(s,self.now)
        self.assertFalse(self.reserve(b,amount=.1)[0])

    def test_completed_cap_stays_committed_and_unresolved_cap_never_ages_out(self):
        self.production();b=self.enqueue(amount=2);self.reserve(b,amount=2)
        self.j.update_batch(b['id'],state='ambiguous')
        status=self.j.status(self.now+2*DAY)
        self.assertEqual(status['rolling_actor_committed_usd'],2)
        self.j.update_batch(b['id'],state='done',finished_at=self.now,charge_units=units(.01))
        status=self.j.status(self.now+DAY+1)
        self.assertEqual(status['rolling_actor_committed_usd'],0)
        self.assertEqual(status['actor_committed_usd'],2)

    def test_rolling_source_and_total_limits(self):
        self.production()
        for n in range(4):
            b=self.enqueue(str(n),2,'linkedin');self.assertTrue(self.reserve(b,amount=2)[0]);self.j.update_batch(b['id'],state='done',finished_at=self.now)
        b=self.enqueue('fifth',.1,'linkedin');self.assertFalse(self.reserve(b,amount=.1)[0])
        with self.store._connection(write=True) as c:
            c.execute('UPDATE campaign_batches SET reserved_units=? WHERE reserved_at IS NOT NULL',(units(12),))
        self.assertIn('Rolling',self.reserve(self.enqueue('indeed'),account='two')[1])
        with self.store._connection(write=True) as c:
            c.execute('UPDATE campaign_batches SET reserved_units=? WHERE reserved_at IS NOT NULL',(units(80),))
        self.assertIn('Campaign budget',self.reserve(self.enqueue('last'),account='two')[1])

    def test_stale_exhausted_cycle_changed_and_unavailable_account(self):
        b=self.enqueue();self.now+=301;self.j.claim(self.worker.owner,self.now)
        self.assertIn('stale',self.reserve(b)[1]);self.worker.refresh_accounts(self.now);self.j.claim(self.worker.owner,self.now)
        s=self.api.snapshot('one');s['limit_usd']=.2;self.j.account(s,self.now)
        self.assertIn('exhausted',self.reserve(b)[1])
        s['cycle']={'start':'new'};self.j.account(s,self.now)
        self.assertIn('unresolved',self.reserve(b,'two')[1])

    def test_restart_reconciles_ambiguous_launch_without_relaunch(self):
        b=self.enqueue();self.api.launch_error=ApiError('ambiguous_write')
        self.worker.tick();self.assertEqual(len(self.api.launched),1)
        self.now+=301
        worker=CampaignWorker(self.store,self.api,access=lambda u:{'allowed':True},clock=lambda:self.now)
        self.api.match=self.api.remote.copy();worker.tick()
        self.assertEqual(len(self.api.launched),1)
        self.assertEqual(self.j.batches()[0]['run_id'],'run1')

    def test_unresolved_launch_retains_reservation_and_blocks_account(self):
        b=self.enqueue();self.reserve(b)
        self.worker.poll(self.j.batches()[0],self.now)
        self.assertEqual(self.j.batches()[0]['state'],'ambiguous')
        self.assertEqual(self.j.status()['actor_committed_usd'],.2)
        self.assertFalse(self.reserve(self.enqueue('another'))[0])

    def test_pilot_import_isolated_idempotent_and_checkpointed(self):
        b=self.enqueue();self.reserve(b);b=self.j.batches()[0]
        self.worker.import_page(b,self.api.pages[0],self.now)
        self.worker.import_page(b,self.api.pages[0],self.now)
        self.assertEqual(self.store.count_jobs(),0)
        with self.store._connection() as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM campaign_pilot_jobs').fetchone()[0],1)
            self.assertEqual(c.execute('SELECT COUNT(*) FROM campaign_items').fetchone()[0],1)
        self.assertEqual(self.j.batches()[0]['checkpoint'],1)

    def test_partial_payload_keeps_identity_fields_provenance_and_application(self):
        self.production();b=self.enqueue();self.reserve(b);b=self.j.batches()[0]
        self.worker.import_page(b,self.api.pages[0],self.now)
        job=self.store.list_jobs()[0]
        self.store.put_application(job['id'],{'expected_revision':0,'notes':'Original notes','drafts':{'cover_letter':'Original draft'}})
        before=self.store.get_application(job['id'])
        new=copy.deepcopy(self.api.pages[0][0]);new.pop('description')
        b2=self.enqueue('next');self.reserve(b2,'two');b2=next(x for x in self.j.batches() if x['id']==b2['id'])
        self.now+=1;self.worker.import_page(b2,[new],self.now)
        current=self.store.get_job(job['id'])
        self.assertEqual(current['description'],job['description'])
        self.assertEqual(current['field_provenance']['description'],job['field_provenance']['description'])
        self.assertEqual(current['discovered_at'],job['discovered_at'])
        self.assertEqual(self.store.get_application(job['id']),before)
        self.assertEqual(self.store.count_jobs(),1)
        self.assertEqual(len(self.store.get_source_evidence(job['id'])),2)

    def test_transaction_failure_rolls_back_items_jobs_and_checkpoint(self):
        self.production();b=self.enqueue();self.reserve(b);b=self.j.batches()[0]
        with patch('campaign.merge_job',side_effect=RuntimeError('crash')):
            with self.assertRaises(RuntimeError):self.worker.import_page(b,self.api.pages[0],self.now)
        self.assertEqual(self.store.count_jobs(),0)
        self.assertEqual(self.j.batches()[0]['checkpoint'],0)

    def test_search_snippets_and_non_singapore_records_are_only_leads(self):
        self.production();b=self.enqueue();self.reserve(b);b=self.j.batches()[0]
        item=copy.deepcopy(self.api.pages[0][0]);item['location']='London'
        self.worker.import_page(b,[item],self.now)
        self.assertEqual(self.store.count_jobs(),0);self.assertEqual(self.j.batches()[0]['lead_count'],1)

    def test_seven_day_shutdown_aborts_and_imports_obtained_results(self):
        b=self.enqueue();self.reserve(b);self.j.update_batch(b['id'],state='running',run_id='run1',dataset_id='data1')
        self.now+=7*DAY+1;self.worker.tick()
        self.assertEqual(self.j.current()['state'],'stopped');self.assertEqual(self.api.aborted,['run1'])
        self.api.remote.update(status='ABORTED',usageTotalUsd=.05)
        self.worker.tick();self.worker.tick()
        self.assertEqual(self.j.batches()[0]['state'],'failed')
        self.assertEqual(self.j.batches()[0]['checkpoint'],1)
        self.assertEqual(self.api.launched,[])

    def test_low_disk_pauses_admissions_without_losing_work(self):
        self.enqueue()
        with patch('campaign.disk_capacity',return_value={'safe':False}):self.worker.tick()
        self.assertEqual(self.j.current()['state'],'paused');self.assertEqual(self.api.launched,[])

    def test_access_failure_has_explicit_status_without_charge(self):
        self.enqueue();self.worker.access=lambda u:(_ for _ in ()).throw(AccessBlocked('robots disallow'))
        self.worker.tick();self.assertEqual(self.j.batches()[0]['state'],'blocked')
        self.assertEqual(self.j.status()['actor_committed_usd'],0)

    def test_discovery_cycles_and_depth_limit(self):
        cid=self.j.current()['id']
        with self.store._connection(write=True) as c:
            for i in range(3):self.worker.discover(c,cid,'https://example.org/careers','https://example.org/jobs',1,None,{},self.now)
            self.worker.discover(c,cid,'https://example.org/jobs/123','https://example.org/careers',3,None,{},self.now)
        with self.store._connection() as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM campaign_discovery').fetchone()[0],2)
            self.assertEqual(c.execute('SELECT COUNT(*) FROM campaign_edges').fetchone()[0],2)
            self.assertEqual(c.execute("SELECT state FROM campaign_discovery WHERE depth=3").fetchone()[0],'blocked')

    def test_backup_restores_all_campaign_tables_and_unchanged_applications(self):
        b=self.enqueue();self.reserve(b)
        path=Path(self.temp.name)/'backup.sqlite3';self.store.backup(path)
        result=Store.restore_backup(path,Path(self.temp.name)/'restore.sqlite3')
        self.assertIn('campaign_batches',result['digests']);self.assertEqual(result['counts']['campaign_batches'],1)

    def test_contracts_use_current_limits_and_rotate_queries(self):
        for source in ('linkedin','indeed','google','careers'):
            payload=input_for(source,'https://example.org/careers' if source=='careers' else 'Thai')
            validate_input(source,payload)
        self.assertEqual(queries(0)[:4],queries(1)[:4]);self.assertNotEqual(queries(0)[4:],queries(1)[4:])
        with self.assertRaises(ValueError):validate_input('indeed',input_for('indeed','Thai',101))


class URLTests(unittest.TestCase):
    def test_unsafe_urls(self):
        for url in ['file:///etc/passwd','http://127.0.0.1/a','http://169.254.169.254/x','http://[::1]/','http://user:pass@example.org','http://localhost/','http://example.local/','https://example.org:8080/','https://example.org\\@127.0.0.1/']:
            with self.subTest(url=url),self.assertRaises(AccessBlocked):canonical_url(url)
        self.assertEqual(canonical_url('https://example.org/jobs?utm_source=a&id=1#x'),'https://example.org/jobs?id=1')

    def test_private_dns_and_mixed_answer_rejected(self):
        with patch('socket.getaddrinfo',return_value=[(2,1,6,'',('93.184.216.34',443)),(2,1,6,'',('127.0.0.1',443))]):
            with self.assertRaises(AccessBlocked):public_addresses('example.org')

    def test_robots_denial_unknown_and_delay(self):
        for status,text in [(200,'User-agent: *\nDisallow: /jobs'),(403,''),(200,'User-agent: *\nCrawl-delay: 5')]:
            with self.assertRaises(AccessBlocked):check_robots('https://example.org/jobs',lambda u:(u,status,text))
        self.assertTrue(check_robots('https://example.org/jobs',lambda u:(u,404,''))['allowed'])

    def test_native_run_cap_timeout_and_no_automatic_restart(self):
        api=Apify(['test-token'])
        batch={'source':'indeed','input_json':json.dumps(input_for('indeed','Thai',10)),'reserved_units':units(.2)}
        with patch.object(api,'request',return_value={'data':{'id':'one'}}) as request:
            api.launch(next(iter(api.tokens)),batch,1020,1000)
            params=request.call_args.kwargs['params']
            self.assertEqual(params['timeout'],15);self.assertEqual(params['maxTotalChargeUsd'],.2)
            self.assertEqual(params['restartOnError'],'false')
        with self.assertRaises(ApiError):api.launch(next(iter(api.tokens)),batch,1002,1000)


class CampaignAPITests(unittest.TestCase):
    def test_authenticated_status_pause_and_discovery_order(self):
        import os
        import app as web
        from fastapi.testclient import TestClient
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'api.sqlite3';store=Store(path).initialize();store.set_meta('seed_version',2)
            old_path=web.app.state.database_path;web.app.state.database_path=path
            auth=(web.AUTH_USERNAME,web.AUTH_PASSWORD)
            try:
                with patch.dict(os.environ,{'DISABLE_BACKGROUND_SYNC':'1','APIFY_TOKENS_JSON':'[]'}),TestClient(web.app) as client:
                    for url in ('/api/campaign','/api/campaign/report','/api/campaign/pilot-evidence','/api/campaign/leads'):
                        self.assertEqual(client.get(url).status_code,401)
                        self.assertEqual(client.get(url,auth=auth).status_code,200)
                    self.assertEqual(client.post('/api/campaign/pause').status_code,401)
                    self.assertEqual(client.post('/api/campaign/pause',auth=auth,headers={'Origin':'https://evil.example'}).status_code,403)
                    journal=CampaignStore(store);journal.create();journal.state('pilot')
                    self.assertEqual(client.post('/api/campaign/pause',auth=auth).json()['state'],'paused')
                    self.assertEqual(client.post('/api/campaign/activate',auth=auth,json={'pilot_verified':True,'evidence_reference':'test'}).status_code,409)
                    self.assertEqual(client.get('/api/jobs?sort_by=discovered',auth=auth).status_code,200)
            finally:web.app.state.database_path=old_path


if __name__=='__main__':unittest.main()
