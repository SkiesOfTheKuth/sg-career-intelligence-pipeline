"""One authorized SGT-day expansion, owned by the existing campaign worker.

No credentials or independent scheduler. All admission checks are repeated under
the campaign's SQLite write transaction. Completed caps are never recycled.
"""
from datetime import datetime, timedelta, timezone
import hashlib
import json
import re
import uuid
from urllib.parse import parse_qs, urlsplit

from campaign_store import ACTIVE, DAY, encode, units
from campaign_sources import CORE, HISTORICAL, input_for

SGT = timezone(timedelta(hours=8), 'Asia/Singapore')
ALLOCATIONS = {'indeed': (70, 95), 'linkedin': (64, 84), 'google': (1, 1), 'careers': (15, 20)}
OPEN = ('active', 'target_reached')
CAPS = {'indeed': .6875, 'linkedin': .25, 'google': .5, 'careers': .5}


def initialize(c):
    columns = {r[1] for r in c.execute('PRAGMA table_info(campaign_batches)')}
    for name, kind in (('burst_id', 'TEXT'), ('burst_tranche', 'INTEGER')):
        if name not in columns:
            c.execute(f'ALTER TABLE campaign_batches ADD COLUMN {name} {kind}')
    statements = [
        '''CREATE TABLE IF NOT EXISTS campaign_bursts (
            id TEXT PRIMARY KEY, campaign_id TEXT NOT NULL UNIQUE, local_day TEXT NOT NULL,
            window_start REAL NOT NULL, window_end REAL NOT NULL, created_at REAL NOT NULL,
            target_units INTEGER NOT NULL, soft_units INTEGER NOT NULL, state TEXT NOT NULL,
            reason TEXT, baseline_charge_units INTEGER NOT NULL, baseline_usage_units INTEGER NOT NULL,
            initial_capacity_units INTEGER NOT NULL, capacity_units INTEGER NOT NULL,
            reserved_units INTEGER NOT NULL DEFAULT 0, charged_units INTEGER NOT NULL DEFAULT 0,
            ancillary_units INTEGER NOT NULL DEFAULT 0, shortfall_units INTEGER NOT NULL,
            checked_at REAL NOT NULL)''',
        '''CREATE TABLE IF NOT EXISTS campaign_burst_sources (
            burst_id TEXT NOT NULL, source TEXT NOT NULL, target_units INTEGER NOT NULL,
            soft_units INTEGER NOT NULL, state TEXT NOT NULL DEFAULT 'active', reason TEXT,
            PRIMARY KEY(burst_id,source))''',
        '''CREATE TABLE IF NOT EXISTS campaign_burst_tranches (
            burst_id TEXT NOT NULL, source TEXT NOT NULL, tranche INTEGER NOT NULL,
            completed_at REAL NOT NULL, new_count INTEGER NOT NULL, duplicate_count INTEGER NOT NULL,
            lead_count INTEGER NOT NULL, updated_count INTEGER NOT NULL, charge_units INTEGER NOT NULL,
            duplicate_lead_ratio REAL NOT NULL, fresh_per_dollar REAL,
            PRIMARY KEY(burst_id,source,tranche))''',
        '''CREATE TABLE IF NOT EXISTS campaign_burst_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT, burst_id TEXT NOT NULL, at REAL NOT NULL,
            kind TEXT NOT NULL, detail_json TEXT NOT NULL)''',
        '''CREATE TABLE IF NOT EXISTS campaign_query_identities (
            campaign_id TEXT NOT NULL, source TEXT NOT NULL, identity TEXT NOT NULL,
            query TEXT NOT NULL, batch_id TEXT NOT NULL, PRIMARY KEY(campaign_id,source,identity))''',
        'CREATE INDEX IF NOT EXISTS campaign_batch_burst ON campaign_batches(burst_id,source,burst_tranche)',
    ]
    for statement in statements:
        c.execute(statement)


def day_window(now):
    start = datetime.fromtimestamp(now, SGT).replace(hour=0, minute=0, second=0, microsecond=0)
    return start.date().isoformat(), start.timestamp(), (start + timedelta(days=1)).timestamp()


def identity(query):
    return hashlib.sha256(re.sub(r'\s+', ' ', query).strip().casefold().encode()).hexdigest()


def batch_queries(batch):
    payload = json.loads(batch['input_json'])
    if batch['source'] == 'indeed':
        return [payload.get('position', '')]
    if batch['source'] == 'linkedin':
        return [parse_qs(urlsplit(url).query).get('keywords', [''])[0] for url in payload.get('urls', [])]
    if batch['source'] == 'google':
        return payload.get('queries', '').splitlines()
    return []


def account_headroom(c, campaign_id, account):
    rows = c.execute('SELECT reserved_units,charge_units FROM campaign_batches WHERE campaign_id=? AND account_id=? AND reserved_at IS NOT NULL',
                     (campaign_id, account['account_id'])).fetchall()
    caps = sum(max(r['reserved_units'], r['charge_units'] or 0) for r in rows)
    charges = sum(r['charge_units'] or 0 for r in rows)
    ancillary = max(0, account['delta_units'] - charges)
    used = max(account['usage_units'], account['baseline_units'] + caps + ancillary)
    return max(0, account['limit_units'] - used - units(.15))


def expansion_candidates(source, jobs):
    """Search intent only: never treat a query as candidate or vacancy facts."""
    families = list(dict.fromkeys(CORE + HISTORICAL + [
        'Content Marketing Executive', 'Brand Executive', 'Marketing Coordinator',
        'Communications Coordinator', 'Account Executive', 'Community Executive']))
    skills = ['content strategy', 'social media campaigns', 'copywriting', 'event coordination',
              'stakeholder communications', 'market research', 'Thai language', 'regional partnerships']
    industries = ['hospitality', 'travel', 'retail', 'consumer goods', 'education', 'technology', 'media', 'events']
    seniorities = ['junior', 'entry level', 'associate', 'executive']
    agencies = ['Adecco', 'Randstad', 'Hays', 'Michael Page', 'Recruit Express', 'Robert Walters', 'Manpower']
    employers = sorted({str(j.get('company', '')).strip() for j in jobs
                        if j.get('company') and j['company'] not in ('Not stated', 'Verified via Search Result')})
    # Interleave dimensions so a short capacity-limited burst covers more than
    # the first role family or alphabetically first employers.
    for i in range(max(len(employers)*5, len(families)*len(skills)*5)):
        family = families[i % len(families)]
        if source == 'google':
            if i < len(employers):
                yield f'"{employers[i]}" Singapore official careers vacancies'
            if i < len(agencies):
                yield f'"{agencies[i]}" Singapore marketing communications jobs'
        else:
            dimension=i%5
            if dimension==0:
                yield f'{family} {skills[(i // len(families) + i) % len(skills)]}'
            elif dimension==1 or dimension==3 and not employers:
                yield f'{family} {industries[(i // len(families) + i) % len(industries)]}'
            elif dimension==2:
                yield f'{seniorities[(i // len(families) + i) % len(seniorities)]} {family}'
            elif dimension==3:
                yield f'{family} "{employers[(i//5)%len(employers)]}"'
            else:
                yield f'{family} "{agencies[(i//5)%len(agencies)]}"'


class Bursts:
    def __init__(self, journal):
        self.journal, self.store = journal, journal.store

    def current(self):
        with self.store._connection() as c:
            row = c.execute('SELECT * FROM campaign_bursts ORDER BY created_at DESC LIMIT 1').fetchone()
            return dict(row) if row else None

    def in_window(self, now):
        row = self.current()
        return row if row and row['window_start'] <= now < row['window_end'] else None

    def create(self, burst_id, now):
        if not isinstance(burst_id, str) or not re.fullmatch(r'[a-zA-Z0-9_-]{8,80}', burst_id):
            raise ValueError('Provide a stable burst_id of 8–80 letters, digits, hyphens or underscores.')
        campaign = self.journal.current()
        if not campaign:
            raise ValueError('An active production campaign is required.')
        with self.store._connection(write=True) as c:
            existing = c.execute('SELECT * FROM campaign_bursts WHERE campaign_id=?', (campaign['id'],)).fetchone()
            if existing:
                if existing['id'] != burst_id:
                    raise ValueError('This campaign already has its authorized one-day burst; reuse its burst_id.')
                return dict(existing)
            if campaign['state'] != 'active' or campaign['mode'] != 'production' or not campaign['stops_at'] or now >= campaign['stops_at']:
                raise ValueError('An active, unexpired production campaign is required.')
            accounts = c.execute('SELECT * FROM campaign_accounts WHERE campaign_id=?', (campaign['id'],)).fetchall()
            if not accounts or any(now-a['checked_at']>300 or a['error'] for a in accounts):
                raise ValueError('Fresh verified account accounting is required.')
            capacity = sum(account_headroom(c, campaign['id'], a) for a in accounts
                           if a['available'] and (not a['expiry'] or a['expiry'] > now))
            rows, _, caps, _, observed, extra = self.journal._exposure(c, campaign['id'], now)
            capacity = max(0, min(capacity, units(315)-caps, units(350)-caps-extra, units(200)))
            local_day, start, end = day_window(now)
            c.execute('''INSERT INTO campaign_bursts
                (id,campaign_id,local_day,window_start,window_end,created_at,target_units,soft_units,state,
                 baseline_charge_units,baseline_usage_units,initial_capacity_units,capacity_units,shortfall_units,checked_at)
                 VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                (burst_id,campaign['id'],local_day,start,min(end,campaign['stops_at']),now,units(150),units(200),'active',
                 sum(r['charge_units'] or 0 for r in rows),observed,capacity,capacity,units(150),now))
            for source, (target, soft) in ALLOCATIONS.items():
                c.execute('INSERT INTO campaign_burst_sources(burst_id,source,target_units,soft_units) VALUES(?,?,?,?)',
                          (burst_id,source,units(target),units(soft)))
            for batch in c.execute('SELECT * FROM campaign_batches WHERE campaign_id=?', (campaign['id'],)).fetchall():
                for query in batch_queries(batch):
                    if query:
                        c.execute('INSERT OR IGNORE INTO campaign_query_identities VALUES(?,?,?,?,?)',
                                  (campaign['id'],batch['source'],identity(query),query,batch['id']))
            self.event(c, burst_id, now, 'started', {'capacity_usd':capacity/1e6,'incremental_target_usd':150,'soft_cap_usd':200})
        return self.current()

    @staticmethod
    def event(c, bid, now, kind, detail):
        c.execute('INSERT INTO campaign_burst_events(burst_id,at,kind,detail_json) VALUES(?,?,?,?)', (bid,now,kind,encode(detail)))

    def metrics(self, c, burst, now):
        rows = c.execute('SELECT * FROM campaign_batches WHERE burst_id=?', (burst['id'],)).fetchall()
        reserved = sum(max(r['reserved_units'],r['charge_units'] or 0) for r in rows if r['reserved_at'] is not None)
        charged = sum(r['charge_units'] or 0 for r in rows)
        all_rows, _, _, _, _, _ = self.journal._exposure(c,burst['campaign_id'],now)
        observed = c.execute('SELECT COALESCE(SUM(delta_units),0) FROM campaign_usage WHERE campaign_id=? AND observed_at>? AND observed_at<=?',
                             (burst['campaign_id'],burst['created_at'],burst['window_end'])).fetchone()[0]
        ancillary = max(0, observed - (sum(r['charge_units'] or 0 for r in all_rows if r['reserved_at']<burst['window_end'])-burst['baseline_charge_units']))
        accounts = c.execute('SELECT * FROM campaign_accounts WHERE campaign_id=?',(burst['campaign_id'],)).fetchall()
        # Temporarily occupied accounts still have capacity; availability controls
        # launch selection, never falsely closes a burst while its runs execute.
        remaining = sum(account_headroom(c,burst['campaign_id'],a) for a in accounts
                        if not a['error'] and (not a['expiry'] or a['expiry']>now))
        capacity = min(burst['initial_capacity_units'],reserved+remaining)
        return rows, reserved, charged, ancillary, capacity, accounts

    def budget_reason(self, c, campaign, batch, amount, now):
        active = c.execute('SELECT * FROM campaign_bursts WHERE campaign_id=?',(campaign['id'],)).fetchone()
        if not batch['burst_id']:
            if active and active['window_start'] <= now < active['window_end']:
                return 'Recurring paid admissions wait until the one-day burst window ends.'
            return None
        if not active or active['id'] != batch['burst_id'] or active['state'] not in OPEN or not active['window_start'] <= now < active['window_end']:
            return 'Burst paid admissions have stopped.'
        rows, reserved, charged, ancillary, capacity, accounts = self.metrics(c,active,now)
        if not accounts or any(now-a['checked_at']>300 or a['error'] for a in accounts):
            return 'Burst account accounting is stale or unresolved.'
        if reserved+amount+ancillary > active['soft_units']:
            return 'Burst US$200 soft cap is fully committed.'
        if reserved+amount > capacity:
            return 'Burst verified capacity is fully committed.'
        allocation = c.execute('SELECT * FROM campaign_burst_sources WHERE burst_id=? AND source=?', (active['id'],batch['source'])).fetchone()
        if allocation['state'] != 'active':
            return 'Burst source stopped: '+str(allocation['reason'])
        used = sum(max(r['reserved_units'],r['charge_units'] or 0) for r in rows if r['source']==batch['source'])
        if used+amount > allocation['soft_units']:
            return 'Burst source soft allocation is fully committed.'
        if used+amount > allocation['target_units'] and batch['source'] in ('indeed','linkedin'):
            latest = c.execute('SELECT * FROM campaign_burst_tranches WHERE burst_id=? AND source=? ORDER BY tranche DESC LIMIT 1', (active['id'],batch['source'])).fetchone()
            if not latest or latest['new_count'] == 0:
                return 'Expansion beyond the source target needs fresh supported vacancies.'
        # Keep a minimum discovery/validation slice while either source has
        # useful queued work. They are allocations, never obligations to spend.
        if batch['source'] in ('indeed','linkedin'):
            protected = 0
            for source, minimum in (('google', units(1)), ('careers', units(2))):
                pending = any(r['source']==source and r['state']=='queued' for r in rows)
                spent = sum(r['reserved_units'] for r in rows if r['source']==source)
                if pending:
                    protected += max(0,minimum-spent)
            if reserved+amount+protected > capacity:
                return 'Remaining burst capacity protects discovery and career validation.'
        if batch['source']=='google':
            _, start, end = day_window(now)
            daily = c.execute("SELECT * FROM campaign_batches WHERE campaign_id=? AND source='google' AND reserved_at>=? AND reserved_at<? AND COALESCE(json_extract(context_json,'$.pilot'),0)=0", (campaign['id'],start,end)).fetchall()
            if len(daily)>=2 or len({identity(q) for r in daily for q in batch_queries(r)} | {identity(q) for q in batch_queries(batch)})>40:
                return 'Google daily query/batch allowance is fully committed.'
        return None

    def reconcile(self, now, account_error=None):
        burst = self.current()
        if not burst:
            return
        with self.store._connection(write=True) as c:
            rows, reserved, charged, ancillary, capacity, accounts = self.metrics(c,burst,now)
            state, reason = burst['state'], burst['reason']
            if state in OPEN:
                if now>=burst['window_end']:
                    state,reason='window_ended','Asia/Singapore burst window ended; recurring policy restored.'
                elif account_error or any(a['error'] for a in accounts):
                    state,reason='account_error',account_error or 'Account accounting needs reconciliation.'
                elif reserved+ancillary+units(.25)>burst['soft_units']:
                    state,reason='soft_cap','US$200 conservative exposure limit reached.'
                elif capacity-reserved<units(.25) or not any(account_headroom(c,burst['campaign_id'],a)>=units(.25) for a in accounts):
                    state,reason='capacity','Verified account capacity is committed; no overage is permitted.'
                elif charged>=burst['target_units']:
                    state,reason='target_reached','Incremental charge target reached; only queued work and value-supported expansion remain eligible.'
            if state != burst['state']:
                self.event(c,burst['id'],now,state,{'reason':reason})
            c.execute('UPDATE campaign_bursts SET state=?,reason=?,reserved_units=?,charged_units=?,ancillary_units=?,capacity_units=?,shortfall_units=?,checked_at=? WHERE id=?',
                      (state,reason,reserved,charged,ancillary,capacity,max(0,burst['target_units']-charged),now,burst['id']))
            # Completed tranches are immutable outcome snapshots; interrupted
            # imports cannot trigger reallocation early or twice after restart.
            groups = {}
            for row in rows:
                if row['burst_tranche'] is not None and row['source'] in ('indeed','linkedin'):
                    groups.setdefault((row['source'],row['burst_tranche']),[]).append(row)
            for (source,tranche),group in sorted(groups.items()):
                if any(r['state'] not in ('done','failed') or r['charge_units'] is None for r in group):
                    continue
                counts = [sum(r[k] for r in group) for k in ('new_count','duplicate_count','lead_count','updated_count')]
                cost = sum(r['charge_units'] for r in group)
                ratio = (counts[1]+counts[2])/sum(counts) if sum(counts) else 0
                c.execute('INSERT OR IGNORE INTO campaign_burst_tranches VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                          (burst['id'],source,tranche,now,*counts,cost,ratio,counts[0]/(cost/1e6) if cost else None))
            for source in ('indeed','linkedin'):
                latest = c.execute('SELECT * FROM campaign_burst_tranches WHERE burst_id=? AND source=? ORDER BY tranche DESC LIMIT 2', (burst['id'],source)).fetchall()
                if len(latest)==2 and all(r['new_count']==0 and r['duplicate_lead_ratio']>.8 for r in latest):
                    donor=c.execute('SELECT * FROM campaign_burst_sources WHERE burst_id=? AND source=?',(burst['id'],source)).fetchone()
                    if donor['state']=='active':
                        reason='Two consecutive tranches returned no fresh supported vacancy and over 80% duplicates/leads.'
                        c.execute("UPDATE campaign_burst_sources SET state='value_stopped',reason=? WHERE burst_id=? AND source=?",(reason,burst['id'],source))
                        recipient='linkedin' if source=='indeed' else 'indeed'
                        receiver=c.execute('SELECT * FROM campaign_burst_sources WHERE burst_id=? AND source=?',(burst['id'],recipient)).fetchone()
                        if receiver['state']=='active':
                            committed=sum(max(r['reserved_units'],r['charge_units'] or 0) for r in rows if r['source']==source)
                            target=max(0,donor['target_units']-committed)
                            soft=max(0,donor['soft_units']-committed)
                            c.execute('UPDATE campaign_burst_sources SET target_units=target_units-?,soft_units=soft_units-? WHERE burst_id=? AND source=?',(target,soft,burst['id'],source))
                            c.execute('UPDATE campaign_burst_sources SET target_units=target_units+?,soft_units=soft_units+? WHERE burst_id=? AND source=?',(target,soft,burst['id'],recipient))
                            self.event(c,burst['id'],now,'reallocation',{'from':source,'to':recipient,'target_usd':target/1e6,'soft_usd':soft/1e6,'reason':reason})
            if state in OPEN and not any(r['state'] in ACTIVE for r in rows):
                allocations=c.execute('SELECT * FROM campaign_burst_sources WHERE burst_id=?',(burst['id'],)).fetchall()
                queued=[r for r in rows if r['state']=='queued' and any(s['source']==r['source'] and s['state']=='active' for s in allocations)]
                if queued and not any(account_headroom(c,burst['campaign_id'],a)>=units(json.loads(r['context_json'])['cap_usd']) for a in accounts for r in queued):
                    c.execute("UPDATE campaign_bursts SET state='capacity',reason='Remaining account fragments cannot admit another eligible batch.' WHERE id=?",(burst['id'],))
                    self.event(c,burst['id'],now,'capacity',{'reason':'Remaining account fragments cannot admit another eligible batch.'})

    def enqueue_searches(self, source, queries, tranche, now):
        burst=self.current()
        with self.store._connection(write=True) as c:
            chosen=[]
            seen=set()
            for query in queries:
                if identity(query) not in seen and not c.execute('SELECT 1 FROM campaign_query_identities WHERE campaign_id=? AND source=? AND identity=?', (burst['campaign_id'],source,identity(query))).fetchone():
                    chosen.append(query)
                    seen.add(identity(query))
            if not chosen:
                return 0
            groups=[chosen] if source=='google' else [[q] for q in chosen]
            for group in groups:
                bid=uuid.uuid4().hex
                context={'burst_id':burst['id'],'tranche':tranche,'queries':group,'query':group[0] if len(group)==1 else '\n'.join(group),
                         'query_identities':[identity(q) for q in group],'cap_usd':CAPS[source]}
                c.execute('''INSERT INTO campaign_batches(id,campaign_id,source,batch_key,input_json,context_json,state,created_at,burst_id,burst_tranche)
                    VALUES(?,?,?,?,?,?,'queued',?,?,?)''',
                    (bid,burst['campaign_id'],source,'burst:'+bid,encode(input_for(source,'\n'.join(group))),encode(context),now,burst['id'],tranche))
                for query in group:
                    c.execute('INSERT INTO campaign_query_identities VALUES(?,?,?,?,?)',(burst['campaign_id'],source,identity(query),query,bid))
            return len(chosen)

    def schedule(self, worker, now):
        burst=self.in_window(now)
        if not burst or burst['state'] not in OPEN:
            return
        report=self.report(now)
        rows=self.journal.batches()
        current=[r for r in rows if r['burst_id']==burst['id']]
        jobs=None
        def candidates(source, count):
            nonlocal jobs
            if jobs is None:
                jobs=self.store.list_jobs()
            used={identity(q) for r in rows if r['source']==source for q in batch_queries(r)}
            selected=[]
            for query in expansion_candidates(source,jobs):
                key=identity(query)
                if key not in used:
                    selected.append(query);used.add(key)
                if len(selected)==count:
                    break
            return selected
        google=[r for r in rows if r['source']=='google' and
                (r['reserved_at'] is not None and burst['window_start']<=r['reserved_at']<burst['window_end'] or
                 r['burst_id']==burst['id'] and r['state']=='queued') and not json.loads(r['context_json']).get('pilot')]
        google_count=len({identity(q) for r in google for q in batch_queries(r)})
        if len(google)<2 and google_count<40:
            self.enqueue_searches('google',candidates('google',min(20,40-google_count)),len(google),now)
        else:
            with self.store._connection(write=True) as c:
                c.execute("UPDATE campaign_burst_sources SET reason='Daily Google discovery allowance already scheduled or consumed.' WHERE burst_id=? AND source='google'",(burst['id'],))
        career=next(s for s in report['sources'] if s['source']=='careers')
        career_pending=[r for r in current if r['source']=='careers' and r['state'] in (*ACTIVE,'queued')]
        if not career_pending and career['reserved_usd']+.5<=career['soft_allocation_usd']:
            # Reuse unlaunched queue membership. This does not repeat a paid
            # crawl or edit its payload, evidence or import checkpoint.
            candidates_career=[r for r in rows if r['source']=='careers' and not r['burst_id'] and r['state']=='queued' and not json.loads(r['context_json']).get('pilot')]
            def priority(batch):
                context=json.loads(batch['context_json'])
                return (not context.get('priority'),not context.get('recheck'),context.get('oldest_success_at') or '',batch['created_at'],batch['id'])
            candidates_career.sort(key=priority)
            limit=min(2,int((career['soft_allocation_usd']-career['reserved_usd'])/.5))
            if candidates_career:
                with self.store._connection(write=True) as c:
                    for batch in candidates_career[:limit]:
                        c.execute("UPDATE campaign_batches SET burst_id=?,retry_at=0,error=NULL WHERE id=? AND state='queued' AND reserved_at IS NULL",(burst['id'],batch['id']))
            else:
                worker.schedule_careers(now,0,seed_rechecks=True,burst_id=burst['id'],batch_limit=limit)
        # Each tranche is two bounded queries. Finish/import it before deciding
        # the next source. Both sources get two measurement tranches first.
        if any(r['source'] in ('indeed','linkedin') and r['state'] in (*ACTIVE,'queued') for r in current):
            return
        sources={s['source']:s for s in report['sources']}
        order=sorted(report['ranking'],key=lambda name:(len(sources[name]['tranches'])>=2,report['ranking'].index(name)))
        for name in order:
            source=sources[name]
            if source['state']!='active' or source['reserved_usd']+CAPS[name]>source['soft_allocation_usd']:
                continue
            if report['charged_usd']>=150 and (not source['tranches'] or not source['tranches'][-1]['new_count']):
                continue
            if source['reserved_usd']+CAPS[name]>source['target_allocation_usd'] and (not source['tranches'] or not source['tranches'][-1]['new_count']):
                continue
            count=min(2,int((source['soft_allocation_usd']-source['reserved_usd'])/CAPS[name]))
            tranche=max([r['burst_tranche'] or 0 for r in current if r['source']==name],default=0)+1
            if self.enqueue_searches(name,candidates(name,count),tranche,now):
                break
        else:
            with self.store._connection(write=True) as c:
                pending=c.execute("SELECT 1 FROM campaign_batches WHERE burst_id=? AND state IN ('queued','launching','ambiguous','running','importing') LIMIT 1",(burst['id'],)).fetchone()
                if not pending:
                    reason='No unused input or source expansion still passes the value/allocation rules.'
                    c.execute("UPDATE campaign_bursts SET state='value_exhausted',reason=? WHERE id=?",(reason,burst['id']))
                    self.event(c,burst['id'],now,'value_exhausted',{'reason':reason})

    def settle_admission(self, batch, reason, now):
        """Permanent admission limits must not leave a retrying queue forever."""
        if not batch['burst_id']:
            return
        state = ('soft_cap' if 'US$200' in reason else 'campaign_cap' if 'Campaign budget' in reason else
                 'capacity' if 'verified capacity' in reason else None)
        with self.store._connection(write=True) as c:
            if state:
                c.execute('UPDATE campaign_bursts SET state=?,reason=? WHERE id=?',(state,reason,batch['burst_id']))
                self.event(c,batch['burst_id'],now,state,{'reason':reason})
            elif 'source soft allocation' in reason or 'Expansion beyond' in reason:
                c.execute("UPDATE campaign_burst_sources SET state='allocation_complete',reason=? WHERE burst_id=? AND source=?",(reason,batch['burst_id'],batch['source']))

    def close_queued(self, now):
        burst=self.current()
        if not burst:
            return
        with self.store._connection(write=True) as c:
            stopped={r['source'] for r in c.execute("SELECT source FROM campaign_burst_sources WHERE burst_id=? AND state!='active'",(burst['id'],))}
            for row in c.execute("SELECT * FROM campaign_batches WHERE burst_id=? AND state='queued'",(burst['id'],)).fetchall():
                if burst['state'] in OPEN and now<burst['window_end'] and row['source'] not in stopped:
                    continue
                c.execute("UPDATE campaign_batches SET state='superseded',error='Burst admission stopped; no paid launch.' WHERE id=?",(row['id'],))
                if row['source']=='careers':
                    for url in json.loads(row['context_json']).get('urls',[]):
                        c.execute("UPDATE campaign_discovery SET state='queued' WHERE campaign_id=? AND url=? AND state='scheduled'",(burst['campaign_id'],url))

    def report(self, now):
        burst=self.current()
        if not burst:
            return None
        with self.store._connection() as c:
            rows,reserved,charged,ancillary,capacity,_=self.metrics(c,burst,now)
            sources=[]
            for source in c.execute('SELECT * FROM campaign_burst_sources WHERE burst_id=? ORDER BY source',(burst['id'],)):
                relevant=[r for r in rows if r['source']==source['source']]
                tranches=[dict(r) for r in c.execute('SELECT * FROM campaign_burst_tranches WHERE burst_id=? AND source=? ORDER BY tranche',(burst['id'],source['source']))]
                sources.append({'source':source['source'],'state':source['state'],'reason':source['reason'],
                    'target_allocation_usd':source['target_units']/1e6,'soft_allocation_usd':source['soft_units']/1e6,
                    'reserved_usd':sum(max(r['reserved_units'],r['charge_units'] or 0) for r in relevant)/1e6,
                    'charged_usd':sum(r['charge_units'] or 0 for r in relevant)/1e6,
                    **{k:sum(r[k] for r in relevant) for k in ('new_count','updated_count','duplicate_count','lead_count')},
                    'failures':sum(r['state']=='failed' or bool(r['error_category']) for r in relevant),
                    'queued':sum(r['state']=='queued' for r in relevant),'tranches':tranches})
            events=[{**dict(r),'detail':json.loads(r['detail_json'])} for r in c.execute('SELECT * FROM campaign_burst_events WHERE burst_id=? ORDER BY id',(burst['id'],))]
        ranking=sorted([s for s in sources if s['source'] in ('indeed','linkedin')],key=lambda s:(
            -(s['tranches'][-1]['fresh_per_dollar'] or 0) if s['tranches'] else 0,
            s['tranches'][-1]['duplicate_lead_ratio'] if s['tranches'] else 0,s['source']))
        return {'id':burst['id'],'campaign_id':burst['campaign_id'],'local_day':burst['local_day'],'timezone':'Asia/Singapore',
                'window_start':burst['window_start'],'window_end':burst['window_end'],'started_at':burst['created_at'],
                'state':burst['state'],'reason':burst['reason'],'target_usd':burst['target_units']/1e6,'soft_cap_usd':burst['soft_units']/1e6,
                'baseline_campaign_charged_usd':burst['baseline_charge_units']/1e6,
                'charged_usd':charged/1e6,'reserved_exposure_usd':reserved/1e6,'observed_ancillary_usd':ancillary/1e6,
                'total_exposure_usd':(reserved+ancillary)/1e6,'initial_capacity_ceiling_usd':burst['initial_capacity_units']/1e6,
                'capacity_ceiling_usd':capacity/1e6,'capacity_shortfall_usd':max(0,burst['target_units']-capacity)/1e6,
                'shortfall_usd':max(0,burst['target_units']-charged)/1e6,
                'pending_imports':sum(r['state'] in ACTIVE for r in rows),
                'ranking':[s['source'] for s in ranking],'sources':sources,'events':events,
                'recurring_policy_restored':now>=burst['window_end'],
                'accounting_note':'Incremental actor charges; completed caps stay committed. Observed ancillary/shared-account usage is separate. Capacity is a ceiling, not promised spend.'}
