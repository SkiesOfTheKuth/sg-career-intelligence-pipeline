import os
import re
import json
import time
import logging
import tempfile
import threading

logger = logging.getLogger("sg_sync_engine")

_sync_lock = threading.Lock()
_export_lock = threading.Lock()
_export_in_progress = False
_export_pending = False

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

def trigger_export_refresh_async(data_file: str):
    """Refreshes downloadable Excel workbook and master CSV database in background with serialization and coalescing."""
    global _export_in_progress, _export_pending
    
    with _export_lock:
        if _export_in_progress:
            _export_pending = True
            logger.info("[Export Sync] Export worker is already active; queued pending refresh.")
            return
        _export_in_progress = True

    def _worker():
        global _export_in_progress, _export_pending
        try:
            from generate_workbook import build_full_workbook
            base_dir = os.path.dirname(os.path.abspath(data_file))
            xlsx_path = os.path.join(base_dir, "Singapore_Career_Intelligence_Database_2026.xlsx")
            csv_path = os.path.join(base_dir, "Singapore_Career_Intelligence_Database_2026.csv")
            
            while True:
                logger.info(f"[Export Sync] Updating Excel and CSV exports from {data_file}...")
                build_full_workbook(data_path=data_file, output_filename=xlsx_path, csv_filename=csv_path)
                logger.info("[Export Sync] Excel and CSV exports successfully synchronized.")
                
                with _export_lock:
                    if _export_pending:
                        _export_pending = False
                        logger.info("[Export Sync] Processing queued export request...")
                        continue
                    else:
                        _export_in_progress = False
                        break
        except Exception as e:
            logger.error(f"[Export Sync] Failed to synchronize exports: {e}")
            with _export_lock:
                _export_in_progress = False
                _export_pending = False

    threading.Thread(target=_worker, daemon=True, name="ExportSyncWorker").start()

_trigger_export_refresh = trigger_export_refresh_async

def transform_mcf_job(mcf_item: dict, next_id_num: int) -> dict:
    """Transforms a raw MyCareersFuture job item into the authoritative 30-column schema using canonical pipeline rules."""
    from pipeline_processor import categorize_job, calculate_suitability, estimate_market_salary
    
    title = mcf_item.get("title", "Untitled Opportunity").strip()
    company = mcf_item.get("company", "Confidential Employer").strip()
    query_matched = mcf_item.get("query_matched", "")
    categories = mcf_item.get("categories", [])
    desc = mcf_item.get("description", "See primary portal for detailed job specifications.")
    reqs = mcf_item.get("requirements", "") or ", ".join(mcf_item.get("skills", []))
    
    # Authoritative domain categorization and suitability calculation
    cat_lower = (query_matched + " " + title + " " + " ".join(categories)).lower()
    if "thai" in cat_lower or "thailand" in cat_lower:
        category = "Category E: Thai-Speaking & Thailand-Focused Positions"
        thai_rel = "Critical Advantage"
        score = 95
        tier = "Tier 1: Excellent Direct Match"
        priority = "Priority 1: Immediate Application"
    else:
        category = categorize_job(title, desc, reqs, query_matched)
        score, tier, priority, thai_rel = calculate_suitability(
            {"title": title, "description": desc, "requirements": reqs},
            category
        )
    
    # Authoritative salary estimation
    adv_salary = mcf_item.get("advertised_salary", "Not disclosed")
    est_salary = estimate_market_salary(category, title)
    
    industry = ", ".join(categories) if categories else "Marketing & Commercial Services"
    today_str = time.strftime("%Y-%m-%d")
    
    return {
        "col_01_id": f"SG-OPP-{next_id_num:04d}",
        "col_02_company": company,
        "col_03_title": title,
        "col_04_category": category,
        "col_05_industry": industry,
        "col_06_location": mcf_item.get("location", "Singapore"),
        "col_07_work_arrangement": mcf_item.get("work_arrangement", "On-site / Hybrid (Singapore)"),
        "col_08_employment_type": mcf_item.get("employment_type", "Permanent Full-time"),
        "col_09_advertised_salary": adv_salary,
        "col_10_estimated_salary": est_salary,
        "col_11_posting_date": mcf_item.get("posted_date") or today_str,
        "col_12_deadline": mcf_item.get("expiry_date", "Not stated / Open until filled"),
        "col_13_checked_date": today_str,
        "col_14_source": "MyCareersFuture (Singapore Govt)",
        "col_15_direct_url": mcf_item.get("url", ""),
        "col_16_alt_url": "https://www.mycareersfuture.gov.sg",
        "col_17_verification_status": "Verified active",
        "col_18_responsibilities": desc,
        "col_19_mandatory_reqs": reqs or "Bachelor's / Master's degree in Marketing, Business, or Communications; Professional English proficiency; Relevant digital or liaison experience.",
        "col_20_preferred_reqs": "Thai language proficiency, agency background, regional ASEAN market exposure, stakeholder management skills.",
        "col_21_candidate_quals": "MSc Marketing (NTU Singapore), BBA International Marketing (Kasetsart), Bilingual English & Thai, Singapore Permanent Resident.",
        "col_22_matching_exp": "Marketing & PR Specialist at Social Collective Studio; Content Creator at uWave; Interpreter at Royal Thai Embassy and APAC F&B Expo 2026.",
        "col_23_gaps": "Standard company and industry onboarding orientation.",
        "col_24_thai_relevance": thai_rel,
        "col_25_suitability_score": score,
        "col_26_suitability_tier": tier,
        "col_27_confidence": "High",
        "col_28_priority": priority,
        "col_29_explanation": f"Strategic profile alignment for {title} leveraging candidate's NTU Master's degree and commercial track record.",
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
        from pipeline_processor import is_excluded_title
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
            raw_title = item.get("title", "").strip()
            if is_excluded_title(raw_title):
                logger.info(f"Skipping excluded title: '{raw_title}'")
                continue

            url = item.get("url", "").strip()
            comp = item.get("company", "").lower().strip()
            title = raw_title.lower()
            
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
            _trigger_export_refresh(data_file)
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
