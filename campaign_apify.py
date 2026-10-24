"""Apify's documented REST API; credentials stay in native secret configuration."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
import time
import requests
from campaign_sources import CONTRACTS, validate_input


class ApiError(RuntimeError):
    def __init__(self, kind, status=None, detail=None):
        self.kind, self.status = kind, status
        super().__init__(f'Apify {kind}' + (f' (HTTP {status})' if status else '') + (': '+detail if detail else ''))


class Apify:
    def __init__(self, tokens=None):
        tokens = tokens if tokens is not None else json.loads(os.environ.get('APIFY_TOKENS_JSON','[]'))
        if not isinstance(tokens,list) or any(not isinstance(t,str) or not t for t in tokens):
            raise ValueError('APIFY_TOKENS_JSON must contain a JSON array of existing tokens')
        self.tokens = {hashlib.sha256(t.encode()).hexdigest():t for t in tokens}

    def request(self, reference, method, path, **kwargs):
        token = self.tokens.get(reference)
        if not token:
            raise ApiError('credential_unavailable')
        # Reads retry boundedly. Mutations never replay after an unclear response.
        for attempt in range(3 if method == 'GET' else 1):
            try:
                response = requests.request(method,'https://api.apify.com/v2/'+path,
                    headers={'Authorization':'Bearer '+token},timeout=(10,30),**kwargs)
            except requests.RequestException:
                if method == 'GET' and attempt < 2:
                    time.sleep(2**attempt)
                    continue
                raise ApiError('transient_read' if method == 'GET' else 'ambiguous_write') from None
            if response.status_code >= 400:
                kind = 'authentication' if response.status_code in (401,403) else 'exhausted' if response.status_code == 402 else 'input' if response.status_code in (400,422) else 'transient_read' if method == 'GET' else 'ambiguous_write'
                if method == 'GET' and response.status_code in (429,500,502,503,504) and attempt < 2:
                    time.sleep(2**attempt)
                    continue
                detail = None
                try:
                    error = response.json().get('error',{})
                    detail = str(error.get('type',''))+': '+str(error.get('message',''))
                    for secret in self.tokens.values():
                        detail = detail.replace(secret,'[redacted]')
                    import re
                    detail = re.sub(r'(?i)(token|authorization|password|api[_-]?key)([=: ]+)\S+',r'\1\2[redacted]',detail)[:1500]
                except (ValueError,AttributeError):
                    pass
                raise ApiError(kind,response.status_code,detail)
            try:
                return response.json()
            except ValueError:
                raise ApiError('invalid_response' if method == 'GET' else 'ambiguous_write') from None

    def snapshot(self, reference):
        me = self.request(reference,'GET','users/me')['data']
        limits = self.request(reference,'GET','users/me/limits')['data']
        usage = self.request(reference,'GET','users/me/usage/monthly')['data']
        # A configured spend limit isn't a balance. Verified included credits in
        # the current free plan establish the only usable capacity here. Unknown
        # promotions cannot enlarge it, and paying accounts are never admitted.
        included = me.get('plan',{}).get('monthlyUsageCreditsUsd')
        hard = limits['limits']['maxMonthlyUsageUsd']
        used = max(float(limits['current']['monthlyUsageUsd']),float(usage['totalUsageCreditsUsdAfterVolumeDiscount']))
        if included is None or me.get('isPaying') is not False or usage['usageCycle'] != limits['monthlyUsageCycle']:
            raise ApiError('credit_capacity_unverified')
        return {'account_id':me['id'],'reference':reference,'usage_usd':used,
                'limit_usd':min(float(hard),float(included)), 'cycle':usage['usageCycle'],
                'available':not me.get('isBanned',False) and limits['current']['activeActorJobCount']==0,
                'expiry':None, 'error':None}

    def snapshots(self):
        def one(ref):
            try: return self.snapshot(ref)
            except ApiError as e: return {'reference':ref,'error':str(e)}
        with ThreadPoolExecutor(max_workers=6) as pool:
            return list(pool.map(one,self.tokens))

    def contract(self, reference, source):
        expected = CONTRACTS[source]
        actor = self.request(reference,'GET','acts/'+expected['actor'])['data']
        build = self.request(reference,'GET','actor-builds/'+expected['build_id'])['data']
        schema = build.get('inputSchema')
        schema = json.loads(schema) if isinstance(schema,str) else schema
        if actor.get('isDeprecated') or build.get('buildNumber') != expected['build'] or schema != expected['schema']:
            raise ApiError('actor_contract_changed')
        pricing = actor.get('pricingInfos',[])[-1:] or [{'pricingModel':'PAY_PER_USAGE'}]
        if pricing != expected['pricing']:
            raise ApiError('actor_pricing_changed')
        return {'actor':expected['actor'],'build':expected['build'],'verified_at':time.time()}

    def launch(self, reference, batch, stops_at, now):
        payload = json.loads(batch['input_json'])
        validate_input(batch['source'],payload)
        remaining = int(stops_at - now) - 5
        if remaining < 1:
            raise ApiError('campaign_expired_before_launch')
        return self.request(reference,'POST','acts/'+CONTRACTS[batch['source']]['actor']+'/runs',
            params={'build':CONTRACTS[batch['source']]['build'], 'maxTotalChargeUsd':batch['reserved_units']/1e6,
                    'timeout':min(1800,remaining),'restartOnError':'false','waitForFinish':0},json=payload)['data']

    def run(self, reference, run_id):
        return self.request(reference,'GET','actor-runs/'+run_id)['data']

    def abort(self, reference, run_id):
        return self.request(reference,'POST','actor-runs/'+run_id+'/abort')['data']

    def reconcile(self, reference, batch):
        # An absent or multiple match never authorizes a retry. The commitment
        # remains blocked. Compare stored INPUT, actor, time and charge cap.
        from evidence import parse_date
        matches = []
        for offset in range(0,1000,100):
            page = self.request(reference,'GET','actor-runs',params={'limit':100,'offset':offset,'desc':'true'})['data']
            for run in page['items']:
                started = parse_date(run.get('startedAt'))
                if not started or not batch['reserved_at']-5 <= started.timestamp() <= batch['reserved_at']+120:
                    continue
                if run.get('actId') != CONTRACTS[batch['source']]['actor_id']:
                    continue
                full = self.run(reference,run['id'])
                if full.get('options',{}).get('maxTotalChargeUsd') != batch['reserved_units']/1e6:
                    continue
                payload = self.request(reference,'GET','key-value-stores/'+full['defaultKeyValueStoreId']+'/records/INPUT')
                if payload == json.loads(batch['input_json']):
                    matches.append(full)
            if len(page['items']) < 100:
                break
        return matches[0] if len(matches)==1 else None

    def items(self, reference, dataset, offset):
        result = self.request(reference,'GET','datasets/'+dataset+'/items',params={'offset':offset,'limit':25,'clean':'false','format':'json'})
        if not isinstance(result,list):
            raise ApiError('invalid_dataset_response')
        return result
