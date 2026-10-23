"""Bounded actor contracts, public-URL admission and lossless normalization."""
import copy
import hashlib
import http.client
import ipaddress
import json
from pathlib import Path
import re
import socket
import ssl
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode, urljoin
from urllib.robotparser import RobotFileParser

from evidence import build_job, source_key, plain_text

CONTRACTS = json.loads((Path(__file__).parent / 'campaign_contracts.json').read_text(encoding='utf8'))
CORE = ['Thai', 'Marketing Executive', 'Social Media Executive', 'Public Relations']
HISTORICAL = ['Thai interpreter', 'Thailand market', 'Digital Marketing Executive', 'Influencer Marketing',
              'KOL Marketing', 'Corporate Communications Executive', 'Partnerships Executive',
              'Business Development Executive', 'Events Executive', 'Trade Show Coordinator',
              'Regional Marketing Executive', 'Market Research Executive']
NAMES = {'linkedin':'LinkedIn Jobs', 'indeed':'Indeed Singapore', 'google':'Google search leads', 'careers':'Career websites'}


class AccessBlocked(ValueError):
    pass


def canonical_url(value):
    if not isinstance(value, str) or len(value) > 4096 or re.search(r'[\x00-\x20\\]', value):
        raise AccessBlocked('Invalid URL')
    try:
        p = urlsplit(value)
        if p.scheme not in ('https','http') or not p.hostname or p.username or p.password or p.port not in (None,80,443):
            raise ValueError()
        host = p.hostname.encode('idna').decode('ascii').lower().rstrip('.')
        if host == 'localhost' or host.endswith(('.localhost','.local','.internal')) or '.' not in host:
            raise ValueError()
        try:
            if not ipaddress.ip_address(host).is_global:
                raise ValueError()
        except ValueError as e:
            if re.fullmatch(r'[\d.]+', host) or ':' in host:
                raise AccessBlocked('Private or malformed address') from e
        query = urlencode(sorted((k,v) for k,v in parse_qsl(p.query, keep_blank_values=True)
                                 if not k.lower().startswith('utm_') and k.lower() not in ('trk','trackingid','ref')))
        return urlunsplit((p.scheme, host, p.path or '/', query, ''))
    except (ValueError, UnicodeError) as e:
        raise AccessBlocked('Unsafe URL') from e


def public_addresses(host):
    addresses = sorted({x[4][0] for x in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)})
    if not addresses or any(not ipaddress.ip_address(a).is_global for a in addresses):
        raise AccessBlocked('Destination resolves to a non-public address')
    return addresses


def public_get(url, max_bytes=262144):
    """Resolve and pin each connection; revalidate every redirect before fetching.

    Native http.client avoids a second DNS lookup and environment HTTP proxies.
    No cookies, authorization, JavaScript or file downloads are used.
    """
    for _ in range(6):
        url = canonical_url(url)
        p = urlsplit(url)
        address = public_addresses(p.hostname)[0]
        port = 443 if p.scheme == 'https' else 80
        conn = http.client.HTTPConnection(p.hostname, port, timeout=15)
        sock = socket.create_connection((address, port), timeout=15)
        try:
            conn.sock = ssl.create_default_context().wrap_socket(sock, server_hostname=p.hostname) if p.scheme == 'https' else sock
            conn.request('GET', urlunsplit(('', '', p.path, p.query, '')),
                         headers={'Host':p.hostname,'User-Agent':'SGCareerCollector/1.0','Accept':'text/html,text/plain'})
            response = conn.getresponse()
            if response.status in (301,302,303,307,308):
                target = response.getheader('Location')
                if not target:
                    raise AccessBlocked('Redirect has no target')
                url = canonical_url(urljoin(url,target))
                continue
            body = response.read(max_bytes+1)
            if len(body) > max_bytes:
                raise AccessBlocked('Response exceeds the bounded inspection size')
            return url, response.status, body.decode('utf8',errors='replace')
        finally:
            conn.close()
            sock.close()
    raise AccessBlocked('Too many redirects')


def check_robots(url, fetch=public_get):
    url = canonical_url(url)
    p = urlsplit(url)
    try:
        _, status, text = fetch(urlunsplit((p.scheme,p.netloc,'/robots.txt','','')))
    except OSError as e:
        raise AccessBlocked('Source access check unavailable: '+type(e).__name__) from None
    if status in (404,410):
        return {'url':url, 'robots_status':status, 'allowed':True}
    if status != 200:
        raise AccessBlocked(f'Robots directives unavailable (HTTP {status})')
    parser = RobotFileParser()
    parser.parse(text.splitlines())
    if not parser.can_fetch('SGCareerCollector',url):
        raise AccessBlocked('Source robots directives disallow this path')
    delay = parser.crawl_delay('SGCareerCollector') or parser.crawl_delay('*')
    if delay:
        raise AccessBlocked('Source crawl-delay cannot be enforced by the selected actor')
    return {'url':url,'robots_status':status,'allowed':True,'robots_sha256':hashlib.sha256(text.encode()).hexdigest()}


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
        # Recursion belongs to our durable vetted queue, never a remote general
        # crawl. Each separately vetted page is depth 0 in the remote actor.
        return {'startUrls':[{'url':query}],'crawlerType':'cheerio','maxCrawlDepth':0,
                'maxCrawlPages':1,'maxResults':1,'respectRobotsTxtFile':True,
                'proxyConfiguration':{'useApifyProxy':False},'maxConcurrency':1,
                'maxRequestRetries':0,'maxSessionRotations':0,'saveFiles':False,
                'saveContentTypes':'','saveMarkdown':True,'saveHtml':False,
                'saveHtmlAsFile':False,'saveScreenshots':False,'summarize':False,
                'useSitemaps':False,'useLlmsTxt':False,'ignoreHttpsErrors':False}
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


def access_url(source, payload):
    if source == 'linkedin': return payload['urls'][0]
    if source == 'indeed': return 'https://sg.indeed.com/jobs?'+urlencode({'q':payload['position'],'l':'Singapore'})
    if source == 'google': return 'https://www.google.com/search?'+urlencode({'q':payload['queries']})
    return payload['startUrls'][0]['url']


def normalize(source, item, checked_at):
    """Only source-provided fields; caller retains the exact item separately."""
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
    return bool(re.search(r'career|vacanc|/jobs?(?:/|\?|$)|recruit|join[-_/]?us|work[-_/]?with',p.path+' '+p.hostname+' '+evidence,re.I))
