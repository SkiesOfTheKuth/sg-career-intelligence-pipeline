"""Single-service campaign owner, restart recovery, scheduling and imports.

There is no desktop dependency, remote cron, or Apify schedule. FastAPI lifespan
owns this worker; SQLite records everything needed to resume after interruption.
"""
import asyncio
from datetime import datetime, timezone
import hashlib
import json
import logging
import shutil
import time
from urllib.parse import urlsplit
import uuid

from campaign_apify import Apify, ApiError
from campaign_sources import (CONTRACTS, CORE, HISTORICAL, NAMES, AccessBlocked,
    access_url, canonical_url, check_robots, input_for, merge_job, normalize,
    queries, relevant_career_url, validate_input)
from campaign_store import CampaignStore, DAY, ACTIVE, encode, units
from evidence import source_key, salary_presentation

logger = logging.getLogger(__name__)
TERMINAL = {'SUCCEEDED','FAILED','ABORTED','TIMED-OUT'}


def iso(now):
    return datetime.fromtimestamp(now,timezone.utc).isoformat()


def disk_capacity(store):
    usage = shutil.disk_usage(store.path.parent)
    database = sum(p.stat().st_size for p in store.path.parent.glob(store.path.name+'*') if p.is_file())
    # Keep room for three retained backups, a new backup, restoration, WAL and
    # application writes. Never expand a disk from inside the application.
    required = max(256*1024*1024, database*3 + 128*1024*1024)
    return {'free_bytes':usage.free,'database_bytes':database,'required_free_bytes':required,
            'safe':usage.free >= required}


class CampaignWorker:
    def __init__(self, store, api=None, access=check_robots, clock=time.time):
        self.store, self.journal = store, CampaignStore(store)
        try:
            self.api = api if api is not None else Apify()
        except (ValueError,TypeError):
            # A malformed collection secret cannot take the private workspace
            # or its independent free MCF scheduler offline.
            self.api = Apify([])
            store.set_meta('campaign_account_error','Invalid APIFY_TOKENS_JSON configuration; paid collection is unavailable.')
        self.access, self.clock = access, clock
        self.owner = uuid.uuid4().hex
        self.last_accounts = 0
        self.contracts = {}
        self.mutation_lock = asyncio.Lock()

    def refresh_accounts(self, now):
        snapshots = self.api.snapshots()
        errors = [r['error'] for r in snapshots if r.get('error')]
        seen = set()
        for row in snapshots:
            if not row.get('error') and row['account_id'] not in seen:
                seen.add(row['account_id'])
                self.journal.account(row, now)
        error = '; '.join(sorted(set(errors))) if errors else None
        self.store.set_meta('campaign_account_error',error or ('No account credentials configured.' if not snapshots else None))
        self.last_accounts = now
        return not errors and bool(snapshots)

    def prepare(self):
        campaign = self.journal.current() or self.journal.create(self.clock())
        self.refresh_accounts(self.clock())
        return self.journal.status()

    def pilot(self):
        if not self.journal.current():
            self.prepare()
        now = self.clock()
        # One bounded Indeed search checks current schema, location, exact text,
        # identity and billing in isolated tables. Other eligible actors receive
        # their own pilot before activation; inaccessible actors remain blocked.
        payload = input_for('indeed','Marketing Executive',10)
        self.journal.enqueue('indeed','pilot:indeed',payload,{'query':'Marketing Executive','pilot':True,'cap_usd':.20},now)
        self.journal.state('pilot')
        return self.journal.status()

    def discover(self, c, cid, url, parent, depth, root, evidence, now):
        try:
            url = canonical_url(url)
        except AccessBlocked:
            return
        if parent:
            c.execute('INSERT OR IGNORE INTO campaign_edges VALUES(?,?,?,?)', (cid,parent,url,encode(evidence)))
        if not relevant_career_url(url, str(evidence.get('title',''))):
            return
        reason = None
        if depth > 2:
            reason = 'Maximum discovery depth reached'
        host = urlsplit(url).hostname
        if host == 'cultjobs.com' or host.endswith('.cultjobs.com'):
            reason = 'Cultjobs consent requirement remains unresolved'
        c.execute('''INSERT OR IGNORE INTO campaign_discovery VALUES(?,?,?,?,?,?,?,?,?,?,?)''',
                  (cid,url,host,parent,root or url,depth,'blocked' if reason else 'queued',now,None,encode(evidence),reason))

    def import_page(self, batch, items, now):
        cid = batch['campaign_id']
        campaign = self.journal.current()
        pilot = campaign['mode']=='pilot' or json.loads(batch['context_json']).get('pilot',False)
        with self.store._connection(write=True) as c:
            current = c.execute('SELECT checkpoint FROM campaign_batches WHERE id=?',(batch['id'],)).fetchone()[0]
            if current != batch['checkpoint']:
                return  # A replayed page cannot move the checkpoint backwards.
            originals = [json.loads(r[0]) for r in c.execute('SELECT data_json FROM jobs')]
            if pilot:
                originals += [json.loads(r[0]) for r in c.execute('SELECT data_json FROM campaign_pilot_jobs WHERE campaign_id=?',(cid,))]
            by_url = {source_key(j.get('url')):j for j in originals if j.get('url')}
            by_id = {(s.get('name'),str(s.get('source_id'))):j for j in originals for s in j.get('sources',[]) if s.get('source_id')}
            counts = {'new_count':0,'updated_count':0,'duplicate_count':0,'lead_count':0}
            for index,item in enumerate(items,current):
                if c.execute('SELECT 1 FROM campaign_items WHERE batch_id=? AND item_index=?',(batch['id'],index)).fetchone():
                    continue
                raw = normalize(batch['source'],item,iso(now)) if isinstance(item,dict) else None
                job = None
                outcome = 'lead'
                if raw:
                    old = by_id.get((raw['source'],str(raw.get('id')))) or by_url.get(source_key(raw['url']))
                    if not old and not raw.get('description'):
                        raw = None  # New search-only items need vacancy text.
                if raw:
                    job = merge_job(raw,old,iso(now))
                    comparable = ('title','company','description','source_requirements','location','employment_type','salary','posted_at','deadline')
                    outcome = 'new' if not old else 'duplicate' if all(job.get(k)==old.get(k) for k in comparable) else 'updated'
                    if not old:
                        candidates = [j['id'] for j in originals if str(j.get('title','')).casefold()==job['title'].casefold() and str(j.get('company','')).casefold()==str(job.get('company','')).casefold()]
                        if candidates:
                            job['possible_duplicate_ids'] = candidates[:20]
                    if pilot:
                        c.execute('INSERT INTO campaign_pilot_jobs VALUES(?,?,?) ON CONFLICT(campaign_id,job_id) DO UPDATE SET data_json=excluded.data_json',(cid,job['id'],encode(job)))
                    else:
                        c.execute('INSERT INTO jobs VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET data_json=excluded.data_json,updated_at=excluded.updated_at',(job['id'],encode(job),iso(now)))
                        c.execute('INSERT INTO source_evidence(job_id,source,data_json,captured_at) VALUES(?,?,?,?)',
                                  (job['id'],NAMES[batch['source']],encode({'record':raw,'raw_response':item,'run_id':batch['run_id'],'context':json.loads(batch['context_json'])}),iso(now)))
                    by_url[source_key(job['url'])] = job
                    if raw.get('id'): by_id[(raw['source'],str(raw['id']))] = job
                counts[outcome+'_count'] += 1
                c.execute('INSERT INTO campaign_items VALUES(?,?,?,?,?)',(batch['id'],index,encode(item),job['id'] if job else None,outcome))
                if isinstance(item,dict):
                    leads = item.get('organicResults',[]) if batch['source']=='google' else []
                    if batch['source']=='careers':
                        leads = [{'url':url,'title':''} for url in item.get('links',[]) if isinstance(url,str)]
                    context = json.loads(batch['context_json'])
                    for lead in leads:
                        self.discover(c,cid,lead.get('url',''),item.get('url') or access_url(batch['source'],json.loads(batch['input_json'])),
                                      context.get('depth',-1)+1,context.get('root_url'),lead,now)
            c.execute('''UPDATE campaign_batches SET checkpoint=?,new_count=new_count+?,updated_count=updated_count+?,
                duplicate_count=duplicate_count+?,lead_count=lead_count+? WHERE id=?''',
                (current+len(items),counts['new_count'],counts['updated_count'],counts['duplicate_count'],counts['lead_count'],batch['id']))

    def schedule(self, now):
        status = self.journal.status(now)
        if status.get('mode')!='production' or status['state']!='active':
            return
        for source in status['sources']:
            name = source['source']
            if source['due_at'] > now:
                continue
            cycle = source['cycle']
            with self.store._connection(write=True) as c:
                c.execute("UPDATE campaign_batches SET state='superseded',error='Replaced by the next scheduled cycle before launch.' WHERE campaign_id=? AND source=? AND state='queued' AND batch_key NOT LIKE 'pilot:%'",(status['id'],name))
            if name in ('linkedin','indeed'):
                for query in queries(cycle):
                    self.journal.enqueue(name,f'{name}:{cycle}:{query}',input_for(name,query),{'query':query,'cycle':cycle,'cap_usd':.25 if name=='linkedin' else .70},now)
            elif name=='google':
                candidates = [f'{q} Singapore careers vacancy' for q in CORE+HISTORICAL]
                employers = sorted({j.get('company','').strip() for j in self.store.list_jobs() if j.get('company') and j.get('company') not in ('Verified via Search Result','Not stated')})
                # Rotating named employers and agencies supplement role families.
                start = (cycle*24)%max(1,len(employers))
                candidates += [f'"{name}" Singapore careers jobs' for name in (employers[start:]+employers[:start])[:24]]
                for query in list(dict.fromkeys(candidates))[:40]:
                    self.journal.enqueue(name,f'google:{cycle}:{query}',input_for(name,query),{'query':query,'cycle':cycle,'cap_usd':.06},now)
            else:
                self.schedule_careers(now,cycle)
            self.journal.source(name,due_at=now+(21600 if name in ('linkedin','indeed') else DAY),cycle=cycle+1)

    def schedule_careers(self, now, cycle):
        cid = self.journal.current()['id']
        with self.store._connection(write=True) as c:
            # Saved non-closed applications go first; other listings rotate by
            # oldest successful check. Queue uniqueness prevents crawl cycles.
            saved = {r['job_id'] for r in c.execute("SELECT job_id FROM applications WHERE stage!='Closed'")}
            jobs = [json.loads(r[0]) for r in c.execute('SELECT data_json FROM jobs')]
            jobs.sort(key=lambda j:(j['id'] not in saved,j.get('verification',{}).get('last_success_at') or '',j['id']))
            for j in jobs[:100]:
                if j.get('url'):
                    self.discover(c,cid,j['url'],None,0,j['url'],{'job_id':j['id'],'title':j.get('title'),'recheck':True,'priority':j['id'] in saved},now)
            queue = c.execute("SELECT * FROM campaign_discovery WHERE campaign_id=? AND state='queued' ORDER BY discovered_at,url",(cid,)).fetchall()
            domains = set()
            pages = {}
            for row in queue:
                if row['domain'] not in domains and len(domains)>=20:
                    continue
                if pages.get(row['domain'],0)>=50:
                    continue
                domains.add(row['domain']);pages[row['domain']]=pages.get(row['domain'],0)+1
                # The official crawler's public schema only offers a post-load
                # pageFunction, not a pre-navigation redirect/IP guard. Do not
                # assert SSRF safety that this actor contract cannot guarantee.
                c.execute("UPDATE campaign_discovery SET state='blocked',reason=?,checked_at=? WHERE campaign_id=? AND url=?",
                          ('Official crawler redirect/private-network isolation is not verified.',now,cid,row['url']))
        self.journal.source('careers',blocked_reason='Official crawler redirect/private-network isolation is not verified; queued career leads are retained.')

    def poll(self, batch, now, expired=False, paused=False):
        account = next((a for a in self.journal.accounts() if a['account_id']==batch['account_id']),None)
        if not account:
            self.journal.update_batch(batch['id'],error='Account reference unavailable; reservation retained.')
            return
        ref = account['reference']
        try:
            if batch['state'] in ('launching','ambiguous'):
                run = self.api.reconcile(ref,batch)
                if run is None:
                    self.journal.update_batch(batch['id'],state='ambiguous',error='Launch outcome unresolved; no retry will be made.',retry_at=now+300)
                    return
                self.journal.update_batch(batch['id'],state='running',run_id=run['id'],dataset_id=run.get('defaultDatasetId'),remote_status=run['status'],error=None)
                batch = {**batch,'run_id':run['id'],'dataset_id':run.get('defaultDatasetId'),'state':'running'}
            if batch['state']=='running':
                run = self.api.run(ref,batch['run_id'])
                if (expired or paused) and run['status'] not in TERMINAL:
                    self.api.abort(ref,batch['run_id'])
                    self.journal.update_batch(batch['id'],error='Abort requested; awaiting terminal confirmation.')
                    return
                if run['status'] not in TERMINAL:
                    self.journal.update_batch(batch['id'],remote_status=run['status'])
                    return
                cost = run.get('usageTotalUsd')
                if cost is None or not isinstance(cost,(int,float)) or cost<0:
                    self.journal.update_batch(batch['id'],error='Final run cost is unknown; reservation retained.',retry_at=now+300)
                    return
                self.store.set_meta('campaign_remote_'+batch['id'],{k:run.get(k) for k in ('id','status','startedAt','finishedAt','usageTotalUsd','options')})
                self.journal.update_batch(batch['id'],state='importing',remote_status=run['status'],charge_units=units(cost),
                                          dataset_id=run.get('defaultDatasetId'),error=None)
                batch = {**batch,'state':'importing','dataset_id':run.get('defaultDatasetId'),'remote_status':run['status']}
            if batch['state']=='importing':
                if not disk_capacity(self.store)['safe']:
                    self.journal.update_batch(batch['id'],error='Import paused to preserve disk capacity.',retry_at=now+300)
                    return
                items = self.api.items(ref,batch['dataset_id'],batch['checkpoint']) if batch['dataset_id'] else []
                if items:
                    self.import_page(batch,items,now)
                else:
                    self.journal.update_batch(batch['id'],state='done' if batch['remote_status']=='SUCCEEDED' else 'failed',finished_at=now,
                                              error=None if batch['remote_status']=='SUCCEEDED' else 'Partial results retained from '+str(batch['remote_status']))
                    if batch['remote_status']=='SUCCEEDED':
                        self.journal.source(batch['source'],last_success=now)
        except ApiError as e:
            self.journal.update_batch(batch['id'],error=str(e),retry_at=now+300)

    def tick(self):
        now = self.clock()
        campaign = self.journal.current()
        if not campaign or not self.journal.claim(self.owner,now):
            return
        self.repair_normalization()
        expired = bool(campaign['stops_at'] and now>=campaign['stops_at'])
        if expired and campaign['state']!='stopped':
            self.journal.state('stopped','The 168-hour campaign has ended.')
        for batch in self.journal.batches(ACTIVE):
            if batch['retry_at']<=now or expired:
                self.poll(batch,now,expired=expired,paused=campaign['state'] in ('paused','stopped'))
        # A deployment may introduce richer run evidence after an earlier pilot
        # already completed. Recover its terminal metadata before retention ends.
        for batch in self.journal.batches(('done','failed')):
            if batch['run_id'] and not self.store.get_meta('campaign_remote_'+batch['id']):
                account=next((a for a in self.journal.accounts() if a['account_id']==batch['account_id']),None)
                if account:
                    try:
                        run=self.api.run(account['reference'],batch['run_id'])
                        if run['status'] in TERMINAL:
                            self.store.set_meta('campaign_remote_'+batch['id'],{k:run.get(k) for k in ('id','status','startedAt','finishedAt','usageTotalUsd','options')})
                    except ApiError:
                        pass  # The final report keeps this evidence unresolved.
                break  # Bound recovery reads per tick.
        self.store.set_meta('campaign_disk',disk_capacity(self.store))
        if expired or campaign['state'] in ('paused','stopped','prepared'):
            if campaign['started_at'] and now-self.last_accounts>=120:
                self.refresh_accounts(self.clock())
            if expired:
                from evidence import parse_date
                unresolved = self.journal.batches(ACTIVE)
                remote = [self.store.get_meta('campaign_remote_'+b['id']) for b in self.journal.batches() if b['run_id']]
                confirmed = not unresolved and all(r and parse_date(r.get('finishedAt')) and parse_date(r['finishedAt']).timestamp()<=campaign['stops_at'] for r in remote)
                self.store.set_meta('campaign_shutdown_verification',{'observed_at':iso(self.clock()),'deadline':iso(campaign['stops_at']),
                    'all_paid_runs_confirmed_stopped_by_deadline':bool(confirmed),
                    'unresolved_batches':len(unresolved),'remote_runs_with_evidence':sum(bool(r) for r in remote),
                    'note':'Imports and account-cost observations may continue after paid collection ends.'})
            self.store.set_meta('campaign_report',self.journal.status(now))
            return
        if not disk_capacity(self.store)['safe']:
            self.journal.state('paused','Low disk capacity; preserving space for backups and application writes.')
            return
        if now-self.last_accounts>=120:
            self.refresh_accounts(self.clock())
        if self.store.get_meta('campaign_account_error'):
            return
        now = self.clock()
        if not self.journal.claim(self.owner,now):
            return
        self.schedule(now)
        for batch in self.journal.batches(('queued',)):
            if batch['retry_at']>now:
                continue
            if len(self.journal.batches(ACTIVE))>=2:
                break
            source = batch['source']
            try:
                payload = json.loads(batch['input_json'])
                validate_input(source,payload)
                evidence = self.access(access_url(source,payload))
                self.store.set_meta('campaign_access_'+source,{**evidence,'checked_at':iso(now)})
                # Every enabled source must pass its own bounded isolated pilot.
                if campaign['mode']=='production' and source not in self.store.get_meta('campaign_validated_sources',[]):
                    raise AccessBlocked('This source has not passed a verified pilot.')
                launched = False
                cap = json.loads(batch['context_json'])['cap_usd']
                commitments = self.journal.batches()
                for account in self.journal.accounts():
                    if not account['available']:
                        continue
                    committed_units = sum(b['reserved_units'] for b in commitments if b['account_id']==account['account_id'])
                    if max(account['usage_units'],account['baseline_units']+committed_units)+units(cap+.15)>account['limit_units']:
                        continue
                    live = self.api.snapshot(account['reference'])
                    self.journal.account(live,self.clock())
                    if source not in self.contracts or now-self.contracts[source]>3600:
                        contract = self.api.contract(account['reference'],source)
                        self.store.set_meta('campaign_contract_'+source,contract)
                        self.contracts[source]=now
                    if not self.journal.claim(self.owner,self.clock()):
                        return
                    ok,reason = self.journal.reserve(batch['id'],account['account_id'],cap,self.owner,self.clock())
                    if not ok:
                        self.journal.source(source,blocked_reason=reason)
                        continue
                    committed = next(b for b in self.journal.batches(('launching',)) if b['id']==batch['id'])
                    try:
                        run = self.api.launch(account['reference'],committed,self.journal.current()['stops_at'],self.clock())
                        if not run.get('id'):
                            raise ApiError('ambiguous_write')
                        self.journal.update_batch(batch['id'],state='running',run_id=run['id'],dataset_id=run.get('defaultDatasetId'),remote_status=run['status'])
                    except ApiError as e:
                        certain = e.kind in ('input','authentication','exhausted','campaign_expired_before_launch')
                        self.journal.update_batch(batch['id'],state='failed' if certain else 'ambiguous',error=str(e),
                                                  finished_at=self.clock() if certain else None,retry_at=self.clock()+300)
                    launched = True
                    break
                if not launched:
                    self.journal.update_batch(batch['id'],retry_at=now+300,error='No account currently admits this reservation.')
            except (AccessBlocked,ValueError) as e:
                self.journal.update_batch(batch['id'],state='blocked',error=str(e))
                self.journal.source(source,blocked_reason=str(e),last_attempt=now)
            except ApiError as e:
                self.journal.update_batch(batch['id'],error=str(e),retry_at=now+300)
                self.journal.source(source,blocked_reason=str(e))
        self.store.set_meta('campaign_report',self.journal.status(self.clock()))

    def repair_normalization(self):
        """Add newly recognized returned salary/date fields from retained items.

        This is a local normalization correction, never a fresh source check.
        Original payloads, application snapshots and successful-check dates stay.
        """
        if self.store.get_meta('campaign_normalization_version') == 2:
            return
        with self.store._connection(write=True) as c:
            rows=c.execute('''SELECT i.*,b.campaign_id,b.source,b.context_json FROM campaign_items i
                JOIN campaign_batches b ON b.id=i.batch_id WHERE i.job_id IS NOT NULL
                ORDER BY b.reserved_at,i.item_index''').fetchall()
            for row in rows:
                payload=json.loads(row['payload_json'])
                pilot=json.loads(row['context_json']).get('pilot',False)
                table='campaign_pilot_jobs' if pilot else 'jobs'
                result=c.execute('SELECT data_json FROM '+table+' WHERE '+('campaign_id=? AND job_id=?' if pilot else 'id=?'),
                                 (row['campaign_id'],row['job_id']) if pilot else (row['job_id'],)).fetchone()
                if not result:continue
                job=json.loads(result[0]);raw=normalize(row['source'],payload,job.get('verification',{}).get('last_success_at'))
                if not raw:continue
                provenance=job.setdefault('field_provenance',{})
                basis=dict(provenance.get('description',{}),basis='retained_actor_field')
                if raw.get('advertised_salary'):
                    job['salary']=salary_presentation(raw);provenance['salary']=basis
                if raw.get('posted_date'):
                    job['posted_at']=raw['posted_date'];provenance['posted_at']=basis
                c.execute('UPDATE '+table+' SET data_json=? WHERE '+('campaign_id=? AND job_id=?' if pilot else 'id=?'),
                          (encode(job),row['campaign_id'],row['job_id']) if pilot else (encode(job),row['job_id']))
            c.execute('INSERT INTO metadata VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json',('campaign_normalization_version','2'))


async def campaign_loop(application):
    worker = application.state.campaign_worker
    while True:
        try:
            # Shield/await the current thread on shutdown; a cancelled coroutine
            # must never leave an unowned mutation running in the background.
            async def owned_tick():
                async with worker.mutation_lock:
                    await asyncio.to_thread(worker.tick)
            tick = asyncio.create_task(owned_tick())
            try:
                await asyncio.shield(tick)
            except asyncio.CancelledError:
                await tick
                raise
        except asyncio.CancelledError:
            raise
        except Exception as error:
            logger.error('Campaign tick failed (%s); reservations retained',type(error).__name__)
            worker.store.set_meta('campaign_worker_error',{'at':iso(time.time()),'type':type(error).__name__})
        await asyncio.sleep(30)


async def owned_operation(worker, operation):
    async with worker.mutation_lock:
        task = asyncio.create_task(asyncio.to_thread(operation))
        try:
            return await asyncio.shield(task)
        except asyncio.CancelledError:
            await task
            raise
