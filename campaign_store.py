"""Transactional campaign journal. Amounts are integer millionths of a US dollar.

Reservations are conservative: a completed batch keeps its original cap in the
admission ledger, so delayed billing can never turn into newly spendable money.
The separately reported actual charges never pretend that a reservation is spend.
"""
import json
import time
import uuid
from decimal import Decimal, ROUND_CEILING

DAY = 86400
ALLOWANCES = {'linkedin': 8, 'indeed': 22, 'google': 3, 'careers': 12}
ACTIVE = ('launching', 'ambiguous', 'running', 'importing')


def units(value):
    return int((Decimal(str(value)) * 1_000_000).to_integral_value(rounding=ROUND_CEILING))


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def initialize(connection):
    # Called inside Store's migration transaction. No application rows change.
    statements = [
        '''CREATE TABLE IF NOT EXISTS campaigns (
            id TEXT PRIMARY KEY, state TEXT NOT NULL, started_at REAL, stops_at REAL,
            created_at REAL NOT NULL, reason TEXT, mode TEXT NOT NULL DEFAULT 'pilot',
            owner TEXT, lease_until REAL, heartbeat REAL)''',
        '''CREATE TABLE IF NOT EXISTS campaign_sources (
            campaign_id TEXT NOT NULL, source TEXT NOT NULL, due_at REAL NOT NULL,
            cycle INTEGER NOT NULL DEFAULT 0, last_attempt REAL, last_success REAL,
            blocked_reason TEXT, PRIMARY KEY(campaign_id,source))''',
        '''CREATE TABLE IF NOT EXISTS campaign_accounts (
            campaign_id TEXT NOT NULL, account_id TEXT NOT NULL, reference TEXT NOT NULL,
            baseline_units INTEGER NOT NULL, usage_units INTEGER NOT NULL,
            delta_units INTEGER NOT NULL DEFAULT 0, cycle TEXT NOT NULL,
            limit_units INTEGER NOT NULL, checked_at REAL NOT NULL, expiry REAL,
            available INTEGER NOT NULL, error TEXT, PRIMARY KEY(campaign_id,account_id))''',
        '''CREATE TABLE IF NOT EXISTS campaign_batches (
            id TEXT PRIMARY KEY, campaign_id TEXT NOT NULL, source TEXT NOT NULL,
            batch_key TEXT NOT NULL, input_json TEXT NOT NULL, context_json TEXT NOT NULL,
            state TEXT NOT NULL, created_at REAL NOT NULL, account_id TEXT,
            reserved_units INTEGER NOT NULL DEFAULT 0, reserved_at REAL, finished_at REAL,
            run_id TEXT UNIQUE, dataset_id TEXT, remote_status TEXT, charge_units INTEGER,
            checkpoint INTEGER NOT NULL DEFAULT 0, new_count INTEGER NOT NULL DEFAULT 0,
            updated_count INTEGER NOT NULL DEFAULT 0, duplicate_count INTEGER NOT NULL DEFAULT 0,
            lead_count INTEGER NOT NULL DEFAULT 0, error TEXT, retry_at REAL NOT NULL DEFAULT 0,
            attempts INTEGER NOT NULL DEFAULT 0, UNIQUE(campaign_id,batch_key))''',
        '''CREATE TABLE IF NOT EXISTS campaign_items (
            batch_id TEXT NOT NULL, item_index INTEGER NOT NULL, payload_json TEXT NOT NULL,
            job_id TEXT, outcome TEXT NOT NULL, PRIMARY KEY(batch_id,item_index))''',
        '''CREATE TABLE IF NOT EXISTS campaign_pilot_jobs (
            campaign_id TEXT NOT NULL, job_id TEXT NOT NULL, data_json TEXT NOT NULL,
            PRIMARY KEY(campaign_id,job_id))''',
        '''CREATE TABLE IF NOT EXISTS campaign_discovery (
            campaign_id TEXT NOT NULL, url TEXT NOT NULL, domain TEXT NOT NULL,
            parent_url TEXT, root_url TEXT NOT NULL, depth INTEGER NOT NULL,
            state TEXT NOT NULL, discovered_at REAL NOT NULL, checked_at REAL,
            evidence_json TEXT NOT NULL, reason TEXT, PRIMARY KEY(campaign_id,url))''',
        '''CREATE TABLE IF NOT EXISTS campaign_edges (
            campaign_id TEXT NOT NULL, parent_url TEXT NOT NULL, child_url TEXT NOT NULL,
            evidence_json TEXT NOT NULL, PRIMARY KEY(campaign_id,parent_url,child_url))''',
        '''CREATE TABLE IF NOT EXISTS campaign_usage (
            id INTEGER PRIMARY KEY AUTOINCREMENT, campaign_id TEXT NOT NULL,
            account_id TEXT NOT NULL, observed_at REAL NOT NULL, delta_units INTEGER NOT NULL)''',
        'CREATE INDEX IF NOT EXISTS campaign_batch_state ON campaign_batches(campaign_id,state)',
    ]
    for statement in statements:
        connection.execute(statement)


class CampaignStore:
    def __init__(self, store):
        self.store = store

    def current(self):
        with self.store._connection() as c:
            row = c.execute('SELECT * FROM campaigns ORDER BY created_at DESC LIMIT 1').fetchone()
            return dict(row) if row else None

    def create(self, now=None):
        now = time.time() if now is None else now
        with self.store._connection(write=True) as c:
            if c.execute('SELECT 1 FROM campaigns').fetchone():
                raise ValueError('A campaign already exists; its clock and budget cannot be reset.')
            cid = uuid.uuid4().hex
            c.execute("INSERT INTO campaigns(id,state,created_at,mode) VALUES(?,'prepared',?,'pilot')", (cid, now))
            for source in ALLOWANCES:
                c.execute('INSERT INTO campaign_sources(campaign_id,source,due_at) VALUES(?,?,?)', (cid, source, now))
        return self.current()

    def state(self, state, reason=None):
        if state not in ('pilot', 'active', 'paused', 'stopped', 'prepared'):
            raise ValueError('Unknown campaign state')
        with self.store._connection(write=True) as c:
            row = c.execute('SELECT * FROM campaigns ORDER BY created_at DESC LIMIT 1').fetchone()
            if not row:
                raise ValueError('No campaign is prepared')
            if row['state'] == 'stopped' or row['stops_at'] and time.time() >= row['stops_at']:
                state, reason = 'stopped', 'The 168-hour campaign has ended.'
            if state == 'active' and row['mode'] != 'production':
                raise ValueError('Pilot verification and production activation have not been recorded.')
            c.execute('UPDATE campaigns SET state=?,reason=? WHERE id=?', (state, reason, row['id']))
        return self.current()

    def activate(self, evidence):
        if not isinstance(evidence, dict) or not all(evidence.get(k) for k in ('pilot_verified', 'backup_verified', 'contracts_verified')):
            raise ValueError('Activation requires verified pilot, backup and actor contracts.')
        row = self.current()
        if not row or not row['started_at']:
            raise ValueError('A paid pilot must establish the campaign clock first.')
        with self.store._connection(write=True) as c:
            c.execute("UPDATE campaigns SET mode='production' WHERE id=?", (row['id'],))
            c.execute('INSERT INTO metadata VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json',
                      ('campaign_activation', encode(evidence)))
        return self.state('active')

    def claim(self, owner, now):
        with self.store._connection(write=True) as c:
            row = c.execute('SELECT * FROM campaigns ORDER BY created_at DESC LIMIT 1').fetchone()
            if not row:
                return False
            if row['owner'] != owner and (row['lease_until'] or 0) > now:
                return False
            c.execute('UPDATE campaigns SET owner=?,lease_until=?,heartbeat=? WHERE id=?', (owner, now + 180, now, row['id']))
            return True

    def account(self, snapshot, now):
        row = self.current()
        aid = snapshot['account_id']
        with self.store._connection(write=True) as c:
            old = c.execute('SELECT * FROM campaign_accounts WHERE campaign_id=? AND account_id=?', (row['id'], aid)).fetchone()
            usage = units(snapshot['usage_usd'])
            cycle = encode(snapshot['cycle'])
            error = snapshot.get('error')
            if old and (old['cycle'] != cycle or usage < old['usage_units']):
                error = 'Usage cycle changed or usage decreased; reconciliation required.'
            delta = max(0, usage - old['usage_units']) if old and not error else 0
            if delta:
                c.execute('INSERT INTO campaign_usage(campaign_id,account_id,observed_at,delta_units) VALUES(?,?,?,?)', (row['id'], aid, now, delta))
            c.execute('''INSERT INTO campaign_accounts VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(campaign_id,account_id) DO UPDATE SET reference=excluded.reference,
                usage_units=excluded.usage_units,delta_units=campaign_accounts.delta_units+?,
                limit_units=excluded.limit_units,checked_at=excluded.checked_at,available=excluded.available,error=excluded.error''',
                (row['id'], aid, snapshot['reference'], old['baseline_units'] if old else usage, max(usage,old['usage_units']) if old else usage,
                 old['delta_units'] if old else 0, old['cycle'] if old else cycle,
                 units(snapshot['limit_usd']), now, snapshot.get('expiry'), int(snapshot['available'] and not error), error, delta))

    def accounts(self):
        row = self.current()
        if not row:
            return []
        with self.store._connection() as c:
            return [dict(r) for r in c.execute('SELECT * FROM campaign_accounts WHERE campaign_id=? ORDER BY expiry IS NULL,expiry,account_id', (row['id'],))]

    def enqueue(self, source, key, payload, context, now):
        row = self.current()
        with self.store._connection(write=True) as c:
            c.execute('''INSERT OR IGNORE INTO campaign_batches
                (id,campaign_id,source,batch_key,input_json,context_json,state,created_at) VALUES(?,?,?,?,?,?,'queued',?)''',
                (uuid.uuid4().hex, row['id'], source, key, encode(payload), encode(context), now))

    def batches(self, states=None):
        row = self.current()
        if not row:
            return []
        with self.store._connection() as c:
            query = 'SELECT * FROM campaign_batches WHERE campaign_id=?'
            params = [row['id']]
            if states:
                query += ' AND state IN (' + ','.join('?' for _ in states) + ')'
                params.extend(states)
            return [dict(r) for r in c.execute(query + ' ORDER BY created_at,id', params)]

    @staticmethod
    def _exposure(c, cid, now):
        rows = c.execute('SELECT * FROM campaign_batches WHERE campaign_id=? AND reserved_at IS NOT NULL', (cid,)).fetchall()
        caps = sum(max(r['reserved_units'], r['charge_units'] or 0) for r in rows)
        recent = [r for r in rows if r['finished_at'] is None or r['finished_at'] > now - DAY]
        rolling = sum(max(r['reserved_units'], r['charge_units'] or 0) for r in recent)
        observed = c.execute('SELECT COALESCE(SUM(delta_units),0) FROM campaign_usage WHERE campaign_id=?', (cid,)).fetchone()[0]
        # Every non-run charge (storage, reads, transfers, external activity) is
        # counted. Retaining the extra throughout the campaign is conservative
        # across API billing delays and rolling-window boundaries.
        extra = max(0, observed - sum(r['charge_units'] or 0 for r in rows))
        return rows, recent, caps, rolling, observed, extra

    def reserve(self, batch_id, account_id, dollars, owner, now):
        amount = units(dollars)
        if amount <= 0 or amount > units(2):
            raise ValueError('Each batch must reserve more than zero and at most US$2.')
        with self.store._connection(write=True) as c:
            b = c.execute('SELECT * FROM campaign_batches WHERE id=?', (batch_id,)).fetchone()
            if not b or b['state'] != 'queued':
                return False, 'Batch is no longer queued.'
            campaign = c.execute('SELECT * FROM campaigns WHERE id=?', (b['campaign_id'],)).fetchone()
            if campaign['owner'] != owner or (campaign['lease_until'] or 0) <= now:
                return False, 'Scheduler lease is unavailable.'
            if campaign['stops_at'] and now >= campaign['stops_at']:
                c.execute("UPDATE campaigns SET state='stopped',reason='168-hour limit reached' WHERE id=?", (campaign['id'],))
                return False, 'Campaign ended.'
            if campaign['state'] not in ('pilot', 'active'):
                return False, 'Paid collection is paused.'
            accounts = c.execute('SELECT * FROM campaign_accounts WHERE campaign_id=?', (campaign['id'],)).fetchall()
            if not accounts or any(now - a['checked_at'] > 300 or a['error'] for a in accounts):
                return False, 'Account accounting is stale or unresolved.'
            active = c.execute("SELECT * FROM campaign_batches WHERE campaign_id=? AND state IN ('launching','ambiguous','running','importing')", (campaign['id'],)).fetchall()
            if len(active) >= 2 or any(r['account_id'] == account_id for r in active):
                return False, 'Concurrency limit reached.'
            account = next((a for a in accounts if a['account_id'] == account_id), None)
            if not account or not account['available'] or account['expiry'] and account['expiry'] <= now:
                return False, 'Account is unavailable.'
            rows, recent, caps, rolling, observed, extra = self._exposure(c, campaign['id'], now)
            # Reserve $35 across seven days for ancillary use; $5 each rolling day.
            total_limit = units(2.5) if campaign['mode'] == 'pilot' else units(315)
            if caps + amount > total_limit or caps + amount + extra > units(3 if campaign['mode'] == 'pilot' else 350):
                return False, 'Campaign budget is fully committed.'
            if rolling + amount > units(45) or rolling + amount + extra > units(50):
                return False, 'Rolling 24-hour budget is fully committed.'
            if sum(r['reserved_units'] for r in recent if r['source'] == b['source']) + amount > units(ALLOWANCES[b['source']]):
                return False, 'Source allowance is fully committed.'
            account_caps = sum(r['reserved_units'] for r in rows if r['account_id'] == account_id)
            # Both observed usage and campaign commitments count against the
            # verified hard limit. No cash-overage settings are ever changed.
            if max(account['usage_units'], account['baseline_units'] + account_caps) + amount + units(.15) > account['limit_units']:
                return False, 'Account credit capacity is exhausted.'
            if not campaign['started_at']:
                c.execute('UPDATE campaigns SET started_at=?,stops_at=? WHERE id=?', (now, now + 7 * DAY, campaign['id']))
            c.execute("UPDATE campaign_batches SET state='launching',account_id=?,reserved_units=?,reserved_at=?,attempts=attempts+1,error=NULL WHERE id=?", (account_id, amount, now, batch_id))
            c.execute('UPDATE campaign_sources SET last_attempt=?,blocked_reason=NULL WHERE campaign_id=? AND source=?', (now, campaign['id'], b['source']))
            return True, None

    def update_batch(self, batch_id, **fields):
        allowed = {'state','run_id','dataset_id','remote_status','charge_units','finished_at','error','retry_at','attempts'}
        if not fields or set(fields) - allowed:
            raise ValueError('Invalid run update')
        with self.store._connection(write=True) as c:
            c.execute('UPDATE campaign_batches SET ' + ','.join(k+'=?' for k in fields) + ' WHERE id=?', [*fields.values(), batch_id])

    def source(self, source, **fields):
        if set(fields) - {'due_at','cycle','blocked_reason','last_success','last_attempt'}:
            raise ValueError('Invalid source update')
        row = self.current()
        with self.store._connection(write=True) as c:
            c.execute('UPDATE campaign_sources SET ' + ','.join(k+'=?' for k in fields) + ' WHERE campaign_id=? AND source=?', [*fields.values(), row['id'], source])

    def status(self, now=None):
        now = time.time() if now is None else now
        row = self.current()
        if not row:
            return {'state':'not_prepared', 'reason':'The paid campaign has not been prepared.', 'sources':[], 'runs':[]}
        with self.store._connection() as c:
            rows, recent, caps, rolling, observed, extra = self._exposure(c, row['id'], now)
            sources = [dict(r) for r in c.execute('SELECT * FROM campaign_sources WHERE campaign_id=? ORDER BY source', (row['id'],))]
            queue = dict(c.execute('SELECT state,COUNT(*) FROM campaign_discovery WHERE campaign_id=? GROUP BY state', (row['id'],)).fetchall())
            accounts = c.execute('SELECT COUNT(*),SUM(available),SUM(expiry IS NULL) FROM campaign_accounts WHERE campaign_id=?', (row['id'],)).fetchone()
            unique = c.execute('SELECT COUNT(DISTINCT i.job_id) FROM campaign_items i JOIN campaign_batches b ON b.id=i.batch_id WHERE b.campaign_id=? AND i.job_id IS NOT NULL',(row['id'],)).fetchone()[0]
        for s in sources:
            relevant = [r for r in rows if r['source'] == s['source']]
            for key in ('new_count','updated_count','duplicate_count','lead_count'):
                s[key] = sum(r[key] for r in relevant)
            s['runs'] = len(relevant)
        return {**{k:v for k,v in row.items() if k not in ('owner','lease_until')},
                'actor_committed_usd':caps/1e6, 'rolling_actor_committed_usd':rolling/1e6,
                'reported_run_charges_usd':sum(r['charge_units'] or 0 for r in rows)/1e6,
                'observed_account_usage_usd':observed/1e6, 'ancillary_or_unreconciled_usd':extra/1e6,
                'total_ceiling_usd':350, 'rolling_ceiling_usd':50, 'pilot_ceiling_usd':3,
                'sources':sources, 'discovery':queue,
                'unique_supported_vacancies':unique,
                'shutdown_verification':self.store.get_meta('campaign_shutdown_verification'),
                'accounts':{'verified':accounts[0], 'available':accounts[1] or 0, 'unknown_expiry':accounts[2] or 0},
                'runs':[{k:r[k] for k in ('id','source','state','reserved_at','finished_at','run_id','remote_status','checkpoint','new_count','updated_count','duplicate_count','lead_count','error')} for r in rows[-100:]],
                'accounting_note':'Caps remain committed after completion. Account usage includes storage, reads and transfers; credit expiry is unknown unless independently verified.'}
