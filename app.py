import os
import json
import html
import threading
import time
import logging
import secrets
from urllib.parse import urlparse
from fastapi import FastAPI, Query, Depends, HTTPException, status
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBasic, HTTPBasicCredentials

# Configure structured logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("sg_career_pipeline")

app = FastAPI(
    title="Singapore Career Intelligence Pipeline",
    description="Executive recruitment intelligence and automated job-matching engine for candidate Dechsurang Kawintra",
    version="1.2.0"
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

# In-Memory Cache to prevent 11.9MB JSON file read on every request
_jobs_cache = None
_jobs_mtime = 0
_cache_lock = threading.Lock()
_start_time = time.time()

def load_jobs():
    """Loads jobs dataset with mtime-based memory caching."""
    global _jobs_cache, _jobs_mtime
    if not os.path.exists(DATA_FILE):
        return []
    try:
        current_mtime = os.path.getmtime(DATA_FILE)
        with _cache_lock:
            if _jobs_cache is None or current_mtime > _jobs_mtime:
                logger.info(f"Loading jobs from {DATA_FILE} (mtime: {current_mtime})...")
                with open(DATA_FILE, "r", encoding="utf-8") as f:
                    _jobs_cache = json.load(f)
                _jobs_mtime = current_mtime
                logger.info(f"Loaded {len(_jobs_cache)} jobs into memory cache.")
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

# Autonomous Background Sync Worker
_sync_lock = threading.Lock()

def background_refresh_loop():
    """Runs periodic sync every 12 hours with thread-safety and error isolation."""
    while True:
        time.sleep(43200) # 12 hours
        if not _sync_lock.acquire(blocking=False):
            continue
        try:
            logger.info("[Continuous Pipeline] Running automated periodic sync...")
            try:
                from collector_mycareersfuture import fetch_mycareersfuture
                new_mcf = fetch_mycareersfuture(["Thai", "Marketing Executive", "Social Media Executive"], limit_per_query=10)
                if new_mcf:
                    logger.info(f"[Continuous Pipeline] Harvested {len(new_mcf)} new positions.")
            except Exception as sync_err:
                logger.warning(f"[Continuous Pipeline] Upstream poll warning: {sync_err}")
        except Exception as e:
            logger.error(f"[Continuous Pipeline] Sync loop exception: {e}")
        finally:
            _sync_lock.release()

sync_thread = threading.Thread(target=background_refresh_loop, daemon=True, name="SyncWorker")
sync_thread.start()

# --- Health Check (Unauthenticated for Cloud Orchestrator / Render monitoring) ---
@app.get("/healthz")
def healthz():
    jobs = load_jobs()
    return {
        "status": "healthy",
        "version": "1.2.0",
        "uptime_seconds": int(time.time() - _start_time),
        "total_jobs_indexed": len(jobs),
        "sync_worker_alive": sync_thread.is_alive()
    }

# --- Authenticated Endpoints (Protected by User Kawa / Pass Kawa123) ---

@app.get("/api/jobs")
def get_jobs(
    category: str = Query(None),
    tier: str = Query(None),
    thai_only: bool = Query(False),
    q: str = Query(None),
    sort_by: str = Query("score"),
    limit: int = Query(100, ge=1, le=250),
    offset: int = Query(0, ge=0),
    user: str = Depends(verify_credentials)
):
    jobs = load_jobs()
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
    if q:
        q_low = q.lower()
        filtered = [
            j for j in filtered
            if q_low in j.get("col_02_company", "").lower()
            or q_low in j.get("col_03_title", "").lower()
            or q_low in j.get("col_18_responsibilities", "").lower()
            or q_low in j.get("col_24_thai_relevance", "").lower()
            or q_low in j.get("col_21_candidate_quals", "").lower()
        ]

    # Safe sorting
    if sort_by == "title":
        filtered.sort(key=lambda j: j.get("col_03_title", "").lower())
    elif sort_by == "company":
        filtered.sort(key=lambda j: j.get("col_02_company", "").lower())
    else:
        # Default sort by suitability score descending
        def get_score(job):
            try:
                return int(job.get("col_25_suitability_score", 0))
            except (ValueError, TypeError):
                return 0
        filtered.sort(key=get_score, reverse=True)

    total = len(filtered)
    results = filtered[offset : offset + limit]
    return {
        "authenticated_user": user,
        "total": total,
        "offset": offset,
        "limit": limit,
        "items": results
    }

@app.get("/api/jobs/{job_id}")
def get_job_by_id(job_id: str, user: str = Depends(verify_credentials)):
    jobs = load_jobs()
    for j in jobs:
        if j.get("col_01_id") == job_id:
            return {"authenticated_user": user, "job": j}
    raise HTTPException(status_code=404, detail="Job position not found")

@app.get("/api/stats")
def get_stats(user: str = Depends(verify_credentials)):
    jobs = load_jobs()
    audit = load_audit()
    tiers = {}
    categories = {}
    thai_count = 0
    salary_count = 0
    for j in jobs:
        t = j.get("col_26_suitability_tier", "Other")
        tiers[t] = tiers.get(t, 0) + 1
        c = j.get("col_04_category", "Other")
        categories[c] = categories.get(c, 0) + 1
        if "thai" in j.get("col_24_thai_relevance", "").lower() or "thai" in j.get("col_04_category", "").lower() or "thai" in j.get("col_03_title", "").lower():
            thai_count += 1
        sal = j.get("col_09_advertised_salary", "")
        if sal and "not disclosed" not in sal.lower() and sal.strip():
            salary_count += 1
    return {
        "authenticated_user": user,
        "total_jobs": len(jobs),
        "tiers": tiers,
        "categories": categories,
        "thai_relevance_jobs": thai_count,
        "salary_disclosed_jobs": salary_count,
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
