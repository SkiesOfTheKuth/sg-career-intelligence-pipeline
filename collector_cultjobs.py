import requests
from bs4 import BeautifulSoup
import json
import time

def fetch_cultjobs(categories):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    all_jobs = {}
    
    for cat in categories:
        print(f"Scraping Cultjobs for: {cat}...")
        url = f"https://www.cultjobs.com/search/{cat}"
        try:
            r = requests.get(url, headers=headers, timeout=12)
            if r.status_code != 200:
                print(f"  Status {r.status_code}")
                continue
            soup = BeautifulSoup(r.text, 'html.parser')
            # Find job links
            cards = soup.select('.job-card, .job, article, .item, .job-listing')
            links = soup.find_all('a', href=True)
            job_urls = list(dict.fromkeys([l['href'] for l in links if '/job/' in l['href']]))
            print(f"  Found {len(job_urls)} job links for '{cat}'")
            
            for jurl in job_urls[:15]:
                full_url = f"https://www.cultjobs.com{jurl}" if jurl.startswith('/') else jurl
                if full_url in all_jobs:
                    continue
                try:
                    jr = requests.get(full_url, headers=headers, timeout=10)
                    if jr.status_code == 200:
                        jsoup = BeautifulSoup(jr.text, 'html.parser')
                        title_el = jsoup.find('h1')
                        title = title_el.text.strip() if title_el else ""
                        
                        company_el = jsoup.select_one('.company, .employer, h2, .company-name')
                        company = company_el.text.strip() if company_el else "Cultjobs Employer"
                        
                        desc_el = jsoup.select_one('.job-description, .description, .content, #job-description')
                        desc = desc_el.text.strip() if desc_el else jsoup.get_text()[:1500]
                        
                        # Look for salary in text
                        sal_str = "Not disclosed"
                        for line in jsoup.get_text().split('\n'):
                            if '$' in line or 'SGD' in line or 'salary' in line.lower():
                                if any(c.isdigit() for c in line) and len(line.strip()) < 80:
                                    sal_str = line.strip()
                                    break
                                    
                        all_jobs[full_url] = {
                            'id': f"CULT-{len(all_jobs)+1:03d}",
                            'title': title,
                            'company': company,
                            'source': 'Cultjobs Singapore',
                            'url': full_url,
                            'advertised_salary': sal_str,
                            'salary_min': None,
                            'salary_max': None,
                            'salary_type': 'Monthly',
                            'employment_type': 'Full Time',
                            'seniority': 'Executive',
                            'categories': [cat],
                            'location': 'Singapore',
                            'work_arrangement': 'On-site / Hybrid (Singapore)',
                            'posted_date': '2026-10-15',
                            'expiry_date': '',
                            'description': desc[:2000],
                            'requirements': '',
                            'skills': [],
                            'query_matched': cat
                        }
                    time.sleep(0.3)
                except Exception as ex:
                    print(f"Error fetching {full_url}: {ex}")
        except Exception as e:
            print(f"Error searching {cat}: {e}")
            
    print(f"\nUnique Cultjobs collected: {len(all_jobs)}")
    return list(all_jobs.values())

if __name__ == '__main__':
    categories = [
        "marketing",
        "social-media",
        "public-relations",
        "content",
        "brand",
        "communications",
        "events",
        "account-executive"
    ]
    jobs = fetch_cultjobs(categories)
    with open('cultjobs_raw.json', 'w', encoding='utf-8') as f:
        json.dump(jobs, f, indent=2, ensure_ascii=False)
    print(f"Saved {len(jobs)} jobs to cultjobs_raw.json")
