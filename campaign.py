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
    access_url, canonical_url, extract_links, input_for, merge_job, normalize,
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
    def __init__(self, store, api=None, access=None, clock=time.time):
        self.store, self.journal = store, CampaignStore(store)
        try:
            self.api = api if api is not None else Apify()
        except (ValueError,TypeError):
            # A malformed collection secret cannot take the private workspace
            # or its independent free MCF scheduler offline.
            self.api = Apify([])
            store.set_meta('campaign_account_error','Invalid APIFY_TOKENS_JSON configuration; paid collection is unavailable.')
        # ``access`` remains an ignored compatibility argument for callers of
        # the first campaign worker. URL identity never performs network checks.
        self.clock = clock
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

    def pilot(self, source='indeed', urls=None, retry_of=None):
        if source not in NAMES:
            raise ValueError('Unknown validation source')
        if not self.journal.current():
            self.prepare()
        now = self.clock()
        campaign = self.journal.current()
        if campaign['state'] in ('paused','stopped'):
            raise ValueError('Resume the campaign before requesting validation')
        query = 'Marketing Executive Singapore careers vacancy' if source == 'google' else 'Marketing Executive'
        if source == 'careers':
            if isinstance(urls,str):
                urls = [urls]
            if not urls:
                with self.store._connection() as c:
                    row = c.execute("SELECT url FROM campaign_discovery WHERE campaign_id=? AND state='queued' ORDER BY discovered_at,url LIMIT 1",(campaign['id'],)).fetchone()
                urls = [row[0]] if row else []
            if not urls:
                raise ValueError('Career validation requires a discovered career URL')
            urls = list(dict.fromkeys(canonical_url(url) for url in urls))
            if len(urls)>10 or len({urlsplit(url).hostname for url in urls})!=1:
                raise ValueError('Career validation accepts up to ten URLs on one domain')
            query = urls
        payload = input_for(source,query,10)
        context = {'query':query,'pilot':True,'cap_usd':.50 if source in ('google','careers') else .20}
        if source == 'careers':
            context.update(urls=urls,domain=urlsplit(urls[0]).hostname,depth=0,root_url=urls[0])
        # A source's supplemental validation never changes an active campaign's
        # mode, original start time, ledger, or recurring sources.
        key = 'pilot:'+source
        if retry_of:
            previous = next((b for b in self.journal.batches() if b['id']==retry_of),None)
            if not previous or previous['source']!=source or previous['state']!='failed' or not json.loads(previous['context_json']).get('pilot'):
                raise ValueError('A validation retry must reference a terminal failed pilot of the same source.')
            key += ':retry:'+retry_of
            context['retry_of'] = retry_of
        self.journal.enqueue(source,key,payload,context,now)
        if campaign['mode']=='pilot' and campaign['state']=='prepared':
            self.journal.state('pilot')
        return self.journal.status()

    def discover(self, c, cid, url, parent, depth, root, evidence, now):
        try:
            url = canonical_url(url)
        except AccessBlocked:
            return
        if parent:
            c.execute('INSERT OR IGNORE INTO campaign_edges VALUES(?,?,?,?)', (cid,parent,url,encode(evidence)))
        if not evidence.get('recheck') and not relevant_career_url(url, str(evidence.get('title',''))):
            return
        reason = None
        if depth > 2:
            reason = 'Maximum discovery depth reached'
        host = urlsplit(url).hostname
        if host == 'cultjobs.com' or host.endswith('.cultjobs.com'):
            reason = 'Cultjobs remains a separately specified dated import'
        c.execute('''INSERT OR IGNORE INTO campaign_discovery VALUES(?,?,?,?,?,?,?,?,?,?,?)''',
                  (cid,url,host,parent,root or url,depth,'blocked' if reason else 'queued',now,None,encode(evidence),reason))

    def career_failure(self, c, cid, url, reason, now):
        """Retain a failed attempt without advancing successful verification."""
        row = c.execute('SELECT evidence_json FROM campaign_discovery WHERE campaign_id=? AND url=?',(cid,url)).fetchone()
        c.execute("UPDATE campaign_discovery SET state='failed',checked_at=?,reason=? WHERE campaign_id=? AND url=?",
                  (now,reason,cid,url))
        jid = json.loads(row[0]).get('job_id') if row else None
        old = c.execute('SELECT data_json FROM jobs WHERE id=?',(jid,)).fetchone() if jid else None
        if old:
            job = json.loads(old[0])
            job['verification'] = {**job.get('verification',{}),'last_attempt_at':iso(now),'last_error':reason,'status':'error'}
            c.execute('UPDATE jobs SET data_json=?,updated_at=? WHERE id=?',(encode(job),iso(now),jid))

    def import_page(self, batch, items, now):
        cid = batch['campaign_id']
        campaign = self.journal.current()
        context = json.loads(batch['context_json'])
        pilot = context.get('pilot',False) or campaign['mode']=='pilot'
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
                        originals.append(job)
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
                if isinstance(item,dict) and not pilot:
                    leads = item.get('organicResults',[]) if batch['source']=='google' else []
                    if batch['source']=='careers':
                        leads = extract_links(item)
                        returned = item.get('crawl',{}).get('loadedUrl') or item.get('url')
                        requested = item.get('url')
                        try:
                            requested = canonical_url(requested)
                        except (AccessBlocked,TypeError):
                            requested = None
                        if requested in context.get('urls',[]):
                            status = item.get('crawl',{}).get('httpStatusCode')
                            failed = isinstance(status,int) and status>=400
                            if failed:
                                self.career_failure(c,cid,requested,'Provider returned HTTP '+str(status),now)
                                c.execute('UPDATE campaign_batches SET error=?,error_category=? WHERE id=?',
                                          ('Provider returned HTTP '+str(status),'source_access' if status in (401,403,429) else 'provider_response',batch['id']))
                            else:
                                c.execute("UPDATE campaign_discovery SET state='done',checked_at=?,reason=NULL WHERE campaign_id=? AND url=?",
                                          (now,cid,requested))
                        # Redirect targets remain identity evidence, without a
                        # pre-navigation DNS or redirect admission policy.
                        if returned and returned != requested:
                            c.execute('INSERT OR IGNORE INTO campaign_edges VALUES(?,?,?,?)',
                                      (cid,requested or access_url(batch['source'],json.loads(batch['input_json'])),returned,
                                       encode({'relation':'returned_page','batch_id':batch['id'],'item_index':index})))
                    for lead in leads:
                        if not isinstance(lead,dict):
                            continue
                        parent = lead.get('parent_url') or item.get('url') or access_url(batch['source'],json.loads(batch['input_json']))
                        page = next((page for page in context.get('pages',[]) if page['url']==item.get('url')),{})
                        evidence = {**lead,'parent_batch_id':batch['id'],'parent_item_index':index,'parent_run_id':batch['run_id']}
                        root = lead.get('url') if batch['source']=='google' else page.get('root_url') or context.get('root_url') or parent
                        self.discover(c,cid,lead.get('url',''),parent,context.get('depth',-1)+1,root,evidence,now)
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
            if name != 'careers':
                with self.store._connection(write=True) as c:
                    c.execute("UPDATE campaign_batches SET state='superseded',error='Replaced by the next scheduled cycle before launch.' WHERE campaign_id=? AND source=? AND state='queued' AND batch_key NOT LIKE 'pilot:%'",(status['id'],name))
            if name in ('linkedin','indeed'):
                for query in queries(cycle):
                    self.journal.enqueue(name,f'{name}:{cycle}:{query}',input_for(name,query),{'query':query,'cycle':cycle,'cap_usd':.25 if name=='linkedin' else .6875},now)
            elif name=='google':
                candidates = [f'{q} Singapore careers vacancy' for q in CORE+HISTORICAL]
                employers = sorted({j.get('company','').strip() for j in self.store.list_jobs() if j.get('company') and j.get('company') not in ('Verified via Search Result','Not stated')})
                # Rotating named employers and agencies supplement role families.
                start = (cycle*24)%max(1,len(employers))
                candidates += [f'"{name}" Singapore careers jobs' for name in (employers[start:]+employers[:start])[:24]]
                distinct = list(dict.fromkeys(candidates))[:40]
                for offset in range(0,len(distinct),20):
                    group = distinct[offset:offset+20]
                    self.journal.enqueue(name,f'google:{cycle}:{offset//20}',input_for(name,'\n'.join(group)),
                                         {'queries':group,'cycle':cycle,'cap_usd':.50},now)
            else:
                self.schedule_careers(now,cycle)
            self.journal.source(name,due_at=now+(21600 if name in ('linkedin','indeed') else DAY),cycle=cycle+1)
        # Process newly returned links immediately; the durable daily domain and
        # page accounting below also applies to these later depth batches.
        career = next((s for s in status['sources'] if s['source']=='careers'),None)
        if career:
            self.schedule_careers(now,career['cycle'],seed_rechecks=False)

    def schedule_careers(self, now, cycle, seed_rechecks=True):
        cid = self.journal.current()['id']
        with self.store._connection(write=True) as c:
            if seed_rechecks:
                saved = {r['job_id'] for r in c.execute("SELECT job_id FROM applications WHERE stage!='Closed'")}
                jobs = [json.loads(r[0]) for r in c.execute('SELECT data_json FROM jobs')]
                jobs.sort(key=lambda j:(j['id'] not in saved,j.get('verification',{}).get('last_success_at') or '',j['id']))
                for j in jobs:
                    if not j.get('url'):
                        continue
                    evidence = {'job_id':j['id'],'title':j.get('title'),'recheck':True,'priority':j['id'] in saved,
                                'last_success_at':j.get('verification',{}).get('last_success_at')}
                    self.discover(c,cid,j['url'],None,0,j['url'],evidence,now)
                    try:
                        url = canonical_url(j['url'])
                    except AccessBlocked:
                        continue
                    # Completed/failed checks rotate again next day; unreturned
                    # pages in active batches are never launched twice.
                    c.execute("""UPDATE campaign_discovery SET state='queued',evidence_json=?,reason=NULL
                        WHERE campaign_id=? AND url=? AND state IN ('done','failed') AND checked_at<=?""",
                              (encode(evidence),cid,url,now-DAY))
                    c.execute("UPDATE campaign_discovery SET evidence_json=? WHERE campaign_id=? AND url=? AND state='queued'",
                              (encode(evidence),cid,url))
            batches = c.execute("SELECT * FROM campaign_batches WHERE campaign_id=? AND source='careers'",(cid,)).fetchall()
            first_domains, page_counts = {}, {}
            for batch in batches:
                context = json.loads(batch['context_json'])
                if context.get('pilot') or batch['state']=='superseded' and batch['reserved_at'] is None:
                    continue
                domain = context.get('domain')
                if not domain:
                    continue
                first_domains[domain] = min(first_domains.get(domain,batch['created_at']),batch['created_at'])
                # Persisted batch membership is a page reservation, including
                # queued runs; this survives restarts and partial imports.
                if batch['created_at']>now-DAY or batch['state'] in ACTIVE or batch['state']=='queued':
                    page_counts[domain] = page_counts.get(domain,0)+len(context.get('urls',[]))
            new_domains = {domain for domain,at in first_domains.items() if at>now-DAY}
            queue = [dict(row) for row in c.execute("SELECT * FROM campaign_discovery WHERE campaign_id=? AND state='queued' AND depth<=2",(cid,))]
            def priority(row):
                ev = json.loads(row['evidence_json'])
                return (not ev.get('priority',False),not ev.get('recheck',False),ev.get('last_success_at') or '',row['discovered_at'],row['url'])
            queue.sort(key=priority)
            groups = {}
            for row in queue:
                domain = row['domain']
                if domain not in first_domains and len(new_domains)>=20:
                    continue
                if page_counts.get(domain,0)>=50:
                    continue
                if domain not in first_domains:
                    first_domains[domain] = now
                    new_domains.add(domain)
                page_counts[domain] = page_counts.get(domain,0)+1
                groups.setdefault((domain,row['depth']),[]).append(row)
            for (domain,depth),rows in groups.items():
                urls = [r['url'] for r in rows]
                context = {'cycle':cycle,'cap_usd':.50,'domain':domain,'depth':depth,'urls':urls,
                           'root_url':rows[0]['root_url'],'pages':[{'url':r['url'],'root_url':r['root_url']} for r in rows],
                           'recheck':any(json.loads(r['evidence_json']).get('recheck') for r in rows),
                           'priority':any(json.loads(r['evidence_json']).get('priority') for r in rows)}
                bid = uuid.uuid4().hex
                c.execute('''INSERT INTO campaign_batches
                    (id,campaign_id,source,batch_key,input_json,context_json,state,created_at)
                    VALUES(?,?,'careers',?,?,?,'queued',?)''',
                          (bid,cid,'careers:'+bid,encode(input_for('careers',urls)),encode(context),now))
                for row in rows:
                    c.execute("UPDATE campaign_discovery SET state='scheduled',reason=NULL WHERE campaign_id=? AND url=?",(cid,row['url']))
        self.journal.source('careers',blocked_reason=None)

    def repair_removed_policy(self, now):
        """Supersede only unlaunched work denied by the removed local policy."""
        if self.store.get_meta('campaign_policy_correction_v2'):
            return
        prefixes = ('Source robots directives','Robots directives unavailable','Source crawl-delay',
                    'Source access check unavailable','Destination resolves to a non-public address',
                    'Official crawler redirect/private-network isolation','Unsafe URL','Private or malformed address')
        observations = []
        with self.store._connection(write=True) as c:
            cid = self.journal.current()['id']
            sources = set()
            for row in c.execute("SELECT * FROM campaign_batches WHERE campaign_id=? AND state IN ('blocked','queued') AND reserved_at IS NULL",(cid,)).fetchall():
                if not (row['error'] or '').startswith(prefixes):
                    continue
                observations.append({'kind':'batch','id':row['id'],'state':row['state'],'reason':row['error']})
                c.execute("UPDATE campaign_batches SET state='superseded',error=?,error_category='superseded_policy' WHERE id=?",
                          ('Superseded local-policy observation: '+row['error'],row['id']))
                sources.add(row['source'])
            for row in c.execute("SELECT * FROM campaign_discovery WHERE campaign_id=? AND state='blocked'",(cid,)).fetchall():
                if not (row['reason'] or '').startswith(prefixes):
                    continue
                observations.append({'kind':'discovery','url':row['url'],'state':row['state'],'reason':row['reason']})
                c.execute("UPDATE campaign_discovery SET state='queued',reason=NULL WHERE campaign_id=? AND url=?",(cid,row['url']))
                sources.add('careers')
            for source in sources:
                c.execute('UPDATE campaign_sources SET due_at=?,blocked_reason=NULL WHERE campaign_id=? AND source=?',(now,cid,source))
            c.execute('INSERT INTO metadata VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json',
                      ('campaign_policy_correction_v2',encode({'at':iso(now),'superseded_observations':observations})))

    def repair_career_inputs(self, now):
        """Migrate batches queued before the validated crawler proxy input.

        The old payload and any failed reservation remain immutable evidence;
        only an unlaunched queued payload is edited in place, while a failed
        reserved batch receives one corrected replacement with a new key.
        """
        if self.store.get_meta('campaign_career_proxy_v1'):
            return
        with self.store._connection(write=True) as c:
            campaign = self.journal.current()
            replacements = []
            for row in c.execute("SELECT * FROM campaign_batches WHERE campaign_id=? AND source='careers' AND state IN ('queued','failed')",(campaign['id'],)).fetchall():
                payload = json.loads(row['input_json'])
                if payload.get('proxyConfiguration',{}).get('useApifyProxy') is not False:
                    continue
                context = json.loads(row['context_json'])
                urls = context.get('urls') or [x.get('url') for x in payload.get('startUrls',[]) if isinstance(x,dict)]
                if not urls:
                    continue
                corrected = input_for('careers',urls)
                if row['state']=='queued' and row['reserved_at'] is None:
                    c.execute('UPDATE campaign_batches SET input_json=? WHERE id=?',(encode(corrected),row['id']))
                elif row['reserved_at'] is not None:
                    replacements.append((row,corrected,context))
            for row, corrected, context in replacements:
                key = row['batch_key']+':proxy-v1'
                c.execute('''INSERT OR IGNORE INTO campaign_batches
                    (id,campaign_id,source,batch_key,input_json,context_json,state,created_at)
                    VALUES(?,?,?,?,?,?,'queued',?)''',
                    (uuid.uuid4().hex,campaign['id'],'careers',key,encode(corrected),encode({**context,'retry_of':row['id'],'input_correction':'proxy-v1'}),now))
            c.execute('INSERT INTO metadata VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json',
                      ('campaign_career_proxy_v1',encode({'at':iso(now),'replaced_failed_batches':len(replacements)})))

    def import_career_errors(self, batch, reference, now):
        """Checkpoint the official crawler's documented named errors dataset.

        Negative item indices distinguish error rows from the default dataset's
        nonnegative offsets, retaining exact output without moving its checkpoint.
        """
        remote = self.store.get_meta('campaign_remote_'+batch['id']) or {}
        dataset = remote.get('storageIds',{}).get('datasets',{}).get('errors')
        if not dataset:
            return True
        key = 'campaign_crawl_errors_'+batch['id']
        saved = self.store.get_meta(key) or {'checkpoint':0,'complete':False,'dataset_id':dataset}
        if saved['complete']:
            return True
        items = self.api.items(reference,dataset,saved['checkpoint'])
        context = json.loads(batch['context_json'])
        with self.store._connection(write=True) as c:
            current = c.execute('SELECT value_json FROM metadata WHERE key=?',(key,)).fetchone()
            if current and json.loads(current[0])['checkpoint']!=saved['checkpoint']:
                return False
            for offset,item in enumerate(items,saved['checkpoint']):
                c.execute('INSERT OR IGNORE INTO campaign_items VALUES(?,?,?,?,?)',
                          (batch['id'],-1-offset,encode(item),None,'error'))
                if not isinstance(item,dict):
                    continue
                status = item.get('httpStatus')
                reason = str(item.get('errorExplanation') or item.get('errorCode') or 'Provider crawl failure')
                category = 'source_access' if status in (401,403,429) else 'provider_response' if status else 'runtime'
                c.execute('UPDATE campaign_batches SET error=?,error_category=? WHERE id=?',(reason,category,batch['id']))
                try:
                    url = canonical_url(item.get('url'))
                except AccessBlocked:
                    continue
                if url in context.get('urls',[]) and not context.get('pilot'):
                    self.career_failure(c,batch['campaign_id'],url,reason,now)
            saved.update(checkpoint=saved['checkpoint']+len(items),complete=not bool(items))
            c.execute('INSERT INTO metadata VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json',(key,encode(saved)))
        return not bool(items)

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
                self.store.set_meta('campaign_remote_'+batch['id'],{k:run.get(k) for k in ('id','status','statusMessage','startedAt','finishedAt','usageTotalUsd','options','storageIds')})
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
                    if batch['source']=='careers' and not self.import_career_errors(batch,ref,now):
                        return
                    success = batch['remote_status']=='SUCCEEDED'
                    context = json.loads(batch['context_json'])
                    error = None if success else 'Partial results retained from '+str(batch['remote_status'])
                    remote = self.store.get_meta('campaign_remote_'+batch['id']) or {}
                    message = str(remote.get('statusMessage') or '')
                    category = None if success else 'source_access' if any(x in message.lower() for x in ('access denied','forbidden','captcha','blocked by','http 403','http 401')) else 'runtime'
                    if message and not success:
                        error += ': '+message
                    final_errors = {'error':error,'error_category':category}
                    if success:
                        with self.store._connection() as c:
                            latest = c.execute('SELECT error_category FROM campaign_batches WHERE id=?',(batch['id'],)).fetchone()
                        if latest[0] in ('source_access','provider_response','runtime'):
                            final_errors = {}  # Keep returned per-page failures.
                    self.journal.update_batch(batch['id'],state='done' if batch['remote_status']=='SUCCEEDED' else 'failed',finished_at=now,
                                              **final_errors)
                    if batch['source']=='careers' and not context.get('pilot'):
                        with self.store._connection(write=True) as c:
                            for url in context.get('urls',[]):
                                pending = c.execute("SELECT 1 FROM campaign_discovery WHERE campaign_id=? AND url=? AND state='scheduled'",(batch['campaign_id'],url)).fetchone()
                                if pending:
                                    self.career_failure(c,batch['campaign_id'],url,error or 'Provider returned no page for this requested URL',now)
                    if batch['remote_status']=='SUCCEEDED':
                        self.journal.source(batch['source'],last_success=now)
        except ApiError as e:
            self.journal.update_batch(batch['id'],error=str(e),error_category=e.kind,retry_at=now+300)

    def tick(self):
        now = self.clock()
        campaign = self.journal.current()
        if not campaign or not self.journal.claim(self.owner,now):
            return
        self.repair_removed_policy(now)
        self.repair_career_inputs(now)
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
                            self.store.set_meta('campaign_remote_'+batch['id'],{k:run.get(k) for k in ('id','status','statusMessage','startedAt','finishedAt','usageTotalUsd','options','storageIds')})
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
        queued = self.journal.batches(('queued',))
        queued.sort(key=lambda b:(not json.loads(b['context_json']).get('pilot',False),
                                  not json.loads(b['context_json']).get('priority',False),b['created_at'],b['id']))
        for batch in queued:
            if batch['retry_at']>now:
                continue
            if len(self.journal.batches(ACTIVE))>=2:
                break
            source = batch['source']
            try:
                payload = json.loads(batch['input_json'])
                validate_input(source,payload)
                # Every enabled source must pass its own bounded isolated pilot.
                context = json.loads(batch['context_json'])
                if campaign['mode']=='production' and not context.get('pilot') and source not in self.store.get_meta('campaign_validated_sources',[]):
                    self.journal.source(source,blocked_reason='Source validation has not completed.')
                    continue
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
                                                  error_category=e.kind,finished_at=self.clock() if certain else None,retry_at=self.clock()+300)
                        if certain and source=='careers' and not context.get('pilot'):
                            with self.store._connection(write=True) as c:
                                for url in context.get('urls',[]):
                                    self.career_failure(c,batch['campaign_id'],url,str(e),self.clock())
                    launched = True
                    break
                if not launched:
                    self.journal.update_batch(batch['id'],retry_at=now+300,error='No account currently admits this reservation.')
            except (AccessBlocked,ValueError) as e:
                self.journal.update_batch(batch['id'],state='blocked',error=str(e),error_category='input')
                self.journal.source(source,blocked_reason=str(e),last_attempt=now)
            except ApiError as e:
                self.journal.update_batch(batch['id'],error=str(e),error_category=e.kind,retry_at=now+300)
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
                    started = time.time()
                    await asyncio.to_thread(worker.tick)
                    current = worker.journal.current()
                    if current and (current['heartbeat'] or 0)>=started:
                        previous = worker.store.get_meta('campaign_worker_error')
                        if previous:
                            worker.store.set_meta('campaign_previous_worker_error',previous)
                            worker.store.set_meta('campaign_worker_error',None)
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
