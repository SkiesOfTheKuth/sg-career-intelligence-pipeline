"""Versioned, deterministic documented-fit rubric. No hiring probabilities.

Points are a transparent prioritization policy, not fitted outcome statistics.
Missing facts earn no points; that means unproven, not incapable. Every awarded
duty/requirement point includes the source wording and specific CV evidence.
"""
import re
import unicodedata
from functools import lru_cache

VERSION = 'documented-fit-v2'
CV_SOURCE = 'CV 2026.pdf, verified 21 October 2026'
RULES = (
    ('social', r'\bsocial[ -]media\b|\bcommunity (?:management|engagement)\b|\bengage communit', 'Social Collective Studio: full-cycle social media accounts, content planning and daily community management.'),
    ('content', r'\bcontent (?:creation|planning|strategy|strategies|calendar|calendars|ideas)\b|\b(?:create|creating|curate|curating|publish|publishing|schedule|scheduling|develop|developing)\b[^.;\n]{0,50}\bcontent\b', 'Social Collective Studio: content planning. uWave: digital content creation across social media platforms.'),
    ('influencer', r'\binfluencer (?:outreach|relations|relationships|campaigns?|contracts?|communications?|engagement|tastings?)\b|\b(?:coordinate|manage|build|develop)\b[^.;\n]{0,45}\binfluencer', 'Social Collective Studio: influencer outreach, contract communications and campaign execution.'),
    ('research', r'\b(?:audience|trend|market|consumer) research\b|\bresearch\b[^.;\n]{0,45}\b(?:audience|trends?|market)\b', 'Social Collective Studio: trend and audience research for marketing proposals and pitch decks.'),
    ('analytics', r'\b(?:social media|campaign|content|performance) (?:analytics|metrics|performance|reports?|reporting)\b|\bmonthly (?:analytics|reports?|reporting)\b|\b(?:monitor|analyse|analyze|track)\b[^.;\n]{0,40}\b(?:engagement|analytics|audience growth)\b', 'Social Collective Studio: performance metrics, monthly reports and campaign recommendations.'),
    ('interpretation', r'\b(?:thai[–— -]+english|english[–— -]+thai)\b[^.;\n]{0,55}\binterpret\w*|\binterpret\w*\b[^.;\n]{0,55}\bthai\b', 'APAC Food & Beverage Expo (21–23 August 2026) and Royal Thai Embassy (24 August 2026): Thai–English interpretation and B2B liaison.'),
    ('pitch', r'\bpitch decks?\b|\bmarketing proposals?\b', 'Social Collective Studio: research-based marketing proposals and pitch decks.'),
    ('sponsor', r'\bsponsor(?:ship)? (?:acquisition|outreach)\b', 'uWave internship (January–April 2021): sponsor acquisition for content.'),
)
# A general overlap cannot establish proficiency in a specialist method or tool.
SPECIALIST = re.compile(r'\b(?:sql|python|seo|sem|ppc|paid (?:media|search|social|ads?)|google (?:ads|analytics)|meta (?:ads|insights)|roas|crm|salesforce|hubspot|adobe|photoshop|illustrator|canva|capcut|premiere|after effects|film(?:ing)?|shoots?|camera|lighting|videograph\w*|video (?:production|editing)|edit(?:ing)? videos?|animation|motion graphics|memoq|cat tools|lqa|translation memor\w*|game localization|payroll|accounting|bookkeeping|reconciliations?|financial (?:reports?|reporting)|audit\w*|tax|budget\w*|forecast\w*|crisis|spokesperson|media (?:relations|enquiries)|manage (?:a |the )?team|team leadership|direct reports|p&l)\b', re.I)
ACTION = re.compile(r'^(?:(?:you (?:will|would)|the role (?:will|involves)|responsible for)\s+)?(?:plan|manage|create|curate|develop|coordinate|support|assist|conduct|research|monitor|analyse|analyze|track|prepare|produce|deliver|lead|own|oversee|drive|ensure|handle|maintain|build|execute|implement|engage|write|edit|film|design|identify|review|work|provide|liaise|facilitate|translate|interpret|brainstorm|suggest|participate|schedule|publish|report)\w*\b', re.I)
DUTY_HEADING = re.compile(r'^(?:(?:key|main|core|job|your|primary)\s+)?(?:duties(?:\s*(?:&|and)\s*responsibilities)?|responsibilities)(?:\s*(?:&|and)\s*duties)?\s*:?$|^(?:what you(?:\'ll| will) do|your role|you will be responsible for|as a .+ you will be accountable for)\s*:?$', re.I)
STOP_HEADING = re.compile(r'^(?:(?:job|key|minimum|essential|preferred|basic|candidate)\s+)?(?:requirements|qualifications|skills|benefits|experience)(?:\s*(?:&|and)\s*(?:experience|skills|qualifications))?\s*:?$|^(?:what (?:we are|we\'re) looking for|about you|who you are|what we offer|about us|our commitment to you|how to apply|apply now|selling pts)\s*:?$', re.I)
PREFERRED = re.compile(r'\b(?:preferred|preferably|desirable|advantage|a plus|nice to have|bonus|not (?:a )?(?:must|required))\b', re.I)
LANGUAGES = ('English','Thai','Japanese','Vietnamese','Mandarin','Chinese','Korean','Tamil','Malay','Indonesian','French','German')


def normalized(text):
    """Comparison form only: retain original quotations in all evidence rows."""
    text = unicodedata.normalize('NFKC', text).translate(str.maketrans({'’': "'", '‘': "'", '–': '-', '—': '-', '‑': '-', '−': '-'}))
    return re.sub(r'^\s*(?:[-•●▪◦‣]+|\d+[.)])\s*', '', text).strip()


def is_boilerplate(line):
    text = normalized(line)
    return bool(re.search(r'^(?:https?://|our (?:company|agency|firm|business|services)|the company|we (?:are|have|were|operate|speciali[sz]e)|established in|founded in|incorporated in|EA\s*(?:licen[cs]e|reg)|(?:recruiter |company )?(?:registration|reg)\s*(?:no|number)|please (?:apply|send|submit)|(?:interested|shortlisted) candidates|submit your|send your|click (?:here|apply|on apply)|to apply\b|by applying|should your application|take an inside look|for job seekers|its clientele)', text, re.I)
        or re.search(r'\b(?:officially opened for business|is an? (?:approved training|professional staffing)|EA licen[cs]e (?:no|number))\b', text, re.I))


def _unique(lines):
    seen = set()
    for line in lines:
        key = re.sub(r'\W+', ' ', normalized(line).casefold()).strip()
        if key and key not in seen:
            seen.add(key)
            yield line


def duty_lines(description, requirements):
    lines = [(re.sub(r'^\s*(?:[-•●▪]+|\d+[.)])\s*', '', line).strip(), bool(re.match(r'^\s*(?:[-•●▪]+|\d+[.)])\s*', line))) for line in description.splitlines() if line.strip()]
    def heading(line):
        return (DUTY_HEADING.fullmatch(line.replace('’', "'"))
                or re.match(r'^(?:job |key )?responsibilities\b.*:\s*$', line, re.I)
                or re.fullmatch(r'job description\s*:?|the scope of work includes[^.]*:', line, re.I))
    explicit = any(heading(line) for line, _ in lines)
    active = not explicit
    result = []
    req_keys = {re.sub(r'\W+', '', line.lower()) for line in requirements}
    for line, listed in lines:
        if heading(line): active = True; continue
        if STOP_HEADING.fullmatch(line.replace('’', "'")): active = False; continue
        if not active or is_boilerplate(line) or re.sub(r'\W+', '', line.lower()) in req_keys: continue
        for sentence in re.split(r'(?<=[.!?])\s+|\s*[;]\s*', line):
            sentence = sentence.strip()
            if ACTION.search(sentence) and not re.search(r'\b(?:must|minimum|required|qualifications)\b', sentence, re.I):
                result.append(sentence)
            elif (listed or explicit) and len(sentence.split()) >= 2 and not sentence.endswith(':'):
                # Do not silently drop unfamiliar duties from the denominator.
                result.append(sentence)
    return list(_unique(result)), explicit


def _clause(quote):
    text = normalized(quote)
    matched = [(key, fact) for key, pattern, fact in RULES if re.search(pattern, text, re.I)]
    # Require the activity to concern the documented task, not merely mention
    # it as the object of purchasing, software development or translation.
    task_actions = {
        'content': r'\b(?:create|creating|creation|plan|planning|curate|curating|publish|publishing|schedule|scheduling|develop|developing|write|writing|edit|editing)\b[^.;]{0,45}\bcontent\b|\bcontent (?:creation|planning|strategy|calendar)',
        'influencer': r'\b(?:coordinate|manage|build|develop|contact|engage|liaise)\w*\b[^.;]{0,45}\binfluencer|\binfluencer (?:outreach|relations|contracts?|communications?|engagement)',
        'research': r'\b(?:conduct|perform|support|undertake|research)\w*\b[^.;]{0,45}\b(?:audience|market|consumer|trends?)|\b(?:audience|market|consumer|trend) research\b',
        'analytics': r'\b(?:monitor|analyse|analyze|track|report|prepare|compile|measure)\w*\b[^.;]{0,60}\b(?:engagement|analytics|performance|reports?|metrics)|\bmonthly (?:analytics|reports?|reporting)\b',
        'pitch': r'\b(?:prepare|develop|create|craft|research|support|assist)\w*\b[^.;]{0,60}\b(?:pitch|proposals?)|\b(?:pitch decks?|marketing proposals?)\s*[.]?$',
        'sponsor': r'\b(?:acquire|identify|contact|secure|support|coordinate)\w*\b[^.;]{0,45}\bsponsor|\bsponsor(?:ship)? (?:acquisition|outreach)\b',
    }
    matched = [(key, fact) for key, fact in matched if key not in task_actions or re.search(task_actions[key], text, re.I)]
    if re.search(r'\b(?:buy|purchas\w*|sell|translat\w*)\b', text, re.I):
        matched = [(key, fact) for key, fact in matched if key == 'interpretation']
    # A topic is not an action. Managing accounts or communities is distinct from
    # producing assets for those channels, advertising or specialised analysis.
    if not re.search(r'\b(?:manag\w*|maintain\w*|engag\w*|plan\w*|schedul\w*|publish\w*|curat\w*|post\w*)\b[^.;]{0,45}\b(?:social[ -]media|communit\w*|content)|\b(?:social[ -]media|community) (?:management|engagement)\b', text, re.I):
        matched = [(key, fact) for key, fact in matched if key != 'social']
    specialist = SPECIALIST.search(text)
    if not specialist:
        specialist = re.search(r'\b(?:software|programming|algorithms?|automation|photography|photos?|graphic(?:s| design)?|visual assets|key visuals|artwork|video\w*|AI tools?|revenue|sales performance|cold calling|sales prospects?|sales opportunities|sales targets?|prospecting|media pitching|media invites|product launches)\b', text, re.I)
    status = 'overlap' if matched and not specialist else 'check'
    return {'quote': quote, 'status': status, 'candidate_evidence': list(dict.fromkeys(fact for _, fact in matched)) if status == 'overlap' else [],
            'evidence_state': 'supported' if status == 'overlap' else 'missing_candidate_evidence',
            'reason': 'Documented task overlap; depth and results still need your review.' if status == 'overlap' else f'The CV does not establish this specialist scope: {specialist.group(0)}.' if specialist else 'No specific CV evidence is mapped to this duty. Review it yourself.',
            'domains': [key for key, _ in matched] if status == 'overlap' else []}


def _duty(quote):
    # Split only when a conjunction introduces an independent action. A noun
    # phrase such as "graphics and animation" stays together with its action.
    pieces = re.split(r'\s*(?:;|,?\s+and|,?\s+as well as|,?\s+while)\s+(?=(?:plan|manage|create|curate|develop|coordinate|support|assist|conduct|research|monitor|analyse|analyze|track|prepare|produce|deliver|lead|own|oversee|drive|ensure|handle|maintain|build|execute|implement|engage|write|edit|film|design|identify|review|work|provide|liaise|facilitate|translate|interpret|schedule|publish)\w*\b)', quote, flags=re.I)
    clauses = [_clause(piece.strip()) for piece in pieces if piece.strip()]
    for clause in clauses: clause['source_quote'] = quote
    supported = [clause for clause in clauses if clause['status'] == 'overlap']
    status = 'overlap' if len(supported) == len(clauses) else 'partial' if supported else 'check'
    return {'quote': quote, 'status': status, 'clauses': clauses,
            'candidate_evidence': list(dict.fromkeys(fact for clause in supported for fact in clause['candidate_evidence'])),
            'domains': list(dict.fromkeys(domain for clause in supported for domain in clause['domains'])),
            'evidence_state': 'supported' if status == 'overlap' else 'missing_candidate_evidence',
            'reason': 'Some clauses have documented support; the other clauses remain unproven.' if status == 'partial' else clauses[0]['reason']}


def requirement(line):
    text = normalized(line).strip(' .').lower()
    result = {'quote': line, 'status': 'check', 'evidence_state':'missing_candidate_evidence', 'candidate_evidence': [], 'reason': 'Not established by the verified CV; this is not a claim that you lack it.'}
    if re.search(r'\b(?:years?|native|fluent|fluency|certifi\w*|advanced|extensive|proven|excellent|strong|expert|leadership)\b', text) or SPECIALIST.search(text):
        return result
    degree = r"(?:(?:a|minimum|at least a) )?(?:diploma\s*/\s*degree|diploma or degree|(?:bachelor'?s?|master'?s?|university) degree|degree)(?: in (?:marketing|business)(?:\s*(?:,|or)\s*(?:(?:a )?related (?:field|discipline)|business|marketing))*)?(?: or equivalent(?: practical experience)?)?"
    alternative_degree = re.fullmatch(r"(?:(?:a|minimum|at least a) )?(?:diploma\s*/\s*degree|diploma or degree|(?:bachelor'?s?|master'?s?|university) degree|degree) in (.+?)(?: or equivalent(?: practical experience)?)?(?: \(or equivalent experience\))?", text)
    degree_options = re.split(r'\s*(?:,|/|\bor\b)\s*', alternative_degree[1]) if alternative_degree else []
    supported_degree = any(re.fullmatch(r'(?:international )?(?:marketing|business(?: administration)?)', option) for option in degree_options)
    if re.fullmatch(degree, text) or supported_degree:
        result.update(status='supported', candidate_evidence=['MSc Marketing, NTU (2022–2023); BBA International Marketing, Kasetsart University (2018–2021).'], reason='The documented degrees meet this subject and level wording.')
    elif re.fullmatch(r'(?:singapore (?:citizen or )?(?:permanent resident|pr)|(?:ability to (?:speak|communicate in)|knowledge of) (?:english|thai)(?: and (?:english|thai))?)', text):
        result.update(status='supported', candidate_evidence=['CV: Singapore Permanent Resident; languages listed as English and Thai.'], reason='This basic wording is documented. No native or fluency level is inferred.')
    elif re.fullmatch(r'(?:experience (?:in|with)|knowledge of) (?:social media(?: management)?|content creation|community management|influencer outreach|audience research|marketing|thai.?english interpretation)(?: and (?:social media|content creation|community management|influencer outreach|audience research|marketing))?', text):
        evidence = [fact for _, pattern, fact in RULES if re.search(pattern, text, re.I)]
        result.update(status='supported', candidate_evidence=evidence or ['Social Collective Studio: Marketing and PR Specialist (2025–present).'], reason='This specific experience is documented in the CV.')
    if result['status'] == 'supported': result['evidence_state'] = 'supported'
    # Explicit exclusion is different from a qualification simply absent in a CV.
    if re.fullmatch(r'(?:only )?singapore citizens? only|singapore citizens? \(no (?:pr|permanent residents?)\)', text):
        result.update(status='incompatible', evidence_state='documented_incompatibility', reason='The listing excludes permanent residents; the CV documents Singapore Permanent Resident status.')
    return result


def language_gaps(lines):
    gaps = []
    for line in lines:
        if PREFERRED.search(line): continue
        if not re.search(r'speaking|language|fluen\w*|proficien\w*|communicat\w*|written|spoken|command of', line, re.I): continue
        found = [language for language in LANGUAGES if re.search(r'\b' + language + r'\b', line, re.I)]
        if not found: continue
        # "Japanese or English" is a supported alternative, not a Japanese gate.
        name = r'\b(?:' + '|'.join(LANGUAGES) + r')\b'
        alternatives = re.findall(name + r'(?:\s*(?:or|/)\s*' + name + r')+', line, re.I)
        waived = set()
        for group in alternatives:
            members = [language for language in LANGUAGES if re.search(r'\b' + language + r'\b', group, re.I)]
            if any(language in ('English','Thai') for language in members): waived.update(members)
        unsupported = [language for language in found if language not in ('English', 'Thai')]
        unsupported = [language for language in unsupported if language not in waived]
        if unsupported:
            gaps.append({'kind': 'language', 'quote': line, 'reason': f"Required language evidence missing: {', '.join(unsupported)}. The CV lists English and Thai; it does not establish the requested language."})
    return gaps


@lru_cache(maxsize=8192)
def evaluate(title, description, mandatory, preferred, complete, family):
    """Inputs are immutable; callers copy the result before adding UI data."""
    mandatory = tuple(_unique(mandatory))
    duties, explicit = duty_lines(description, mandatory + preferred)
    duty_rows = [_duty(line) for line in duties]
    req_rows = [requirement(line) for line in mandatory]
    preferred_rows = [requirement(line) for line in _unique(preferred)]
    direct = family in ('Social media and content','Marketing','Public relations and communications','Interpretation and language services')
    related = family in ('Events and trade','Business development and partnerships')
    family_points = 20 if direct else 10 if related else 0
    family_evidence = 'Social Collective Studio: Marketing and PR Specialist; MSc and BBA in Marketing.' if family in ('Marketing','Public relations and communications','Social media and content') else 'Thai–English interpretation and trade-show/B2B liaison assignments, August 2026.' if family in ('Events and trade','Interpretation and language services') else 'uWave: sponsor acquisition; Royal Thai Embassy: B2B liaison.' if related else 'No direct job-family evidence mapped from the CV.'
    clause_rows = [clause for row in duty_rows for clause in row['clauses']]
    matched = sum(row['status'] == 'overlap' for row in clause_rows)
    supported = sum(row['status'] == 'supported' for row in req_rows)
    # Collapse repeated supported domains so repeating the same duty cannot boost fit.
    domain_groups = {tuple(row['domains']) for row in clause_rows if row['status'] == 'overlap'}
    unknown_duties = len(clause_rows) - matched
    duty_denominator = len(domain_groups) + unknown_duties
    duty_points = round(50 * len(domain_groups) / duty_denominator) if duty_denominator else 0
    req_points = round(30 * supported / len(req_rows)) if req_rows else 0
    strict_language_lines = [line for line in re.split(r'[\n.!?]', description) if re.search(r'\b(?:must|required|requires|fluency|fluent|proficiency|command of)\b', line, re.I)]
    gates = language_gaps(list(mandatory) + strict_language_lines + [title])
    finance = re.search(r'\b(?:accounts? receivable|accounts? payable|accountant|accounting|financial (?:controller|analyst)|auditor|credit (?:analyst|control))\b', title, re.I)
    if finance:
        gates.append({'kind':'specialist','quote':title,'reason':'Specialist accounting or finance experience is not documented in the CV.'})
    for line in mandatory:
        years = re.search(r'(?:minimum|at least|over|more than)?\s*(\d+)\s*(?:\+|[-–]\s*\d+)?\s*(?:years?|yrs?)\b', line, re.I)
        if years and int(years[1]) >= 3 and not PREFERRED.search(line):
            gates.append({'kind':'experience','quote':line,'reason':'The CV lists a 2025–present role, a four-month 2021 internship and short interpretation assignments. It does not establish this required experience duration.'})
        if re.search(r'\b(?:cpa|acca|chartered accountant|medical licen[cs]e|law degree)\b', line, re.I) and not PREFERRED.search(line):
            gates.append({'kind':'qualification','quote':line,'reason':'The required specialist qualification is not documented in the CV.'})
    if re.search(r'\b(?:director|head of|vice president|chief|senior|team lead)\b', title, re.I):
        gates.append({'kind':'seniority','quote':title,'reason':'The CV does not establish senior leadership scope. Confirm team, budget and experience expectations.'})
    gates = list({(gate['kind'],gate['quote']):gate for gate in gates}.values())
    for row in req_rows:
        if row['status'] == 'incompatible': gates.append({'kind':'eligibility', 'quote':row['quote'], 'reason':row['reason'], 'evidence_state':'documented_incompatibility'})
    for gate in gates: gate.setdefault('evidence_state', 'missing_candidate_evidence')
    unknown_requirements = len(req_rows) - supported
    limits = []
    if gates: limits.append({'maximum':39,'reason':'Required or senior-level evidence is missing. Resolve the flagged gate before treating this as a strong option.'})
    if not req_rows or unknown_requirements: limits.append({'maximum':59,'reason':'Mandatory requirements are missing or not fully supported by the CV.'})
    if not explicit: limits.append({'maximum':59,'reason':'The source does not clearly separate responsibilities. The extracted duties need review.'})
    if not direct: limits.append({'maximum':59,'reason':'The role family is adjacent or outside the documented background.'})
    available = bool(complete and description and duty_rows)
    subtotal = family_points + duty_points + req_points
    value = min([subtotal] + [limit['maximum'] for limit in limits]) if available else None
    provisional = not available or bool(limits or unknown_duties)
    return {'version':VERSION,'value':value,'maximum':100,'label':'Documented fit', 'provisional':provisional,
            'evidence_state': 'missing_source' if not available or not req_rows else 'documented_incompatibility' if any(g['evidence_state'] == 'documented_incompatibility' for g in gates) else 'missing_candidate_evidence' if provisional else 'supported',
            'unavailable_reason':None if available else 'No score: the retained description is incomplete, missing, or has no identifiable duties.',
            'summary':f'{matched} of {len(clause_rows)} responsibility clauses show documented overlap; {supported} of {len(req_rows)} mandatory requirements supported.' if available else 'Open the original listing to establish responsibilities before comparing fit.',
            'components':[
                {'label':'Role family','earned':family_points,'maximum':20,'basis':family,'candidate_evidence':family_evidence},
                {'label':'Responsibility overlap','earned':duty_points,'maximum':50,'basis':f'{len(domain_groups)} distinct supported duty groups; {unknown_duties} unmapped duty statements. Repeated matches count once.'},
                {'label':'Mandatory requirements','earned':req_points,'maximum':30,'basis':f'{supported} of {len(req_rows)} explicitly supported; missing requirements earn no points.'}],
            'subtotal':subtotal,'limits':limits,'gates':gates,'duties':duty_rows,'requirements':req_rows,'preferred':preferred_rows,
            'unknown_duties':unknown_duties,'unknown_requirements':unknown_requirements,'candidate_source':CV_SOURCE,
            'method':'A rule-based reading aid: 20 points for job family, 50 for documented duty overlap, 30 for supported mandatory requirements. Weights express review priorities, not measured hiring outcomes. Unknowns earn no points; low scores may reflect missing CV evidence. Pay, prestige, nationality, company geography and source freshness do not add fit points. Preferred requirements are shown for review without a bonus. Source freshness is reported separately.'}
