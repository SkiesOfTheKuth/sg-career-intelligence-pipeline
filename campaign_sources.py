"""Bounded actor inputs, URL identities and source-grounded normalization.

URL handling here performs no network admission checks. Raw actor output is
retained by the campaign journal; normalized fields never replace that output.
"""
import copy
import hashlib
import json
from pathlib import Path
import re
from html import unescape
from html.parser import HTMLParser
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode, urljoin

from evidence import build_job, source_key, plain_text

CONTRACTS = json.loads((Path(__file__).parent / 'campaign_contracts.json').read_text(encoding='utf8'))
CORE = ['Thai', 'Marketing Executive', 'Social Media Executive', 'Public Relations']
HISTORICAL = ['Thai interpreter', 'Thailand market', 'Digital Marketing Executive', 'Influencer Marketing',
              'KOL Marketing', 'Corporate Communications Executive', 'Partnerships Executive',
              'Business Development Executive', 'Events Executive', 'Trade Show Coordinator',
              'Regional Marketing Executive', 'Market Research Executive']
NAMES = {'linkedin':'LinkedIn Jobs', 'indeed':'Indeed Singapore', 'google':'Google search leads', 'careers':'Career websites'}


class AccessBlocked(ValueError):
    """Compatibility name for a syntactically invalid HTTP URL."""
    pass


def canonical_url(value):
    """Normalize an HTTP(S) identity, without DNS, robots or destination policy."""
    if not isinstance(value, str) or len(value) > 4096 or re.search(r'[\x00-\x20\\]', value):
        raise AccessBlocked('Invalid URL')
    try:
        p = urlsplit(value)
        if p.scheme not in ('https','http') or not p.hostname:
            raise ValueError()
        host = p.hostname.encode('idna').decode('ascii').lower().rstrip('.')
        if ':' in host:
            host = '[' + host + ']'
        if p.port is not None and p.port != (443 if p.scheme == 'https' else 80):
            host += ':' + str(p.port)
        if '@' in p.netloc:
            host = p.netloc.rsplit('@',1)[0] + '@' + host
        query = urlencode(sorted((k,v) for k,v in parse_qsl(p.query, keep_blank_values=True)
                                 if not k.lower().startswith('utm_') and k.lower() not in ('trk','trackingid','ref')))
        return urlunsplit((p.scheme, host, p.path or '/', query, ''))
    except (ValueError, UnicodeError) as e:
        raise AccessBlocked('Invalid URL') from e


def queries(cycle):
    start = (cycle * 4) % len(HISTORICAL)
    return CORE + [HISTORICAL[(start+i)%len(HISTORICAL)] for i in range(4)]


def input_for(source, query, limit=100):
    if source == 'linkedin':
        return {'urls':['https://www.linkedin.com/jobs/search/?'+urlencode({'keywords':query,'location':'Singapore','geoId':'102454443'})],
                'limitPerSource':limit,'scrapeCompany':False,'autoConvertToAiSearch':False}
    if source == 'indeed':
        return {'position':query,'country':'SG','location':'Singapore','maxItemsPerSearch':limit,
                'parseCompanyDetails':False,'saveOnlyUniqueItems':True,'followApplyRedirects':False}
    if source == 'google':
        return {'queries':query,'maxPagesPerQuery':3,'countryCode':'sg','languageCode':'en',
                'maximumLeadsEnrichmentRecords':0,'websiteContentScraper':{'enable':False},
                'aiOverview':{'scrapeFullAiOverview':False},'aiModeSearch':{'enableAiMode':False},
                'geminiSearch':{'enableGemini':False},'perplexitySearch':{'enablePerplexity':False},
                'chatGptSearch':{'enableChatGpt':False},'copilotSearch':{'enableCopilot':False}}
    if source == 'careers':
        # Recursion belongs to the durable queue, so every batch contains only
        # the explicit pages of one domain at one recorded discovery depth.
        urls = [query] if isinstance(query,str) else list(query)
        urls = list(dict.fromkeys(canonical_url(url) for url in urls))
        if not 1 <= len(urls) <= 50 or len({urlsplit(url).hostname for url in urls}) != 1:
            raise ValueError('Career batches require 1–50 URLs from one domain')
        return {'startUrls':[{'url':url} for url in urls],'crawlerType':'cheerio','maxCrawlDepth':0,
                'maxCrawlPages':len(urls),'maxResults':len(urls),'respectRobotsTxtFile':False,
                'proxyConfiguration':{'useApifyProxy':False},'maxConcurrency':1,
                'maxRequestRetries':0,'maxSessionRotations':0,'saveFiles':False,
                'saveContentTypes':'','saveMarkdown':True,'saveHtml':True,
                'saveHtmlAsFile':False,'saveScreenshots':False,'summarize':False,
                'useSitemaps':False,'useLlmsTxt':False,'ignoreHttpsErrors':False,
                'htmlTransformer':'none',
                'removeElementsCssSelector':'script, style, noscript, svg, img[src^="data:"]'}
    raise ValueError('Unknown source')


def validate_input(source, payload):
    schema = CONTRACTS[source]['schema']
    if any(k not in payload for k in schema.get('required',[])):
        raise ValueError('Actor input is missing a required field')
    for k,v in payload.items():
        spec = schema['properties'].get(k)
        if not spec:
            raise ValueError(f'Unrecognized actor field: {k}')
        expected = {'string':str,'integer':int,'boolean':bool,'object':dict,'array':list}.get(spec.get('type'))
        if expected and type(v) is not expected or 'enum' in spec and v not in spec['enum']:
            raise ValueError(f'Invalid actor field: {k}')
        if isinstance(v,(int,float)) and (v < spec.get('minimum',v) or v > spec.get('maximum',v)):
            raise ValueError(f'Out-of-bounds actor field: {k}')
    if source == 'indeed' and (payload.get('country') != 'SG' or payload.get('location') != 'Singapore' or payload.get('maxItemsPerSearch',101)>100):
        raise ValueError('Indeed scope exceeds the Singapore contract')
    if source == 'linkedin' and (payload.get('limitPerSource',101)>100 or len(payload.get('urls',[]))!=1):
        raise ValueError('LinkedIn scope exceeds the per-query contract')
    if source == 'google':
        search_queries = payload.get('queries','').splitlines()
        if not 1 <= len(search_queries) <= 20 or any(not q.strip() for q in search_queries) or len(set(search_queries)) != len(search_queries) or payload.get('maxPagesPerQuery',4) > 3:
            raise ValueError('Google scope exceeds 20 distinct queries and three pages each')
    if source == 'careers':
        urls = [canonical_url(entry['url']) for entry in payload.get('startUrls',[])]
        if (not 1 <= len(urls) <= 50 or len(set(urls)) != len(urls) or len({urlsplit(url).hostname for url in urls}) != 1
                or payload.get('maxCrawlDepth') != 0 or payload.get('maxCrawlPages') != len(urls)
                or payload.get('maxResults') != len(urls) or payload.get('respectRobotsTxtFile') is not False):
            raise ValueError('Career scope exceeds the explicit-page batch contract')


def access_url(source, payload):
    if source == 'linkedin': return payload['urls'][0]
    if source == 'indeed': return 'https://sg.indeed.com/jobs?'+urlencode({'q':payload['position'],'l':'Singapore'})
    if source == 'google': return 'https://www.google.com/search?'+urlencode({'q':payload['queries']})
    return payload['startUrls'][0]['url']


class _CareerHTML(HTMLParser):
    """Read documented crawler HTML without executing or downloading content."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links, self.json_ld, self.headings = [], [], []
        self.anchor, self.script, self.heading, self.base_url = None, None, None, None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'base' and attrs.get('href'):
            self.base_url = attrs['href']
        if tag == 'a' and attrs.get('href'):
            self.anchor = {'url':attrs['href'],'title':attrs.get('aria-label') or attrs.get('title') or ''}
        if tag == 'script' and attrs.get('type','').lower() == 'application/ld+json':
            self.script = []
        if tag == 'h1':
            self.heading = []

    def handle_data(self, data):
        if self.anchor is not None:
            self.anchor['title'] += data
        if self.script is not None:
            self.script.append(data)
        if self.heading is not None:
            self.heading.append(data)

    def handle_endtag(self, tag):
        if tag == 'a' and self.anchor is not None:
            self.links.append(self.anchor)
            self.anchor = None
        if tag == 'script' and self.script is not None:
            try:
                self.json_ld.append(json.loads(''.join(self.script)))
            except (ValueError, TypeError):
                pass  # Malformed structured data stays inspectable in the item.
            self.script = None
        if tag == 'h1' and self.heading is not None:
            self.headings.append(''.join(self.heading).strip())
            self.heading = None


def _crawler_html(item):
    parser = _CareerHTML()
    if isinstance(item.get('html'),str):
        parser.feed(item['html'])
    return parser


def _page_url(item):
    crawl = item.get('crawl') if isinstance(item.get('crawl'),dict) else {}
    return crawl.get('loadedUrl') or item.get('url') or ''


def extract_links(item):
    """Extract evidence-bearing links from documented Markdown and HTML output.

    The official crawler does not document a `links` output field. References
    are resolved against its loaded URL (including redirects), not a search
    query. The caller persists and bounds discovery depth and page/domain use.
    """
    if not isinstance(item,dict):
        return []
    parent = _page_url(item)
    parser = _crawler_html(item)
    base = urljoin(parent,parser.base_url) if parser.base_url else parent
    candidates = [(entry['url'],entry['title'],'html') for entry in parser.links]
    markdown = item.get('markdown') if isinstance(item.get('markdown'),str) else ''
    # Inline links, optional angle brackets/titles, and one balanced pair in a
    # URL cover links emitted by the crawler's Markdown conversion.
    inline = r'(?<!!)\[([^\]\n]*)\]\(\s*(<[^>\n]+>|(?:[^\s()\\]|\\.|\([^()\n]*\))+)(?:\s+["\'][^\n]*?["\'])?\s*\)'
    candidates += [(url.strip('<>'),title,'markdown') for title,url in re.findall(inline,markdown)]
    references = {key.strip().casefold():url.strip('<>') for key,url in re.findall(r'^\s{0,3}\[([^\]]+)\]:\s*(<[^>]+>|\S+)',markdown,re.M)}
    for title,key in re.findall(r'(?<!!)\[([^\]\n]+)\]\[([^\]\n]*)\]',markdown):
        if (key or title).strip().casefold() in references:
            candidates.append((references[(key or title).strip().casefold()],title,'markdown'))
    candidates += [(url,url,'markdown') for url in re.findall(r'<(https?://[^<>\s]+)>',markdown)]
    results, seen = [], set()
    for target,title,field in candidates:
        if target.startswith('#'):
            continue
        target = re.sub(r'\\([()\[\]\\])',r'\1',unescape(target))
        try:
            url = canonical_url(urljoin(base,target))
        except AccessBlocked:
            continue
        if url in seen:
            continue
        seen.add(url)
        results.append({'url':url,'title':plain_text(title),'parent_url':parent,
                        'returned_href':target,'evidence_field':field})
    return results


def _job_postings(value):
    if isinstance(value,list):
        for entry in value:
            yield from _job_postings(entry)
    elif isinstance(value,dict):
        kinds = value.get('@type',[])
        if isinstance(kinds,str):
            kinds = [kinds]
        if any(str(kind).rsplit('/',1)[-1] == 'JobPosting' for kind in kinds):
            yield value
        for key,entry in value.items():
            if key != '@type' and isinstance(entry,(dict,list)):
                yield from _job_postings(entry)


def _location_parts(value):
    if isinstance(value,list):
        return [part for entry in value for part in _location_parts(entry)]
    if isinstance(value,dict):
        if 'address' in value:
            return _location_parts(value['address'])
        return [part for key in ('streetAddress','addressLocality','addressRegion','postalCode','addressCountry','name')
                if key in value for part in _location_parts(value[key])]
    return [plain_text(value)] if value else []


def _singapore_location(value):
    parts = _location_parts(value)
    if not any(re.search(r'\bSingapore\b',part,re.I) or part.upper() == 'SG' for part in parts):
        return None
    return ', '.join(dict.fromkeys('Singapore' if part.upper() == 'SG' else part for part in parts))


def _text_label(text, labels):
    values = list(dict.fromkeys(value.strip(' *\t') for value in
                  re.findall(r'(?im)^\s*(?:[-*#]\s*)?(?:'+labels+r')\s*[:：]\s*([^\n]+)',text)))
    return values[0] if len(values) == 1 else None


def career_vacancy(item, checked_at):
    """Promote one supported vacancy; landing pages and ambiguity stay leads.

    JSON-LD JobPosting is read from documented `metadata.jsonLd` or `html`. The text fallback needs
    an explicit role, employer, job location and a vacancy-description section;
    page metadata, a search query and a Singapore footer cannot supply them.
    """
    if not isinstance(item,dict):
        return None
    crawl = item.get('crawl') if isinstance(item.get('crawl'),dict) else {}
    if isinstance(crawl.get('httpStatusCode'),int) and crawl['httpStatusCode'] >= 400:
        return None
    try:
        url = canonical_url(item.get('url') or _page_url(item))
    except AccessBlocked:
        return None
    parser = _crawler_html(item)
    metadata = item.get('metadata') if isinstance(item.get('metadata'),dict) else {}
    postings = list(_job_postings(metadata.get('jsonLd')))
    structured_field = 'metadata.jsonLd' if postings else 'html'
    if not postings:
        postings = list(_job_postings(parser.json_ld))
    # Some employers repeat the same structured node in several script tags.
    postings = list({json.dumps(posting,sort_keys=True,ensure_ascii=False):posting for posting in postings}.values())
    if len(postings) > 1:
        return None
    raw = {'source':NAMES['careers'],'url':url,'returned_url':item.get('url'),
           'returned_text':copy.deepcopy(item.get('text')),
           'returned_crawl':copy.deepcopy(item.get('crawl'))}
    if postings:
        posting = postings[0]
        company = posting.get('hiringOrganization')
        if isinstance(company,dict):
            company = company.get('name')
        location = _singapore_location(posting.get('jobLocation'))
        if not location and posting.get('jobLocationType') == 'TELECOMMUTE':
            location = _singapore_location(posting.get('applicantLocationRequirements'))
        raw.update(title=plain_text(posting.get('title')),company=plain_text(company),
                   location=location,description=posting.get('description'))
        raw['extraction_evidence'] = {'format':'schema.org/JobPosting','field':structured_field,'record':copy.deepcopy(posting)}
        identifier = posting.get('identifier')
        if isinstance(identifier,dict):
            identifier = identifier.get('value')
        if identifier is not None and isinstance(identifier,(str,int)):
            # Employer requisition numbers are not globally unique, including
            # employers sharing an ATS host. Keep the original beside its scope.
            raw['id'] = urlsplit(url).hostname + ':' + raw['company'].casefold() + ':' + str(identifier)
            raw['original_source_id'] = identifier
        for source,destination in [('datePosted','posted_date'),('validThrough','expiry_date'),
                                   ('employmentType','employment_type'),('qualifications','requirements')]:
            if posting.get(source) is not None:
                raw[destination] = copy.deepcopy(posting[source])
        if posting.get('jobLocationType') == 'TELECOMMUTE':
            raw['work_arrangement'] = 'Remote'
    else:
        text = item.get('text') if isinstance(item.get('text'),str) else plain_text(item.get('html'))
        # Markdown formatting can hide label separators but does not add facts.
        labelled = re.sub(r'\*\*|__','',text)
        title = _text_label(labelled,r'job title|role|position(?: title)?')
        if not title and len(parser.headings) == 1:
            title = parser.headings[0]
        company = _text_label(labelled,r'employer|company(?: name)?|hiring org(?:anization|anisation)')
        location = _singapore_location(_text_label(labelled,r'(?:job |work |office )?location|based in'))
        description = re.search(r'(?im)^\s*(?:#{1,6}\s*)?(?:job description|(?:key |your |job )?responsibilities|what you(?: will|\'ll) do|about (?:the |this )?role)\s*:?\s*(?:\n|$)',labelled)
        if not description or len(plain_text(labelled[description.end():])) < 40:
            return None
        raw.update(title=title,company=company,location=location,description=text)
        raw['extraction_evidence'] = {'format':'explicit page fields','field':'text',
                                      'title':title,'company':company,'location':location}
        for labels,destination in [(r'(?:date )?posted|posting date','posted_date'),
                                    (r'employment type|job type','employment_type'),
                                    (r'requisition (?:id|number)|job (?:id|reference)','original_source_id')]:
            value = _text_label(labelled,labels)
            if value:
                raw[destination] = value
        if raw.get('original_source_id'):
            raw['id'] = urlsplit(url).hostname + ':' + str(raw.get('company') or '').casefold() + ':' + raw['original_source_id']
    if (not raw.get('title') or not raw.get('company') or not raw.get('location')
            or not plain_text(raw.get('description'))
            or re.fullmatch(r'(?:careers?|jobs?|vacancies|open positions|job opportunities|join us)',raw['title'],re.I)):
        return None
    raw['verified_at'] = checked_at
    raw['employment_type_verified'] = bool(raw.get('employment_type'))
    return raw


def normalize(source, item, checked_at):
    """Only source-provided fields; caller retains the exact item separately."""
    if source == 'careers':
        return career_vacancy(item,checked_at)
    if source not in ('linkedin','indeed'):
        return None
    mappings = {'linkedin':{'id':['id','jobId'],'title':['title'],'company':['companyName'],
                           'url':['link','url','jobUrl'],'description':['descriptionText','description'],
                           'location':['location'],'employment_type':['employmentType'],'posted_date':['postedAt','postedDate']},
                'indeed':{'id':['id','jobKey'],'title':['positionName','jobTitle','title'],'company':['company','companyName'],
                          'url':['url','jobUrl'],'description':['description','jobDescriptionText'],
                          'location':['location'],'employment_type':['jobType','jobTypes'],'posted_date':['postingDateParsed','postedAt','datePublished']}}
    raw = {'source':NAMES[source]}
    for field, aliases in mappings[source].items():
        for alias in aliases:
            if alias in item and item[alias] is not None:
                value = item[alias]
                if field in ('company','location') and isinstance(value,dict):
                    value = value.get('name') or value.get('formattedAddress')
                if value is not None:
                    raw[field] = value
                break
    if not raw.get('title') or not raw.get('url'):
        return None
    try:
        raw['url'] = canonical_url(raw['url'])
    except AccessBlocked:
        return None
    # Search filters aren't location evidence. Unclear/off-market records remain
    # leads until an actual Singapore listing supplies supporting evidence.
    if 'singapore' not in plain_text(raw.get('location')).lower():
        return None
    if raw.get('description'):
        raw['verified_at'] = checked_at
    else:
        raw['description_incomplete'] = True
    for field in ('requirements','salary','salaryCurrency','salaryType'):
        if field in item and item[field] is not None:
            raw[field] = copy.deepcopy(item[field])
    if isinstance(item.get('salary'),str) and item['salary'].strip():
        raw['advertised_salary'] = item['salary']
    raw['employment_type_verified'] = bool(raw.get('employment_type'))
    if item.get('isExpired') is True:
        raw['status'] = 'expired'
    return raw


def merge_job(raw, old, now):
    jid = old['id'] if old else 'SG-CAM-' + hashlib.sha256((raw['source']+'|'+str(raw.get('id') or source_key(raw['url']))).encode()).hexdigest()[:20]
    job = build_job(raw,jid)
    job['discovered_at'] = old.get('discovered_at') if old else now
    if old:
        job['url'] = old.get('url') or job['url']
        retained_sources = copy.deepcopy(old.get('sources',[]))
        for source in job['sources']:
            if not any((s.get('name'),s.get('source_id'),s.get('url'))==(source.get('name'),source.get('source_id'),source.get('url')) for s in retained_sources):
                retained_sources.append(source)
        job['sources'] = retained_sources
        for field, raw_field in [('description','description'),('source_requirements','requirements'),('company','company'),('location','location'),('employment_type','employment_type'),('posted_at','posted_date'),('salary','salary'),('deadline','expiry_date')]:
            if raw_field not in raw:
                job[field] = copy.deepcopy(old.get(field))
                job.setdefault('field_provenance',{})[field] = copy.deepcopy(old.get('field_provenance',{}).get(field,{}))
                if field == 'description':
                    job['description_complete'] = old.get('description_complete',False)
                if field == 'source_requirements':
                    job['source_requirement_evidence'] = copy.deepcopy(old.get('source_requirement_evidence'))
                    job['field_provenance']['requirements'] = copy.deepcopy(old.get('field_provenance',{}).get('requirements',{}))
        if not raw.get('verified_at'):
            job['verification'] = {**old.get('verification',{}),'last_attempt_at':now,'status':'degraded','last_error':'The latest response omitted vacancy text.'}
        if old.get('status') in ('closed','expired','unavailable') and not raw.get('verified_at'):
            job['status'] = old['status']
    job.pop('raw_evidence',None)
    return job


def relevant_career_url(url, evidence=''):
    try:
        url = canonical_url(url)
    except AccessBlocked:
        return False
    p = urlsplit(url)
    if p.hostname == 'cultjobs.com' or p.hostname.endswith('.cultjobs.com'):
        return False
    if re.search(r'\.(pdf|docx?|xlsx?|zip|png|jpe?g|mp4|mp3)(?:$|\?)',url,re.I):
        return False
    return bool(re.search(r'career|vacanc|/jobs?(?:/|\?|$)|job[-_]?detail|requisition|/positions?(?:/|\?|$)|/openings?(?:/|\?|$)|recruit|join[-_/]?us|work[-_/]?with',p.path+' '+p.hostname+' '+evidence,re.I))
