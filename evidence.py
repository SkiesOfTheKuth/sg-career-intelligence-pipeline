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
        if values:
            if re.search(r"\b(?:up to|maximum|max)\b", display, re.I):
                maximum = values[0]
            else:
                minimum, maximum = values[0], (values[1] if len(values) > 1 else values[0])
                if re.search(r"\b(?:from|minimum|min)\b", display, re.I) and len(values) == 1:
                    maximum = None
    disclosed = minimum is not None or maximum is not None
    currency = "SGD" if re.search(r"SGD|S\$", display, re.I) else None
    if currency is None:
        currency = next((c for c in ("USD", "AUD", "HKD", "EUR", "GBP") if c in display.upper()), None)
    # Singapore vacancy source dollar amounts are SGD; explicit foreign currencies remain foreign.
    if currency is None and "$" in display and "singapore" in str(raw.get("source", "")).lower():
        currency = "SGD"
    divisor = 12 if unit == "year" else 1 if unit == "month" else None
    return dict(display=display, disclosed=disclosed, minimum=minimum, maximum=maximum, unit=unit,
                currency=currency, monthly_minimum=round(minimum / divisor, 2) if divisor and minimum is not None else None,
                monthly_maximum=round(maximum / divisor, 2) if divisor and maximum is not None else None)


_REQ_HEADING = re.compile(r"^(?:(?:job|key|minimum|essential|basic|candidate)\s+)?(?:requirements|qualifications|skills)(?:\s*(?:and|&)\s*(?:experience|qualifications|skills))?\s*:?$|^what (?:we are|we're|you are) looking for\s*:?$|^about you\s*:?$|^who you are\s*:?$", re.I)
_PREFERRED = re.compile(r"\b(?:preferred|preferably|desirable|advantage|a plus|nice to have|bonus)\b", re.I)
_END_HEADING = re.compile(r"^(?:job responsibilities|responsibilities|benefits|what we offer|our commitment to you|about us|about the company|how to apply|equal opportunity|apply now)\s*:?$", re.I)


def extract_requirements(description, explicit=None):
    mandatory, preferred = [], []
    section = None
    # Explicit requirements retain all original wording, splitting only source lines.
    if isinstance(explicit, dict):
        mandatory.extend(plain_text(explicit.get("mandatory")).splitlines())
        preferred.extend(plain_text(explicit.get("preferred")).splitlines())
    elif explicit:
        for line in plain_text(explicit).splitlines():
            (preferred if _PREFERRED.search(line) else mandatory).append(line)
    for line in description.splitlines():
        clean = line.strip(" -•\t")
        if re.fullmatch(r"(?:preferred|desired|additional)\s+(?:qualifications|requirements|skills)\s*:?", clean, re.I):
            section = "preferred"
            continue
        if _REQ_HEADING.search(clean):
            section = "mandatory"
            continue
        if _END_HEADING.search(clean):
            section = None
            continue
        if section:
            (preferred if section == "preferred" or _PREFERRED.search(clean) else mandatory).append(clean)
        elif re.search(r"\b(?:must|minimum qualifications|is required|are required)\b", clean, re.I):
            mandatory.append(clean)
    return {"mandatory": list(dict.fromkeys(filter(None, mandatory))),
            "preferred": list(dict.fromkeys(filter(None, preferred)))}


def thai_relevance(title, description, requirements):
    sentences = re.split(r"[\n.!?]", title + "\n" + description)
    preferred, required = False, False
    for sentence in sentences:
        if not re.search(r"\bthai\b", sentence, re.I):
            continue
        # Geography and search queries do not establish a language requirement.
        if re.search(r"(?:thai[ -]speaking|thai language|fluen\w*[^.!?\n]{0,60}\bthai\b|\bthai\b[^.!?\n]{0,60}fluen\w*|(?:speak|read|write|communicat\w*|proficien\w*|translat\w*|interpret\w*)[^.!?\n]{0,60}\bthai\b|\bthai\b[^.!?\n]{0,40}(?:speaker|translat\w*|interpret\w*))", sentence, re.I):
            if _PREFERRED.search(sentence) or sentence.strip() in requirements["preferred"]:
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


def _supported_requirement(line):
    """Only narrow statements directly supported by the verified résumé pass."""
    text = line.lower().strip(" .-•")
    if re.search(r"\b(?:years?|native|fluent|fluency|expert|certifi\w*|advanced|extensive|proven|excellent|strong|leadership|manage a team|sql|python|adobe|seo|sem|cpa|roas|crm|paid media)\b", text):
        return False
    if re.fullmatch(r"(?:(?:a|minimum) )?(?:bachelor'?s?|master'?s?|university) degree(?: in (?:marketing|business|communications?)(?: (?:or|and) (?:a )?related (?:field|discipline))?)?(?: or equivalent(?: practical experience)?)?", text):
        return True
    if re.fullmatch(r"(?:singapore (?:citizen or )?(?:permanent resident|pr)|(?:ability to (?:speak|communicate in)|knowledge of) (?:english|thai)(?: and (?:english|thai))?)", text):
        return True
    if re.fullmatch(r"(?:experience (?:in|with)|knowledge of) (?:social media|content creation|community management|influencer outreach|audience research|marketing|thai.?english interpretation)(?: and (?:social media|content creation|community management|influencer outreach|audience research|marketing))?", text):
        return True
    return False


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
    unsupported_language = []
    for language in ("Japanese", "Vietnamese", "Mandarin", "Chinese", "Korean", "Tamil", "Malay", "Indonesian", "French", "German"):
        for sentence in re.split(r"[\n.!?]", language_text):
            if re.search(r"\b" + language + r"\b", sentence, re.I) and not _PREFERRED.search(sentence) and re.search(r"speaking|language|fluen\w*|proficien\w*|communicat\w*|written|spoken|(?:English|Thai)[, /]", sentence, re.I):
                unsupported_language.append(language)
                break
    for language in unsupported_language:
        gaps.append(f"The listing requests {language}; the résumé documents English and Thai only.")
    financial = re.search(r"\b(?:accounts? receivable|accounts? payable|accountant|accounting|financial (?:controller|analyst)|audit(?:or)?|credit (?:analyst|control))\b", title, re.I)
    if financial:
        gaps.append("Specialist finance or accounting experience is not documented in the résumé.")
    if not requirements["mandatory"]:
        gaps.append("Mandatory requirements are not clearly available in the retained source; check the original listing.")
    unsupported = [line for line in requirements["mandatory"] if not _supported_requirement(line)]
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
        employment = "Freelance"
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
    if status == "unavailable" and _is_search_page(url):
        job["source_warning"] = "This retained link is a search-results page, not an individual vacancy."
    return present_job(job)


def present_job(job, now=None):
    job = copy.deepcopy(job)
    now = parse_date(now) if isinstance(now, str) else now or datetime.now(UTC)
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    verification = job.setdefault("verification", {})
    checked = parse_date(verification.get("checked_at"))
    verification["needs_recheck"] = not checked or now - checked >= timedelta(hours=24) or verification.get("status") != "verified"
    deadline = parse_date(job.get("deadline"))
    # Date-only closing dates remain open through the recorded Singapore date.
    deadline_expired = bool(deadline and (deadline.date() < (now + timedelta(hours=8)).date()
                            if len(str(job.get("deadline"))) == 10 else deadline < now))
    if deadline_expired and job.get("status") not in ("closed", "unavailable"):
        job["status"] = "expired"
    if job.get("status") not in ("open", "expired", "closed", "unknown", "unavailable"):
        job["status"] = "unknown"
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
    return (FIT_ORDER.get(assessment.get("fit"), 2), -assessment.get("overlap", 0),
            {"Thai required": 0, "Thai preferred": 1, "Thailand market context": 2}.get(job.get("thai_relevance"), 3),
            verification.get("needs_recheck", True), job.get("title", "").lower(), job.get("id", ""))


def draft_templates(job):
    """Editable starting points using only facts verified against the candidate CV."""
    title = job.get("title") or "this role"
    company = job.get("company")
    opportunity = f"{title} at {company}" if company else title
    recruiter = (
        f"Hello,\n\nI’m interested in the {opportunity} opportunity. "
        "I work as a Marketing and PR Specialist at Social Collective Studio, where my responsibilities include "
        "social media content and community management, monthly analytics, and influencer outreach and contracts. "
        "I hold an MSc in Marketing from Nanyang Technological University and a BBA in International Marketing "
        "from Kasetsart University.\n\nI’d welcome a conversation about the role and the experience you are looking for.\n\nDechsurang"
    )
    letter = (
        f"Dear hiring team,\n\nI’m writing to express my interest in the {opportunity} opportunity.\n\n"
        "In my Marketing and PR Specialist role at Social Collective Studio, I work on social media content and "
        "community management, monthly analytics, trend and audience research, pitch decks, and influencer outreach "
        "and contracts. My education includes an MSc in Marketing from Nanyang Technological University and a BBA "
        "in International Marketing from Kasetsart University.\n\n"
        "My experience also includes Thai–English interpretation at the APAC Food & Beverage Expo in August 2026 "
        "and B2B interpretation and liaison for the Royal Thai Embassy.\n\n"
        "[Add a specific example relevant to the responsibilities in this listing. Confirm any requirements listed "
        "under Requirements to check before sending.]\n\n"
        "Thank you for considering my application. I’d welcome the opportunity to discuss how my experience relates "
        "to your team’s needs.\n\nDechsurang"
    )
    mandatory = job.get("requirements", {}).get("mandatory", [])
    if mandatory:
        quoted = mandatory[0]
        if len(quoted) > 400:
            quoted = quoted[:400].rstrip() + "… [source excerpt]"
        letter = letter.replace(
            "[Add a specific example relevant to the responsibilities in this listing. Confirm any requirements listed "
            "under Requirements to check before sending.]",
            f'Your listing states: “{quoted}”\n[Add a verified example addressing this requirement, '
            'or explain what needs clarification. Review all Requirements to check before sending.]')
    gaps = job.get("assessment", {}).get("gaps", [])
    preparation = (
        "Prepare examples from your documented work: a social media campaign, monthly analytics or audience research, "
        "and influencer outreach or contract coordination. Describe your own contribution and use only results you can verify.\n\n"
        "Questions to clarify:\n" + "\n".join("- " + gap for gap in gaps[:8])
    )
    return {"recruiter_message": recruiter, "cover_letter": letter, "interview_prep": preparation}
