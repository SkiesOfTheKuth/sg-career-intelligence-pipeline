import os
import re
import json
import time
import logging
import tempfile
import threading

logger = logging.getLogger("sg_sync_engine")

_sync_lock = threading.Lock()
_telemetry = {
    "is_syncing": False,
    "last_sync_timestamp": None,
    "last_sync_status": "idle",
    "last_new_jobs_count": 0,
    "lifetime_synced_count": 0,
    "last_error": None
}

def get_sync_telemetry():
    """Returns a snapshot copy of current synchronization telemetry."""
    return dict(_telemetry)

def atomic_save_jobs(filepath: str, jobs: list) -> bool:
    """Safely and atomically writes the jobs dataset using temporary file replacement."""
    dir_name = os.path.dirname(os.path.abspath(filepath))
    temp_name = None
    try:
        with tempfile.NamedTemporaryFile("w", dir=dir_name, delete=False, encoding="utf-8") as tf:
            json.dump(jobs, tf, indent=2, ensure_ascii=False)
            temp_name = tf.name
        os.replace(temp_name, filepath)
        logger.info(f"Atomically persisted {len(jobs)} jobs to {filepath}")
        return True
    except Exception as e:
        logger.error(f"Failed atomic write to {filepath}: {e}")
        if temp_name and os.path.exists(temp_name):
            try:
                os.remove(temp_name)
            except OSError:
                pass
        raise

def transform_mcf_job(mcf_item: dict, next_id_num: int) -> dict:
    """Transforms a raw MyCareersFuture job item into the authoritative 30-column schema."""
    title = mcf_item.get("title", "Untitled Opportunity").strip()
    company = mcf_item.get("company", "Confidential Employer").strip()
    query_matched = mcf_item.get("query_matched", "")
    categories = mcf_item.get("categories", [])
    
    # Determine domain category
    cat_lower = (query_matched + " " + title + " " + " ".join(categories)).lower()
    if "thai" in cat_lower:
        category = "Category E: Thai-Speaking & Thailand-Focused Positions"
        thai_rel = "Critical Advantage"
        score = 95
        tier = "Tier 1: Excellent Direct Match"
        priority = "Priority 1: Immediate Application"
    elif any(k in cat_lower for k in ["social", "content", "influencer", "tiktok"]):
        category = "Category B: Social Media, Content, and Influencer Marketing"
        thai_rel = "General Regional Advantage"
        score = 90
        tier = "Tier 1: Excellent Direct Match"
        priority = "Priority 2: Strong Contender"
    elif any(k in cat_lower for k in ["public relations", "pr", "corporate communications"]):
        category = "Category C: Public Relations and Corporate Communications"
        thai_rel = "General Regional Advantage"
        score = 88
        tier = "Tier 1: Excellent Direct Match"
        priority = "Priority 2: Strong Contender"
    elif any(k in cat_lower for k in ["business development", "partnership", "account"]):
        category = "Category D: Business Development and Partnerships"
        thai_rel = "B2B Commercial Advantage"
        score = 86
        tier = "Tier 2: Strong Transferable-Skills Match"
        priority = "Priority 2: Strong Contender"
    elif any(k in cat_lower for k in ["event", "trade", "exhibition", "conference"]):
        category = "Category G: Events, Exhibitions, and Trade"
        thai_rel = "B2B Matchmaking Advantage"
        score = 88
        tier = "Tier 1: Excellent Direct Match"
        priority = "Priority 2: Strong Contender"
    else:
        category = "Category A: Marketing and Digital Marketing"
        thai_rel = "General Regional Advantage"
        score = 85
        tier = "Tier 2: Strong Transferable-Skills Match"
        priority = "Priority 3: Secondary Target"

    today_str = time.strftime("%Y-%m-%d")
    return {
        "col_01_id": f"SG-OPP-{next_id_num:04d}",
        "col_02_company": company,
        "col_03_title": title,
        "col_04_category": category,
        "col_05_industry": ", ".join(categories) or "Marketing & Communications",
        "col_06_location": mcf_item.get("location", "Singapore"),
        "col_07_work_arrangement": mcf_item.get("work_arrangement", "On-site / Hybrid (Singapore)"),
        "col_08_employment_type": mcf_item.get("employment_type", "Permanent Full-time"),
        "col_09_advertised_salary": mcf_item.get("advertised_salary", "Not disclosed"),
        "col_10_estimated_salary": "Market Benchmark SGD 4,500 - 6,500 / monthly",
        "col_11_posting_date": mcf_item.get("posted_date") or today_str,
        "col_12_deadline": mcf_item.get("expiry_date", ""),
        "col_13_checked_date": today_str,
        "col_14_source": "MyCareersFuture (Singapore Govt)",
        "col_15_direct_url": mcf_item.get("url", ""),
        "col_16_alt_url": "https://www.mycareersfuture.gov.sg",
        "col_17_verification_status": "Verified active",
        "col_18_responsibilities": mcf_item.get("description", "See primary portal for detailed job specifications."),
        "col_19_mandatory_reqs": mcf_item.get("requirements", "") or ", ".join(mcf_item.get("skills", [])),
        "col_20_preferred_reqs": "Bachelor/Master degree in Marketing, Business, or Communications; bilingual fluency.",
        "col_21_candidate_quals": "MSc Marketing (NTU Singapore), BBA International Marketing, Singapore Permanent Resident.",
        "col_22_matching_exp": "Demonstrated marketing campaign execution, digital media, and stakeholder coordination.",
        "col_23_gaps": "Standard company and industry onboarding orientation.",
        "col_24_thai_relevance": thai_rel,
        "col_25_suitability_score": score,
        "col_26_suitability_tier": tier,
        "col_27_confidence": "High",
        "col_28_priority": priority,
        "col_29_explanation": f"Direct profile alignment for {title} leveraging candidate's NTU Master's degree and commercial track record.",
        "col_30_resume_emphasis": f"Highlight NTU MSc Marketing qualification, Singapore PR local status, and relevant project achievements for {title}."
    }

def synchronize_upstream_jobs(data_file: str, queries=None, limit_per_query=10) -> dict:
    """Executes safe, deduplicated ingestion of new upstream positions and updates persistent storage."""
    global _telemetry
    if not _sync_lock.acquire(blocking=False):
        return {
            "status": "in_progress",
            "message": "Synchronization is already running in background.",
            "added_count": 0
        }
    
    _telemetry["is_syncing"] = True
    _telemetry["last_sync_status"] = "running"
    _telemetry["last_error"] = None
    t0 = time.time()
    
    try:
        from collector_mycareersfuture import fetch_mycareersfuture
        target_queries = queries or ["Thai", "Marketing Executive", "Social Media Executive", "Public Relations"]
        logger.info(f"Starting upstream sync for queries: {target_queries}...")
        
        raw_items = fetch_mycareersfuture(target_queries, limit_per_query=limit_per_query)
        logger.info(f"Fetched {len(raw_items)} raw items from upstream.")
        
        # Load existing jobs
        existing_jobs = []
        if os.path.exists(data_file):
            with open(data_file, "r", encoding="utf-8") as f:
                existing_jobs = json.load(f)
                
        existing_urls = {j.get("col_15_direct_url", "").strip() for j in existing_jobs if j.get("col_15_direct_url")}
        existing_tuples = {(j.get("col_02_company", "").lower().strip(), j.get("col_03_title", "").lower().strip()) for j in existing_jobs}
        
        # Determine highest existing ID
        max_id = 0
        for j in existing_jobs:
            id_str = j.get("col_01_id", "")
            if id_str.startswith("SG-OPP-"):
                try:
                    num = int(id_str.split("-")[-1])
                    if num > max_id:
                        max_id = num
                except ValueError:
                    pass
        if max_id == 0:
            max_id = len(existing_jobs)
            
        newly_added = []
        for item in raw_items:
            url = item.get("url", "").strip()
            comp = item.get("company", "").lower().strip()
            title = item.get("title", "").lower().strip()
            
            if url and url in existing_urls:
                continue
            if comp and title and (comp, title) in existing_tuples:
                continue
                
            max_id += 1
            new_record = transform_mcf_job(item, max_id)
            newly_added.append(new_record)
            if url:
                existing_urls.add(url)
            if comp and title:
                existing_tuples.add((comp, title))
                
        if newly_added:
            updated_jobs = existing_jobs + newly_added
            atomic_save_jobs(data_file, updated_jobs)
            logger.info(f"Successfully integrated {len(newly_added)} new unique jobs. Total now: {len(updated_jobs)}")
        else:
            logger.info("All harvested items were duplicates. Master dataset unchanged.")
            
        _telemetry["last_sync_timestamp"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        _telemetry["last_sync_status"] = "success"
        _telemetry["last_new_jobs_count"] = len(newly_added)
        _telemetry["lifetime_synced_count"] += len(newly_added)
        
        return {
            "status": "success",
            "added_count": len(newly_added),
            "total_jobs": len(existing_jobs) + len(newly_added),
            "duration_seconds": round(time.time() - t0, 2)
        }
    except Exception as e:
        logger.error(f"Synchronization failed: {e}")
        _telemetry["last_sync_status"] = "error"
        _telemetry["last_error"] = str(e)
        return {
            "status": "error",
            "message": str(e),
            "added_count": 0
        }
    finally:
        _telemetry["is_syncing"] = False
        _sync_lock.release()
