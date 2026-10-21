"""MyCareersFuture collection with explicit success and failure evidence.

The public endpoint is the existing upstream integration. A successful search only
verifies returned vacancies; absence from a limited search does not mean closure.
"""
import json
import logging
from datetime import datetime, timezone

import requests

logger = logging.getLogger("sg_collector_mcf")
SOURCE = "MyCareersFuture (Singapore Govt)"
API_URL = "https://api.mycareersfuture.gov.sg/v2/jobs"


def _now():
    return datetime.now(timezone.utc).isoformat()


def _labels(items, key):
    return [str(item[key]) for item in (items or []) if isinstance(item, dict) and item.get(key)]


def normalize_mcf_item(item, query="", checked_at=None):
    job_uuid = item.get("uuid")
    if not job_uuid or not item.get("title"):
        raise ValueError("Upstream vacancy is missing its UUID or title.")
    salary = item.get("salary") or {}
    minimum, maximum = salary.get("minimum"), salary.get("maximum")
    salary_type = (salary.get("type") or {}).get("salaryType")
    salary_text = "Not disclosed"
    try:
        numbers = [float(v) if v is not None else None for v in (minimum, maximum)]
        minimum, maximum = numbers
        if minimum is not None and maximum is not None:
            salary_text = f"SGD {minimum:,.2f} – {maximum:,.2f}"
        elif minimum is not None:
            salary_text = f"From SGD {minimum:,.2f}"
        elif maximum is not None:
            salary_text = f"Up to SGD {maximum:,.2f}"
        if salary_text != "Not disclosed" and salary_type:
            salary_text += f" / {salary_type.lower()}"
    except (ValueError, TypeError):
        minimum = maximum = None
    metadata = item.get("metadata") or {}
    slug = metadata.get("jobDetailsUrl") or ""
    job_url = ("https://www.mycareersfuture.gov.sg" + slug if slug.startswith("/") else slug)
    if not job_url:
        job_url = f"https://www.mycareersfuture.gov.sg/job/{job_uuid}"
    addresses = []
    for address in item.get("addresses") or []:
        parts = [address.get(key) for key in ("building", "street", "district", "postalCode") if address.get(key)]
        if parts:
            addresses.append(", ".join(str(part) for part in parts))
    status = item.get("status") or metadata.get("status") or ""
    if isinstance(status, dict):
        status = status.get("jobStatus") or status.get("status") or ""
    status = str(status).lower()
    # Returned search results verify existence, not an inferred unlimited deadline.
    status = "closed" if status in ("closed", "withdrawn", "removed", "filled") else "expired" if status == "expired" else "open"
    return {
        "id": f"MCF-{job_uuid}", "uuid": job_uuid,
        "title": str(item["title"]).strip(), "company": (item.get("postedCompany") or {}).get("name"),
        "source": SOURCE, "url": job_url,
        "advertised_salary": salary_text, "salary_min": minimum, "salary_max": maximum,
        "salary_type": salary_type, "structured_salary_verified": True,
        "employment_type": ", ".join(_labels(item.get("employmentTypes"), "employmentType")) or None,
        "employment_type_verified": True,
        "seniority": ", ".join(_labels(item.get("positionLevels"), "position")) or None,
        "categories": _labels(item.get("categories"), "category"),
        "location": "; ".join(addresses) or None,
        "work_arrangement": None,
        "posted_date": metadata.get("originalPostingDate"),
        "expiry_date": metadata.get("expiryDate"),
        "description": item.get("description") or "",
        "requirements": item.get("requirements") or "",
        "skills": _labels(item.get("skills"), "skill"),
        "query_matched": query, "verified_at": checked_at or _now(), "status": status,
        "raw_response": item,
    }


def fetch_mycareersfuture(queries, limit_per_query=50, timeout=10, return_report=False):
    """Return records, optionally with source failures instead of disguising errors as zero results."""
    jobs, errors, successes = {}, [], []
    headers = {"User-Agent": "SGCareerIntelligence/2.0", "Accept": "application/json"}
    for query in queries:
        count, page = 0, 0
        while count < limit_per_query and page < 5:
            attempted_at = _now()
            try:
                response = requests.get(API_URL, headers=headers,
                                        params={"search": query, "limit": min(20, limit_per_query - count), "page": page},
                                        timeout=timeout)
                response.raise_for_status()
                payload = response.json()
                if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
                    raise ValueError("Upstream response does not contain a results list.")
                results = payload["results"]
                for item in results[:limit_per_query - count]:
                    try:
                        record = normalize_mcf_item(item, query, attempted_at)
                        jobs[record["uuid"]] = record
                        count += 1
                    except (TypeError, ValueError) as error:
                        errors.append({"source": SOURCE, "query": query, "page": page,
                                       "attempted_at": attempted_at, "message": str(error)})
                successes.append({"source": SOURCE, "query": query, "page": page,
                                  "checked_at": attempted_at, "returned_count": len(results)})
                if not results:
                    break
                page += 1
            except (requests.RequestException, ValueError, TypeError) as error:
                errors.append({"source": SOURCE, "query": query, "page": page,
                               "attempted_at": attempted_at, "message": str(error)})
                logger.warning("MyCareersFuture query failed: %s, page %s: %s", query, page, error)
                break
    report = {"jobs": list(jobs.values()), "errors": errors, "successes": successes,
              "status": "degraded" if errors and successes else "error" if errors else "success"}
    if return_report:
        return report
    if errors and not successes:
        raise RuntimeError("MyCareersFuture could not be checked: " + errors[0]["message"])
    return report["jobs"]


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    report = fetch_mycareersfuture(["Thai", "Marketing Executive", "Social Media Executive", "Public Relations"],
                                  limit_per_query=40, return_report=True)
    if report["status"] == "error":
        raise SystemExit("Collection failed; retained data was not replaced.")
    with open("mcf_jobs_raw.json", "w", encoding="utf-8") as output:
        json.dump(report["jobs"], output, indent=2, ensure_ascii=False)
    print(f"Saved {len(report['jobs'])} jobs; {len(report['errors'])} source errors.")
