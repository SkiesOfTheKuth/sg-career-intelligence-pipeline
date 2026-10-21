import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import requests

from collector_mycareersfuture import fetch_mycareersfuture, normalize_mcf_item
from evidence import build_job
from storage import Store
from sync_engine import synchronize_upstream_jobs


class SyncTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name) / "workspace.db").initialize()
        self.raw = {"id": "MCF-abc", "title": "Marketing Executive", "company": "Company", "source": "MyCareersFuture (Singapore Govt)",
                    "url": "https://www.mycareersfuture.gov.sg/job/abc", "description": "Original complete description",
                    "verified_at": "2026-10-01T00:00:00Z", "expiry_date": "2099-11-01", "status": "open"}
        self.store.upsert_jobs([build_job(self.raw, "SG-OPP-0042")])

    def tearDown(self):
        self.temp.cleanup()

    @patch("collector_mycareersfuture.fetch_mycareersfuture")
    def test_refresh_updates_existing_identity_and_closure(self, fetch):
        changed = dict(self.raw, description="Updated full source description", status="closed", verified_at="2026-10-21T12:00:00Z")
        fetch.return_value = {"jobs": [changed], "errors": [], "successes": [{}], "status": "success"}
        result = synchronize_upstream_jobs(store=self.store)
        self.assertEqual(result["added_count"], 0)
        self.assertEqual(result["updated_count"], 1)
        self.assertEqual(len(self.store.list_jobs()), 1)
        job = self.store.get_job("SG-OPP-0042")
        self.assertEqual(job["description"], changed["description"])
        self.assertEqual(job["status"], "closed")
        self.assertEqual(len(self.store.get_source_evidence(job["id"])), 1)

    @patch("collector_mycareersfuture.fetch_mycareersfuture")
    def test_failed_check_preserves_previous_successful_evidence(self, fetch):
        fetch.return_value = {"jobs": [], "errors": [{"source": "MCF", "attempted_at": "2026-10-21T12:00:00Z", "message": "timeout"}],
                              "successes": [], "status": "error"}
        result = synchronize_upstream_jobs(store=self.store)
        self.assertEqual(result["status"], "error")
        job = self.store.get_job("SG-OPP-0042")
        self.assertEqual(job["description"], self.raw["description"])
        self.assertEqual(job["verification"]["checked_at"], self.raw["verified_at"])
        self.assertEqual(job["verification"]["status"], "degraded")
        self.assertTrue(job["verification"]["needs_recheck"])
        self.assertEqual(job["status"], "open")
        self.assertEqual(self.store.get_sync_history()[0]["status"], "error")

    @patch("collector_mycareersfuture.fetch_mycareersfuture")
    def test_search_absence_neither_closes_nor_verifies_existing_job(self, fetch):
        fetch.return_value = {"jobs": [], "errors": [], "successes": [{}], "status": "success"}
        synchronize_upstream_jobs(store=self.store)
        job = self.store.get_job("SG-OPP-0042")
        self.assertEqual(job["status"], "open")
        self.assertEqual(job["verification"]["checked_at"], self.raw["verified_at"])

    @patch("collector_mycareersfuture.requests.get")
    def test_http_failure_is_not_a_successful_empty_collection(self, get):
        response = Mock()
        response.raise_for_status.side_effect = requests.HTTPError("503 unavailable")
        get.return_value = response
        report = fetch_mycareersfuture(["marketing"], return_report=True)
        self.assertEqual(report["status"], "error")
        self.assertEqual(report["successes"], [])
        self.assertTrue(report["errors"])
        with self.assertRaises(RuntimeError):
            fetch_mycareersfuture(["marketing"])

    @patch("collector_mycareersfuture.requests.get")
    def test_partial_source_failure_is_degraded(self, get):
        success, failed = Mock(), Mock()
        success.raise_for_status.return_value = None
        success.json.return_value = {"results": [{"uuid": "one", "title": "Marketing", "description": "Full source text"}]}
        failed.raise_for_status.side_effect = requests.Timeout("upstream timeout")
        get.side_effect = [success, failed]
        report = fetch_mycareersfuture(["marketing", "Thai"], limit_per_query=1, return_report=True)
        self.assertEqual(report["status"], "degraded")
        self.assertEqual(len(report["jobs"]), 1)
        self.assertEqual(len(report["errors"]), 1)

    def test_upstream_normalization_preserves_response_and_missing_facts(self):
        item = {"uuid": "one", "title": "Marketing", "description": "<p>" + "Full text " * 100 + "</p>"}
        job = normalize_mcf_item(item, "Thai")
        self.assertEqual(job["raw_response"], item)
        self.assertGreater(len(job["description"]), 350)
        self.assertIsNone(job["employment_type"])
        self.assertIsNone(job["work_arrangement"])
        self.assertEqual(job["requirements"], "")
        self.assertIsNone(job["salary_type"])


if __name__ == "__main__":
    unittest.main()
