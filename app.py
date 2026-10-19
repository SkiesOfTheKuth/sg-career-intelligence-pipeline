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
    version="1.1.0"
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
            # Safe sync execution
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
        "version": "1.1.0",
        "uptime_seconds": int(time.time() - _start_time),
        "total_jobs_indexed": len(jobs),
        "sync_worker_alive": sync_thread.is_alive()
    }

# --- Authenticated Endpoints (Protected by User Kawa / Pass Kawa123) ---

@app.get("/api/jobs")
def get_jobs(
    category: str = Query(None),
    tier: str = Query(None),
    q: str = Query(None),
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
    if q:
        q_low = q.lower()
        filtered = [
            j for j in filtered
            if q_low in j.get("col_02_company", "").lower()
            or q_low in j.get("col_03_title", "").lower()
            or q_low in j.get("col_18_responsibilities", "").lower()
            or q_low in j.get("col_24_thai_relevance", "").lower()
        ]
    total = len(filtered)
    results = filtered[offset : offset + limit]
    return {
        "authenticated_user": user,
        "total": total,
        "offset": offset,
        "limit": limit,
        "items": results
    }

@app.get("/api/stats")
def get_stats(user: str = Depends(verify_credentials)):
    jobs = load_jobs()
    audit = load_audit()
    tiers = {}
    categories = {}
    thai_count = 0
    for j in jobs:
        t = j.get("col_26_suitability_tier", "Other")
        tiers[t] = tiers.get(t, 0) + 1
        c = j.get("col_04_category", "Other")
        categories[c] = categories.get(c, 0) + 1
        if "Thai" in j.get("col_24_thai_relevance", "") or "Thai" in j.get("col_04_category", ""):
            thai_count += 1
    return {
        "authenticated_user": user,
        "total_jobs": len(jobs),
        "tiers": tiers,
        "categories": categories,
        "thai_relevance_jobs": thai_count,
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
    thai_count = len([j for j in jobs if "Thai" in j.get("col_24_thai_relevance", "") or "Category E" in j.get("col_04_category", "")])
    
    # Safe HTML building with full XSS escaping
    cards_html_parts = []
    for idx, j in enumerate(top25, 1):
        s_title = html.escape(str(j.get("col_03_title", "Untitled Position")))
        s_company = html.escape(str(j.get("col_02_company", "Confidential Employer")))
        s_score = html.escape(str(j.get("col_25_suitability_score", "N/A")))
        s_priority = html.escape(str(j.get("col_28_priority", "Standard")))
        s_source = html.escape(str(j.get("col_14_source", "Singapore Portal")))
        s_salary = html.escape(str(j.get("col_09_advertised_salary", "Not disclosed")))
        s_location = html.escape(str(j.get("col_06_location", "Singapore")))
        s_emp_type = html.escape(str(j.get("col_08_employment_type", "Full-time")))
        s_desc = html.escape(str(j.get("col_18_responsibilities", ""))[:240])
        s_exp = html.escape(str(j.get("col_29_explanation", "Direct profile alignment.")))
        s_emphasis = html.escape(str(j.get("col_30_resume_emphasis", "Highlight relevant experience.")))
        s_thai = html.escape(str(j.get("col_24_thai_relevance", "General")))
        s_url = sanitize_url(j.get("col_15_direct_url", ""))
        
        cards_html_parts.append(f"""
        <div class="job-card">
            <div class="job-header">
                <div>
                    <span class="badge tier1">Score: {s_score}/100</span>
                    <span class="badge priority">{s_priority}</span>
                    <span class="badge source">{s_source}</span>
                </div>
                <div class="salary-tag">{s_salary}</div>
            </div>
            <h3 class="job-title">{idx}. {s_title}</h3>
            <div class="company-name">{s_company} &bull; {s_location} &bull; {s_emp_type}</div>
            <p class="job-desc">{s_desc}...</p>
            <div class="match-box">
                <strong>Matching Rationale:</strong> {s_exp}<br>
                <strong>Tailored Résumé Focus:</strong> {s_emphasis}
            </div>
            <div class="job-footer">
                <span class="thai-badge">{s_thai}</span>
                <a href="{s_url}" target="_blank" rel="noopener noreferrer" class="apply-btn">Apply Directly &rarr;</a>
            </div>
        </div>
        """)
        
    top25_html = "\n".join(cards_html_parts)
    safe_user = html.escape(user)
    
    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Singapore Career Intelligence Pipeline | Executive Recruitment Intelligence</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
    <style>
        :root {{
            --primary: #1B365D;
            --primary-accent: #0066CC;
            --bg: #F8FAFC;
            --card-bg: #FFFFFF;
            --text-main: #0F172A;
            --text-muted: #64748B;
            --border: #E2E8F0;
            --tier1: #059669;
            --tier1-bg: #ECFDF5;
        }}
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            font-family: 'Inter', -apple-system, sans-serif;
            background: var(--bg);
            color: var(--text-main);
            line-height: 1.5;
            padding-bottom: 60px;
        }}
        header {{
            background: var(--primary);
            color: white;
            padding: 36px 24px;
            border-bottom: 4px solid #0066CC;
        }}
        .header-container {{
            max-width: 1200px;
            margin: 0 auto;
        }}
        .header-top {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 12px;
            flex-wrap: wrap;
            gap: 12px;
        }}
        .header-title {{
            font-size: 26px;
            font-weight: 700;
        }}
        .header-subtitle {{
            font-size: 14px;
            color: #CBD5E1;
            margin-bottom: 20px;
        }}
        .user-tag {{
            background: rgba(255, 255, 255, 0.15);
            padding: 6px 14px;
            border-radius: 20px;
            font-size: 13px;
            display: flex;
            align-items: center;
            gap: 8px;
        }}
        .candidate-meta {{
            display: flex;
            flex-wrap: wrap;
            gap: 16px;
            background: rgba(255, 255, 255, 0.08);
            padding: 14px 20px;
            border-radius: 8px;
            font-size: 13px;
        }}
        .candidate-meta span {{ color: #94A3B8; }}
        .candidate-meta strong {{ color: #FFFFFF; }}
        .metrics-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 16px;
            max-width: 1200px;
            margin: -24px auto 32px auto;
            padding: 0 24px;
        }}
        .metric-card {{
            background: var(--card-bg);
            padding: 20px;
            border-radius: 10px;
            box-shadow: 0 4px 6px -1px rgba(0,0,0,0.05), 0 2px 4px -2px rgba(0,0,0,0.05);
            border: 1px solid var(--border);
        }}
        .metric-val {{
            font-size: 26px;
            font-weight: 700;
            color: var(--primary);
        }}
        .metric-label {{
            font-size: 13px;
            color: var(--text-muted);
            margin-top: 4px;
        }}
        .main-container {{
            max-width: 1200px;
            margin: 0 auto;
            padding: 0 24px;
        }}
        .section-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 20px;
            flex-wrap: wrap;
            gap: 12px;
        }}
        .section-title {{
            font-size: 20px;
            font-weight: 700;
            color: var(--primary);
        }}
        .action-btns {{
            display: flex;
            gap: 12px;
            flex-wrap: wrap;
        }}
        .btn {{
            display: inline-flex;
            align-items: center;
            padding: 10px 18px;
            font-size: 13px;
            font-weight: 600;
            border-radius: 6px;
            text-decoration: none;
            cursor: pointer;
            transition: all 0.2s;
        }}
        .btn-primary {{
            background: var(--primary-accent);
            color: white;
            border: none;
        }}
        .btn-primary:hover {{ background: #0052A3; }}
        .btn-secondary {{
            background: white;
            color: var(--primary);
            border: 1px solid var(--border);
        }}
        .btn-secondary:hover {{ background: #F1F5F9; }}
        .jobs-grid {{
            display: grid;
            grid-template-columns: 1fr;
            gap: 18px;
            margin-bottom: 40px;
        }}
        .job-card {{
            background: var(--card-bg);
            border: 1px solid var(--border);
            border-radius: 10px;
            padding: 22px;
            transition: transform 0.15s, box-shadow 0.15s;
        }}
        .job-card:hover {{
            transform: translateY(-2px);
            box-shadow: 0 10px 15px -3px rgba(0,0,0,0.07);
        }}
        .job-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 12px;
            flex-wrap: wrap;
            gap: 8px;
        }}
        .badge {{
            display: inline-block;
            padding: 4px 10px;
            border-radius: 20px;
            font-size: 12px;
            font-weight: 600;
            margin-right: 6px;
        }}
        .badge.tier1 {{ background: #ECFDF5; color: #047857; }}
        .badge.priority {{ background: #FEF3C7; color: #B45309; }}
        .badge.source {{ background: #EFF6FF; color: #1D4ED8; }}
        .thai-badge {{
            font-size: 12px;
            font-weight: 600;
            color: #7C3AED;
            background: #F5F3FF;
            padding: 4px 10px;
            border-radius: 20px;
        }}
        .salary-tag {{
            font-weight: 600;
            color: #0F172A;
            font-size: 14px;
        }}
        .job-title {{
            font-size: 18px;
            font-weight: 700;
            color: var(--primary);
            margin-bottom: 4px;
        }}
        .company-name {{
            font-size: 14px;
            color: var(--text-muted);
            margin-bottom: 12px;
        }}
        .job-desc {{
            font-size: 14px;
            color: #334155;
            margin-bottom: 14px;
        }}
        .match-box {{
            background: #F8FAFC;
            border-left: 3px solid var(--primary-accent);
            padding: 12px 16px;
            border-radius: 0 6px 6px 0;
            font-size: 13px;
            color: #1E293B;
            margin-bottom: 16px;
        }}
        .match-box strong {{ color: var(--primary); }}
        .job-footer {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-top: 1px solid var(--border);
            padding-top: 14px;
            flex-wrap: wrap;
            gap: 10px;
        }}
        .apply-btn {{
            background: var(--primary);
            color: white;
            text-decoration: none;
            padding: 8px 16px;
            border-radius: 6px;
            font-size: 13px;
            font-weight: 600;
            transition: background 0.2s;
        }}
        .apply-btn:hover {{ background: var(--primary-accent); }}
        .live-badge {{
            display: inline-flex;
            align-items: center;
            gap: 6px;
            background: #22C55E;
            color: white;
            font-size: 12px;
            padding: 3px 8px;
            border-radius: 12px;
            font-weight: 600;
        }}
        .pulse {{
            width: 8px;
            height: 8px;
            background: white;
            border-radius: 50%;
            animation: pulse 1.5s infinite;
        }}
        @keyframes pulse {{
            0% {{ transform: scale(0.95); opacity: 0.8; }}
            50% {{ transform: scale(1.3); opacity: 1; }}
            100% {{ transform: scale(0.95); opacity: 0.8; }}
        }}
    </style>
</head>
<body>
    <header>
        <div class="header-container">
            <div class="header-top">
                <div style="display:flex; align-items:center; gap:12px;">
                    <h1 class="header-title">Singapore Career Intelligence Pipeline</h1>
                    <span class="live-badge"><span class="pulse"></span> LIVE RECRUITMENT PIPELINE</span>
                </div>
                <div class="user-tag">&#128274; Authenticated as: <strong>{safe_user}</strong></div>
            </div>
            <p class="header-subtitle">Executive recruitment intelligence, candidate matching matrix, and multi-source job vacancy harvester</p>
            <div class="candidate-meta">
                <div><span>Candidate:</span> <strong>Dechsurang Kawintra</strong></div>
                <div><span>Education:</span> <strong>MSc Marketing (NTU Singapore) &bull; BBA Int'l Marketing (Kasetsart)</strong></div>
                <div><span>Eligibility:</span> <strong>Singapore Permanent Resident (Local Parity)</strong></div>
                <div><span>Languages:</span> <strong>Bilingual Thai (Native) &bull; English (Fluent)</strong></div>
                <div><span>Current Role:</span> <strong>Marketing & PR Specialist, Social Collective Studio</strong></div>
            </div>
        </div>
    </header>

    <div class="metrics-grid">
        <div class="metric-card">
            <div class="metric-val">{len(jobs):,}</div>
            <div class="metric-label">Total Verified Vacancies</div>
        </div>
        <div class="metric-card">
            <div class="metric-val">{tier1_count:,}</div>
            <div class="metric-label">Tier 1 Direct Matches</div>
        </div>
        <div class="metric-card">
            <div class="metric-val">{thai_count:,}</div>
            <div class="metric-label">Thai-Language Advantage Roles</div>
        </div>
        <div class="metric-card">
            <div class="metric-val">${audit.get('total_spend_usd', 33.5563):.2f}</div>
            <div class="metric-label">Apify Scraping Budget Invested</div>
        </div>
        <div class="metric-card">
            <div class="metric-val">{audit.get('runs_count', 33)} Runs</div>
            <div class="metric-label">Apify Multi-Account Scrapers</div>
        </div>
    </div>

    <div class="main-container">
        <div class="section-header">
            <div>
                <h2 class="section-title">Top 25 Recommended Vacancies (Ranked Shortlist)</h2>
                <p style="font-size:13px; color:var(--text-muted); margin-top:2px;">Prioritized based on candidate qualifications, NTU Master's degree, bilingual advantage, and Singapore PR status.</p>
            </div>
            <div class="action-btns">
                <a href="/download/excel" class="btn btn-primary">&#128196; Download Excel Workbook (.xlsx)</a>
                <a href="/download/csv" class="btn btn-secondary">&#128195; Export CSV</a>
            </div>
        </div>

        <div class="jobs-grid">
            {top25_html}
        </div>
    </div>
</body>
</html>
    """
    return HTMLResponse(content=html_content)

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("app:app", host="0.0.0.0", port=port, log_level="info")
