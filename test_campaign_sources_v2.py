"""Isolated regressions for corrected policy and documented crawler evidence."""
import copy
import json
import unittest
from unittest.mock import patch

import campaign_sources as sources


NOW = '2026-10-24T03:00:00+00:00'
DESCRIPTION = '<h2>Responsibilities</h2><p>Manage social media content and monthly analytics.</p><h2>Requirements</h2><p>Degree in Marketing.</p>'


def posting_item(**changes):
    posting = {'@context':'https://schema.org','@type':'JobPosting',
               'title':'Marketing Executive','hiringOrganization':{'@type':'Organization','name':'Example Employer'},
               'jobLocation':{'@type':'Place','address':{'addressLocality':'Singapore','addressCountry':'SG'}},
               'description':DESCRIPTION,'identifier':{'@type':'PropertyValue','value':'MKT-42'},
               'datePosted':'2026-10-22','employmentType':'FULL_TIME'}
    posting.update(changes)
    return {'url':'https://example.org/jobs/42?utm_source=google',
            'crawl':{'loadedUrl':'https://example.org/jobs/42','loadedTime':NOW,'depth':0},
            'text':'Marketing Executive\nExact returned  text.\n\nResponsibilities\nManage social media.',
            'html':'<html><script type="application/ld+json">'+json.dumps(posting)+'</script></html>',
            'markdown':'# Marketing Executive\n[Other careers](/careers)'}


class CorrectedSourcePolicyTests(unittest.TestCase):
    def test_canonicalization_does_not_recreate_network_gates(self):
        with patch('socket.getaddrinfo',side_effect=AssertionError('No DNS admission')):
            for url in ('http://127.0.0.1:8000/jobs','http://[::1]:8080/jobs',
                        'http://10.1.2.3/jobs','http://localhost/jobs','http://host.internal:8888/jobs',
                        'https://example.org:8443/jobs','https://name:pass@example.org/jobs'):
                with self.subTest(url=url):
                    self.assertEqual(sources.canonical_url(url),url)
        self.assertFalse(hasattr(sources,'check_robots'))
        self.assertFalse(hasattr(sources,'public_addresses'))
        self.assertFalse(hasattr(sources,'public_get'))
        self.assertEqual(sources.canonical_url('https://EXAMPLE.org:443/jobs?utm_source=google&id=42#apply'),
                         'https://example.org/jobs?id=42')

    def test_canonicalization_still_rejects_non_url_values(self):
        for value in (None,'javascript:alert(1)','/relative','https://','https://example.org/bad path'):
            with self.subTest(value=value), self.assertRaises(sources.AccessBlocked):
                sources.canonical_url(value)

    def test_crawler_uses_documented_bounded_output_settings(self):
        payload = sources.input_for('careers',['http://localhost:8000/careers','http://localhost:8000/jobs/42'])
        sources.validate_input('careers',payload)
        self.assertFalse(payload['respectRobotsTxtFile'])
        self.assertEqual(payload['maxCrawlDepth'],0)
        self.assertEqual(payload['maxCrawlPages'],2)
        self.assertEqual(payload['maxResults'],2)
        self.assertTrue(payload['saveHtml'])
        self.assertTrue(payload['saveMarkdown'])
        self.assertFalse(payload['saveFiles'])
        self.assertFalse(payload['summarize'])
        self.assertEqual(payload['htmlTransformer'],'none')
        with self.assertRaises(ValueError):
            sources.input_for('careers',['https://example.org/jobs','https://other.org/jobs'])
        with self.assertRaises(ValueError):
            sources.input_for('careers',['https://example.org/jobs/'+str(n) for n in range(51)])

    def test_google_batch_accepts_twenty_distinct_queries(self):
        payload = sources.input_for('google','\n'.join('Singapore role '+str(n) for n in range(20)))
        sources.validate_input('google',payload)
        self.assertEqual(payload['maxPagesPerQuery'],3)
        self.assertFalse(payload['websiteContentScraper']['enable'])
        payload['queries'] += '\nSingapore role 20'
        with self.assertRaises(ValueError):
            sources.validate_input('google',payload)


class CareerEvidenceTests(unittest.TestCase):
    def test_native_metadata_json_ld_is_preferred_and_duplicate_tags_deduplicate(self):
        item = posting_item()
        posting = json.loads(item['html'].split('application/ld+json">')[1].split('</script>')[0])
        item['metadata'] = {'jsonLd':[{'@graph':[posting]},posting]}
        item['html'] = '<h1>Marketing Executive</h1>'
        raw = sources.normalize('careers',item,NOW)
        self.assertEqual(raw['extraction_evidence']['field'],'metadata.jsonLd')
        self.assertEqual(raw['extraction_evidence']['record'],posting)
        self.assertEqual(raw['title'],'Marketing Executive')

    def test_json_ld_preserves_returned_text_dates_and_identifier(self):
        item = posting_item()
        original = copy.deepcopy(item)
        raw = sources.normalize('careers',item,NOW)
        self.assertEqual(raw['title'],'Marketing Executive')
        self.assertEqual(raw['company'],'Example Employer')
        self.assertEqual(raw['location'],'Singapore')
        self.assertEqual(raw['description'],DESCRIPTION)
        self.assertEqual(raw['returned_text'],item['text'])
        self.assertEqual(raw['returned_crawl'],item['crawl'])
        self.assertEqual(raw['original_source_id'],'MKT-42')
        self.assertEqual(raw['id'],'example.org:example employer:MKT-42')
        self.assertEqual(raw['posted_date'],'2026-10-22')
        self.assertEqual(raw['verified_at'],NOW)
        self.assertEqual(item,original)
        old = sources.merge_job(raw,None,NOW)
        merged = sources.merge_job(raw,old,'2026-10-25T03:00:00+00:00')
        self.assertEqual(merged['id'],old['id'])
        self.assertEqual(merged['discovered_at'],NOW)
        self.assertEqual(merged['posted_at'],'2026-10-22')

    def test_required_vacancy_facts_cannot_come_from_search_or_footer(self):
        for changes in ({'title':None},{'hiringOrganization':None},{'description':None},
                        {'jobLocation':None},{'jobLocation':{'address':{'addressCountry':'US'}}}):
            item = posting_item(**changes)
            item['text'] += '\nSingapore office. Careers opportunities.'
            item['metadata'] = {'title':'Marketing Executive | Example Employer Singapore'}
            with self.subTest(changes=changes):
                self.assertIsNone(sources.normalize('careers',item,NOW))

    def test_multiple_postings_remain_ambiguous_lead(self):
        item = posting_item()
        item['html'] += item['html'].replace('Marketing Executive','Sales Executive')
        self.assertIsNone(sources.normalize('careers',item,NOW))

    def test_failed_returned_page_does_not_refresh_vacancy(self):
        item = posting_item()
        item['crawl']['httpStatusCode'] = 403
        self.assertIsNone(sources.normalize('careers',item,NOW))

    def test_remote_location_requires_explicit_singapore_eligibility(self):
        item = posting_item(jobLocation=None,jobLocationType='TELECOMMUTE',
                            applicantLocationRequirements={'@type':'Country','name':'Singapore'})
        raw = sources.normalize('careers',item,NOW)
        self.assertEqual(raw['location'],'Singapore')
        self.assertEqual(raw['work_arrangement'],'Remote')
        item = posting_item(jobLocation=None,jobLocationType='TELECOMMUTE')
        self.assertIsNone(sources.normalize('careers',item,NOW))

    def test_explicit_page_fields_promote_without_inferred_employer(self):
        text = ('Job title: Social Media Executive\nEmployer: Returned Company\nLocation: Singapore\n'
                'Date posted: 23 October 2026\nJob ID: SM-2\nResponsibilities\n'
                'Create social media campaigns and report monthly campaign performance.\n'
                'Requirements\nDegree in marketing required.\n')
        item = {'url':'https://employer.org/positions/2','text':text}
        raw = sources.normalize('careers',item,NOW)
        self.assertEqual(raw['description'],text)
        self.assertEqual(raw['posted_date'],'23 October 2026')
        self.assertEqual(raw['id'],'employer.org:returned company:SM-2')
        item['text'] = text.replace('Employer: Returned Company\n','')
        item['metadata'] = {'title':'Social Media Executive at Returned Company'}
        self.assertIsNone(sources.normalize('careers',item,NOW))

    def test_landing_page_and_duplicate_role_labels_remain_leads(self):
        item = {'url':'https://example.org/careers','text':
                'Job title: Careers\nEmployer: Example\nLocation: Singapore\nResponsibilities\n'
                'Explore the opportunities across our international team and join us.'}
        self.assertIsNone(sources.normalize('careers',item,NOW))
        item['text'] = item['text'].replace('Job title: Careers','Job title: Marketing Executive\nJob title: Sales Executive')
        self.assertIsNone(sources.normalize('careers',item,NOW))

    def test_documented_markdown_and_html_links_use_loaded_parent(self):
        item = {'url':'https://example.org/old','crawl':{'loadedUrl':'https://example.org/careers/'},
                'html':'<a href="../jobs/42?utm_source=x">Marketing Executive</a><a href="/contact">Contact</a>',
                'markdown':'[Marketing](/jobs/42)\n[Regional (SG)](/jobs/role(SG))\n'
                           '[Opening][open]\n[open]: /positions/12 "Role"\n'
                           '<https://other.org/careers>\n[Section](#top)\n![Photo](/image.png)'}
        links = sources.extract_links(item)
        by_url = {entry['url']:entry for entry in links}
        self.assertEqual(len(links),5)
        self.assertEqual(by_url['https://example.org/jobs/42']['title'],'Marketing Executive')
        self.assertEqual(by_url['https://example.org/jobs/42']['parent_url'],'https://example.org/careers/')
        self.assertIn('https://example.org/jobs/role(SG)',by_url)
        self.assertIn('https://example.org/positions/12',by_url)
        self.assertIn('https://other.org/careers',by_url)
        self.assertTrue(sources.relevant_career_url('https://example.org/positions/12'))
        self.assertFalse(sources.relevant_career_url('https://example.org/careers/list.pdf'))

    def test_google_search_snippets_never_become_vacancies(self):
        item = {'organicResults':[{'title':'Marketing Executive','url':'https://example.org/jobs/42',
                                  'description':'Example Employer hiring in Singapore.'}]}
        self.assertIsNone(sources.normalize('google',item,NOW))

    def test_shared_ats_requisition_numbers_do_not_merge_employers(self):
        first = sources.normalize('careers',posting_item(),NOW)
        second = sources.normalize('careers',posting_item(hiringOrganization={'name':'Another Employer'}),NOW)
        self.assertNotEqual(first['id'],second['id'])
        self.assertEqual(first['original_source_id'],second['original_source_id'])


if __name__ == '__main__':
    unittest.main()
