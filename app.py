"""Private, evidence-based workspace: one process and one durable SQLite store."""
import asyncio
from contextlib import asynccontextmanager, suppress
from datetime import datetime, timezone
import html
import json
import logging
import os
from pathlib import Path
import secrets
import time
from urllib.parse import urlparse
from fastapi import FastAPI, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, Response, FileResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.staticfiles import StaticFiles
from evidence import repair_jobs, present_job, draft_templates, sort_key, prepare_assessments, normalize_employment_types, parse_date
from storage import Store, Conflict, STAGES
from exports import safe_cell, JOB_HEADERS, job_row, export_response
from sync_engine import synchronize_upstream_jobs
from source_audit import build_audit, audit_records, inspect_record
from campaign import CampaignWorker, campaign_loop, disk_capacity, owned_operation
from campaign_store import CampaignStore

BASE = Path(__file__).resolve().parent
DATA_FILE = BASE / 'processed_master_jobs.json'
DB_PATH = Path(os.environ.get('DATABASE_PATH', str(BASE / 'data' / 'career.sqlite3')))
AUTH_USERNAME = os.environ.get('AUTH_USERNAME', 'Kawa')
AUTH_PASSWORD = os.environ.get('AUTH_PASSWORD', 'Kawa123')
security = HTTPBasic()
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)
REFRESH_SECONDS = 12 * 60 * 60


def verify_credentials(credentials: HTTPBasicCredentials = Depends(security)):
    if not (secrets.compare_digest(credentials.username.encode(), AUTH_USERNAME.encode())
            and secrets.compare_digest(credentials.password.encode(), AUTH_PASSWORD.encode())):
        raise HTTPException(401, 'Invalid username or password', headers={'WWW-Authenticate': 'Basic realm="SG Career Intelligence"'})
    return credentials.username


def get_store(request: Request):
    return request.app.state.store


def verified_backup(store):
    directory = store.path.parent / 'backups'
    directory.mkdir(exist_ok=True)
    path = directory / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '.sqlite3')
    result = store.backup(path)
    store.set_meta('last_backup', {'path': str(path), 'at': time.time(), 'verification': result})
    for old in sorted(directory.glob('*.sqlite3'))[:-3]:
        old.unlink()
    return path


async def run_sync(application):
    active = getattr(application.state, 'sync_run_task', None)
    if active and not active.done():
        return {'status': 'in_progress'}
    task = asyncio.create_task(_run_sync_once(application), name='source-check')
    application.state.sync_run_task = task
    # Disconnecting a browser must not release the lock while the worker thread
    # still writes. Lifespan owns and awaits this task during graceful shutdown.
    return await asyncio.shield(task)


async def _run_sync_once(application):
    async with application.state.sync_lock:
        store = application.state.store
        store.set_meta('active_sync', {'started_at':datetime.now(timezone.utc).isoformat()})
        completed = False
        try:
            result = await asyncio.to_thread(synchronize_upstream_jobs, store=store)
            try:
                await asyncio.to_thread(verified_backup, store)
                store.set_meta('last_backup_error', None)
            except Exception:
                logger.exception('Backup failed after source check')
                store.set_meta('last_backup_error', {'at':datetime.now(timezone.utc).isoformat(), 'message':'Backup failed after source check.'})
                result = {**result, 'storage_warning':'The source result was saved, but the backup could not be completed.'}
            completed = True
            return result
        except Exception:
            logger.exception('Refresh failed')
            result = {'status': 'error', 'message': 'Source refresh failed; previous evidence retained.'}
            store.record_sync(result)
            completed = True
            return result
        finally:
            if completed:
                store.set_meta('active_sync', None)
                store.set_meta('next_sync_at', time.time() + REFRESH_SECONDS)


async def refresh_loop(application):
    store = application.state.store
    while True:
        due = store.get_meta('next_sync_at', time.time() + REFRESH_SECONDS)
        await asyncio.sleep(max(0, min(60, due - time.time())))
        # A manual check may have completed while this loop slept. Its durable
        # schedule supersedes the due time read before sleeping.
        due = store.get_meta('next_sync_at', time.time() + REFRESH_SECONDS)
        if time.time() >= due:
            await run_sync(application)


@asynccontextmanager
async def lifespan(application):
    store = Store(application.state.database_path).initialize()
    application.state.store = store
    application.state.sync_lock = asyncio.Lock()
    application.state.sync_run_task = None
    if not store.get_meta('seed_version'):
        raw = json.loads(DATA_FILE.read_text(encoding='utf-8'))
        jobs = repair_jobs(raw)
        store.seed_jobs(jobs)
        store.record_source_batch([(job['id'], job.get('sources',[{'name':'Retained source'}])[0]['name'], job.get('raw_evidence',job)) for job in jobs])
        store.set_meta('seed_version', 2)
        store.set_meta('migration_job_ids', sorted(job['id'] for job in jobs))
        verified_backup(store)
    # Preparation belongs to lifespan: health checks only report ready after it
    # finishes, rather than making the first user's search do the cold work.
    logger.info('Preparing documented-fit assessments')
    await asyncio.to_thread(prepare_assessments, store.list_jobs())
    if store.get_meta('next_sync_at') is None:
        store.set_meta('next_sync_at', time.time() + REFRESH_SECONDS)
    if store.get_meta('active_sync'):
        store.record_sync({'status':'interrupted','started_at':store.get_meta('active_sync')['started_at'], 'message':'Refresh was interrupted by a restart and will be retried.'})
        store.set_meta('active_sync', None)
        store.set_meta('next_sync_at', time.time())
    task = None
    if os.environ.get('DISABLE_BACKGROUND_SYNC') != '1':
        task = asyncio.create_task(refresh_loop(application), name='source-refresh')
    application.state.refresh_task = task
    application.state.campaign_worker = CampaignWorker(store)
    campaign_task = None
    if os.environ.get('DISABLE_BACKGROUND_SYNC') != '1':
        campaign_task = asyncio.create_task(campaign_loop(application), name='paid-campaign')
    application.state.campaign_task = campaign_task
    try:
        yield
    finally:
        if campaign_task:
            campaign_task.cancel()
            with suppress(asyncio.CancelledError):
                await campaign_task
        if task:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
        active = application.state.sync_run_task
        if active and not active.done():
            await active
        await asyncio.to_thread(verified_backup, store)


app = FastAPI(title='SG Career Intelligence', version='2.4.0', lifespan=lifespan)
app.state.database_path = DB_PATH
app.mount('/static', StaticFiles(directory=BASE / 'static', check_dir=False), name='static')


@app.middleware('http')
async def security_headers(request, call_next):
    if request.method in {'PUT', 'POST', 'PATCH', 'DELETE'}:
        origin = request.headers.get('origin')
        if request.headers.get('sec-fetch-site') == 'cross-site' or (origin and
                (urlparse(origin).netloc != request.headers.get('host') or urlparse(origin).scheme != request.url.scheme)):
            return Response('Cross-origin writes are not allowed', status_code=403)
    response = await call_next(request)
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'same-origin'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['Cache-Control'] = 'no-store'
    response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
    return response


def sanitize_url(url):
    try:
        parsed = urlparse(url or '')
        return html.escape(url, quote=True) if parsed.scheme in ('http', 'https') and parsed.netloc else '#'
    except (TypeError, ValueError):
        return '#'


def filter_parameters(q: str = '', category: str = '', fit: str = '', thai_relevance: str = '',
                      employment_type: str = '', salary_only: bool = False,
                      min_salary: float | None = Query(None, ge=0), sort_by: str = 'recommended',
                      include_closed: bool = False, opportunity_type: str = 'salaried'):
    return dict(q=q, category=category, fit=fit, thai_relevance=thai_relevance,
                employment_type=employment_type, salary_only=salary_only,
                min_salary=min_salary, sort_by=sort_by, include_closed=include_closed, opportunity_type=opportunity_type)


def filter_jobs(jobs, **filters):
    results = [present_job(j, copy_result=False) for j in jobs]
    q = filters.get('q', '').strip().lower()
    tokens = [q[1:-1]] if len(q) > 1 and q[0] == q[-1] and q[0] in "\"'" else q.split()
    def matches(j):
        if not filters.get('include_closed') and j.get('status') in ('closed', 'expired', 'unavailable'):
            return False
        types = set(j.get('employment_types') or normalize_employment_types(j.get('employment_type')) or ['Not stated'])
        freelance = 'Freelance' in types
        # Unknown employment stays discoverable. A mixed listing belongs in both views.
        employment = bool(types - {'Freelance', 'Not stated'}) or not freelance
        if filters.get('opportunity_type') == 'salaried' and not employment: return False
        if filters.get('opportunity_type') == 'freelance' and not freelance: return False
        corpus = ' '.join(str(j.get(k) or '') for k in ('title','company','category','location','description','requirements','preferred_requirements')).lower()
        if any(t not in corpus for t in tokens): return False
        if filters.get('fit') and j.get('assessment',{}).get('fit') != filters['fit']: return False
        if filters.get('category') and str(j.get('category') or '').lower() != filters['category'].lower(): return False
        if filters.get('employment_type') and not set(normalize_employment_types(filters['employment_type']) or ['Not stated']).issubset(types): return False
        thai = filters.get('thai_relevance')
        if thai and str(j.get('thai_relevance', '')).lower().replace('thai ', '').replace('thailand market ', '') != thai.lower(): return False
        salary = j.get('salary') or {}
        if filters.get('salary_only') and not salary.get('disclosed'): return False
        threshold = filters.get('min_salary')
        if threshold is not None and (salary.get('monthly_minimum') is None or salary['monthly_minimum'] < threshold or salary.get('currency') != 'SGD'): return False
        return True
    results = [j for j in results if matches(j)]
    results.sort(key=sort_key)
    sort = filters.get('sort_by')
    if sort == 'salary': results.sort(key=lambda j:(j.get('salary',{}).get('monthly_minimum') or -1),reverse=True)
    if sort == 'freshness':
        results.sort(key=lambda j: (parse_date(j.get('verification',{}).get('last_success_at')) or datetime.min.replace(tzinfo=timezone.utc)), reverse=True)
    if sort in ('title','company'): results.sort(key=lambda j:j.get(sort,'').lower())
    if sort == 'discovered':
        results.sort(key=lambda j: (parse_date(j.get('discovered_at')) or datetime.min.replace(tzinfo=timezone.utc)), reverse=True)
    return results


@app.get('/healthz')
def healthz(request: Request, store=Depends(get_store)):
    task = request.app.state.refresh_task
    campaign_task = getattr(request.app.state,'campaign_task',None)
    return {'status':'healthy','version':app.version,'total_jobs_indexed':store.count_jobs(),
            'sync_worker_alive':bool(task and not task.done()),
            'campaign_worker_alive':bool(campaign_task and not campaign_task.done()),
            'revision':os.environ.get('RENDER_GIT_COMMIT')}


@app.get('/', response_class=HTMLResponse)
def index(user=Depends(verify_credentials)):
    return HTMLResponse((BASE/'templates'/'index.html').read_text(encoding='utf-8').replace('__SAFE_USER__',html.escape(user)))


@app.get('/api/jobs')
def get_jobs(filters=Depends(filter_parameters),limit:int=Query(50,ge=1,le=250),offset:int=Query(0,ge=0),
             user=Depends(verify_credentials),store=Depends(get_store)):
    rows=filter_jobs(store.list_jobs(),**filters)
    return {'total':len(rows),'offset':offset,'limit':limit,'items':rows[offset:offset+limit]}


@app.get('/sources',response_class=HTMLResponse)
def source_page(user=Depends(verify_credentials)):
    return HTMLResponse((BASE/'templates'/'sources.html').read_text(encoding='utf-8'))


@app.get('/api/audit/sources')
def source_overview(request:Request,user=Depends(verify_credentials),store=Depends(get_store)):
    task=request.app.state.refresh_task
    return build_audit(store,scheduler_enabled=bool(task and not task.done()),running=request.app.state.sync_lock.locked(),interval_seconds=REFRESH_SECONDS)


@app.get('/api/audit/records')
def source_records(source:str='',q:str='',status:str='',offset:int=Query(0,ge=0),limit:int=Query(25,ge=1,le=100),user=Depends(verify_credentials),store=Depends(get_store)):
    return audit_records(store,source,q,status,offset,limit)


@app.get('/api/campaign')
def campaign_status(user=Depends(verify_credentials),store=Depends(get_store)):
    return {**CampaignStore(store).status(), 'disk':disk_capacity(store),
            'accounting_error':store.get_meta('campaign_account_error'),
            'worker_error':store.get_meta('campaign_worker_error')}


@app.post('/api/campaign/pause')
async def pause_campaign(request:Request,user=Depends(verify_credentials),store=Depends(get_store)):
    try:
        await owned_operation(request.app.state.campaign_worker,
            lambda:CampaignStore(store).state('paused','Paused from the authenticated workspace.'))
        return CampaignStore(store).status()
    except ValueError as exc:
        raise HTTPException(409,str(exc))


@app.post('/api/campaign/prepare')
async def prepare_campaign(request:Request,user=Depends(verify_credentials)):
    worker = request.app.state.campaign_worker
    try:
        return await owned_operation(worker,worker.prepare)
    except ValueError as exc:
        raise HTTPException(409,str(exc))


@app.post('/api/campaign/pilot')
async def pilot_campaign(request:Request,payload:dict=None,user=Depends(verify_credentials)):
    worker = request.app.state.campaign_worker
    try:
        options = payload or {}
        return await owned_operation(worker,lambda:worker.pilot(options.get('source','indeed'),options.get('urls'),options.get('retry_of')))
    except ValueError as exc:
        raise HTTPException(409,str(exc))


@app.get('/api/campaign/pilot-evidence')
def pilot_evidence(user=Depends(verify_credentials),store=Depends(get_store)):
    from source_audit import redacted
    with store._connection() as connection:
        rows = [{**dict(r),'payload':json.loads(r['payload_json'])} for r in connection.execute('SELECT * FROM campaign_items WHERE batch_id IN (SELECT id FROM campaign_batches WHERE batch_key LIKE ?)',('pilot:%',))]
        for row in rows:row.pop('payload_json',None)
    return redacted({'items':rows,'campaign':CampaignStore(store).status()})


@app.get('/api/campaign/leads')
def campaign_leads(offset:int=Query(0,ge=0),limit:int=Query(25,ge=1,le=100),source:str='',pilot:bool=False,user=Depends(verify_credentials),store=Depends(get_store)):
    from source_audit import redacted
    with store._connection() as connection:
        where = "i.outcome IN ('lead','error') AND COALESCE(json_extract(b.context_json,'$.pilot'),0)=?"
        params=[int(pilot)]
        if source:
            where+=' AND b.source=?';params.append(source)
        query=' FROM campaign_items i JOIN campaign_batches b ON b.id=i.batch_id WHERE '+where
        total=connection.execute('SELECT COUNT(*)'+query,params).fetchone()[0]
        records=connection.execute('SELECT i.*,b.source,b.created_at,b.finished_at,b.context_json,b.error,b.error_category'+query+' ORDER BY b.created_at DESC,i.item_index LIMIT ? OFFSET ?', [*params,limit,offset])
        rows=[]
        for record in records:
            item=json.loads(record['payload_json'])
            context=json.loads(record['context_json'])
            obj=item if isinstance(item,dict) else {}
            url=obj.get('url') or obj.get('searchQuery',{}).get('url')
            queue=connection.execute('SELECT * FROM campaign_discovery WHERE url=?',(url,)).fetchone() if url else None
            discovered=[{k:r[k] for k in ('url','domain','parent_url','depth','state','checked_at','reason')} for r in connection.execute(
                "SELECT * FROM campaign_discovery WHERE json_extract(evidence_json,'$.parent_batch_id')=? AND json_extract(evidence_json,'$.parent_item_index')=? ORDER BY depth,url",
                (record['batch_id'],record['item_index']))]
            rows.append({'id':record['batch_id']+':'+str(record['item_index']), 'source':record['source'],
                'url':url,'title':obj.get('title') or obj.get('positionName') or obj.get('metadata',{}).get('title') or context.get('query') or 'Returned source evidence',
                'reason':record['error'] or 'Returned evidence does not establish a supported Singapore vacancy.',
                'state':queue['state'] if queue else 'lead','discovered_at':record['finished_at'] or record['created_at'],
                'parent_url':queue['parent_url'] if queue else context.get('parent_url'),
                'payload':item,'context':{**context,'discovered_pages':discovered},'pilot':pilot,'job_id':record['job_id'],
                'depth':queue['depth'] if queue else context.get('depth'),
                'queue':dict(queue) if queue else None,'error_category':record['error_category']})
    return redacted({'items':rows,'total':total,'offset':offset,'limit':limit})


@app.post('/api/campaign/activate')
async def activate_campaign(payload:dict,request:Request,user=Depends(verify_credentials),store=Depends(get_store)):
    worker = request.app.state.campaign_worker
    async with worker.mutation_lock:
        journal = CampaignStore(store)
        from campaign_sources import CONTRACTS
        requested = payload.get('sources') or ([payload['source']] if payload.get('source') else ['indeed'])
        if not isinstance(requested,list) or not requested or any(s not in CONTRACTS for s in requested):
            raise HTTPException(422,'Specify known collection sources.')
        pilots = [b for b in journal.batches() if json.loads(b['context_json']).get('pilot') and b['source'] in requested]
        def supported(batch):
            if batch['source'] != 'google':
                return batch['new_count']+batch['updated_count']+batch['duplicate_count'] > 0
            # A search pilot establishes search-result evidence, never a vacancy.
            with store._connection() as connection:
                for row in connection.execute('SELECT payload_json FROM campaign_items WHERE batch_id=?',(batch['id'],)):
                    item=json.loads(row[0])
                    if any(isinstance(r,dict) and r.get('url') and (r.get('title') or r.get('description')) for r in item.get('organicResults',[])):
                        return True
            return False
        verified = [b for b in pilots if b['state']=='done' and b['remote_status']=='SUCCEEDED' and b['charge_units'] is not None and supported(b)]
        if not all(any(b['source']==s for b in verified) for s in requested):
            raise HTTPException(409,'Each requested source needs a successful, reconciled isolated validation with returned evidence.')
        if not store.get_meta('last_backup') or not all(store.get_meta('campaign_contract_'+b['source']) for b in pilots):
            raise HTTPException(409,'Backup and current actor contract verification are required.')
        await asyncio.to_thread(worker.refresh_accounts,time.time())
        current=journal.status()
        if store.get_meta('campaign_account_error') or current['observed_account_usage_usd'] < current['reported_run_charges_usd']:
            raise HTTPException(409,'Account usage has not reconciled the pilot charges.')
        if (current['mode']=='pilot' and current['observed_account_usage_usd'] > 3) or any(b['charge_units'] is not None and b['charge_units']>b['reserved_units'] for b in pilots):
            raise HTTPException(409,'Pilot cost exceeded its expected bound; investigation is required.')
        if not payload.get('pilot_verified') or not payload.get('evidence_reference'):
            raise HTTPException(422,'Provide the verified pilot evidence reference.')
        evidence = {**payload,'backup_verified':True,'contracts_verified':True,'verified_at':datetime.now(timezone.utc).isoformat()}
        try:
            store.set_meta('campaign_validated_sources',sorted(set(store.get_meta('campaign_validated_sources',[])) | set(requested)))
            for source in requested:
                journal.source(source,due_at=time.time(),blocked_reason=None)
            journal.activate(evidence)
            return journal.status()
        except ValueError as exc:
            raise HTTPException(409,str(exc))


@app.get('/api/campaign/report')
def campaign_report(user=Depends(verify_credentials),store=Depends(get_store)):
    return {**CampaignStore(store).status(), 'activation':store.get_meta('campaign_activation'),
            'limitations':['Credit expiry is unknown unless verified separately.',
                          'Cultjobs remains a separately specified dated import.',
                          'Future unattended cycles and deadline shutdown require observed runtime evidence.']}


@app.get('/api/audit/records/{job_id}')
def source_record(job_id:str,offset:int=Query(0,ge=0),limit:int=Query(10,ge=1,le=50),user=Depends(verify_credentials),store=Depends(get_store)):
    result=inspect_record(store,job_id,offset,limit)
    if result is None:raise HTTPException(404,'No retained source record was found for this job.')
    return result


@app.get('/api/jobs/batch')
def get_jobs_batch(ids:str,user=Depends(verify_credentials),store=Depends(get_store)):
    rows=[present_job(j) for jid in ids.split(',') if (j:=store.get_job(jid))]
    return {'count':len(rows),'items':rows}


@app.get('/api/jobs/{job_id}')
def get_job(job_id:str,user=Depends(verify_credentials),store=Depends(get_store)):
    job=store.get_job(job_id)
    if not job:
        saved=store.get_application(job_id)
        if saved:
            job=dict(saved['job_snapshot'],status='unavailable')
        else: raise HTTPException(404,'This listing is unavailable.')
    return {'job':present_job(job)}


@app.get('/api/options')
def get_options(user=Depends(verify_credentials),store=Depends(get_store)):
    jobs=store.list_jobs()
    return {'category':sorted({str(j['category']) for j in jobs if j.get('category')}),
            'employment_type':sorted({kind for j in jobs for kind in (normalize_employment_types(j.get('employment_type')) or ['Not stated'])})}


@app.get('/api/applications')
def get_applications(stage:str|None=None,user=Depends(verify_credentials),store=Depends(get_store)):
    if stage and stage not in STAGES: raise HTTPException(422,'Unknown application stage')
    rows=store.list_applications(stage=stage)
    for row in rows:
        job=store.get_job(row['job_id'])
        row['job']=present_job(job or dict(row['job_snapshot'],status='unavailable'))
    return {'items':rows,'total':len(rows)}


@app.post('/api/applications/import')
def import_applications(payload:dict,user=Depends(verify_credentials),store=Depends(get_store)):
    try: return store.import_applications(payload.get('records',payload))
    except (ValueError,TypeError) as exc: raise HTTPException(422,str(exc))


@app.put('/api/applications/{job_id}')
def put_application(job_id:str,payload:dict,user=Depends(verify_credentials),store=Depends(get_store)):
    try: return store.put_application(job_id,payload)
    except Conflict as exc: return Response(json.dumps({'detail':str(exc),'current':exc.current}),status_code=409,media_type='application/json')
    except (ValueError,TypeError) as exc: raise HTTPException(422,str(exc))


@app.get('/api/applications/{job_id}/history')
def application_history(job_id:str,offset:int=Query(0,ge=0),limit:int=Query(25,ge=1,le=100),
                        user=Depends(verify_credentials),store=Depends(get_store)):
    result=store.application_history(job_id,offset=offset,limit=limit)
    if result is None: raise HTTPException(404,'No saved application was found for this role.')
    return result


@app.get('/api/drafts/{job_id}')
def get_drafts(job_id:str,user=Depends(verify_credentials),store=Depends(get_store)):
    job=store.get_job(job_id)
    saved=store.get_application(job_id)
    if not job and saved: job=saved['job_snapshot']
    if not job: raise HTTPException(404,'This listing is unavailable.')
    return draft_templates(present_job(job))


@app.get('/api/export/filtered')
def export_jobs(filters=Depends(filter_parameters),format:str='csv',user=Depends(verify_credentials),store=Depends(get_store)):
    return export_response(JOB_HEADERS,[job_row(j) for j in filter_jobs(store.list_jobs(),**filters)],'Singapore_roles',format)


@app.get('/api/export/applications')
def export_applications(stage:str|None=None,ids:str|None=None,format:str='csv',user=Depends(verify_credentials),store=Depends(get_store)):
    if stage and stage not in STAGES: raise HTTPException(422,'Unknown application stage')
    rows=store.list_applications(stage=stage)
    if ids is not None:rows=[r for r in rows if r['job_id'] in ids.split(',')]
    headers=['ID','Title','Company','Stage','Notes','Next action','Follow-up date','Applied at','Outcome','Original URL','Recruiter message','Cover letter','History','Job snapshot']
    values=[]
    for r in rows:
        j=r['job_snapshot'];d=r.get('drafts') or {}
        retained_history=store.application_history(r['job_id'],limit=None)['items']
        values.append([r['job_id'],j.get('title'),j.get('company'),r['stage'],r['notes'],r.get('next_action'),r.get('follow_up_date'),r.get('applied_at'),r.get('outcome'),j.get('url'),d.get('recruiter_message'),d.get('cover_letter'),json.dumps(retained_history,ensure_ascii=False),json.dumps(j,ensure_ascii=False)])
    return export_response(headers,values,'Applications',format)


@app.get('/download/csv')
def download_csv(user=Depends(verify_credentials),store=Depends(get_store)):
    return export_response(JOB_HEADERS,[job_row(j) for j in filter_jobs(store.list_jobs())],'Singapore_roles')


@app.get('/download/excel')
def download_excel(user=Depends(verify_credentials),store=Depends(get_store)):
    return export_response(JOB_HEADERS,[job_row(j) for j in filter_jobs(store.list_jobs())],'Singapore_roles','xlsx')


@app.get('/api/stats')
def stats(user=Depends(verify_credentials),store=Depends(get_store)):
    return {'authenticated_user':user,'total_jobs':store.count_jobs(),'sync_history':store.get_sync_history(10),'next_sync_at':store.get_meta('next_sync_at'), 'storage': {'path': str(store.path),'last_backup':store.get_meta('last_backup')}}


@app.get('/api/backup')
def download_backup(user=Depends(verify_credentials),store=Depends(get_store)):
    path=verified_backup(store)
    return FileResponse(path,media_type='application/vnd.sqlite3',filename='career-backup.sqlite3')


@app.post('/api/sync')
async def trigger_sync(request:Request,user=Depends(verify_credentials)):
    return await run_sync(request.app)
