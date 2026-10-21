"""Upsert verified source records without discarding historical evidence.

Scheduling belongs to the FastAPI lifespan; this module performs one bounded run.
SQLite is authoritative when a Store is provided. JSON support is retained for
offline migration and source repair, not production application state.
"""
import copy
import json
import logging
import os
import re
import tempfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from evidence import build_job, present_job, repair_jobs, source_key

logger = logging.getLogger("sg_sync_engine")
_sync_lock = threading.Lock()
DEFAULT_QUERIES = ("Thai", "Marketing Executive", "Social Media Executive", "Public Relations")
DEFAULT_LIMIT = 10
_telemetry = {"is_syncing": False, "last_sync_timestamp": None, "last_sync_status": "idle",
              "last_new_jobs_count": 0, "lifetime_synced_count": 0, "last_error": None}


def _now():
    return datetime.now(timezone.utc).isoformat()


def get_sync_telemetry():
    return dict(_telemetry)


def atomic_save_jobs(filepath, jobs):
    destination = Path(filepath).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile("w", dir=destination.parent, delete=False, encoding="utf-8") as output:
            temporary = output.name
            json.dump(jobs, output, ensure_ascii=False, indent=2)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, destination)
        return True
    finally:
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)


def transform_mcf_job(mcf_item, next_id_num):
    return build_job(mcf_item, f"SG-OPP-{next_id_num:04d}")


def synchronize_upstream_jobs(data_file=None, queries=None, limit_per_query=DEFAULT_LIMIT, store=None):
    """Upsert returned MCF vacancies and persist source errors separately.

    An existing record absent from a limited search is not declared closed or
    newly verified. A failed check preserves its prior source facts and check date.
    """
    if store is None and hasattr(data_file, "list_jobs"):
        store, data_file = data_file, None
    if not _sync_lock.acquire(blocking=False):
        return {"status": "in_progress", "added_count": 0, "updated_count": 0}
    _telemetry.update(is_syncing=True, last_sync_status="running", last_error=None)
    started_at, started_clock = _now(), time.monotonic()
    result = None
    try:
        from collector_mycareersfuture import fetch_mycareersfuture, SOURCE
        from pipeline_processor import is_excluded_title
        existing = store.list_jobs() if store else json.loads(Path(data_file).read_text(encoding="utf-8-sig")) if data_file and Path(data_file).exists() else []
        if any(not job.get("evidence_version") for job in existing):
            existing = repair_jobs(existing)
        by_id = {job["id"]: job for job in existing}
        by_url = {source_key(job.get("url")): job for job in existing if source_key(job.get("url"))}
        max_id = max((int(job["id"].split("-")[-1]) for job in existing
                      if re.fullmatch(r"SG-OPP-\d+", job["id"])), default=0)
        report = fetch_mycareersfuture(queries or DEFAULT_QUERIES,
                                      limit_per_query=limit_per_query, return_report=True)
        # Accept legacy/custom collectors only as returned records, never as proof
        # that all previously stored vacancies were checked.
        if isinstance(report, list):
            report = {"jobs": report, "errors": [], "successes": [], "status": "success"}
        changed, updated_ids, added_count, updated_count = {}, set(), 0, 0
        for raw in report["jobs"]:
            key = source_key(raw.get("url"))
            if not key:
                continue
            previous = by_url.get(key)
            if previous is None and is_excluded_title(raw.get("title")):
                continue
            if previous:
                job_id = previous["id"]
                updated_count += 1
            else:
                max_id += 1
                job_id = f"SG-OPP-{max_id:04d}"
                added_count += 1
            updated = build_job(raw, job_id)
            # Each field keeps its own source date. A listing check does not
            # refresh content omitted by that response, including requirements
            # provided separately from its description.
            if previous:
                updated["url"] = previous["url"]
                for field, source_field in (('company', 'company'), ('location', 'location'),
                                            ('work_arrangement', 'work_arrangement'), ('posted_at', 'posted_date'),
                                            ('deadline', 'expiry_date'), ('employment_type', 'employment_type')):
                    if not raw.get(source_field) and previous.get(field):
                        updated[field] = copy.deepcopy(previous[field])
                if not raw.get('employment_type'):
                    updated['employment_types'] = copy.deepcopy(previous.get('employment_types', []))
                raw_response = raw.get('raw_response')
                salary_omitted = ('salary' not in raw_response if isinstance(raw_response, dict) else
                                  not any(raw.get(key) not in (None, '', 'Not disclosed')
                                          for key in ('salary_min', 'salary_max', 'advertised_salary')))
                if salary_omitted and previous.get('salary'):
                    updated['salary'] = copy.deepcopy(previous['salary'])
                if not updated["description"] and previous.get("description"):
                    for field in ("description", "description_complete"):
                        updated[field] = copy.deepcopy(previous.get(field))
                    updated.setdefault('field_provenance', {})['description'] = copy.deepcopy(previous.get('field_provenance', {}).get('description', {}))
                    updated["source_warning"] = "The latest source response omitted the description; the previously retained text is shown."
                # The native collector normalizes omitted/empty fields to ''.
                # Only non-empty explicit source text can supersede retained text.
                if not raw.get('requirements'):
                    updated['source_requirements'] = copy.deepcopy(previous.get('source_requirements',
                        previous.get('retained_requirements_source', previous.get('raw_evidence', {}).get('requirements'))))
                    updated['source_requirement_evidence'] = copy.deepcopy(previous.get('source_requirement_evidence', []))
                    updated.setdefault('field_provenance', {})['requirements'] = copy.deepcopy(previous.get('field_provenance', {}).get('requirements', {}))
                    if previous.get('requirements_source_unknown'):
                        updated['requirements_source_unknown'] = True
                        updated['requirements'] = copy.deepcopy(previous.get('requirements'))
                updated = present_job(updated)
            by_id[job_id] = updated
            by_url[key] = updated
            changed[job_id] = updated
            updated_ids.add(job_id)
            if store:
                store.record_source_evidence(job_id, SOURCE, {"status": "success", "checked_at": raw.get("verified_at"), "record": raw})
        errors = report.get("errors", [])
        if errors:
            latest_attempt = max((error.get("attempted_at", started_at) for error in errors), default=started_at)
            message = "; ".join(dict.fromkeys(error["message"] for error in errors))
            for job_id, job in by_id.items():
                if job_id in updated_ids or not any("mycareersfuture" in str(source.get("name", "")).lower() for source in job.get("sources", [])):
                    continue
                degraded = copy.deepcopy(job)
                degraded.setdefault("verification", {}).update(status="degraded", last_attempt_at=latest_attempt, last_error=message)
                degraded = present_job(degraded)
                by_id[job_id] = changed[job_id] = degraded
            if store:
                store.record_source_evidence("__source__:mycareersfuture", SOURCE, {"status": report["status"], "errors": errors})
        # Expiry can change even when no new upstream record is returned.
        for job_id, job in list(by_id.items()):
            current = present_job(job)
            if current != job:
                by_id[job_id] = changed[job_id] = current
        if store and changed:
            store.upsert_jobs(list(changed.values()))
        elif data_file and changed:
            atomic_save_jobs(data_file, list(by_id.values()))
        result = {"status": report.get("status", "success"), "started_at": started_at, "finished_at": _now(),
                  "added_count": added_count, "updated_count": updated_count, "total_jobs": len(by_id),
                  "errors": errors, "sources": report.get("successes", []),
                  "duration_seconds": round(time.monotonic() - started_clock, 2)}
        if store:
            store.record_sync(result)
        _telemetry.update(last_sync_timestamp=result["finished_at"], last_sync_status=result["status"],
                          last_new_jobs_count=added_count, lifetime_synced_count=_telemetry["lifetime_synced_count"] + added_count,
                          last_error=errors[0]["message"] if errors else None)
        return result
    except Exception as error:
        logger.exception("Source synchronization failed")
        result = {"status": "error", "started_at": started_at, "finished_at": _now(),
                  "added_count": 0, "updated_count": 0, "message": str(error),
                  "errors": [{"source": "MyCareersFuture (Singapore Govt)", "attempted_at": _now(), "message": str(error)}]}
        _telemetry.update(last_sync_status="error", last_error=str(error), last_sync_timestamp=result["finished_at"])
        if store:
            store.record_sync(result)
        return result
    finally:
        _telemetry["is_syncing"] = False
        _sync_lock.release()
