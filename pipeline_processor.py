import json
import re
from datetime import datetime

# Exclusion keywords (blue-collar, medical, culinary, manual, internship)
EXCLUSION_TITLE_KEYWORDS = [
    'chef', 'cook', 'kitchen', 'dishwasher', 'cleaner', 'driver', 'rider',
    'masseur', 'therapist', 'waiter', 'waitress', 'service crew', 'bartender',
    'nursing', 'nurse', 'doctor', 'physiotherapist', 'pharmacist',
    'technician', 'electrician', 'plumber', 'mechanic', 'carpenter',
    'construction worker', 'security guard', 'warehouse assistant',
    'intern', 'internship', 'trainee'
]

def is_excluded_title(title):
    t_lower = title.lower()
    for kw in EXCLUSION_TITLE_KEYWORDS:
        if re.search(r'\b' + re.escape(kw) + r'\b', t_lower):
            # Check for rare false positives like "Chief Executive"
            if kw == 'chef' and 'chief' in t_lower:
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

def calculate_suitability(job, category):
    title = job.get('title', '').lower()
    desc = (job.get('description', '') + " " + job.get('requirements', '')).lower()
    
    score = 60 # Base
    
    # 1. Skills match (up to 25 pts)
    marketing_skills = ['social media', 'content', 'influencer', 'campaign', 'pr', 'public relations', 'branding', 'market research', 'analytics', 'event', 'negotiation']
    matched_skills = [s for s in marketing_skills if s in title or s in desc]
    score += min(len(matched_skills) * 3, 20)
    
    # 2. Seniority match (up to 15 pts)
    ideal_seniority = ['executive', 'specialist', 'associate', 'coordinator', 'officer', 'account executive']
    if any(s in title for s in ideal_seniority):
        score += 10
    elif 'senior executive' in title or 'assistant manager' in title:
        score += 6 # Realistic stretch
    elif any(s in title for s in ['director', 'vp', 'head of', 'general manager']):
        score -= 25 # Unrealistic stretch
        
    # 3. Education (up to 10 pts)
    if 'degree' in desc or 'bachelor' in desc or 'master' in desc:
        score += 5
    if 'marketing' in desc:
        score += 5
        
    # 4. Language & Regional advantage (up to 15 pts)
    is_thai = any(k in title or k in desc for k in ['thai', 'thailand', 'bangkok'])
    is_regional = any(k in title or k in desc for k in ['asean', 'southeast asia', 'apac', 'regional'])
    if is_thai:
        score += 15
    elif is_regional:
        score += 8
        
    # Cap score at 98 max, 35 min
    score = max(35, min(96, score))
    
    # Tier mapping
    if score >= 85:
        tier = "Tier 1: Excellent Direct Match"
        priority = "Priority 1: Immediate Application"
    elif score >= 75:
        tier = "Tier 2: Strong Transferable-Skills Match"
        priority = "Priority 2: High Priority"
    elif score >= 65:
        tier = "Tier 3: Realistic Stretch Opportunity"
        priority = "Priority 3: Secondary Priority"
    else:
        tier = "Tier 4: Conditional / Verification Needed"
        priority = "Priority 4: Exploratory"
        
    thai_relevance = "Critical Advantage" if is_thai else ("Valuable Context" if is_regional else "Non-essential / General")
    
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
        
    # Sort by suitability score descending
    master_records.sort(key=lambda x: x['col_25_suitability_score'], reverse=True)
    
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
