"""Retained lead recovery keeps evidence, budgets, dates and applications intact."""
import json
import unittest
from unittest.mock import patch

from test_campaign_scheduler_v2 import SchedulerTests
from campaign import CampaignWorker, iso
from campaign_sources import input_for
from campaign_store import encode


class LocalityRecoveryTests(SchedulerTests):
    # Reuse only setup/helpers, not the parent's collected test methods.
    def test_retained_leads_recover_in_pages_and_survive_restart(self):
        self.production()
        self.worker.last_accounts = self.now
        batch = self.batch('indeed',input_for('indeed','Marketing Executive'),{'cap_usd':.5})
        items = [{'id':'local-'+str(i),'positionName':'Marketing Executive '+str(i),'company':'Employer',
                  'url':'https://sg.indeed.com/viewjob?jk=local-'+str(i),'location':'Geylang',
                  'description':'Responsibilities\nManage social media content and marketing events.',
                  'scrapedAt':iso(self.now-10),'postingDateParsed':'2026-10-20'} for i in range(102)]
        items += [{**items[0],'id':'remote','url':'https://sg.indeed.com/viewjob?jk=remote','location':'Remote'}]
        with patch('campaign.normalize',return_value=None):
            self.worker.import_page(batch,items,self.now-10)
        with self.store._connection(write=True) as c:
            c.execute("UPDATE campaign_batches SET state='done',reserved_at=?,finished_at=?,charge_units=20000,reserved_units=500000 WHERE id=?",
                      (self.now-20,self.now-5,batch['id']))
        before = self.j.batches()[0]
        self.worker.repair_locality_leads(self.now)
        self.assertEqual(self.store.get_meta('campaign_locality_recovery_v2')['promoted'],100)
        self.assertFalse(self.store.get_meta('campaign_locality_recovery_v2')['complete'])
        restarted = CampaignWorker(self.store,self.api,clock=lambda:self.now+30)
        restarted.repair_locality_leads(self.now+30)
        self.assertTrue(self.store.get_meta('campaign_locality_recovery_v2')['complete'])
        self.assertEqual(self.store.get_meta('campaign_locality_recovery_v2')['promoted'],102)
        restarted.repair_locality_leads(self.now+60)
        after = self.j.batches()[0]
        for key in ('checkpoint','reserved_at','finished_at','charge_units','reserved_units','state','run_id','input_json','context_json'):
            self.assertEqual(after[key],before[key],key)
        self.assertEqual((after['new_count'],after['lead_count']),(102,1))
        with self.store._connection() as c:
            self.assertEqual([json.loads(r[0]) for r in c.execute('SELECT payload_json FROM campaign_items ORDER BY item_index')],items)
            self.assertEqual(c.execute('SELECT COUNT(*) FROM source_evidence').fetchone()[0],102)
            self.assertEqual(c.execute('SELECT COUNT(*) FROM jobs').fetchone()[0],102)
        for job in self.store.list_jobs():
            self.assertEqual(job['discovered_at'],iso(self.now-10))
            self.assertEqual(job['verification']['last_success_at'],iso(self.now-10))
            self.assertEqual(job['posted_at'],'2026-10-20')

    def test_recovery_preserves_newer_facts_existing_id_and_application(self):
        self.production()
        item = {'id':'old','positionName':'Old Marketing Role','company':'Employer','location':'Outram',
                'url':'https://sg.indeed.com/viewjob?jk=old','description':'Old retained responsibilities for marketing events.'}
        batch = self.batch('indeed',input_for('indeed','Thai'),{'cap_usd':.5})
        with patch('campaign.normalize',return_value=None):
            self.worker.import_page(batch,[item],self.now-100)
        with self.store._connection(write=True) as c:
            c.execute("UPDATE campaign_batches SET state='done',reserved_at=?,finished_at=? WHERE id=?",(self.now-100,self.now-90,batch['id']))
        job = {'id':'stable','title':'Newer Marketing Role','company':'Employer','url':item['url'],
               'description':'Newer source description.','location':'Singapore','sources':[],
               'verification':{'last_success_at':iso(self.now)},'discovered_at':iso(self.now-200)}
        self.store.upsert_jobs([job])
        self.store.put_application('stable',{'expected_revision':0,'notes':'Preserve my notes','drafts':{'cover_letter':'My original draft'}})
        with self.store._connection() as c:
            tables={'applications':[tuple(r) for r in c.execute('SELECT * FROM applications')]}
        self.worker.repair_locality_leads(self.now+1)
        kept = self.store.list_jobs()[0]
        self.assertEqual((kept['id'],kept['title'],kept['description']),('stable','Newer Marketing Role','Newer source description.'))
        self.assertEqual(kept['verification'],job['verification'])
        with self.store._connection() as c:
            for name,rows in tables.items():
                self.assertEqual([tuple(r) for r in c.execute('SELECT * FROM '+name)],rows)
            self.assertEqual(c.execute('SELECT job_id,outcome FROM campaign_items').fetchone()[:],('stable','duplicate'))


# unittest inherits test methods; keep this module scoped to recovery coverage.
for name in dir(SchedulerTests):
    if name.startswith('test_') and name not in LocalityRecoveryTests.__dict__:
        setattr(LocalityRecoveryTests,name,None)

if __name__ == '__main__':
    unittest.main()
