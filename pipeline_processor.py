"""Offline repair of retained source records. No paid collection is performed."""
import json
import re
from pathlib import Path

EXCLUSION_TITLE_KEYWORDS = (
    'chef', 'cook', 'kitchen', 'dishwasher', 'cleaner', 'driver', 'rider',
    'masseur', 'therapist', 'waiter', 'waitress', 'service crew', 'bartender',
    'nursing', 'nurse', 'doctor', 'physiotherapist', 'pharmacist',
    'technician', 'electrician', 'plumber', 'mechanic', 'carpenter',
    'construction worker', 'security guard', 'security officer', 'warehouse assistant',
    'intern', 'internship', 'trainee',
)


def is_excluded_title(title):
    title = (title or '').lower()
    if any(term in title for term in ('management trainee', 'graduate trainee', 'executive trainee',
                                      'marketing trainee', 'commercial trainee', 'growth driver', 'business driver')):
        return False
    for term in EXCLUSION_TITLE_KEYWORDS:
        if not re.search(r'\b' + re.escape(term) + r'\b', title):
            continue
        if term in ('security guard', 'security officer') and re.search(r'cyber|information|it security|infosec|network security', title):
            continue
        if term == 'driver' and re.search(r'growth|business|commercial|strategy|revenue', title):
            continue
        return True
    return False


def categorize_job(title, desc='', reqs='', matched_query=''):
    """Job family is derived from the role title, never the search query."""
    from evidence import job_family
    return job_family(title or '')


def calculate_suitability(job, category=None):
    """Compatibility adapter; unsupported percentage scores are unavailable."""
    from evidence import assess, plain_text, extract_requirements, thai_relevance
    title = job.get('title') or job.get('col_03_title') or ''
    description = plain_text(job.get('description') or '')
    requirements = extract_requirements(description, job.get('requirements'))
    assessment = assess(title, description, requirements)
    return None, assessment['fit'], 'Review the role requirements', thai_relevance(title, description, requirements)


def estimate_market_salary(category, title):
    """An unverified market benchmark is not an advertised salary."""
    return None


def extract_salary_max(salary):
    from evidence import salary_presentation
    return salary_presentation({'advertised_salary': salary})['maximum']


def process_all_jobs(data_file='processed_master_jobs.json', raw_dir=None):
    """Repair retained data, preserving every existing job identity."""
    from evidence import RAW_FILES, repair_jobs, source_key, build_job, sort_key
    from sync_engine import atomic_save_jobs
    root = Path(raw_dir) if raw_dir else Path(__file__).resolve().parent
    target = Path(data_file)
    if not target.is_absolute():
        target = root / target
    old = json.loads(target.read_text(encoding='utf-8-sig')) if target.exists() else []
    jobs = repair_jobs(old, root)
    known = {source_key(job.get('url')) for job in jobs}
    max_id = max((int(job['id'].removeprefix('SG-OPP-')) for job in jobs
                  if re.fullmatch(r'SG-OPP-\d+', job.get('id', ''))), default=0)
    for filename in RAW_FILES:
        source = root / filename
        if not source.exists():
            continue
        for raw in json.loads(source.read_text(encoding='utf-8-sig')):
            key = source_key(raw.get('url'))
            if not key or key in known or not raw.get('title') or is_excluded_title(raw['title']):
                continue
            max_id += 1
            jobs.append(build_job(raw, f'SG-OPP-{max_id:04d}'))
            known.add(key)
    jobs.sort(key=sort_key)
    atomic_save_jobs(str(target), jobs)
    print(f'Preserved {len(old)} existing identities; wrote {len(jobs)} source-grounded records.')
    return jobs


if __name__ == '__main__':
    process_all_jobs()
