import requests
import json
import time
import logging

logger = logging.getLogger("sg_collector_mcf")

def fetch_mycareersfuture(queries, limit_per_query=50, timeout=10):
    """Harvests active job positions from MyCareersFuture API with error handling and deduplication."""
    all_jobs = {}
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'application/json'
    }
    
    for q in queries:
        logger.info(f"Querying MyCareersFuture API for: '{q}' (limit={limit_per_query})...")
        page = 0
        total_found = 0
        while True:
            url = 'https://api.mycareersfuture.gov.sg/v2/jobs'
            params = {
                'search': q,
                'limit': 20,
                'page': page
            }
            try:
                res = requests.get(url, headers=headers, params=params, timeout=timeout)
                if res.status_code != 200:
                    logger.warning(f"Upstream MCF returned HTTP {res.status_code} for query '{q}' page {page}")
                    break
                data = res.json()
                results = data.get('results', [])
                if not results:
                    break
                
                for item in results:
                    job_uuid = item.get('uuid')
                    if not job_uuid:
                        continue
                    
                    # Extract fields
                    title = item.get('title', '').strip()
                    company = item.get('postedCompany', {}).get('name', '').strip()
                    
                    # Salary
                    sal = item.get('salary', {})
                    sal_min = sal.get('minimum')
                    sal_max = sal.get('maximum')
                    sal_type = sal.get('type', {}).get('salaryType', 'Monthly')
                    
                    try:
                        s_min = float(sal_min) if sal_min is not None else None
                        s_max = float(sal_max) if sal_max is not None else None
                        st = str(sal_type or 'Monthly').lower()
                        if s_min is not None and s_max is not None:
                            advertised_sal = f"SGD {s_min:,.0f} - {s_max:,.0f} / {st}"
                        elif s_min is not None:
                            advertised_sal = f"From SGD {s_min:,.0f} / {st}"
                        else:
                            advertised_sal = "Not disclosed"
                    except (ValueError, TypeError):
                        advertised_sal = "Not disclosed"
                        
                    # Employment & location
                    emp_types = [t.get('employmentType') for t in item.get('employmentTypes', []) if t.get('employmentType')]
                    emp_type = ", ".join(emp_types) if emp_types else "Full Time"
                    
                    # Work arrangement / position level
                    levels = [lvl.get('position') for lvl in item.get('positionLevels', []) if lvl.get('position')]
                    seniority = ", ".join(levels) if levels else "Executive"
                    
                    # Categories / Industries
                    categories = [c.get('category') for c in item.get('categories', []) if c.get('category')]
                    
                    # URLs
                    slug = item.get('metadata', {}).get('jobDetailsUrl', '')
                    if slug:
                        job_url = f"https://www.mycareersfuture.gov.sg{slug}" if slug.startswith('/') else slug
                    else:
                        job_url = f"https://www.mycareersfuture.gov.sg/job/{job_uuid}"
                    
                    posted_date = item.get('metadata', {}).get('originalPostingDate', '')[:10]
                    expiry_date = item.get('metadata', {}).get('expiryDate', '')[:10]
                    
                    # Job description & requirements
                    desc = item.get('description', '')
                    reqs = item.get('requirements', '')
                    skills = [s.get('skill') for s in item.get('skills', []) if s.get('skill')]
                    
                    all_jobs[job_uuid] = {
                        'id': f"MCF-{job_uuid[:8]}",
                        'uuid': job_uuid,
                        'company': company,
                        'title': title,
                        'source': 'MyCareersFuture (Singapore Govt)',
                        'url': job_url,
                        'advertised_salary': advertised_sal,
                        'salary_min': sal_min,
                        'salary_max': sal_max,
                        'salary_type': sal_type,
                        'employment_type': emp_type,
                        'seniority': seniority,
                        'categories': categories,
                        'location': 'Singapore',
                        'work_arrangement': 'On-site / Hybrid (Singapore)',
                        'posted_date': posted_date,
                        'expiry_date': expiry_date,
                        'description': desc,
                        'requirements': reqs,
                        'skills': skills,
                        'query_matched': q
                    }
                    total_found += 1
                
                page += 1
                if total_found >= limit_per_query or page >= 5:
                    break
                time.sleep(0.2)
            except requests.RequestException as req_err:
                logger.warning(f"Network error querying MCF for '{q}': {req_err}")
                break
            except Exception as e:
                logger.error(f"Unexpected exception processing MCF response for '{q}': {e}")
                break
                
        logger.info(f"Collected {total_found} postings for query '{q}'.")
        
    logger.info(f"Total unique MyCareersFuture positions harvested: {len(all_jobs)}")
    return list(all_jobs.values())

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    target_queries = [
        "Thai",
        "Thailand",
        "Thai speaking",
        "Marketing Executive",
        "Social Media Executive",
        "Public Relations Executive",
        "Influencer Marketing",
        "Content Marketing",
        "Digital Marketing Executive",
        "Brand Executive",
        "Partnerships Executive",
        "Events Executive",
        "Trade Show",
        "Bilingual Interpreter",
        "Communications Executive",
        "Regional Marketing",
        "ASEAN Marketing",
        "Client Success Executive",
        "Market Research Executive"
    ]
    jobs = fetch_mycareersfuture(target_queries, limit_per_query=40)
    with open('mcf_jobs_raw.json', 'w', encoding='utf-8') as f:
        json.dump(jobs, f, indent=2, ensure_ascii=False)
    print(f"Saved {len(jobs)} jobs to mcf_jobs_raw.json")
