import requests
import json
import time

def fetch_mycareersfuture(queries, limit_per_query=50):
    all_jobs = {}
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'application/json'
    }
    
    for q in queries:
        print(f"Searching MyCareersFuture for: '{q}'...")
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
                res = requests.get(url, headers=headers, params=params, timeout=12)
                if res.status_code != 200:
                    print(f"  Error {res.status_code} for query '{q}' page {page}")
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
                    
                    if sal_min and sal_max:
                        advertised_sal = f"SGD {sal_min:,.0f} - {sal_max:,.0f} / {sal_type.lower()}"
                    elif sal_min:
                        advertised_sal = f"From SGD {sal_min:,.0f} / {sal_type.lower()}"
                    else:
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
                time.sleep(0.3)
            except Exception as e:
                print(f"Exception fetching {q}: {e}")
                break
                
        print(f"  Total collected for '{q}': {total_found}")
        
    print(f"\nUnique MyCareersFuture jobs collected: {len(all_jobs)}")
    return list(all_jobs.values())

if __name__ == '__main__':
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
