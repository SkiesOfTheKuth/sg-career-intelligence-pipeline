"""Regressions for retained source fields and application import history."""
from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from evidence import build_job, present_job
from storage import Store
from sync_engine import synchronize_upstream_jobs
from collector_mycareersfuture import normalize_mcf_item
from source_audit import redacted


class PreservationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'workspace.db'
        self.store = Store(self.path).initialize()
        self.raw = {'id': 'MCF-jp', 'title': 'Marketing Executive', 'company': 'Example',
                    'source': 'MyCareersFuture (Singapore Govt)',
                    'url': 'https://www.mycareersfuture.gov.sg/job/jp',
                    'description': 'Responsibilities\nManage social media campaigns and analyze campaign performance.',
                    'requirements': 'Japanese language proficiency is required.',
                    'requirements_evidence': [{'field': 'requirements', 'quote': 'Japanese language proficiency is required.'}],
                    'verified_at': '2026-10-01T00:00:00Z'}

    def refresh(self, raw):
        report = {'jobs': [raw], 'errors': [], 'successes': [], 'status': 'success'}
        with patch('collector_mycareersfuture.fetch_mycareersfuture', return_value=report):
            result = synchronize_upstream_jobs(store=self.store)
        self.assertEqual(result['status'], 'success')
        return present_job(Store(self.path).get_job('SG-OPP-0042'))

    def test_roundtrip_partial_response_retains_explicit_requirement_and_dates(self):
        original = build_job(self.raw, 'SG-OPP-0042')
        self.store.upsert_jobs([original])
        partial = {key: value for key, value in self.raw.items()
                   if key not in ('description', 'requirements', 'requirements_evidence')}
        partial['verified_at'] = '2026-10-21T00:00:00Z'
        current = self.refresh(partial)
        self.assertIn('Japanese language proficiency is required.', current['requirements']['mandatory'])
        self.assertEqual(current['source_requirements'], self.raw['requirements'])
        self.assertEqual(current['source_requirement_evidence'], self.raw['requirements_evidence'])
        self.assertEqual(current['assessment']['fit'], original['assessment']['fit'])
        self.assertEqual(current['assessment']['score']['value'], original['assessment']['score']['value'])
        self.assertEqual(current['verification']['last_success_at'], partial['verified_at'])
        for field in ('description', 'requirements'):
            self.assertEqual(current['field_provenance'][field], original['field_provenance'][field])

    def test_new_description_does_not_erase_omitted_explicit_requirements(self):
        original = build_job(self.raw, 'SG-OPP-0042')
        self.store.upsert_jobs([original])
        changed = {key: value for key, value in self.raw.items() if key not in ('requirements', 'requirements_evidence')}
        changed.update(description='Responsibilities\nManage social media campaigns.', verified_at='2026-10-21T00:00:00Z')
        current = self.refresh(changed)
        self.assertEqual(current['description'], changed['description'])
        self.assertIn('Japanese language proficiency is required.', current['requirements']['mandatory'])
        self.assertEqual(current['field_provenance']['requirements'], original['field_provenance']['requirements'])
        self.assertNotEqual(current['field_provenance']['description'], original['field_provenance']['description'])

    def test_partial_listing_preserves_omitted_employer_facts(self):
        raw = {**self.raw, 'employment_type': 'Full-time', 'employment_type_verified': True,
               'salary_min': 4000, 'salary_max': 5000, 'salary_type': 'Monthly',
               'structured_salary_verified': True, 'advertised_salary': 'SGD 4000 - 5000 / month',
               'location': 'Singapore', 'expiry_date': '2099-12-01'}
        original = build_job(raw, 'SG-OPP-0042')
        self.store.upsert_jobs([original])
        current = self.refresh({'title': raw['title'], 'url': raw['url'], 'source': raw['source'],
                                'verified_at': '2026-10-21T00:00:00Z'})
        for field in ('company', 'employment_type', 'employment_types', 'salary', 'location', 'deadline'):
            self.assertEqual(current[field], original[field], field)

    def test_explicit_empty_fields_replace_old_facts_while_omitted_fields_remain(self):
        raw = {**self.raw, 'employment_type': 'Full-time', 'employment_type_verified': True,
               'location': 'Singapore', 'expiry_date': '2099-12-01'}
        self.store.upsert_jobs([build_job(raw, 'SG-OPP-0042')])
        item = {'uuid': 'jp', 'title': raw['title'], 'metadata': {'jobDetailsUrl': raw['url'], 'expiryDate': None},
                'description': '', 'requirements': '', 'employmentTypes': [], 'addresses': []}
        current = self.refresh(normalize_mcf_item(item, checked_at='2026-10-22T00:00:00Z'))
        self.assertEqual(current['description'], '')
        self.assertEqual(current['source_requirements'], '')
        self.assertEqual(current['requirements']['mandatory'], [])
        self.assertEqual(current['employment_types'], [])
        self.assertIsNone(current['location'])
        self.assertIsNone(current['deadline'])
        self.assertEqual(current['company'], raw['company'])
        self.assertIsNone(current['assessment']['score']['value'])

    def test_same_source_uuid_with_new_slug_preserves_workspace_identity_and_url(self):
        raw = {**self.raw, 'uuid': 'jp'}
        self.store.upsert_jobs([build_job(raw, 'SG-OPP-0042')])
        changed = {**raw, 'url': 'https://www.mycareersfuture.gov.sg/job/new-title-jp',
                   'description': 'Responsibilities\nManage campaigns.', 'verified_at': '2026-10-22T00:00:00Z'}
        current = self.refresh(changed)
        self.assertEqual(self.store.count_jobs(), 1)
        self.assertEqual(current['description'], changed['description'])
        self.assertEqual(current['url'], raw['url'])
        self.assertEqual(current['sources'][0]['url'], changed['url'])

    def test_refreshed_description_replaces_derived_work_arrangement(self):
        initial = normalize_mcf_item({'uuid': 'jp', 'title': self.raw['title'],
                                     'description': 'Responsibilities\nManage social media.\nFully remote working.'},
                                    checked_at='2026-10-01T00:00:00Z')
        self.store.upsert_jobs([build_job(initial, 'SG-OPP-0042')])
        changed = normalize_mcf_item({'uuid': 'jp', 'title': self.raw['title'],
                                     'description': 'Responsibilities\nManage social media.\nThis position works on-site at our office.'},
                                    checked_at='2026-10-22T00:00:00Z')
        current = self.refresh(changed)
        self.assertIsNone(current['work_arrangement'])
        self.assertNotEqual(current['field_provenance']['work_arrangement'].get('checked_at'), initial['verified_at'])

    def test_description_omission_retains_derived_arrangement_and_its_evidence(self):
        initial = normalize_mcf_item({'uuid': 'jp', 'title': self.raw['title'],
                                     'description': 'Responsibilities\nManage social media.\nFully remote working.'},
                                    checked_at='2026-10-01T00:00:00Z')
        original = build_job(initial, 'SG-OPP-0042')
        self.store.upsert_jobs([original])
        partial = normalize_mcf_item({'uuid': 'jp', 'title': self.raw['title']},
                                    checked_at='2026-10-22T00:00:00Z')
        current = self.refresh(partial)
        self.assertEqual(current['work_arrangement'], original['work_arrangement'])
        self.assertEqual(current['field_provenance']['work_arrangement'], original['field_provenance']['work_arrangement'])

    def test_new_description_preserves_omitted_explicit_arrangement(self):
        original = build_job({**self.raw, 'work_arrangement': 'Hybrid, two days at the office'}, 'SG-OPP-0042')
        self.store.upsert_jobs([original])
        partial = normalize_mcf_item({'uuid': 'jp', 'title': self.raw['title'],
                                     'description': 'Responsibilities\nManage social media.'},
                                    checked_at='2026-10-22T00:00:00Z')
        current = self.refresh(partial)
        self.assertEqual(current['work_arrangement'], original['work_arrangement'])
        self.assertEqual(current['field_provenance']['work_arrangement'], original['field_provenance']['work_arrangement'])

    def test_failed_job_commit_does_not_leave_new_source_payloads(self):
        self.store.upsert_jobs([build_job(self.raw, 'SG-OPP-0042')])
        before = self.store.get_job('SG-OPP-0042')
        with closing(sqlite3.connect(self.path)) as connection:
            connection.execute("CREATE TRIGGER fail_job_update BEFORE UPDATE ON jobs BEGIN SELECT RAISE(ABORT, 'isolated failure'); END")
        report = {'jobs': [{**self.raw, 'description': 'New evidence'}], 'errors': [], 'successes': [], 'status': 'success'}
        with patch('collector_mycareersfuture.fetch_mycareersfuture', return_value=report):
            result = synchronize_upstream_jobs(store=self.store)
        self.assertEqual(result['status'], 'error')
        self.assertEqual(self.store.get_job('SG-OPP-0042'), before)
        self.assertEqual(self.store.get_source_evidence('SG-OPP-0042'), [])

    def test_omitted_description_keeps_derived_thai_classification(self):
        raw = {**self.raw, 'description': 'Responsibilities\nManage campaigns.\nRequirements\nThai fluency is required.', 'requirements': ''}
        original = build_job(raw, 'SG-OPP-0042')
        self.store.upsert_jobs([original])
        current = self.refresh({key: value for key, value in raw.items() if key != 'description'})
        self.assertEqual(current['thai_relevance'], original['thai_relevance'])

    def test_audit_redacts_hyphenated_and_spaced_credential_keys(self):
        value = {'headers': {'X-API-Key': 'private-value'}, 'nested': [{'access key': 'private-value'}], 'title': 'Role'}
        safe = redacted(value)
        self.assertEqual(safe['headers']['X-API-Key'], '[redacted]')
        self.assertEqual(safe['nested'][0]['access key'], '[redacted]')
        self.assertEqual(safe['title'], 'Role')

    def test_resolved_import_history_retains_original_and_resolution(self):
        self.store.put_application('role', {'expected_revision': 0, 'notes': 'Server note', 'stage': 'Applied'})
        result = self.store.import_applications({'role': {'notes': 'Original browser note', 'status': 'Ready'}})
        conflict_id = result['conflicts'][0]['id']
        self.store.put_application('role', {'expected_revision': 2, 'notes': 'Merged note',
                                          'resolve_import_conflicts': [conflict_id]})
        history = Store(self.path).get_application_history('role', 0, 25)
        retained = next(item for item in history['items'] if item['type'] == 'import_version')
        self.assertEqual(retained['incoming']['original']['notes'], 'Original browser note')
        self.assertEqual(retained['incoming']['application']['stage'], 'Preparing')
        self.assertEqual(retained['resolution']['notes'], 'Merged note')
        self.assertEqual(retained['resolution']['stage'], 'Applied')
        self.assertTrue(retained['resolved_at'])
        self.assertEqual(self.store.get_application('role')['import_conflicts'], [])
        self.assertEqual(self.store.get_application_history('role', 0, 1)['total'], history['total'])
        self.assertEqual(len(self.store.get_application_history('role', 0, 1)['items']), 1)

    def test_v1_migration_backfills_from_retained_payload_without_rewriting_it(self):
        legacy = build_job(self.raw, 'SG-OPP-0042')
        for key in ('source_requirements', 'source_requirement_evidence', 'field_provenance', 'raw_evidence'):
            legacy.pop(key, None)
        self.store.upsert_jobs([legacy])
        self.store.record_source_evidence(legacy['id'], self.raw['source'], self.raw)
        before = self.store.get_source_evidence(legacy['id'])
        with closing(sqlite3.connect(self.path)) as connection:
            connection.execute('PRAGMA user_version = 1')
        migrated = Store(self.path).initialize()
        job = migrated.get_job(legacy['id'])
        self.assertEqual(job['source_requirements'], self.raw['requirements'])
        self.assertEqual(job['source_requirement_evidence'], self.raw['requirements_evidence'])
        self.assertEqual(migrated.get_source_evidence(legacy['id']), before)
        manifest = migrated.verify_database(self.path)
        migrated.initialize()
        self.assertEqual(manifest, migrated.verify_database(self.path))
        with closing(sqlite3.connect(self.path)) as connection:
            self.assertGreaterEqual(connection.execute('PRAGMA user_version').fetchone()[0], 2)

    def test_migration_content_provenance_matches_retained_text_not_latest_payload(self):
        legacy = build_job(self.raw, 'SG-OPP-0042')
        for key in ('source_requirements', 'source_requirement_evidence', 'field_provenance', 'raw_evidence'):
            legacy.pop(key, None)
        legacy['retained_requirements_source'] = self.raw['requirements']
        self.store.upsert_jobs([legacy])
        old_id = self.store.record_source_evidence(legacy['id'], self.raw['source'], self.raw)
        self.store.record_source_evidence(legacy['id'], self.raw['source'],
            {**self.raw, 'description': 'Different source version', 'requirements': 'Different requirement',
             'verified_at': '2026-10-21T00:00:00Z'})
        with closing(sqlite3.connect(self.path)) as connection:
            connection.execute('PRAGMA user_version = 1')
        job = Store(self.path).initialize().get_job(legacy['id'])
        for field in ('description', 'requirements'):
            self.assertEqual(job['field_provenance'][field]['checked_at'], self.raw['verified_at'])
            self.assertEqual(job['field_provenance'][field]['evidence_id'], old_id)


if __name__ == '__main__':
    unittest.main()
