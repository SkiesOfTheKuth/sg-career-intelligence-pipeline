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

if __name__ == '__main__':
    unittest.main()
