import unittest
import base64
import json
import os
import openpyxl
from fastapi.testclient import TestClient

from app import app, sanitize_url, load_jobs
from generate_workbook import sanitize_cell, HEADERS

class CareerIntelligenceAuditTestSuite(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        cls.valid_user = "Kawa"
        cls.valid_pass = "Kawa123"
        cls.auth_header = {
            "Authorization": "Basic " + base64.b64encode(f"{cls.valid_user}:{cls.valid_pass}".encode()).decode()
        }
        cls.bad_auth_header = {
            "Authorization": "Basic " + base64.b64encode(b"Kawa:WrongPassword").decode()
        }

    # =========================================================================
    # 1. AUTHENTICATION & ACCESS CONTROL TESTS
    # =========================================================================
    def test_01_unauthenticated_request_rejected(self):
        """Verify that all public access without credentials is unconditionally rejected with 401."""
        endpoints = ["/", "/api/jobs", "/api/stats", "/api/top25", "/download/excel", "/download/csv"]
        for ep in endpoints:
            res = self.client.get(ep)
            self.assertEqual(res.status_code, 401, f"Endpoint {ep} should require authentication!")
            self.assertIn("WWW-Authenticate", res.headers)
            self.assertIn("Basic", res.headers["WWW-Authenticate"])

    def test_02_invalid_credentials_rejected(self):
        """Verify that incorrect credentials fail with 401."""
        res = self.client.get("/", headers=self.bad_auth_header)
        self.assertEqual(res.status_code, 401)
        self.assertIn("Invalid username or password", res.text)

    def test_03_authenticated_access_succeeds(self):
        """Verify that valid credentials (Kawa / Kawa123) successfully access all routes."""
        res_home = self.client.get("/", headers=self.auth_header)
        self.assertEqual(res_home.status_code, 200)
        self.assertIn("Authenticated as: <strong>Kawa</strong>", res_home.text)

        res_stats = self.client.get("/api/stats", headers=self.auth_header)
        self.assertEqual(res_stats.status_code, 200)
        data = res_stats.json()
        self.assertEqual(data.get("authenticated_user"), "Kawa")
        self.assertGreater(data.get("total_jobs"), 1000)

        res_top25 = self.client.get("/api/top25", headers=self.auth_header)
        self.assertEqual(res_top25.status_code, 200)
        self.assertEqual(len(res_top25.json().get("items")), 25)

    def test_04_healthz_endpoint_accessible_unauthenticated(self):
        """Verify that /healthz is unauthenticated so Cloud/Render uptime monitors remain healthy."""
        res = self.client.get("/healthz")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data.get("status"), "healthy")
        self.assertTrue(data.get("sync_worker_alive"))

    # =========================================================================
    # 2. SECURITY & INPUT SANITIZATION TESTS (XSS & FORMULA INJECTION)
    # =========================================================================
    def test_05_url_sanitization(self):
        """Verify that dangerous pseudo-protocols (javascript:, data:) are neutralized."""
        self.assertEqual(sanitize_url("javascript:alert(1)"), "#")
        self.assertEqual(sanitize_url("data:text/html,<script>alert(1)</script>"), "#")
        self.assertEqual(sanitize_url(""), "#")
        self.assertEqual(sanitize_url(None), "#")
        valid_url = "https://www.linkedin.com/jobs/view/12345"
        self.assertEqual(sanitize_url(valid_url), valid_url)

    def test_06_formula_injection_defense(self):
        """Verify that spreadsheet formula injection payloads are safely quoted."""
        self.assertEqual(sanitize_cell("=cmd|' /C calc'!A0"), "'=cmd|' /C calc'!A0")
        self.assertEqual(sanitize_cell("@SUM(A1:A10)"), "'@SUM(A1:A10)")
        self.assertEqual(sanitize_cell("+cmd|..."), "'+cmd|...")
        # Purely numeric negative/positive values should NOT be quoted
        self.assertEqual(sanitize_cell("-500"), "-500")
        self.assertEqual(sanitize_cell("+100"), "+100")
        self.assertEqual(sanitize_cell("Standard Marketing Title"), "Standard Marketing Title")

    # =========================================================================
    # 3. PERFORMANCE & IN-MEMORY CACHE TESTS
    # =========================================================================
    def test_07_in_memory_cache_behavior(self):
        """Verify that repeated calls to load_jobs return identical in-memory instances without disk thrashing."""
        jobs1 = load_jobs()
        jobs2 = load_jobs()
        self.assertIs(jobs1, jobs2, "load_jobs() must return cached in-memory reference!")
        self.assertGreater(len(jobs1), 4000)

    # =========================================================================
    # 4. API CONTRACT & BOUNDARY TESTS
    # =========================================================================
    def test_08_api_pagination_bounds(self):
        """Verify pagination clamp bounds (limit <= 250, offset >= 0)."""
        # Test large limit clamped to <= 250
        res = self.client.get("/api/jobs?limit=5000", headers=self.auth_header)
        self.assertEqual(res.status_code, 422, "FastAPI validation should reject limit > 250!")

        res_ok = self.client.get("/api/jobs?limit=250&offset=0", headers=self.auth_header)
        self.assertEqual(res_ok.status_code, 200)
        self.assertEqual(len(res_ok.json().get("items")), 250)

    def test_09_adversarial_search_queries(self):
        """Verify that special characters and non-matching filters execute safely without 500 error."""
        res = self.client.get("/api/jobs?q=%27%22%3C%3E%26%24%25%5E*()_+", headers=self.auth_header)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json().get("total"), 0)

        res_cat = self.client.get("/api/jobs?category=NON_EXISTENT_CATEGORY_123", headers=self.auth_header)
        self.assertEqual(res_cat.status_code, 200)
        self.assertEqual(res_cat.json().get("total"), 0)

    # =========================================================================
    # 5. DATASET & WORKBOOK INTEGRITY TESTS
    # =========================================================================
    def test_10_excel_workbook_structure(self):
        """Verify the generated Excel workbook exists, contains all 9 sheets and 30 columns."""
        wb_path = "Singapore_Career_Intelligence_Database_2026.xlsx"
        self.assertTrue(os.path.exists(wb_path), "Master Excel workbook must exist on disk!")
        wb = openpyxl.load_workbook(wb_path, read_only=True)
        expected_sheets = [
            "Master Job Database",
            "Top Priority Opportunities",
            "Marketing & Communications",
            "Thai-Speaking & Regional",
            "Business Dev & Partnerships",
            "Interpretation & Freelance",
            "Transferable Skills",
            "Verification Required",
            "Research Coverage & Audit"
        ]
        for s in expected_sheets:
            self.assertIn(s, wb.sheetnames, f"Sheet '{s}' missing from workbook!")

        # Verify headers count
        self.assertEqual(len(HEADERS), 30, "Workbook must define exactly 30 required columns!")

    def test_11_file_download_endpoints(self):
        """Verify that authenticated download endpoints deliver the expected binary files."""
        res_xl = self.client.get("/download/excel", headers=self.auth_header)
        self.assertEqual(res_xl.status_code, 200)
        self.assertIn("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", res_xl.headers["Content-Type"])
        self.assertGreater(len(res_xl.content), 1_000_000)

        res_csv = self.client.get("/download/csv", headers=self.auth_header)
        self.assertEqual(res_csv.status_code, 200)
        self.assertIn("text/csv", res_csv.headers["Content-Type"])
        self.assertGreater(len(res_csv.content), 1_000_000)

    # =========================================================================
    # 6. UX & PRODUCT EXTENSION TESTS
    # =========================================================================
    def test_12_single_job_lookup(self):
        """Verify single job lookup by ID and proper 404 handling."""
        res = self.client.get("/api/jobs/SG-OPP-0001", headers=self.auth_header)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("job", data)
        self.assertEqual(data["job"]["col_01_id"], "SG-OPP-0001")
        self.assertIn("BANDAI NAMCO", data["job"]["col_02_company"])

        # Non-existent ID returns 404
        res_404 = self.client.get("/api/jobs/NON_EXISTENT_ID_9999", headers=self.auth_header)
        self.assertEqual(res_404.status_code, 404)

    def test_13_thai_only_filter(self):
        """Verify thai_only boolean filter returns only Thai-relevant positions."""
        res = self.client.get("/api/jobs?thai_only=true&limit=100", headers=self.auth_header)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertGreater(data["total"], 50)
        for job in data["items"]:
            is_thai = (
                "thai" in job.get("col_24_thai_relevance", "").lower()
                or "thai" in job.get("col_04_category", "").lower()
                or "thai" in job.get("col_03_title", "").lower()
            )
            self.assertTrue(is_thai, f"Job {job.get('col_01_id')} should be Thai-relevant!")

    def test_14_sort_by_options(self):
        """Verify sorting by score, title, and company."""
        # By title
        res_title = self.client.get("/api/jobs?sort_by=title&limit=10", headers=self.auth_header)
        self.assertEqual(res_title.status_code, 200)
        titles = [j.get("col_03_title").lower() for j in res_title.json()["items"]]
        self.assertEqual(titles, sorted(titles))

        # By company
        res_comp = self.client.get("/api/jobs?sort_by=company&limit=10", headers=self.auth_header)
        self.assertEqual(res_comp.status_code, 200)
        comps = [j.get("col_02_company").lower() for j in res_comp.json()["items"]]
        self.assertEqual(comps, sorted(comps))

    def test_15_ux_redesign_components(self):
        """Verify redesigned UI contains Spotlight, Explorer, Shortlist, and Dossier Drawer without telemetry leaks."""
        res = self.client.get("/", headers=self.auth_header)
        self.assertEqual(res.status_code, 200)
        text = res.text
        # Essential IA tabs
        self.assertIn("id=\"tab-btn-spotlight\"", text)
        self.assertIn("id=\"tab-btn-explorer\"", text)
        self.assertIn("id=\"tab-btn-shortlist\"", text)
        # Interactive Role Dossier Drawer
        self.assertIn("id=\"drawer-overlay\"", text)
        self.assertIn("id=\"dossier-title\"", text)
        # Telemetry removed from candidate hero view
        self.assertNotIn("Apify Scraping Budget Invested", text)
        # Candidate value KPIs present
        self.assertIn("Total Verified Vacancies", text)
        self.assertIn("Tier 1 Direct Matches", text)
        self.assertIn("Thai Bilingual Advantage", text)
        self.assertIn("Salary Disclosed", text)

    def test_16_min_salary_filter(self):
        """Verify min_salary filtering extracts numeric ranges and isolates high comp positions."""
        res = self.client.get("/api/jobs?min_salary=6000&limit=50", headers=self.auth_header)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertGreater(data["total"], 500)
        for job in data["items"]:
            sal = job.get("col_09_advertised_salary", "")
            self.assertTrue(bool(sal))

    def test_17_jobs_batch_endpoint(self):
        """Verify batch lookup fetches multiple arbitrary jobs by ID without page limits."""
        res = self.client.get("/api/jobs/batch?ids=SG-OPP-0001,SG-OPP-0004", headers=self.auth_header)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["count"], 2)
        returned_ids = [j.get("col_01_id") for j in data["items"]]
        self.assertIn("SG-OPP-0001", returned_ids)
        self.assertIn("SG-OPP-0004", returned_ids)

    def test_18_filtered_csv_export(self):
        """Verify dynamic filtered search export streams CSV with UTF-8 BOM."""
        res = self.client.get("/api/export/filtered?thai_only=true", headers=self.auth_header)
        self.assertEqual(res.status_code, 200)
        self.assertIn("text/csv", res.headers["Content-Type"])
        self.assertTrue(res.content.startswith(b"\xef\xbb\xbf"), "CSV must include UTF-8 BOM for Excel compatibility!")
        self.assertGreater(len(res.content), 10_000)

    def test_19_v1_3_advanced_ux_components(self):
        """Verify advanced UX elements: table view, preset pills, cover letter box, and pipeline tracker."""
        res = self.client.get("/", headers=self.auth_header)
        self.assertEqual(res.status_code, 200)
        text = res.text
        self.assertIn("id=\"explorer-table-container\"", text)
        self.assertIn("id=\"filter-min-salary\"", text)
        self.assertIn("id=\"dossier-cover-letter\"", text)
        self.assertIn("id=\"st-tab-applied\"", text)
        self.assertIn("id=\"st-tab-interviewing\"", text)

    # =========================================================================
    # 7. INGESTION, ATOMIC PERSISTENCE & SYNC QA TESTS
    # =========================================================================
    def test_20_sync_telemetry_in_healthz(self):
        """Verify /healthz exposes background sync worker telemetry."""
        res = self.client.get("/healthz")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("sync_telemetry", data)
        self.assertIn("is_syncing", data["sync_telemetry"])
        self.assertIn("last_sync_status", data["sync_telemetry"])

    def test_21_manual_sync_endpoint(self):
        """Verify POST /api/sync requires authentication and rejects unauthorized access."""
        # Unauth should fail 401
        res_unauth = self.client.post("/api/sync")
        self.assertEqual(res_unauth.status_code, 401)

        # Auth should succeed
        res_auth = self.client.post("/api/sync", headers=self.auth_header)
        self.assertEqual(res_auth.status_code, 200)
        data = res_auth.json()
        self.assertEqual(data["authenticated_user"], "Kawa")
        self.assertIn("sync_result", data)
        self.assertIn("telemetry", data)

    def test_22_atomic_persistence_and_mcf_transformation(self):
        """Verify transform_mcf_job enforces 30 columns and atomic_save_jobs writes safely."""
        from sync_engine import transform_mcf_job, atomic_save_jobs
        import tempfile

        raw_sample = {
            "title": "Regional Thai Social Media Strategist",
            "company": "ByteDance Pte. Ltd.",
            "query_matched": "Thai",
            "url": "https://www.mycareersfuture.gov.sg/job/mock-uuid-9999",
            "advertised_salary": "SGD 7,000 - 9,500 / monthly"
        }
        transformed = transform_mcf_job(raw_sample, 9999)
        self.assertEqual(len(transformed), 30, "Transformed job must satisfy the 30-column master schema exactly!")
        self.assertEqual(transformed["col_01_id"], "SG-OPP-9999")
        self.assertEqual(transformed["col_02_company"], "ByteDance Pte. Ltd.")
        self.assertEqual(transformed["col_04_category"], "Category E: Thai-Speaking & Thailand-Focused Positions")
        self.assertEqual(transformed["col_25_suitability_score"], 95)

        # Test atomic file write
        with tempfile.TemporaryDirectory() as td:
            target_path = os.path.join(td, "test_jobs.json")
            success = atomic_save_jobs(target_path, [transformed])
            self.assertTrue(success)
            self.assertTrue(os.path.exists(target_path))
            with open(target_path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            self.assertEqual(len(loaded), 1)
            self.assertEqual(loaded[0]["col_01_id"], "SG-OPP-9999")

    # =========================================================================
    # 6. ADVANCED SEARCH & RELEVANCE ENGINE TESTS
    # =========================================================================
    def test_23_multi_token_search_recall(self):
        """Verify multi-token query matches across non-contiguous words (e.g. 'Thai Marketing')."""
        res = self.client.get("/api/jobs?q=Thai+Marketing&limit=100", headers=self.auth_header)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["total"], 45, "Multi-token search 'Thai Marketing' must return exactly 45 genuine job postings!")
        for job in data["items"]:
            corpus = f"{job['col_03_title']} {job['col_02_company']} {job['col_04_category']} {job['col_05_industry']} {job['col_06_location']} {job['col_18_responsibilities']} {job['col_24_thai_relevance']}".lower()
            self.assertTrue("thai" in corpus and "marketing" in corpus, f"Job {job['col_01_id']} must contain both tokens!")

    def test_24_quoted_exact_phrase_search(self):
        """Verify quoted query searches for exact phrase match."""
        res = self.client.get('/api/jobs?q="Localization+Project+Coordinator"&limit=10', headers=self.auth_header)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertGreater(data["total"], 0)
        first_title = data["items"][0]["col_03_title"]
        self.assertIn("Localization Project Coordinator", first_title)

    def test_25_search_relevance_ranking(self):
        """Verify relevance boosting places exact title matches before deep-description matches."""
        res = self.client.get("/api/jobs?q=Localization&limit=10", headers=self.auth_header)
        self.assertEqual(res.status_code, 200)
        items = res.json()["items"]
        self.assertGreater(len(items), 0)
        # Top result should feature Localization directly in title
        self.assertIn("localization", items[0]["col_03_title"].lower())

    def test_26_automated_export_sync_workbook_and_csv(self):
        """Verify build_full_workbook creates both styled 9-sheet Excel workbook and UTF-8 BOM CSV atomically."""
        from generate_workbook import build_full_workbook
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            mock_data_path = os.path.join(td, "mock_jobs.json")
            xlsx_out = os.path.join(td, "test_db.xlsx")
            csv_out = os.path.join(td, "test_db.csv")
            
            sample_jobs = load_jobs()[:10]
            with open(mock_data_path, "w", encoding="utf-8") as f:
                json.dump(sample_jobs, f)
                
            res = build_full_workbook(data_path=mock_data_path, output_filename=xlsx_out, csv_filename=csv_out)
            self.assertEqual(res["total_jobs"], 10)
            self.assertTrue(os.path.exists(xlsx_out))
            self.assertTrue(os.path.exists(csv_out))
            
            wb = openpyxl.load_workbook(xlsx_out)
            self.assertEqual(len(wb.sheetnames), 9)
            
            with open(csv_out, "rb") as cf:
                content = cf.read()
                self.assertTrue(content.startswith(b"\xef\xbb\xbf"), "Master CSV export must contain UTF-8 BOM!")
                self.assertIn(b"Job ID,Company Name,Exact Job Title", content)

    def test_27_indexed_batch_lookup_integrity(self):
        """Verify O(1) batch lookup returns exact matching jobs in request order without data leakage."""
        target_ids = "SG-OPP-0001,SG-OPP-0004"
        res = self.client.get(f"/api/jobs/batch?ids={target_ids}", headers=self.auth_header)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["count"], 2)
        self.assertEqual(data["items"][0]["col_01_id"], "SG-OPP-0001")
        self.assertEqual(data["items"][1]["col_01_id"], "SG-OPP-0004")
        for item in data["items"]:
            self.assertNotIn("_search_corpus", item)
            self.assertNotIn("_search_title", item)
            self.assertNotIn("_max_salary", item)

    def test_28_candidate_profile_not_polluting_search_corpus(self):
        """Verify candidate resume boilerplate (e.g. 'Kasetsart', 'MSc Marketing NTU') does not match unrelated jobs."""
        res = self.client.get("/api/jobs?q=Kasetsart", headers=self.auth_header)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["total"], 0, "Candidate CV terms like 'Kasetsart' must never match job postings!")

    def test_29_salary_normalization_annual_and_hourly(self):
        """Verify annual and hourly salaries are normalized to monthly equivalent for sorting/filtering."""
        from app import extract_salary_range
        # Annual: $60,000 - $72,000 a year -> $5,000 - $6,000 /mo
        s_min, s_max = extract_salary_range("$60,000 - $72,000 a year")
        self.assertEqual(s_min, 5000)
        self.assertEqual(s_max, 6000)
        
        # Annually single figure
        s_min2, s_max2 = extract_salary_range("$120,000 annually")
        self.assertEqual(s_min2, 10000)
        self.assertEqual(s_max2, 10000)
        
        # Hourly: $20 - $30 an hour -> $3,460 - $5,190 /mo (x173)
        s_min3, s_max3 = extract_salary_range("$20 - $30 an hour")
        self.assertEqual(s_min3, 20 * 173)
        self.assertEqual(s_max3, 30 * 173)

        # Standard monthly remains unaltered
        s_min4, s_max4 = extract_salary_range("$5,000 - $7,000 monthly")
        self.assertEqual(s_min4, 5000)
        self.assertEqual(s_max4, 7000)

    def test_30_title_exclusion_whitelist_and_preservation(self):
        """Verify legitimate graduate and management trainee schemes are preserved while blue-collar roles are excluded."""
        from pipeline_processor import is_excluded_title
        # Whitelisted entry schemes
        self.assertFalse(is_excluded_title("Management Trainee - Regional Marketing"))
        self.assertFalse(is_excluded_title("Graduate Trainee (Commercial & Sales)"))
        self.assertFalse(is_excluded_title("Growth Driver / Management Associate"))
        self.assertFalse(is_excluded_title("Leadership Development Program Associate"))
        
        # Excluded blue collar / unrelated roles
        self.assertTrue(is_excluded_title("Thai Chef"))
        self.assertTrue(is_excluded_title("Dishwasher"))
        self.assertTrue(is_excluded_title("Security Officer"))
        self.assertTrue(is_excluded_title("Driver / Delivery Man"))

    def test_31_export_sync_coalescing_and_concurrency(self):
        """Verify export synchronization coalesces rapid triggers without temp file conflicts."""
        import sync_engine
        import tempfile
        import time
        with tempfile.TemporaryDirectory() as td:
            data_file = os.path.join(td, "jobs.json")
            with open(data_file, "w", encoding="utf-8") as f:
                json.dump(load_jobs()[:5], f)
            
            # Rapidly trigger export refresh multiple times
            sync_engine.trigger_export_refresh_async(data_file)
            sync_engine.trigger_export_refresh_async(data_file)
            sync_engine.trigger_export_refresh_async(data_file)
            
            # Wait for export lock / progress to clear
            max_wait = 15
            start = time.time()
            while (sync_engine._export_in_progress or sync_engine._export_pending) and (time.time() - start < max_wait):
                time.sleep(0.2)
                
            self.assertFalse(sync_engine._export_in_progress)

if __name__ == '__main__':
    unittest.main()
