"""Read-only provenance and collection coverage for the authenticated source audit."""
from collections import Counter
from datetime import datetime, timezone
from evidence import present_job, parse_date, safe_url
from collector_mycareersfuture import API_URL
from sync_engine import DEFAULT_QUERIES, DEFAULT_LIMIT

SOURCE_CATALOG = [
    {'id':'mycareersfuture','name':'MyCareersFuture','match':'mycareersfuture','method':'Public API search','mode':'scheduled','endpoint':API_URL,'home':'https://www.mycareersfuture.gov.sg/','retained_file':'mcf_jobs_raw.json',
     'scope':'Four keyword searches, up to 10 results each. Only returned vacancies are checked; this is not a scan of every saved listing.'},
    {'id':'linkedin','name':'LinkedIn','match':'linkedin','method':'Retained Apify collector records','mode':'retained','home':'https://www.linkedin.com/jobs/','retained_file':'apify_jobs_raw.json','scope':'Imported listing evidence. No recurring LinkedIn collector is running.'},
    {'id':'indeed','name':'Indeed','match':'indeed','method':'Retained Apify collector records','mode':'retained','home':'https://sg.indeed.com/','retained_file':'apify_jobs_raw.json','scope':'Imported listing evidence. No recurring Indeed collector is running.'},
    {'id':'cultjobs','name':'Cultjobs','match':'cultjobs','method':'Retained site collector records','mode':'retained','home':'https://www.cultjobs.com/','retained_file':'cultjobs_raw.json','scope':'Imported listing evidence. Some descriptions were truncated by the original collector. No recurring Cultjobs collector is running.'},
    {'id':'google','name':'Google search','match':'google','method':'Retained search-result snippets','mode':'retained','home':'https://www.google.com/','retained_file':'apify_jobs_raw.json','scope':'Search results are leads, not verified vacancies. Identified aggregate results pages are excluded from discovery.'},
]


def source_id(job):
    name = ' '.join(str(source.get('name','')) for source in job.get('sources',[])).lower()
    for source in SOURCE_CATALOG:
        if source['match'] in name:
            return source['id']
    return 'other'


def _latest(values):
    parsed = [(parse_date(value),value) for value in values if value]
    return max((item for item in parsed if item[0]),default=(None,None),key=lambda pair:pair[0])[1]


def coverage(jobs):
    total=len(jobs)
    counts={
        'Complete retained description':sum(bool(j.get('description_complete') and j.get('description')) for j in jobs),
        'Mandatory requirements available':sum(bool(j.get('requirements',{}).get('mandatory')) for j in jobs),
        'Advertised salary available':sum(bool(j.get('salary',{}).get('disclosed')) for j in jobs),
        'Successfully checked within 24 hours':sum(j.get('verification',{}).get('status')=='verified' and not j['verification'].get('needs_recheck') for j in jobs),
    }
    return [{'label':label,'count':count,'total':total,'percent':round(count*100/total,1) if total else 0} for label,count in counts.items()]


def record_summary(job):
    return {key:job.get(key) for key in ['id','title','company','status','description_complete','verification','url']} | {
        'source_id':source_id(job),'requirements_available':bool(job.get('requirements',{}).get('mandatory')),
        'source_name':', '.join(s.get('name','') for s in job.get('sources',[])),
    }


def build_audit(store, *, scheduler_enabled, running, interval_seconds):
    now=datetime.now(timezone.utc)
    jobs=[present_job(j,now,with_assessment=False) for j in store.list_jobs()]
    history=store.get_sync_history(100)
    sources=[]
    catalog=SOURCE_CATALOG+([{'id':'other','name':'Other retained sources','method':'Retained records','mode':'retained','scope':'Source provenance is shown per record.'}] if any(source_id(j)=='other' for j in jobs) else [])
    for config in catalog:
        selected=[j for j in jobs if source_id(j)==config['id']]
        counts=Counter(j.get('status','unknown') for j in selected)
        verifications=[j.get('verification',{}) for j in selected]
        automated=config['mode']=='scheduled'
        latest=history[0] if automated and history else None
        successful_times=[j.get('verification',{}).get('last_success_at') or j.get('raw_evidence',{}).get('verified_at') for j in selected]
        # Historical imported check dates never count as successful collector runs.
        for run in history if automated else []:
            successful_times.extend(x.get('checked_at') for x in run.get('sources',[]))
        state='checking' if automated and running else 'paused' if automated and not scheduler_enabled else 'error' if latest and latest.get('status')=='error' else 'degraded' if latest and latest.get('status') in ('degraded','interrupted') else 'scheduled' if automated else 'retained'
        sources.append({**{k:v for k,v in config.items() if k!='match'},'state':state,'count':len(selected),
                        'available':sum(j['status'] not in ('expired','closed','unavailable') for j in selected),
                        'needs_recheck':sum(j.get('verification',{}).get('needs_recheck',True) for j in selected),
                        'status_counts':dict(counts),'coverage':coverage(selected),
                        'last_attempt':latest.get('started_at') or latest.get('recorded_at') if latest else None,
                        'last_success':_latest(successful_times),
                        'latest_record_date':_latest(v.get('checked_at') for v in verifications),
                        'latest_errors':latest.get('errors',[]) if latest else [],
                        'next_check_at':store.get_meta('next_sync_at') if automated and scheduler_enabled else None})
    return {'generated_at':now.isoformat(),'total':len(jobs),'sources':sources,'coverage':coverage(jobs),
            'discovery_count':sum(j['status'] not in ('expired','closed','unavailable') for j in jobs),
            'excluded_count':sum(j['status'] in ('expired','closed','unavailable') for j in jobs),
            'applications_count':len(store.list_applications()),
            'scheduler':{'enabled':scheduler_enabled,'running':running,'interval_hours':interval_seconds/3600,
                         'next_check_at':store.get_meta('next_sync_at') if scheduler_enabled else None,
                         'current_run':store.get_meta('active_sync'),'queries':list(DEFAULT_QUERIES), 'limit_per_query':DEFAULT_LIMIT},
            'history':history,'history_limit':100,
            'explanation':'Collection checks returned listings, not every stored vacancy. Missing listings in a limited search are not treated as closed.'}


def audit_records(store,source='',q='',status='',offset=0,limit=25):
    jobs=[]
    for original in store.list_jobs():
        job=present_job(original,with_assessment=False)
        if source and source_id(job)!=source:continue
        if q and not all(token in (str(job.get('title',''))+' '+str(job.get('company',''))+' '+job['id']).lower() for token in q.lower().split()):continue
        if status=='needs_recheck' and not job.get('verification',{}).get('needs_recheck'):continue
        if status=='missing_requirements' and job.get('requirements',{}).get('mandatory'):continue
        if status=='excluded' and job['status'] not in ('expired','closed','unavailable'):continue
        if status=='recent' and (job.get('verification',{}).get('needs_recheck') or job.get('verification',{}).get('status')!='verified'):continue
        jobs.append(job)
    jobs.sort(key=lambda job:job['id'])
    return {'total':len(jobs),'offset':offset,'limit':limit,'items':[record_summary(j) for j in jobs[offset:offset+limit]]}


# Show source records as data, with credential-like keys redacted at any depth.
def redacted(value):
    if isinstance(value,dict):
        return {k:('[redacted]' if any(t in str(k).lower() for t in ('token','password','secret','authorization','api_key','apikey','cookie')) else redacted(v)) for k,v in value.items()}
    if isinstance(value,list):return [redacted(v) for v in value]
    return value


def inspect_record(store,job_id,offset=0,limit=10):
    stored=store.get_job(job_id)
    if not stored:return None
    job=present_job(stored)
    evidence=store.get_source_evidence_page(job_id,offset,limit)
    latest=store.get_source_evidence_page(job_id,0,1)['items']
    record=(latest[0]['payload'] if latest else {})
    record=record.get('record',record) if isinstance(record,dict) else {}
    provenance=[
        {'field':'Description','basis':'Retained source description, converted from HTML to text.','value':job.get('description'),'quality':'Complete retained text' if job.get('description_complete') else 'Partial or missing source text'},
        {'field':'Requirements','basis':'Explicit requirement fields and headings in the retained source. Unknown requirements stay empty.','value':job.get('requirements')},
        {'field':'Salary','basis':'Advertised source values. Annual amounts normalized to monthly; daily/hourly amounts retain their units.','value':job.get('salary')},
        {'field':'Thai relevance','basis':'Wording in the role title, description, and requirements; search terms are excluded.','value':job.get('thai_relevance')},
        {'field':'Assessment','basis':'Derived comparison with CV 2026.pdf. This is not an employer statement or a hiring probability.','value':job.get('assessment')},
    ]
    collector_context={k:record.get(k) for k in ('query_matched','source','id','uuid','verified_at','legacy_source_missing','description_incomplete') if k in record}
    return {'job':redacted(job),'source_id':source_id(job),'collector_context':redacted(collector_context),'provenance':redacted(provenance),
            'evidence':redacted(evidence),
            'notice':'These are the retained collector records. Earlier collectors sometimes inserted defaults; the displayed fields discard unsupported defaults. A stored-at timestamp is not an upstream verification date.'}
