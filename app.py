import os
import re
import io
import csv
import json
import html
import threading
import time
import logging
import secrets
from urllib.parse import urlparse
from fastapi import FastAPI, Query, Depends, HTTPException, status
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from sync_engine import synchronize_upstream_jobs, get_sync_telemetry, atomic_save_jobs

# Configure structured logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("sg_career_pipeline")

app = FastAPI(
    title="Singapore Career Intelligence Pipeline",
    description="Executive recruitment intelligence and automated job-matching engine for candidate Dechsurang Kawintra",
    version="1.4.0"
)

# Restrict CORS appropriately
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET", "HEAD", "OPTIONS"],
    allow_headers=["*"],
)

DATA_FILE = "processed_master_jobs.json"
EXCEL_FILE = "Singapore_Career_Intelligence_Database_2026.xlsx"
CSV_FILE = "Singapore_Career_Intelligence_Database_2026.csv"
AUDIT_FILE = "apify_spend_audit.json"
TEMPLATE_FILE = os.path.join(os.path.dirname(__file__), "templates", "index.html")

AUTH_USERNAME = os.environ.get("AUTH_USERNAME", "Kawa")
AUTH_PASSWORD = os.environ.get("AUTH_PASSWORD", "Kawa123")

security = HTTPBasic()

def verify_credentials(credentials: HTTPBasicCredentials = Depends(security)):
    """Enforces constant-time HTTP Basic Authentication."""
    is_user_correct = secrets.compare_digest(credentials.username.encode("utf8"), AUTH_USERNAME.encode("utf8"))
    is_pass_correct = secrets.compare_digest(credentials.password.encode("utf8"), AUTH_PASSWORD.encode("utf8"))
    if not (is_user_correct and is_pass_correct):
        logger.warning(f"Failed authentication attempt for user '{credentials.username}'")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
            headers={"WWW-Authenticate": 'Basic realm="Singapore Career Intelligence Pipeline"'},
        )
    return credentials.username

# In-Memory Cache and Search Index to maximize throughput and search recall
_jobs_cache = None
_jobs_by_id = {}
_jobs_mtime = 0
_search_index = None
_stats_cache = None
_cache_lock = threading.Lock()
_start_time = time.time()

def load_jobs():
    """Loads jobs dataset with thread-safe mtime-based memory caching, ID indexing, and precalculated search indices."""
    global _jobs_cache, _jobs_by_id, _jobs_mtime, _search_index, _stats_cache
    if not os.path.exists(DATA_FILE):
        return []
    try:
        current_mtime = os.path.getmtime(DATA_FILE)
        with _cache_lock:
            if _jobs_cache is None or current_mtime > _jobs_mtime:
                logger.info(f"Loading jobs from {DATA_FILE} (mtime: {current_mtime})...")
                with open(DATA_FILE, "r", encoding="utf-8") as f:
                    raw_jobs = json.load(f)

                by_id = {}
                index_data = []
                tiers = {}
                cats = {}
                thai_count = 0
                salary_count = 0

                for j in raw_jobs:
                    jid = j.get("col_01_id", "")
                    if jid:
                        by_id[jid] = j

                    title_str = j.get("col_03_title", "")
                    comp_str = j.get("col_02_company", "")
                    cat_str = j.get("col_04_category", "")
                    tier_str = j.get("col_26_suitability_tier", "")
                    sal_str = j.get("col_09_advertised_salary", "")
                    resp_str = j.get("col_18_responsibilities", "")
                    thai_rel_str = j.get("col_24_thai_relevance", "")
                    quals_str = j.get("col_21_candidate_quals", "")
                    reqs_str = j.get("col_19_mandatory_reqs", "")

                    t_low = title_str.lower()
                    c_low = comp_str.lower()
                    cat_low = cat_str.lower()
                    tier_low = tier_str.lower()
                    thai_rel_low = thai_rel_str.lower()

                    is_thai = ("thai" in thai_rel_low) or ("thai" in cat_low) or ("thai" in t_low)
                    if is_thai:
                        thai_count += 1

                    has_salary = bool(sal_str and "not disclosed" not in sal_str.lower() and sal_str.strip())
                    if has_salary:
                        salary_count += 1

                    tiers[tier_str] = tiers.get(tier_str, 0) + 1
                    cats[cat_str] = cats.get(cat_str, 0) + 1

                    sal_max = extract_salary_range(sal_str)[1]

                    try:
                        num_score = int(j.get("col_25_suitability_score", 0))
                    except (ValueError, TypeError):
                        num_score = 0

                    corpus = f"{t_low} {c_low} {cat_low} {thai_rel_low} {resp_str.lower()} {quals_str.lower()} {reqs_str.lower()}"

                    index_data.append({
                        "title": t_low,
                        "company": c_low,
                        "category": cat_low,
                        "tier": tier_low,
                        "is_thai": is_thai,
                        "has_salary": has_salary,
                        "max_salary": sal_max,
                        "score": num_score,
                        "corpus": corpus
                    })

                _jobs_cache = raw_jobs
                _jobs_by_id = by_id
                _search_index = index_data
                _stats_cache = {
                    "total_jobs": len(raw_jobs),
                    "tiers": tiers,
                    "categories": cats,
                    "thai_relevance_jobs": thai_count,
                    "salary_disclosed_jobs": salary_count
                }
                _jobs_mtime = current_mtime
                logger.info(f"Loaded {len(_jobs_cache)} jobs into memory cache (indexed {len(_jobs_by_id)} IDs, {len(_search_index)} search records).")
            return _jobs_cache
    except Exception as e:
        logger.error(f"Error loading jobs dataset: {e}")
        return _jobs_cache or []

def load_audit():
    if os.path.exists(AUDIT_FILE):
        try:
            with open(AUDIT_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"total_spend_usd": 33.5563, "runs_count": 33, "audit_log": []}

_template_cache = None
_template_mtime = 0

def load_template() -> str:
    """Loads HTML template with mtime caching."""
    global _template_cache, _template_mtime
    if not os.path.exists(TEMPLATE_FILE):
        return "<html><body>Template missing</body></html>"
    try:
        mtime = os.path.getmtime(TEMPLATE_FILE)
        if _template_cache is None or mtime > _template_mtime:
            with open(TEMPLATE_FILE, "r", encoding="utf-8") as f:
                _template_cache = f.read()
            _template_mtime = mtime
        return _template_cache
    except Exception as e:
        logger.error(f"Error loading template: {e}")
        return _template_cache or ""

def sanitize_url(url: str) -> str:
    """Ensures URLs only use http/https to prevent javascript: pseudo-protocol XSS."""
    if not url:
        return "#"
    try:
        parsed = urlparse(url)
        if parsed.scheme in ["http", "https"]:
            return html.escape(url, quote=True)
    except Exception:
        pass
    return "#"

def extract_salary_range(sal_str: str):
    """Extracts min and max numeric monthly figures from salary string."""
    if not sal_str:
        return (0, 0)
    nums = [int(n.replace(',', '')) for n in re.findall(r'\b\d{1,3}(?:,\d{3})+\b|\b\d{4,6}\b', sal_str)]
    if not nums:
        return (0, 0)
    return (min(nums), max(nums))

def filter_jobs(jobs, category=None, tier=None, thai_only=False, min_salary=None, salary_only=False, q=None, sort_by="score"):
    """Unified, high-performance in-memory filtering and sorting engine with multi-token recall."""
    global _jobs_cache, _search_index

    # Check if we can use the precomputed index
    if jobs is _jobs_cache and _search_index is not None and len(_search_index) == len(_jobs_cache):
        matching = list(range(len(_jobs_cache)))

        if category:
            cat_low = category.lower()
            matching = [i for i in matching if cat_low in _search_index[i]["category"]]
        if tier:
            tier_low = tier.lower()
            matching = [i for i in matching if tier_low in _search_index[i]["tier"]]
        if thai_only:
            matching = [i for i in matching if _search_index[i]["is_thai"]]
        if salary_only:
            matching = [i for i in matching if _search_index[i]["has_salary"]]
        if min_salary and min_salary > 0:
            matching = [i for i in matching if _search_index[i]["max_salary"] >= min_salary]
        if q:
            q_raw = q.strip()
            q_low = q_raw.lower()
            if (q_raw.startswith('"') and q_raw.endswith('"')) or (q_raw.startswith("'") and q_raw.endswith("'")):
                phrase = q_low[1:-1].strip()
                matching = [i for i in matching if phrase in _search_index[i]["corpus"]]
            else:
                tokens = [t for t in q_low.split() if t]
                if tokens:
                    matching = [i for i in matching if all(t in _search_index[i]["corpus"] for t in tokens)]

        # Sorting
        if sort_by == "title":
            matching.sort(key=lambda i: _search_index[i]["title"])
        elif sort_by == "company":
            matching.sort(key=lambda i: _search_index[i]["company"])
        elif sort_by == "salary":
            matching.sort(key=lambda i: _search_index[i]["max_salary"], reverse=True)
        elif sort_by == "relevance" or (q and sort_by == "score"):
            # Multi-tiered relevance scoring
            def get_relevance(i):
                item = _search_index[i]
                rel = item["score"]
                if q:
                    q_clean = q.strip().lower()
                    if q_clean == item["title"]:
                        rel += 200
                    elif q_clean in item["title"]:
                        rel += 100
                    elif all(t in item["title"] for t in q_clean.split()):
                        rel += 60
                    if q_clean in item["company"]:
                        rel += 40
                return rel
            matching.sort(key=get_relevance, reverse=True)
        else:
            matching.sort(key=lambda i: _search_index[i]["score"], reverse=True)

        return [_jobs_cache[i] for i in matching]

    # Fallback path for arbitrary or mock job lists (unit tests)
    filtered = jobs
    if category:
        cat_low = category.lower()
        filtered = [j for j in filtered if cat_low in j.get("col_04_category", "").lower()]
    if tier:
        tier_low = tier.lower()
        filtered = [j for j in filtered if tier_low in j.get("col_26_suitability_tier", "").lower()]
    if thai_only:
        filtered = [
            j for j in filtered
            if "thai" in j.get("col_24_thai_relevance", "").lower()
            or "thai" in j.get("col_04_category", "").lower()
            or "thai" in j.get("col_03_title", "").lower()
        ]
    if salary_only:
        filtered = [
            j for j in filtered
            if j.get("col_09_advertised_salary")
            and "not disclosed" not in j.get("col_09_advertised_salary", "").lower()
            and j.get("col_09_advertised_salary", "").strip()
        ]
    if min_salary and min_salary > 0:
        filtered = [
            j for j in filtered
            if extract_salary_range(j.get("col_09_advertised_salary", ""))[1] >= min_salary
        ]
    if q:
        q_raw = q.strip()
        q_low = q_raw.lower()
        if (q_raw.startswith('"') and q_raw.endswith('"')) or (q_raw.startswith("'") and q_raw.endswith("'")):
            phrase = q_low[1:-1].strip()
            filtered = [
                j for j in filtered
                if phrase in f"{j.get('col_03_title', '')} {j.get('col_02_company', '')} {j.get('col_18_responsibilities', '')} {j.get('col_24_thai_relevance', '')} {j.get('col_21_candidate_quals', '')}".lower()
            ]
        else:
            tokens = [t for t in q_low.split() if t]
            if tokens:
                def matches_tokens(j):
                    text = f"{j.get('col_03_title', '')} {j.get('col_02_company', '')} {j.get('col_18_responsibilities', '')} {j.get('col_24_thai_relevance', '')} {j.get('col_21_candidate_quals', '')}".lower()
                    return all(t in text for t in tokens)
                filtered = [j for j in filtered if matches_tokens(j)]

    if sort_by == "title":
        filtered.sort(key=lambda j: j.get("col_03_title", "").lower())
    elif sort_by == "company":
        filtered.sort(key=lambda j: j.get("col_02_company", "").lower())
    elif sort_by == "salary":
        filtered.sort(key=lambda j: extract_salary_range(j.get("col_09_advertised_salary", ""))[1], reverse=True)
    elif sort_by == "relevance" or (q and sort_by == "score"):
        def get_fallback_rel(j):
            try:
                rel = int(j.get("col_25_suitability_score", 0))
            except (ValueError, TypeError):
                rel = 0
            if q:
                q_clean = q.strip().lower()
                t_low = j.get("col_03_title", "").lower()
                c_low = j.get("col_02_company", "").lower()
                if q_clean == t_low:
                    rel += 200
                elif q_clean in t_low:
                    rel += 100
                elif all(t in t_low for t in q_clean.split()):
                    rel += 60
                if q_clean in c_low:
                    rel += 40
            return rel
        filtered.sort(key=get_fallback_rel, reverse=True)
    else:
        def get_score(job):
            try:
                return int(job.get("col_25_suitability_score", 0))
            except (ValueError, TypeError):
                return 0
        filtered.sort(key=get_score, reverse=True)

    return filtered

# Autonomous Background Sync Worker
def background_refresh_loop():
    """Runs periodic sync every 12 hours with thread-safety and error isolation."""
    while True:
        time.sleep(43200) # 12 hours
        try:
            logger.info("[Continuous Pipeline] Running automated periodic sync...")
            res = synchronize_upstream_jobs(DATA_FILE)
            logger.info(f"[Continuous Pipeline] Sync completed: {res}")
        except Exception as e:
            logger.error(f"[Continuous Pipeline] Sync loop exception: {e}")

sync_thread = threading.Thread(target=background_refresh_loop, daemon=True, name="SyncWorker")
sync_thread.start()

# --- Health Check (Unauthenticated for Cloud Orchestrator / Render monitoring) ---
@app.get("/healthz")
def healthz():
    jobs = load_jobs()
    return {
        "status": "healthy",
        "version": "1.4.0",
        "uptime_seconds": int(time.time() - _start_time),
        "total_jobs_indexed": len(jobs),
        "sync_worker_alive": sync_thread.is_alive(),
        "sync_telemetry": get_sync_telemetry()
    }

# --- Authenticated Endpoints (Protected by User Kawa / Pass Kawa123) ---

@app.get("/api/jobs")
def get_jobs(
    category: str = Query(None),
    tier: str = Query(None),
    thai_only: bool = Query(False),
    min_salary: int = Query(None, ge=0),
    salary_only: bool = Query(False),
    q: str = Query(None),
    sort_by: str = Query("score"),
    limit: int = Query(100, ge=1, le=250),
    offset: int = Query(0, ge=0),
    user: str = Depends(verify_credentials)
):
    jobs = load_jobs()
    filtered = filter_jobs(
        jobs,
        category=category,
        tier=tier,
        thai_only=thai_only,
        min_salary=min_salary,
        salary_only=salary_only,
        q=q,
        sort_by=sort_by
    )
    total = len(filtered)
    results = filtered[offset : offset + limit]
    return {
        "authenticated_user": user,
        "total": total,
        "offset": offset,
        "limit": limit,
        "items": results
    }

@app.get("/api/jobs/batch")
def get_jobs_batch(ids: str = Query(...), user: str = Depends(verify_credentials)):
    """Fetches any arbitrary list of jobs by comma-separated IDs in a single query."""
    id_list = [i.strip() for i in ids.split(",") if i.strip()]
    load_jobs()
    results = [_jobs_by_id[jid] for jid in id_list if jid in _jobs_by_id]
    return {
        "authenticated_user": user,
        "count": len(results),
        "items": results
    }

@app.get("/api/jobs/{job_id}")
def get_job_by_id(job_id: str, user: str = Depends(verify_credentials)):
    load_jobs()
    job = _jobs_by_id.get(job_id)
    if job:
        return {"authenticated_user": user, "job": job}
    raise HTTPException(status_code=404, detail="Job position not found")

@app.post("/api/sync")
def trigger_sync(user: str = Depends(verify_credentials)):
    """Allows authorized operator to trigger an on-demand upstream synchronization."""
    logger.info(f"Manual synchronization triggered by operator: '{user}'")
    result = synchronize_upstream_jobs(DATA_FILE)
    return {
        "authenticated_user": user,
        "sync_result": result,
        "telemetry": get_sync_telemetry()
    }

@app.get("/api/export/filtered")
def export_filtered_csv(
    category: str = Query(None),
    tier: str = Query(None),
    thai_only: bool = Query(False),
    min_salary: int = Query(None, ge=0),
    salary_only: bool = Query(False),
    q: str = Query(None),
    sort_by: str = Query("score"),
    user: str = Depends(verify_credentials)
):
    """Exports currently filtered search results directly into an Excel-friendly CSV with UTF-8 BOM."""
    jobs = load_jobs()
    filtered = filter_jobs(
        jobs,
        category=category,
        tier=tier,
        thai_only=thai_only,
        min_salary=min_salary,
        salary_only=salary_only,
        q=q,
        sort_by=sort_by
    )
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "ID", "Company", "Title", "Category", "Location", "Advertised Salary",
        "Suitability Score", "Suitability Tier", "Priority", "Direct URL",
        "Strategic Match Rationale", "Tailored Resume Focus"
    ])
    for j in filtered:
        writer.writerow([
            j.get("col_01_id", ""),
            j.get("col_02_company", ""),
            j.get("col_03_title", ""),
            j.get("col_04_category", ""),
            j.get("col_06_location", ""),
            j.get("col_09_advertised_salary", ""),
            j.get("col_25_suitability_score", ""),
            j.get("col_26_suitability_tier", ""),
            j.get("col_28_priority", ""),
            j.get("col_15_direct_url", ""),
            j.get("col_29_explanation", ""),
            j.get("col_30_resume_emphasis", "")
        ])
    csv_bytes = output.getvalue().encode("utf-8-sig")
    return Response(
        content=csv_bytes,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=Filtered_Singapore_Opportunities.csv"}
    )

@app.get("/api/stats")
def get_stats(user: str = Depends(verify_credentials)):
    jobs = load_jobs()
    audit = load_audit()
    return {
        "authenticated_user": user,
        "total_jobs": _stats_cache.get("total_jobs", len(jobs)) if _stats_cache else len(jobs),
        "tiers": _stats_cache.get("tiers", {}) if _stats_cache else {},
        "categories": _stats_cache.get("categories", {}) if _stats_cache else {},
        "thai_relevance_jobs": _stats_cache.get("thai_relevance_jobs", 0) if _stats_cache else 0,
        "salary_disclosed_jobs": _stats_cache.get("salary_disclosed_jobs", 0) if _stats_cache else 0,
        "apify_spend_usd": audit.get("total_spend_usd", 33.5563),
        "apify_runs_completed": audit.get("runs_count", 33)
    }

@app.get("/api/top25")
def get_top25(user: str = Depends(verify_credentials)):
    jobs = load_jobs()
    return {
        "authenticated_user": user,
        "count": min(25, len(jobs)),
        "items": jobs[:25]
    }

@app.get("/download/excel")
def download_excel(user: str = Depends(verify_credentials)):
    if os.path.exists(EXCEL_FILE):
        return FileResponse(
            EXCEL_FILE,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            filename="Singapore_Career_Intelligence_Database_2026.xlsx"
        )
    raise HTTPException(status_code=404, detail="Excel workbook not found")

@app.get("/download/csv")
def download_csv(user: str = Depends(verify_credentials)):
    if os.path.exists(CSV_FILE):
        return FileResponse(
            CSV_FILE,
            media_type="text/csv",
            filename="Singapore_Career_Intelligence_Database_2026.csv"
        )
    raise HTTPException(status_code=404, detail="CSV database not found")

@app.get("/", response_class=HTMLResponse)
def index(user: str = Depends(verify_credentials)):
    jobs = load_jobs()
    top25 = jobs[:25]
    audit = load_audit()
    
    if _stats_cache:
        tiers_dict = _stats_cache.get("tiers", {})
        tier1_count = sum(v for k, v in tiers_dict.items() if "Tier 1" in k)
        thai_count = _stats_cache.get("thai_relevance_jobs", 0)
        salary_count = _stats_cache.get("salary_disclosed_jobs", 0)
    else:
        tier1_count = len([j for j in jobs if "Tier 1" in j.get("col_26_suitability_tier", "")])
        thai_count = len([j for j in jobs if "thai" in j.get("col_24_thai_relevance", "").lower() or "thai" in j.get("col_04_category", "").lower() or "thai" in j.get("col_03_title", "").lower()])
        salary_count = len([j for j in jobs if j.get("col_09_advertised_salary") and "not disclosed" not in j.get("col_09_advertised_salary", "").lower() and j.get("col_09_advertised_salary", "").strip()])

    template = load_template()
    safe_user = html.escape(user)
    
    content = template.replace("__SAFE_USER__", safe_user)
    content = content.replace("__TOTAL_JOBS__", f"{len(jobs):,}")
    content = content.replace("__TIER1_COUNT__", f"{tier1_count:,}")
    content = content.replace("__THAI_COUNT__", f"{thai_count:,}")
    content = content.replace("__SALARY_COUNT__", f"{salary_count:,}")
    content = content.replace("__TOP25_JSON__", json.dumps(top25, ensure_ascii=False))
    content = content.replace("__AUDIT_SPEND__", f"${audit.get('total_spend_usd', 33.56):.2f}")
    content = content.replace("__AUDIT_RUNS__", str(audit.get("runs_count", 33)))
    
    return HTMLResponse(content=content)

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("app:app", host="0.0.0.0", port=port, log_level="info")
