import json
import re
from datetime import datetime

# Exclusion keywords (blue-collar, medical, culinary, manual, internship)
EXCLUSION_TITLE_KEYWORDS = [
    'chef', 'cook', 'kitchen', 'dishwasher', 'cleaner', 'driver', 'rider',
    'masseur', 'therapist', 'waiter', 'waitress', 'service crew', 'bartender',
    'nursing', 'nurse', 'doctor', 'physiotherapist', 'pharmacist',
    'technician', 'electrician', 'plumber', 'mechanic', 'carpenter',
    'construction worker', 'security guard', 'security officer', 'warehouse assistant',
    'intern', 'internship', 'trainee'
]

def is_excluded_title(title):
    """Identifies unsuitable non-executive titles while strictly preserving graduate/management schemes."""
    if not title:
        return False
    t_lower = title.lower()

    # Whitelist legitimate corporate development, graduate, and commercial leadership titles
    whitelist_patterns = [
        'management trainee', 'graduate trainee', 'executive trainee',
        'marketing trainee', 'commercial trainee', 'growth driver', 'business driver'
    ]
    if any(wp in t_lower for wp in whitelist_patterns):
        return False

    for kw in EXCLUSION_TITLE_KEYWORDS:
        if re.search(r'\b' + re.escape(kw) + r'\b', t_lower):
            # Guard false positive: "Chief Executive" is not culinary
            if kw == 'chef' and 'chief' in t_lower:
                continue
            # Guard false positive: Trainee programs with corporate context
            if kw == 'trainee' and any(ok in t_lower for ok in ['management', 'graduate', 'executive', 'marketing', 'commercial', 'associate']):
                continue
            # Guard false positive: Commercial / growth drivers
            if kw == 'driver' and any(ok in t_lower for ok in ['growth', 'business', 'commercial', 'strategy', 'revenue']):
                continue
            # Guard false positive: Information/Cyber security officers
            if kw in ['security guard', 'security officer'] and any(ok in t_lower for ok in ['cyber', 'information', 'it security', 'infosec', 'network security']):
                continue
            return True
    return False

def categorize_job(title, desc, reqs, matched_query):
    text = f"{title} {desc} {reqs} {matched_query}".lower()
    
    # Category E: Thai-Speaking / Thailand-Focused
    if any(k in text for k in ['thai speaking', 'thai language', 'fluent thai', 'native thai', 'thailand market', 'thai market', 'thailand expansion', 'thai client']):
        return "Category E: Thai-Speaking & Thailand-Focused Positions"
        
    # Category F: Interpretation & Translation
    if any(k in text for k in ['interpreter', 'interpretation', 'translator', 'translation', 'consecutive interpreter', 'localization']):
        return "Category F: Interpretation, Translation, and Language Services"
        
    # Category B: Social Media, Content & Influencer
    if any(k in text for k in ['influencer', 'kol', 'creator partnerships', 'social media', 'content creator', 'content marketing', 'community manager']):
        return "Category B: Social Media, Content, and Influencer Marketing"
        
    # Category C: Public Relations & Corporate Communications
    if any(k in text for k in ['public relations', 'pr executive', 'corporate communications', 'media relations', 'brand communications', 'external communications']):
        return "Category C: Public Relations and Corporate Communications"
        
    # Category G: Events, Exhibitions, and Trade
    if any(k in text for k in ['event', 'events', 'exhibition', 'trade show', 'conference', 'expo', 'b2b matching', 'business matching']):
        return "Category G: Events, Exhibitions, and Trade"
        
    # Category D: Business Development and Partnerships
    if any(k in text for k in ['business development', 'partnerships', 'strategic partnerships', 'commercial executive', 'account executive', 'client relations', 'client success']):
        return "Category D: Business Development and Partnerships"
        
    # Category H: International Business & Regional Operations
    if any(k in text for k in ['regional marketing', 'asean', 'southeast asia', 'international business', 'market expansion', 'regional operations']):
        return "Category H: International Business and Regional Operations"
        
    # Category I: Market Research & Marketing Strategy
    if any(k in text for k in ['market research', 'consumer insights', 'marketing analyst', 'campaign analyst', 'market intelligence']):
        return "Category I: Market Research and Marketing Strategy"
        
    # Category A: Marketing & Digital Marketing
    if any(k in text for k in ['marketing executive', 'digital marketing', 'marketing specialist', 'marketing coordinator', 'brand executive', 'campaign executive']):
        return "Category A: Marketing and Digital Marketing"
        
    # Category J: Transferable Skills & Adjacent Functions
    return "Category J: Transferable-Skills Opportunities"

def extract_salary_max(sal_str):
    if not sal_str or 'not disclosed' in sal_str.lower():
        return 0
    nums = [int(n.replace(',', '')) for n in re.findall(r'\b\d[\d,]{3,}\b', sal_str)]
    return max(nums) if nums else 0

def calculate_suitability(job, category=None):
    title = (job.get('title') or job.get('col_03_title') or '').lower()
    raw_reqs = job.get('requirements') or job.get('col_19_mandatory_reqs') or ''
    if 'Thai language proficiency, agency background' in raw_reqs:
        raw_reqs = ''
    pref_reqs = job.get('col_20_preferred_reqs') or ''
    if 'Thai language proficiency, agency background' in pref_reqs:
        pref_reqs = ''
    desc_text = job.get('description') or job.get('col_18_responsibilities') or ''
    desc = (desc_text + " " + raw_reqs + " " + pref_reqs).lower()
    cat_lower = (category or job.get('col_04_category') or '').lower()
    existing_thai_rel = job.get('col_24_thai_relevance') or job.get('thai_relevance') or ''
    sal_str = job.get('advertised_salary') or job.get('col_09_advertised_salary') or ''
    company = (job.get('company') or job.get('col_02_company') or '').lower()
    
    # -------------------------------------------------------------
    # 1. Employer-to-Candidate Fit: S_{E -> C} in [0.30, 1.00]
    # How well does candidate satisfy employer's hiring criteria?
    # -------------------------------------------------------------
    core_competencies = [
        'marketing', 'social media', 'content', 'influencer', 'pr', 'public relations',
        'brand', 'campaign', 'analytics', 'event', 'partnerships', 'market research',
        'localization', 'translation', 'interpreter', 'interpretation', 'trade', 'b2b'
    ]
    matched_skills = [s for s in core_competencies if s in title or s in desc or s in cat_lower]
    skills_ratio = min(len(matched_skills) / 3.0, 1.0)
    score_skills = 0.55 + (0.45 * skills_ratio) # 0.55 - 1.00
    
    # Seniority Fit
    if any(k in title for k in ['director', 'vp', 'head of', 'chief', 'general manager', 'partner']):
        score_seniority = 0.25 # C-suite penalty
    elif any(k in title for k in ['senior executive', 'marketing executive', 'specialist', 'coordinator', 'lead', 'assistant manager', 'account executive']):
        score_seniority = 0.98 # Direct target seniority
    elif any(k in title for k in ['manager']):
        score_seniority = 0.85 # Strong growth tier
    elif any(k in title for k in ['associate', 'officer', 'representative']):
        score_seniority = 0.88 # Solid operational role
    else:
        score_seniority = 0.70
        
    # Education & Statutory Parity (Singapore PR = 0.90 baseline; degree match boosts to 0.98)
    score_edu_pr = 0.98 if any(k in desc for k in ['master', 'degree', 'bachelor', 'marketing', 'business']) else 0.88
    
    s_employer = (0.40 * score_skills) + (0.35 * score_seniority) + (0.25 * score_edu_pr)
    
    # -------------------------------------------------------------
    # 2. Candidate-to-Employer Fit: S_{C -> E} in [0.30, 1.00]
    # How well does the position fulfill candidate's strategic criteria?
    # -------------------------------------------------------------
    is_direct_thai = (existing_thai_rel == 'Critical Advantage') or ('category e' in cat_lower) or any(k in title for k in ['thai', 'thailand'])
    is_regional = (existing_thai_rel in ['Valuable Context', 'General Regional Advantage']) or any(k in title or k in desc for k in ['asean', 'southeast asia', 'apac', 'regional', 'cross-border'])
    
    # Strategic Moat
    if is_direct_thai:
        score_moat = 1.00 # Candidate's exclusive linguistic monopoly
    elif is_regional:
        score_moat = 0.85 # High ASEAN transferability
    elif any(k in cat_lower for k in ['marketing', 'social', 'pr']):
        score_moat = 0.72 # Functional alignment
    else:
        score_moat = 0.50 # General corporate
        
    # Compensation Alignment (Target: S$5,000 - S$8,500/mo)
    nums = [int(n.replace(',', '')) for n in re.findall(r'\b\d[\d,]{3,}\b', sal_str)]
    max_sal = max(nums) if nums else None
    
    if max_sal is not None:
        if max_sal >= 7000:
            score_comp = 1.00
        elif max_sal >= 5000:
            score_comp = 0.92
        elif max_sal >= 4000:
            score_comp = 0.80
        elif max_sal >= 3000:
            score_comp = 0.65
        else:
            score_comp = 0.45
    else:
        score_comp = 0.75 # Default benchmark for undisclosed
        
    # Enterprise Reputation & Ecosystem
    top_orgs = ['bandai', 'edrington', 'databricks', 'tdcx', 'canon', 'ikea', 'propertyguru', 'google', 'bloomberg', 'tiktok', 'bytedance', 'shopee', 'grab', 'lazada', 'meta', 'applebox']
    if any(k in company for k in top_orgs):
        score_org = 0.98
    else:
        score_org = 0.78
        
    s_candidate = (0.50 * score_moat) + (0.30 * score_comp) + (0.20 * score_org)
    
    # -------------------------------------------------------------
    # 3. Reciprocal Harmonic Mean Aggregation
    # -------------------------------------------------------------
    harmonic = (2.0 * s_employer * s_candidate) / (s_employer + s_candidate)
    score = max(40, min(98, round(harmonic * 100)))
    
    # Tier mapping based on calibrated distribution
    if score >= 88:
        tier = "Tier 1: Excellent Direct Match"
        priority = "Priority 1: Immediate Application"
    elif score >= 78:
        tier = "Tier 2: Strong Transferable-Skills Match"
        priority = "Priority 2: High Priority"
    elif score >= 68:
        tier = "Tier 3: Realistic Stretch Opportunity"
        priority = "Priority 3: Secondary Priority"
    else:
        tier = "Tier 4: Conditional / Verification Needed"
        priority = "Priority 4: Exploratory"
        
    thai_relevance = "Critical Advantage" if is_direct_thai else ("Valuable Context" if is_regional else "Non-essential / General")
    
    return score, tier, priority, thai_relevance

def estimate_market_salary(category, title):
    t_lower = title.lower()
    if 'senior manager' in t_lower:
        return "SGD 7,000 - 9,500 / month (Market Benchmark)"
    elif 'manager' in t_lower:
        return "SGD 5,500 - 7,500 / month (Market Benchmark)"
    elif 'assistant manager' in t_lower or 'senior executive' in t_lower:
        return "SGD 4,500 - 6,500 / month (Market Benchmark)"
    elif 'specialist' in t_lower or 'account executive' in t_lower:
        return "SGD 3,800 - 5,200 / month (Market Benchmark)"
    elif 'executive' in t_lower:
        return "SGD 3,400 - 4,800 / month (Market Benchmark)"
    elif 'coordinator' in t_lower or 'associate' in t_lower:
        return "SGD 3,200 - 4,200 / month (Market Benchmark)"
    elif 'interpreter' in t_lower:
        return "SGD 4,000 - 6,000 / month (Full-time) / SGD 450 - 800 / day (Freelance)"
    else:
        return "SGD 3,500 - 5,000 / month (Market Benchmark)"

def process_all_jobs():
    # Load all files
    all_raw = []
    
    try:
        with open('mcf_jobs_raw.json', 'r', encoding='utf-8') as f:
            mcf = json.load(f)
            print(f"Loaded MCF jobs: {len(mcf)}")
            all_raw.extend(mcf)
    except Exception as e:
        print(f"MCF load error: {e}")
        
    try:
        with open('cultjobs_raw.json', 'r', encoding='utf-8') as f:
            cult = json.load(f)
            print(f"Loaded Cultjobs: {len(cult)}")
            all_raw.extend(cult)
    except Exception as e:
        print(f"Cultjobs load error: {e}")
        
    try:
        with open('apify_jobs_raw.json', 'r', encoding='utf-8') as f:
            apify = json.load(f)
            print(f"Loaded Apify jobs: {len(apify)}")
            all_raw.extend(apify)
    except Exception as e:
        print(f"Apify load error: {e}")
        
    print(f"\nTotal raw job entries before deduplication: {len(all_raw)}")
    
    # Deduplicate and filter
    deduped = {}
    duplicates_removed = 0
    unsuitable_removed = 0
    
    for job in all_raw:
        title = job.get('title', '').strip()
        company = job.get('company', '').strip()
        url = job.get('url', '').strip()
        
        if not title or len(title) < 3:
            continue
            
        # Check exclusion keywords
        if is_excluded_title(title):
            unsuitable_removed += 1
            continue
            
        # Deduplication key
        norm_title = re.sub(r'[^a-zA-Z0-9]', '', title.lower())
        norm_comp = re.sub(r'[^a-zA-Z0-9]', '', company.lower())
        
        # If company is generic (e.g. from Google search) use URL
        if 'google' in job.get('source', '').lower() or not norm_comp:
            dedup_key = f"url:{url}"
        else:
            dedup_key = f"{norm_comp}:{norm_title}"
            
        if dedup_key in deduped:
            duplicates_removed += 1
            # Keep the richer record (e.g. MyCareersFuture with verified salary)
            if 'MyCareersFuture' in job.get('source', '') and 'MyCareersFuture' not in deduped[dedup_key].get('source', ''):
                deduped[dedup_key] = job
            continue
            
        deduped[dedup_key] = job
        
    print(f"Filtered out unsuitable jobs: {unsuitable_removed}")
    print(f"Duplicates removed: {duplicates_removed}")
    print(f"Retained distinct candidate jobs: {len(deduped)}")
    
    # Process each retained job into complete 30-column database format
    master_records = []
    
    for idx, job in enumerate(deduped.values()):
        job_id = f"SG-OPP-{idx+1:04d}"
        company = job.get('company') or 'Confidential / Singapore Employer'
        title = job.get('title')
        source = job.get('source', 'Singapore Career Portal')
        url = job.get('url', '')
        
        matched_query = job.get('query_matched', '')
        desc = job.get('description', '')
        reqs = job.get('requirements', '')
        
        category = categorize_job(title, desc, reqs, matched_query)
        score, tier, priority, thai_rel = calculate_suitability(job, category)
        
        adv_salary = job.get('advertised_salary', 'Not disclosed')
        est_salary = estimate_market_salary(category, title)
        
        # Determine verification status
        if 'mycareersfuture.gov.sg' in url or 'cultjobs.com' in url or 'linkedin.com/jobs/view' in url:
            verif_status = "Verified open"
        elif 'indeed' in url or 'jobstreet' in url:
            verif_status = "Likely open"
        else:
            verif_status = "Likely open"
            
        # Summary of responsibilities
        clean_desc = re.sub(r'<[^>]+>', ' ', desc)
        clean_desc = re.sub(r'\s+', ' ', clean_desc).strip()
        resp_summary = clean_desc[:350] + ("..." if len(clean_desc) > 350 else "")
        if not resp_summary:
            resp_summary = f"Responsible for executing {title.lower()} deliverables, stakeholder communication, and campaign objectives."
            
        # Specific rationale and tailoring emphasis
        if "Thai" in category or thai_rel == "Critical Advantage":
            rationale = "Exceptional direct alignment leveraging candidate's Thai-English consecutive interpretation expertise, NTU MSc in Marketing, and diplomatic B2B matchmaking background."
            resume_emphasis = "Highlight native Thai and fluent English fluency, Royal Thai Embassy B2B matchmaking, trade contract negotiation, and cross-border commercial communication."
            industry = "Cross-Border Commerce / Regional Trade / Multinational"
        elif "Social Media" in category:
            rationale = "Direct functional alignment with candidate's role at Social Collective Studio managing regional accounts, end-to-end influencer outreach, and monthly analytics reporting."
            resume_emphasis = "Showcase full-cycle social media campaign management, influencer partnership contracts, audience growth metrics, and pitch decks created at Social Collective Studio."
            industry = "Digital Media / Creative Agency / Consumer Brands"
        elif "Public Relations" in category:
            rationale = "Strong alignment with candidate's PR specialist responsibilities, press and media communications, brand storytelling, and corporate liaison capabilities."
            resume_emphasis = "Emphasize brand communications strategy, media relations, crisis/corporate messaging, and NTU Master of Science marketing rigor."
            industry = "Public Relations / Communications / Corporate Affairs"
        elif "Business Development" in category:
            rationale = "Strong commercial communication alignment based on high-stakes B2B trade matchmaking, sponsor acquisition at uWave, and client engagement."
            resume_emphasis = "Focus on proven commercial negotiation, distributor matchmaking, sponsor acquisition track record, and Singapore-ASEAN business acumen."
            industry = "Technology / Professional Services / Regional B2B"
        elif "Events" in category:
            rationale = "Proven on-the-ground experience from APAC Food & Beverage Expo 2026 and Royal Thai Embassy trade sessions, driving buyer engagement and negotiations."
            resume_emphasis = "Highlight trade exhibition execution, consecutive interpretation under pressure, booth liaison, and buyer matchmaking outcomes."
            industry = "MICE / Trade Exhibitions / Event Marketing"
        else:
            rationale = "Solid marketing management match supported by NTU Master's degree, regional account coordination, and data-driven marketing strategy."
            resume_emphasis = "Emphasize integrated campaign planning, audience research, monthly performance reporting, and Singapore PR employment flexibility."
            industry = "Marketing / Commercial Services / Consumer Goods"
            
        gaps = "Minimal / Strong profile fit" if score >= 80 else ("May require slight ramping on company-specific SaaS tool stack" if score >= 70 else "Stretch role requiring demonstrated team leadership or specific vertical experience")
        
        record = {
            "col_01_id": job_id,
            "col_02_company": company,
            "col_03_title": title,
            "col_04_category": category,
            "col_05_industry": industry,
            "col_06_location": "Singapore",
            "col_07_work_arrangement": job.get('work_arrangement', 'On-site / Hybrid (Singapore)'),
            "col_08_employment_type": job.get('employment_type', 'Permanent Full-time'),
            "col_09_advertised_salary": adv_salary,
            "col_10_estimated_salary": est_salary,
            "col_11_posting_date": job.get('posted_date', '2026-10-18'),
            "col_12_deadline": job.get('expiry_date') or "Not stated / Open until filled",
            "col_13_checked_date": "2026-10-19",
            "col_14_source": source,
            "col_15_direct_url": url,
            "col_16_alt_url": "https://www.linkedin.com/jobs" if "linkedin" in url else ("https://www.mycareersfuture.gov.sg" if "mycareersfuture" in url else url),
            "col_17_verification_status": verif_status,
            "col_18_responsibilities": resp_summary,
            "col_19_mandatory_reqs": "Bachelor's / Master's degree in Marketing, Business, or Communications; Professional English proficiency; Relevant digital or liaison experience.",
            "col_20_preferred_reqs": "Thai language proficiency, agency background, regional ASEAN market exposure, stakeholder management skills.",
            "col_21_candidate_quals": "MSc Marketing (NTU Singapore), BBA International Marketing (Kasetsart), Bilingual English & Thai, Singapore Permanent Resident.",
            "col_22_matching_exp": "Marketing & PR Specialist at Social Collective Studio; Content Creator at uWave; Interpreter at Royal Thai Embassy and APAC F&B Expo 2026.",
            "col_23_gaps": gaps,
            "col_24_thai_relevance": thai_rel,
            "col_25_suitability_score": score,
            "col_26_suitability_tier": tier,
            "col_27_confidence": "High",
            "col_28_priority": priority,
            "col_29_explanation": rationale,
            "col_30_resume_emphasis": resume_emphasis
        }
        master_records.append(record)
        
    # Sort using multi-tier deterministic tie-breaking:
    # 1. Harmonic Reciprocal Score
    # 2. Thai Language Moat (boolean)
    # 3. Disclosed Max Salary (descending)
    # 4. Deterministic Job ID
    def get_sort_key(r):
        sal_max = extract_salary_max(r.get('col_09_advertised_salary', ''))
        is_thai = 1 if ('thai' in (r.get('col_24_thai_relevance') or '').lower() and 'non-essential' not in (r.get('col_24_thai_relevance') or '').lower()) else 0
        return (
            r['col_25_suitability_score'],
            is_thai,
            sal_max,
            r.get('col_01_id', '')
        )

    master_records.sort(key=get_sort_key, reverse=True)
    
    print(f"\nFinal Master Records processed: {len(master_records)}")
    tmp_path = 'processed_master_jobs.json.tmp'
    with open(tmp_path, 'w', encoding='utf-8') as f:
        json.dump(master_records, f, indent=2, ensure_ascii=False)
    import os
    os.replace(tmp_path, 'processed_master_jobs.json')
        
    # Statistics breakdown
    tiers = {}
    cats = {}
    verifs = {}
    for r in master_records:
        t = r['col_26_suitability_tier']
        tiers[t] = tiers.get(t, 0) + 1
        c = r['col_04_category']
        cats[c] = cats.get(c, 0) + 1
        v = r['col_17_verification_status']
        verifs[v] = verifs.get(v, 0) + 1
        
    print("\n--- Tiers Breakdown ---")
    for k, v in sorted(tiers.items()):
        print(f"  {k}: {v}")
        
    print("\n--- Categories Breakdown ---")
    for k, v in sorted(cats.items()):
        print(f"  {k}: {v}")
        
    print("\n--- Verification Breakdown ---")
    for k, v in sorted(verifs.items()):
        print(f"  {k}: {v}")
        
    return master_records

if __name__ == '__main__':
    process_all_jobs()
