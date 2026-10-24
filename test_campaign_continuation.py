"""Continuation API/accounting regressions against disposable storage."""
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
import app as web
from campaign_store import CampaignStore, units, DAY
from campaign_sources import input_for
from storage import Store


class ContinuationTests(unittest.TestCase):
    def test_existing_schema_three_gets_additive_error_category_migration(self):
        path=Path(self.temp.name)/'old.sqlite3'
        store=Store(path).initialize()
        with store._connection(write=True) as c:
            c.execute('ALTER TABLE campaign_batches DROP COLUMN error_category')
            c.execute('PRAGMA user_version=3')
        store.initialize()
        with store._connection() as c:
            self.assertEqual(c.execute('PRAGMA user_version').fetchone()[0],4)
            self.assertIn('error_category',[r[1] for r in c.execute('PRAGMA table_info(campaign_batches)')])
        journal=CampaignStore(store);journal.create();journal.status()
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.path=Path(self.temp.name)/'test.sqlite3'
        self.store=Store(self.path).initialize();self.store.set_meta('seed_version',2)
        self.old=web.app.state.database_path;web.app.state.database_path=self.path
        self.env=patch.dict(os.environ,{'DISABLE_BACKGROUND_SYNC':'1','APIFY_TOKENS_JSON':'[]'})
        self.env.start();self.client=TestClient(web.app);self.client.__enter__()
        self.auth=(web.AUTH_USERNAME,web.AUTH_PASSWORD)
        self.j=CampaignStore(self.store);self.now=time.time();self.j.create(self.now)
        with self.store._connection(write=True) as c:
            c.execute("UPDATE campaigns SET mode='production',state='active',started_at=?,stops_at=?",(self.now,self.now+7*DAY))
        self.store.set_meta('campaign_validated_sources',['indeed'])
        self.worker=web.app.state.campaign_worker
        self.network=patch('requests.request',side_effect=AssertionError('Network forbidden'));self.network.start()

    def tearDown(self):
        self.network.stop();self.client.__exit__(None,None,None);self.env.stop()
        web.app.state.database_path=self.old;self.temp.cleanup()

    def post(self,path,payload=None):
        return self.client.post('/api/campaign/'+path,auth=self.auth,**({'json':payload} if payload is not None else {}))

    def completed(self,source,pilot,item,amount=.1):
        query=['https://employer.example/jobs/one'] if source=='careers' else 'Marketing Executive'
        key=('pilot:' if pilot else 'cycle:')+source
        self.j.enqueue(source,key,input_for(source,query,10),{'pilot':pilot,'cap_usd':.5},self.now)
        batch=next(b for b in self.j.batches() if b['batch_key']==key)
        self.j.update_batch(batch['id'],state='done',remote_status='SUCCEEDED',charge_units=units(amount),finished_at=self.now)
        with self.store._connection(write=True) as c:
            c.execute('UPDATE campaign_batches SET reserved_units=?,reserved_at=?,new_count=?,lead_count=? WHERE id=?',
                (units(.5),self.now,int(source!='google'),int(source=='google'),batch['id']))
            c.execute('INSERT INTO campaign_items VALUES(?,?,?,?,?)',(batch['id'],0,json.dumps(item),'job-'+source if source!='google' else None,'lead' if source=='google' else 'new'))
        self.store.set_meta('campaign_contract_'+source,{'verified':True})
        return batch

    def test_source_pilots_do_not_change_production_or_clock_and_are_idempotent(self):
        original=self.j.current()
        for source in ['linkedin','google','careers']:
            payload={'source':source}
            if source=='careers':payload['urls']=['http://127.0.0.1:8080/jobs']
            self.assertEqual(self.post('pilot',payload).status_code,200)
            self.assertEqual(self.post('pilot',payload).status_code,200)
        self.assertEqual(self.post('pilot').status_code,200) # Existing Indeed caller.
        current=self.j.current()
        self.assertEqual([(current[k],original[k]) for k in ['state','mode','started_at','stops_at']],[(original[k],original[k]) for k in ['state','mode','started_at','stops_at']])
        self.assertEqual(len(self.j.batches()),4)
        self.assertEqual(self.post('pilot',{'source':'unknown'}).status_code,409)

    def test_google_activation_uses_search_evidence_and_preserves_enabled_sources(self):
        web.verified_backup(self.store)
        self.completed('google',True,{'organicResults':[{'url':'https://company.example/careers','title':'Careers'}]})
        with self.store._connection(write=True) as c:
            c.execute('INSERT INTO campaign_usage(campaign_id,account_id,observed_at,delta_units) VALUES(?,?,?,?)',(self.j.current()['id'],'one',self.now,units(.1)))
        with patch.object(self.worker,'refresh_accounts',return_value=True):
            response=self.post('activate',{'source':'google','pilot_verified':True,'evidence_reference':'isolated fixture'})
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(self.store.get_meta('campaign_validated_sources'),['google','indeed'])
        self.assertEqual(self.j.current()['mode'],'production')
        self.assertEqual(self.post('activate',{'source':'careers','pilot_verified':True,'evidence_reference':'missing'}).status_code,409)

    def test_google_snippet_leads_are_paginated_isolated_and_inspectable(self):
        payload={'organicResults':[{'url':'https://company.example/careers','title':'Careers','description':'Search evidence'}],'searchQuery':{'url':'https://google.com/search?q=careers'}}
        self.completed('google',True,payload)
        production=self.completed('google',False,payload)
        r=self.client.get('/api/campaign/leads?source=google&pilot=false&limit=1',auth=self.auth)
        self.assertEqual(r.status_code,200);result=r.json();self.assertEqual(result['total'],1)
        self.assertEqual(result['items'][0]['payload'],payload)
        self.assertTrue(result['items'][0]['id'].startswith(production['id']))
        self.assertFalse(result['items'][0]['pilot'])
        self.assertEqual(self.client.get('/api/campaign/leads?pilot=true',auth=self.auth).json()['total'],1)
        status=self.j.status();self.assertEqual(status['production_counts']['lead_count'],1)
        self.assertEqual(status['pilot_counts']['lead_count'],1)

    def test_supplemental_reservations_keep_original_pilot_cap(self):
        self.j.claim('owner',self.now)
        self.j.account({'account_id':'one','reference':'one','usage_usd':0,'limit_usd':100,'cycle':{},'available':True},self.now)
        for index in range(5):
            self.j.enqueue('careers','pilot:'+str(index),input_for('careers','https://example.com/jobs'),{'pilot':True,'cap_usd':.5},self.now)
            batch=next(b for b in self.j.batches() if b['batch_key']=='pilot:'+str(index))
            self.assertTrue(self.j.reserve(batch['id'],'one',.5,'owner',self.now)[0])
            self.j.update_batch(batch['id'],state='done',finished_at=self.now,charge_units=0)
        self.j.enqueue('google','pilot:google',input_for('google','careers'),{'pilot':True,'cap_usd':.5},self.now)
        batch=next(b for b in self.j.batches() if b['batch_key']=='pilot:google')
        ok,reason=self.j.reserve(batch['id'],'one',.5,'owner',self.now)
        self.assertFalse(ok);self.assertIn('original pilot allowance',reason)

    def test_google_minimum_cap_is_transactional(self):
        self.j.claim('owner',self.now)
        self.j.account({'account_id':'one','reference':'one','usage_usd':0,'limit_usd':100,'cycle':{},'available':True},self.now)
        self.j.enqueue('google','google',input_for('google','careers'),{'cap_usd':.49},self.now)
        batch=self.j.batches()[0]
        self.assertIn('minimum',self.j.reserve(batch['id'],'one',.49,'owner',self.now)[1])
        self.assertEqual(self.j.status()['actor_committed_usd'],0)


if __name__=='__main__':unittest.main()
