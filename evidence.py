"""Source-grounded presentation and candidate assessment.

Historical collectors inserted defaults into even their "raw" records. This module
only retains fields supported by those records, never uses search queries as job
facts, and keeps the original record available for provenance. Assessment is a
conservative reading aid, not a probability of employment.
"""
from __future__ import annotations

import copy
import json
import re
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import parse_qs, urlsplit, urlunsplit
from functools import lru_cache
from fit_score import evaluate as evaluate_fit, requirement as check_requirement, language_gaps, normalized, is_boilerplate, requirement_parts, requirement_not_required
from source_fields import source_field_supplied

UTC = timezone.utc
RAW_FILES = ("mcf_jobs_raw.json", "apify_jobs_raw.json", "cultjobs_raw.json")
FIT_ORDER = {"Relevant": 0, "Adjacent": 1, "Check requirements": 2, "Not suitable": 3}
CANDIDATE_FACTS = {
    "education": ["MSc Marketing, Nanyang Technological University (2022–2023)",
                  "BBA International Marketing, Kasetsart University (2018–2021)"],
    "languages": ["English", "Thai"],
    "residency": "Singapore Permanent Resident",
    "experience": [
        "Marketing and PR Specialist, Social Collective Studio (2025–present): social media content and community management, monthly analytics, trend and audience research, pitch decks, influencer outreach and contracts.",
        "Content Creator and Brand Development Intern, uWave (January–April 2021): content creation and sponsor acquisition.",
        "Thai–English trade-show interpretation, APAC Food & Beverage Expo (21–23 August 2026).",
        "B2B interpretation and liaison, Royal Thai Embassy (24 August 2026).",
    ],
    "source": "CV 2026.pdf, verified 21 October 2026",
}


class _Text(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self.hidden = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript"):
            self.hidden += 1
        if tag in ("p", "li", "br", "div", "h1", "h2", "h3", "h4", "tr"):
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript"):
            self.hidden = max(0, self.hidden - 1)
        if tag in ("p", "li", "div", "h1", "h2", "h3", "h4", "tr"):
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def plain_text(value):
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        return "\n".join(filter(None, (plain_text(v) for v in value)))
    parser = _Text()
    parser.feed(str(value))
    lines = [re.sub(r"[^\S\n]+", " ", line).strip() for line in "".join(parser.parts).splitlines()]
    return "\n".join(line for line in lines if line)


def safe_url(value):
    value = str(value or "").strip()
    return value if urlsplit(value).scheme.lower() in ("https", "http") else ""


def source_key(value):
    """Match the actual vacancy identity, ignoring tracking URLs and host aliases."""
    url = safe_url(value)
    if not url:
        return ""
    parts = urlsplit(url)
    host = (parts.hostname or "").lower().removeprefix("www.")
    if "linkedin.com" in host:
        match = re.search(r"(?:-|/)(\d{8,})(?:/|$)", parts.path)
        if match:
            return "linkedin:" + match[1]
    if "mycareersfuture.gov.sg" in host:
        match = re.search(r"([a-f0-9]{32})(?:/|$)", parts.path)
        if match:
            return "mcf:" + match[1]
    if "indeed." in host:
        key = parse_qs(parts.query).get("jk", [None])[0]
        if key:
            return "indeed:" + key
    # Preserve identifying query parameters for sources without a known URL schema.
    query = "&".join(f"{k}={v}" for k, values in sorted(parse_qs(parts.query).items())
                     if not k.lower().startswith("utm_") and k not in ("ref", "trackingId", "trk")
                     for v in values)
    return urlunsplit(("https", host, parts.path.rstrip("/"), query, ""))


def parse_date(value):
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)
    except (ValueError, TypeError):
        return None


def _number(value):
    try:
        result = float(str(value).replace(",", ""))
        return result if result >= 0 and result < float("inf") else None
    except (ValueError, TypeError):
        return None


def salary_presentation(raw):
    display = plain_text(raw.get("advertised_salary") or raw.get("col_09_advertised_salary"))
    if not display or re.search(r"not (?:disclosed|stated)|undisclosed|market benchmark|estimated", display, re.I):
        return dict(display="Not disclosed", disclosed=False, minimum=None, maximum=None,
                    unit=None, currency=None, monthly_minimum=None, monthly_maximum=None)
    # The old collectors defaulted salary_type to Monthly. Only source wording or
    # an explicitly marked structured upstream response can substantiate the unit.
    unit_text = display.lower()
    if raw.get("structured_salary_verified"):
        unit_text += " " + str(raw.get("salary_type") or "").lower()
    unit = None
    for label, pattern in (("year", r"\b(?:annual(?:ly)?|year(?:ly)?|annum|yr)\b"),
                           ("month", r"\b(?:month(?:ly)?|mo)\b"),
                           ("day", r"\b(?:daily|day)\b"),
                           ("hour", r"\b(?:hour(?:ly)?|hr)\b"),
                           ("week", r"\b(?:week(?:ly)?|wk)\b")):
        if re.search(pattern, unit_text):
            unit = label
            break
    minimum, maximum = _number(raw.get("salary_min")), _number(raw.get("salary_max"))
    if minimum is None and maximum is None:
        # Salary snippets can contain posting dates. Start at the currency marker.
        currency_marker = re.search(r"(?:S\$|SGD|USD|AUD|HKD|EUR|GBP|\$|£|€)\s*", display, re.I)
        pay_text = display[currency_marker.end():] if currency_marker else display
        pay_text = re.split(r"/|\bper\b", pay_text, maxsplit=1, flags=re.I)[0]
        values = [float(v.replace(",", "")) * (1000 if suffix else 1)
                  for v, suffix in re.findall(r"(\d[\d,]*(?:\.\d+)?)\s*([kK]?)", pay_text)]
        if len(values) == 2 and re.fullmatch(r'\s*\d+(?:\.\d+)?\s*[-–—]\s*\d+(?:\.\d+)?\s*[kK]\s*', pay_text) and values[0] < 1000:
            values[0] *= 1000
        if values:
            if re.search(r"\b(?:up to|maximum|max)\b", display, re.I):
                maximum = values[0]
            else:
                minimum, maximum = values[0], (values[1] if len(values) > 1 else values[0])
                if re.search(r"\b(?:from|minimum|min)\b", display, re.I) and len(values) == 1:
                    maximum = None
    disclosed = minimum is not None or maximum is not None
    currency = next((code for marker, code in ((r'US\$', 'USD'), (r'HK\$', 'HKD'), (r'(?:AU|A)\$', 'AUD'), (r'(?:CA|C)\$', 'CAD'), (r'NZ\$', 'NZD')) if re.search(marker, display, re.I)), None)
    if currency is None: currency = "SGD" if re.search(r"\bSGD\b|(?<![A-Za-z])S\$", display, re.I) else None
    if currency is None:
        currency = next((c for c in ("USD", "AUD", "HKD", "EUR", "GBP") if c in display.upper()), None)
    # Singapore vacancy source dollar amounts are SGD; explicit foreign currencies remain foreign.
    if currency is None and "$" in display and "singapore" in str(raw.get("source", "")).lower():
        currency = "SGD"
    divisor = 12 if unit == "year" else 1 if unit == "month" else None
    return dict(display=display, disclosed=disclosed, minimum=minimum, maximum=maximum, unit=unit,
                currency=currency, monthly_minimum=round(minimum / divisor, 2) if divisor and minimum is not None else None,
                monthly_maximum=round(maximum / divisor, 2) if divisor and maximum is not None else None)


_REQ_HEADING = re.compile(r"^(?:(?:job|key|minimum|essential|basic|candidate)\s+)?(?:requirements|qualifications|skills)(?:\s*(?:and|&)\s*(?:experience|qualifications|skills))?(?:\s+(?:we're|we are) looking for)?\s*:?$|^what (?:we are|we're|you are) looking for\s*:?$|^about you\s*:?$|^who you are\s*:?$", re.I)
_PREFERRED = re.compile(r"\b(?:preferred|preferably|ideally|desirable|advantage|a plus|nice to have|bonus)\b", re.I)
_END_HEADING = re.compile(r"^(?:job responsibilities|responsibilities|benefits|what we offer|why join us|our commitment to you|about us|about the company|how to apply|equal opportunity|apply now|selling pts|disclaimer)\s*[:?]?$|^(?:to apply|we regret to inform|posted by|date posted)\b", re.I)


def extract_requirements(description, explicit=None):
    mandatory, preferred = _requirements_cached(description, json.dumps(explicit, ensure_ascii=False, sort_keys=True))
    # Cached values are immutable. Every caller receives its own mutable lists.
    return {'mandatory': list(mandatory), 'preferred': list(preferred)}


@lru_cache(maxsize=8192)
def _requirements_cached(description, explicit_json):
    explicit = json.loads(explicit_json)
    mandatory, preferred = [], []
    section = None
    # Derived requirements use literal source spans; original explicit fields
    # and their evidence references remain intact in source_requirements.
    if isinstance(explicit, dict):
        for section_name in ('mandatory', 'preferred'):
            for line in plain_text(explicit.get(section_name)).splitlines():
                for part in requirement_parts(line):
                    (preferred if section_name == 'preferred' or _PREFERRED.search(part) or requirement_not_required(part) else mandatory).append(part)
    elif explicit:
        for line in plain_text(explicit).splitlines():
            for part in requirement_parts(line):
                (preferred if _PREFERRED.search(part) or requirement_not_required(part) else mandatory).append(part)
    for line in description.splitlines():
        clean = re.sub(r'^\s*(?:[-•●▪◦‣]+|\d+[.)])\s*', '', line).strip()
        if is_boilerplate(clean):
            section = None
            continue
        if re.fullmatch(r"(?:preferred|desired|additional)\s+(?:qualifications|requirements|skills)\s*:?|what sets you apart\s*:?", clean, re.I):
            section = "preferred"
            continue
        if _REQ_HEADING.search(clean.replace('’', "'")):
            section = "mandatory"
            continue
        if _END_HEADING.search(clean):
            section = None
            continue
        if section:
            for part in requirement_parts(clean):
                (preferred if section == "preferred" or _PREFERRED.search(part) or requirement_not_required(part) else mandatory).append(part)
        elif re.search(r"\b(?:must|minimum qualifications|is required|are required)\b", clean, re.I):
            for part in requirement_parts(clean):
                (preferred if _PREFERRED.search(part) or requirement_not_required(part) else mandatory).append(part)
    def candidate_lines(lines):
        seen = set()
        for line in lines:
            key = normalized(line).casefold().strip(' .')
            if key and key not in seen and not is_boilerplate(line):
                seen.add(key)
                yield line
    return tuple(candidate_lines(mandatory)), tuple(candidate_lines(preferred))


def _canonical_requirements(job):
    raw = job.get('raw_evidence')
    retained = job.get('requirements') or {}
    if raw is None and 'source_requirements' not in job and 'retained_requirements_source' not in job:
        return copy.deepcopy(retained)
    requirements = extract_requirements(job.get('description') or '', job.get('source_requirements',
        job.get('retained_requirements_source', (raw or {}).get('requirements'))))
    if job.get('requirements_source_unknown'):
        for section in ('mandatory', 'preferred'):
            requirements[section] = list(dict.fromkeys(requirements[section] + retained.get(section, [])))
    return requirements


def thai_relevance(title, description, requirements):
    return _thai_relevance_cached(title, description, tuple(requirements.get('mandatory') or []),
                                  tuple(requirements.get('preferred') or []))


@lru_cache(maxsize=8192)
def _thai_relevance_cached(title, description, mandatory, preferred_requirements):
    text = '\n'.join([title, description] + list(mandatory) + list(preferred_requirements))
    # Most records never mention Thai. Do not parse every responsibility and
    # requirement again on each search/source read; changed evidence has its own
    # immutable cache key, including requirement-section classification.
    sentences = ([part for line in re.split(r"[\n.!?]", text) for part in requirement_parts(line)]
                 if re.search(r'\bthai\b', text, re.I) else [])
    preferred, required = False, False
    for sentence in sentences:
        if requirement_not_required(sentence): continue
        if not re.search(r"\bthai\b", sentence, re.I):
            continue
        # Geography and search queries do not establish a language requirement.
        if re.search(r"(?:thai[ -]speaking|thai language|fluen\w*[^.!?\n]{0,60}\bthai\b|\bthai\b[^.!?\n]{0,60}fluen\w*|(?:speak|read|write|communicat\w*|proficien\w*|translat\w*|interpret\w*)[^.!?\n]{0,60}\bthai\b|\bthai\b[^.!?\n]{0,40}(?:speaker|translat\w*|interpret\w*))", sentence, re.I):
            if _PREFERRED.search(sentence) or sentence.strip() in preferred_requirements:
                preferred = True
            else:
                required = True
    if required:
        return "Thai required"
    if preferred:
        return "Thai preferred"
    if re.search(r"\b(?:thailand|thai market|thai clients?|thai customers?)\b", title + " " + description, re.I):
        return "Thailand market context"
    return None


_FAMILIES = (
    ("Interpretation and language services", r"\b(?:interpreter|translator|localization|localisation|language expert)\b"),
    ("Social media and content", r"\b(?:social media|content|influencer|creator|community)\b"),
    ("Public relations and communications", r"\b(?:public relations|communications?|pr)\b"),
    ("Events and trade", r"\b(?:events?|exhibition|trade show|conference)\b"),
    ("Marketing", r"\b(?:marketing|brand|campaign|consumer insights|market research)\b"),
    ("Business development and partnerships", r"\b(?:business development|partnerships?|account executive|client success)\b"),
)


def job_family(title):
    return next((label for label, pattern in _FAMILIES if re.search(pattern, title, re.I)), "Other roles")


def assess(title, description, requirements, source_complete=True):
    family = job_family(title)
    reasons, gaps = [], []
    overlap_patterns = (
        (r"\bsocial media\b", "Social media work overlaps with content and community management at Social Collective Studio."),
        (r"\binfluencer\b", "Influencer work overlaps with documented outreach and contract coordination."),
        (r"\b(?:audience research|market research|analytics|monthly reporting)\b", "Research or reporting overlaps with documented audience research and monthly analytics."),
        (r"\b(?:content creation|content creator|content marketing)\b", "Content responsibilities overlap with documented content creation experience."),
        (r"\b(?:interpreter|interpretation|b2b matching|trade show)\b", "Language or trade-show work overlaps with the documented August 2026 interpretation assignments."),
    )
    for pattern, reason in overlap_patterns:
        if re.search(pattern, title + " " + description, re.I):
            reasons.append(reason)
    if family == "Marketing":
        reasons.append("Marketing aligns with the MSc and BBA in Marketing and current Marketing and PR Specialist role.")
    if family == "Public relations and communications":
        reasons.append("The role family relates to the current Marketing and PR Specialist position; specialist duties still need checking.")
    language_sentences = [sentence for sentence in re.split(r"[\n.!?]", description)
                          if re.search(r"\b(?:must|required|requires|fluency|fluent|proficiency|command of|ability to communicate)\b", sentence, re.I)]
    language_text = title + "\n" + "\n".join(requirements["mandatory"] + language_sentences)
    unsupported_language = language_gaps(language_text.splitlines())
    gaps.extend(gap['reason'] for gap in unsupported_language)
    financial = re.search(r"\b(?:accounts? receivable|accounts? payable|accountant|accounting|financial (?:controller|analyst)|audit(?:or)?|credit (?:analyst|control))\b", title, re.I)
    if financial:
        gaps.append("Specialist finance or accounting experience is not documented in the résumé.")
    if not requirements["mandatory"]:
        gaps.append("Mandatory requirements are not clearly available in the retained source; check the original listing.")
    unsupported = [line for line in requirements["mandatory"] if check_requirement(line)['status'] != 'supported']
    gaps.extend("Check against your experience: " + line for line in unsupported)
    if not source_complete:
        gaps.append("The retained source is incomplete or is a search-result snippet; confirm the full vacancy with the employer.")
    if unsupported_language or financial:
        fit = "Not suitable"
    elif not source_complete or not description or not requirements["mandatory"] or unsupported:
        fit = "Check requirements"
    elif family == "Other roles" or family == "Business development and partnerships":
        fit = "Adjacent"
    else:
        fit = "Relevant"
    if not reasons:
        reasons.append("No specific responsibility overlap is established from the retained source and résumé.")
    return {"fit": fit, "reasons": reasons, "gaps": list(dict.fromkeys(gaps)), "overlap": len(reasons) if not reasons[0].startswith("No specific") else 0}


@lru_cache(maxsize=8192)
def _current_assessment(title, description, mandatory, preferred, complete):
    requirements = {'mandatory': list(mandatory), 'preferred': list(preferred)}
    assessment = assess(title, description, requirements, complete)
    score = evaluate_fit(title, description, mandatory, preferred, complete, job_family(title))
    assessment['score'] = score
    if score['gates'] and assessment['fit'] != 'Not suitable':
        assessment['fit'] = 'Check requirements'
    if assessment['fit'] == 'Relevant' and (score['value'] is None or score['value'] < 70 or score['unknown_duties']):
        assessment['fit'] = 'Check requirements'
    assessment['gaps'] = list(dict.fromkeys([gate['reason'] for gate in score['gates']] + assessment['gaps']))
    supported_duties = [clause for row in score['duties'] for clause in row['clauses'] if clause['status'] == 'overlap']
    if supported_duties:
        assessment['reasons'] = [f"The listing asks: “{row['quote']}” CV evidence: {' '.join(row['candidate_evidence'])}" for row in supported_duties]
    else:
        assessment['reasons'] = ['No specific responsibility overlap is established from the retained source and résumé.']
    domain_labels = {'social':'social media management', 'content':'content planning and creation', 'influencer':'influencer outreach', 'research':'audience and market research', 'analytics':'campaign reporting', 'interpretation':'Thai–English interpretation', 'pitch':'marketing proposals', 'sponsor':'sponsor outreach'}
    assessment['summary'] = (score['gates'][0]['reason'] if score['gates'] else
        'Documented overlap in ' + ', '.join(dict.fromkeys(domain_labels.get(domain, domain) for row in supported_duties for domain in row['domains'])) + '.'
        if supported_duties else score['unavailable_reason'] or 'No specific responsibility overlap is documented.')
    return assessment


def prepare_assessments(jobs):
    """Prepare bounded derived-data caches before the service becomes ready.

    Source records remain unchanged. Changed evidence produces a new cache key.
    """
    for job in jobs:
        description = job.get('description') or ''
        requirements = _canonical_requirements(job)
        thai_relevance(job.get('title') or '', description, requirements)
        _current_assessment(job.get('title') or '', description, tuple(requirements.get('mandatory') or []),
                            tuple(requirements.get('preferred') or []), bool(job.get('description_complete')))


def _work_arrangement(raw, description):
    value = raw.get("work_arrangement")
    if value and value not in ("On-site / Hybrid (Singapore)", "On-site / Hybrid", "Not stated"):
        return plain_text(value)
    for line in description.splitlines():
        if re.search(r"\bhybrid\b.*\b(?:work|working|arrangement)\b|\b(?:work|working)\b.*\bhybrid\b", line, re.I):
            return "Hybrid (stated in source)"
        if re.search(r"\b(?:fully remote|remote working|work from home)\b", line, re.I):
            return "Remote work mentioned; check conditions"
    return None


def _is_search_page(url):
    parts = urlsplit(url)
    host, path = (parts.hostname or "").lower(), parts.path.lower()
    return (("jobstreet" in host and path.endswith("-jobs"))
            or ("linkedin" in host and "/jobs/" in path and "/jobs/view/" not in path)
            or ("indeed" in host and path.startswith("/q-"))
            or ("glassdoor" in host and "srch_" in path)
            or ("jora." in host and path.endswith("-jobs"))
            or ("jooble." in host and path.startswith("/jobs-")))


def normalize_employment_types(value):
    """Canonical memberships, accepting original combined query values."""
    if isinstance(value, (list, tuple)):
        values = [item for part in value for item in normalize_employment_types(part)]
    else:
        values = []
        for part in re.split(r'[,;/|]|\s+and\s+', str(value or ''), flags=re.I):
            key = re.sub(r'[\s_-]+', '', part).casefold()
            label = {'fulltime':'Full-time', 'parttime':'Part-time', 'freelance':'Freelance', 'freelancer':'Freelance', 'contract':'Contract', 'contractual':'Contract', 'temporary':'Temporary', 'temp':'Temporary', 'internship':'Internship', 'intern':'Internship', 'permanent':'Permanent'}.get(key)
            if label: values.append(label)
            elif part.strip() and key not in ('notstated','unknown','none'): values.append(part.strip())
    return list(dict.fromkeys(values))


def build_job(raw, job_id, legacy=None):
    legacy = legacy or {}
    description = plain_text(raw.get("description"))
    title = plain_text(raw.get("title") or legacy.get("col_03_title") or legacy.get("title"))
    url = safe_url(legacy.get("col_15_direct_url") or legacy.get("url") or raw.get("url"))
    source = plain_text(raw.get("source") or legacy.get("col_14_source") or "Source not recorded")
    source_complete = bool(description) and "google search" not in source.lower() and not raw.get("description_incomplete", False)
    if "cultjobs" in source.lower() and len(str(raw.get("description", ""))) >= 1995:
        source_complete = False  # The old collector truncated these before retention.
    requirements = extract_requirements(description, raw.get("requirements"))
    checked = raw.get("verified_at") or raw.get("checked_at")
    previous_checked = legacy.get("col_13_checked_date")
    verification = {"checked_at": checked or previous_checked or None,
                    "last_success_at": checked or None,
                    "status": "verified" if checked else "historical" if previous_checked else "unverified",
                    "needs_recheck": True,
                    "last_attempt_at": raw.get("last_attempt_at") or checked,
                    "last_error": raw.get("last_error")}
    status = raw.get("status") if raw.get("status") in ("open", "closed", "expired", "unavailable") else "open" if checked else "unknown"
    if "google search" in source.lower() and _is_search_page(url):
        status = "unavailable"  # A results page is not an individual vacancy.
    employment = plain_text(raw.get("employment_type")) or None
    # Several historical collectors inserted Full-time unconditionally or as a
    # fallback. Without original field provenance, require supporting source text.
    if not raw.get("employment_type_verified") and (
            any(name in source.lower() for name in ("google search", "cultjobs", "indeed"))
            or re.fullmatch(r"full[ -]?time", employment or "", re.I)):
        employment = None
        if re.search(r"\bfull[ -]time\b", title + " " + description, re.I):
            employment = "Full-time"
        elif re.search(r"\bpart[ -]time\b", title + " " + description, re.I):
            employment = "Part-time"
    if re.search(r"\bfreelanc(?:e|er)\b", title, re.I):
        employment = ', '.join(normalize_employment_types(employment) + ([] if 'Freelance' in normalize_employment_types(employment) else ['Freelance']))
    job = dict(id=job_id, title=title, company=plain_text(raw.get("company") or legacy.get("col_02_company") or legacy.get("company")),
               category=job_family(title), location=plain_text(raw.get("location")) or None,
               employment_type=employment, work_arrangement=_work_arrangement(raw, description), url=url,
               salary=salary_presentation(raw), description=description, description_complete=source_complete,
               requirements=requirements, assessment=assess(title, description, requirements, source_complete),
               thai_relevance=thai_relevance(title, description, requirements),
               sources=[{"name": source, "url": safe_url(raw.get("url")) or url, "source_id": raw.get("uuid") or raw.get("id"),
                         "kind": "search_result" if "google search" in source.lower() else "listing",
                         "checked_at": checked or previous_checked or None}],
               verification=verification, deadline=raw.get("expiry_date") or legacy.get("col_12_deadline") or None,
               posted_at=raw.get("posted_date") or None, status=status, evidence_version=1,
               raw_evidence=copy.deepcopy(raw))
    job['source_requirements'] = copy.deepcopy(raw.get('requirements'))
    provenance = {'checked_at': checked or None, 'source_record_date': previous_checked or None, 'url': safe_url(raw.get('url')) or url}
    source_fields = {'description':'description', 'requirements':'requirements', 'company':'company', 'location':'location', 'work_arrangement':'work_arrangement', 'posted_at':'posted_date', 'deadline':'expiry_date', 'employment_type':'employment_type', 'salary':'salary'}
    job['field_provenance'] = {field: copy.deepcopy(provenance) if source_field_supplied(raw, source_field) else {'checked_at':None, 'source_record_date':None, 'url':provenance['url']} for field, source_field in source_fields.items()}
    if job['work_arrangement']:
        explicit_arrangement = raw.get('work_arrangement')
        if explicit_arrangement and explicit_arrangement not in ('On-site / Hybrid (Singapore)', 'On-site / Hybrid', 'Not stated'):
            job['field_provenance']['work_arrangement']['basis'] = 'explicit_source'
        else:
            job['field_provenance']['work_arrangement'] = {**copy.deepcopy(job['field_provenance']['description']), 'basis':'description'}
    job['source_requirement_evidence'] = copy.deepcopy(raw.get('requirements_evidence', provenance)) if raw.get('requirements') is not None else None
    if status == "unavailable" and _is_search_page(url):
        job["source_warning"] = "This retained link is a search-results page, not an individual vacancy."
    return present_job(job)


def present_job(job, now=None, *, with_assessment=True):
    raw_evidence = job.get('raw_evidence')
    # The stored assessment is obsolete derived data and will be replaced below.
    # Copying its entire evidence tree for every search is wasted work.
    job = {k: copy.deepcopy(v) for k,v in job.items() if k != 'assessment' and (with_assessment or k != 'raw_evidence')}
    now = parse_date(now) if isinstance(now, str) else now or datetime.now(UTC)
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    verification = job.setdefault("verification", {})
    if not verification.get("last_success_at"):
        verification["last_success_at"] = (raw_evidence or {}).get("verified_at")
    checked = parse_date(verification.get("checked_at"))
    verification["needs_recheck"] = not checked or now - checked >= timedelta(hours=24) or verification.get("status") != "verified"
    deadline = parse_date(job.get("deadline"))
    if not deadline:
        job['deadline'] = None
    # Date-only closing dates remain open through the recorded Singapore date.
    deadline_expired = bool(deadline and (deadline.date() < (now + timedelta(hours=8)).date()
                            if len(str(job.get("deadline"))) == 10 else deadline < now))
    if deadline_expired and job.get("status") not in ("closed", "unavailable"):
        job["status"] = "expired"
    if job.get("status") not in ("open", "expired", "closed", "unknown", "unavailable"):
        job["status"] = "unknown"
    requirements_input = job if with_assessment else {**job, **({'raw_evidence': raw_evidence} if raw_evidence is not None else {})}
    job['requirements'] = _canonical_requirements(requirements_input)
    job['thai_relevance'] = thai_relevance(job.get('title') or '', job.get('description') or '', job['requirements'])
    if job.get('field_provenance'):
        job['field_provenance']['derived_requirements'] = copy.deepcopy(job['field_provenance'].get('description', {}))
    requirements = job.get('requirements') or {}
    job['employment_types'] = normalize_employment_types(job.get('employment_type'))
    if with_assessment:
        job['assessment'] = copy.deepcopy(_current_assessment(job.get('title') or '', job.get('description') or '',
            tuple(requirements.get('mandatory') or []), tuple(requirements.get('preferred') or []), bool(job.get('description_complete'))))
        job['assessment_summary'] = job['assessment']['summary']
    return job


def repair_jobs(legacy_jobs, raw_dir=None):
    """Repair existing identities without deleting, re-numbering, or inventing records."""
    root = Path(raw_dir) if raw_dir is not None else Path(__file__).resolve().parent
    index = {}
    for filename in RAW_FILES:
        path = root / filename
        if not path.exists():
            continue
        records = json.loads(path.read_text(encoding="utf-8-sig"))
        for raw in records:
            key = source_key(raw.get("url"))
            if key and (key not in index or len(raw.get("description") or "") > len(index[key].get("description") or "")):
                index[key] = raw
    repaired = []
    for legacy in legacy_jobs:
        if legacy.get("evidence_version") == 1:
            repaired.append(present_job(legacy))
            continue
        job_id = legacy.get("col_01_id") or legacy.get("id")
        raw = index.get(source_key(legacy.get("col_15_direct_url") or legacy.get("url")))
        if raw is None:
            # Legacy descriptions are retained as explicitly incomplete excerpts;
            # the generated requirements, industry, arrangement and salary estimates
            # never become evidence when the source cannot be recovered.
            raw = {"title": legacy.get("col_03_title") or legacy.get("title"),
                   "company": legacy.get("col_02_company") or legacy.get("company"),
                   "url": legacy.get("col_15_direct_url") or legacy.get("url"),
                   "source": legacy.get("col_14_source"),
                   "description": legacy.get("col_18_responsibilities") or "",
                   "description_incomplete": True,
                   "advertised_salary": legacy.get("col_09_advertised_salary"),
                   "legacy_source_missing": True}
        repaired.append(build_job(raw, job_id, legacy))
    return repaired


def sort_key(job):
    assessment = job.get("assessment", {})
    verification = job.get("verification", {})
    return (FIT_ORDER.get(assessment.get("fit"), 2), -(assessment.get('score',{}).get('value') if assessment.get('score',{}).get('value') is not None else -1),
            {"Thai required": 0, "Thai preferred": 1, "Thailand market context": 2}.get(job.get("thai_relevance"), 3),
            verification.get("needs_recheck", True), job.get("title", "").lower(), job.get("id", ""))


def draft_templates(job):
    """Role-specific editable drafts derived from supported source/CV pairs.

    The endpoint supplies starting points only; existing application draft text
    remains authoritative and is never regenerated on save or source refresh.
    """
    job = present_job(job)
    title = job.get("title") or "this role"
    opportunity = f"{title} at {job['company']}" if job.get('company') else title
    score = job['assessment']['score']
    pairs = [clause for row in score['duties'] for clause in row['clauses'] if clause['status'] == 'overlap']
    facts = list(dict.fromkeys(fact for pair in pairs for fact in pair['candidate_evidence']))
    body = "\n\n".join(f'Your listing asks: “{pair["quote"]}”\nMy relevant documented experience: {" ".join(pair["candidate_evidence"])}' for pair in pairs[:4])
    # Supported requirements are useful when a retained source has no duties;
    # unresolved requirements belong exclusively in the preparation checklist.
    if not body:
        supported = [row for row in score['requirements'] if row['status'] == 'supported']
        body = "\n\n".join(f'Your listing states: “{row["quote"]}”\nMy documented background: {" ".join(row["candidate_evidence"])}' for row in supported[:2])
    example = '[Add a specific example from your own work and only results you can verify.]'
    letter = (f'Dear hiring team,\n\nI’m interested in the {opportunity} opportunity.\n\n'
              + (body + '\n\n' if body else '') + example
              + '\n\nThank you for considering my application. I’d welcome a conversation about the role.\n\nDechsurang')
    recruiter = (f'Hello,\n\nI’m interested in the {opportunity} opportunity.\n\n'
                 + ('My relevant documented experience: ' + ' '.join(facts[:2]) + '\n\n' if facts else '')
                 + 'I’d welcome a conversation about the responsibilities and experience you are looking for.\n\nDechsurang')
    unresolved = [f'{row["quote"]} — {row["reason"]}' for row in score['requirements'] if row['status'] != 'supported']
    unresolved += [gate['reason'] for gate in score['gates']]
    unresolved += [f'{clause["quote"]} — {clause["reason"]}' for row in score['duties'] for clause in row['clauses'] if clause['status'] != 'overlap']
    if not score['requirements']: unresolved.append('Mandatory requirements are absent from the retained source; check the original listing.')
    if score['value'] is None: unresolved.append(score['unavailable_reason'])
    preparation = ('Evidence to prepare:\n' + ('\n'.join('- ' + pair['quote'] + '\n  CV: ' + ' '.join(pair['candidate_evidence']) for pair in pairs) if pairs else '- Establish the responsibilities from the original listing before choosing examples.')
        + '\n\nDescribe your own contribution and use only results you can verify.\n\nRequirements to check:\n'
        + ('\n'.join('- ' + gap for gap in dict.fromkeys(unresolved)) if unresolved else '- Confirm the listing is current and review the supported evidence before sending.'))
    return {'recruiter_message': recruiter, 'cover_letter': letter, 'interview_prep': preparation,
            'requirements_to_check': list(dict.fromkeys(unresolved)), 'supported_pairs': copy.deepcopy(pairs)}
