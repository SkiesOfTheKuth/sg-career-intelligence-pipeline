import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from evidence import (assess, build_job, draft_templates, extract_requirements,
                      present_job, repair_jobs, salary_presentation, source_key, thai_relevance)


class EvidenceTests(unittest.TestCase):
    def test_repair_preserves_identity_full_text_and_rejects_generated_defaults(self):
        raw = {"id": "LI-1234567890", "title": "Marketing Executive", "company": "A", "source": "LinkedIn Jobs",
               "url": "https://sg.linkedin.com/jobs/view/marketing-1234567890?trackingId=first",
               "description": "<p>Full description " + "source words " * 100 + "</p>",
               "work_arrangement": "On-site / Hybrid (Singapore)"}
        legacy = {"col_01_id": "SG-OPP-0042", "col_03_title": raw["title"],
                  "col_15_direct_url": "https://www.linkedin.com/jobs/view/1234567890?trackingId=second",
                  "col_19_mandatory_reqs": "Invented bachelor qualification", "col_20_preferred_reqs": "Invented Thai requirement",
                  "col_13_checked_date": "2026-10-19"}
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, "apify_jobs_raw.json").write_text(json.dumps([raw]))
            repaired = repair_jobs([legacy], directory)[0]
        self.assertEqual(repaired["id"], "SG-OPP-0042")
        self.assertEqual(repaired["url"], legacy["col_15_direct_url"])
        self.assertGreater(len(repaired["description"]), 1000)
        self.assertEqual(repaired["requirements"], {"mandatory": [], "preferred": []})
        self.assertIsNone(repaired["work_arrangement"])
        self.assertTrue(repaired["verification"]["needs_recheck"])
        self.assertEqual(repaired["verification"]["status"], "historical")

    def test_unmatched_record_keeps_excerpt_with_unknown_requirements(self):
        with tempfile.TemporaryDirectory() as directory:
            job = repair_jobs([{"col_01_id": "old", "col_18_responsibilities": "Retained excerpt",
                                "col_19_mandatory_reqs": "Fabricated"}], directory)[0]
        self.assertEqual(job["description"], "Retained excerpt")
        self.assertFalse(job["description_complete"])
        self.assertEqual(job["assessment"]["fit"], "Check requirements")

    def test_aggregate_search_pages_and_inserted_full_time_are_not_vacancy_facts(self):
        job = build_job({"title": "Thai jobs in Singapore", "source": "Google Search Verified Index",
                         "url": "https://sg.jobstreet.com/thai-speaking-jobs", "description": "24 jobs found"}, "search")
        self.assertEqual(job["status"], "unavailable")
        job = build_job({"title": "Marketing Executive", "source": "Indeed Singapore", "employment_type": "Full-time",
                         "description": "Marketing responsibilities"}, "indeed")
        self.assertIsNone(job["employment_type"])

    def test_thailand_footprint_is_context_and_search_query_is_not_evidence(self):
        job = build_job({"title": "Communications Specialist", "company": "PropertyGuru", "query_matched": "Thai speaking",
                         "description": "We operate in Singapore, Malaysia, Thailand and Vietnam."}, "one")
        self.assertEqual(job["thai_relevance"], "Thailand market context")
        job = build_job({"title": "Marketing Executive", "query_matched": "Thai speaking", "description": "Social media campaigns."}, "two")
        self.assertIsNone(job["thai_relevance"])

    def test_thai_preferred_and_required_are_distinct(self):
        for description, expected in [("Thai language proficiency is preferred.", "Thai preferred"),
                                      ("Must speak Thai to support customers.", "Thai required")]:
            self.assertEqual(thai_relevance("Customer Support", description, extract_requirements(description)), expected)

    def test_language_requirements_and_specialist_finance_prevent_top_fit(self):
        for description in ("Requirements\nFluent Japanese or Vietnamese is required.",
                            "You must communicate in Japanese or Vietnamese fluently to manage the market."):
            result = assess("Influencer Marketing", description, extract_requirements(description))
            self.assertEqual(result["fit"], "Not suitable")
            self.assertTrue(any("Japanese" in gap for gap in result["gaps"]))
        result = assess("Accounts Receivable Specialist", "Marketing team support", {"mandatory": [], "preferred": []})
        self.assertEqual(result["fit"], "Not suitable")

    def test_supported_basic_requirements_can_be_relevant_but_years_and_fluency_need_checking(self):
        base = {"mandatory": ["Bachelor's degree in marketing", "Experience in social media"], "preferred": []}
        self.assertEqual(assess("Marketing Executive", "Manage social media", base)["fit"], "Relevant")
        for requirement in ("Native Thai speaker", "Fluent English", "5 years of marketing experience", "Strong experience in social media and Python"):
            reqs = {"mandatory": base["mandatory"] + [requirement], "preferred": []}
            self.assertEqual(assess("Marketing Executive", "Manage social media", reqs)["fit"], "Check requirements")

    def test_salary_units_and_minimum_are_factual(self):
        cases = [("SGD 60,000 - 84,000 /yr", "year", 5000, 7000),
                 ("SGD 3,000 - 6,000 / monthly", "month", 3000, 6000),
                 ("SGD 450 - 800 / day", "day", None, None),
                 ("SGD 20 - 35 /hour", "hour", None, None),
                 ("Up to SGD 8,000 / month", "month", None, 8000),
                 ("SGD 5,000", None, None, None)]
        for display, unit, low, high in cases:
            with self.subTest(display=display):
                salary = salary_presentation({"advertised_salary": display, "salary_type": "Monthly"})
                self.assertEqual(salary["unit"], unit)
                self.assertEqual(salary["monthly_minimum"], low)
                self.assertEqual(salary["monthly_maximum"], high)
        salary = salary_presentation({"advertised_salary": "Singapore October 17, 2026 $1000 - $1400 / month", "source": "Cultjobs Singapore"})
        self.assertEqual(salary["minimum"], 1000)
        self.assertEqual(salary["currency"], "SGD")
        self.assertFalse(salary_presentation({"advertised_salary": "Not disclosed"})["disclosed"])

    def test_expiry_freshness_and_unavailable(self):
        job = {"id": "one", "status": "open", "deadline": "2026-10-20",
               "verification": {"checked_at": "2026-10-19T12:00:00Z", "status": "verified"}}
        current = present_job(job, "2026-10-21T12:00:00Z")
        self.assertEqual(current["status"], "expired")
        self.assertTrue(current["verification"]["needs_recheck"])
        job["status"] = "unavailable"
        self.assertEqual(present_job(job, "2026-10-21T12:00:00Z")["status"], "unavailable")
        job["status"], job["deadline"] = "open", "2026-10-21"
        self.assertEqual(present_job(job, "2026-10-21T12:00:00Z")["status"], "open")

    def test_scripts_removed_and_drafts_do_not_invent_credentials(self):
        job = build_job({"title": "Marketing Executive", "description": "<script>alert(1)</script><p>Social media</p>"}, "one")
        self.assertNotIn("alert", job["description"])
        drafts = "\n".join(draft_templates(job).values()).lower()
        for unsupported in ("native thai", "fluent", "immediately available", "@", "+65", "i specialize in highlight"):
            self.assertNotIn(unsupported, drafts)
        self.assertIn("[add a specific example", drafts)
        tailored = draft_templates(build_job({"title": "Marketing Executive", "requirements": "Experience in social media"}, "two"))
        self.assertIn('Your listing states: “Experience in social media”', tailored['cover_letter'])

    def test_source_identity_preserves_identifying_queries(self):
        self.assertNotEqual(source_key("https://sg.indeed.com/viewjob?jk=one"), source_key("https://sg.indeed.com/viewjob?jk=two"))
        self.assertEqual(source_key("https://sg.indeed.com/viewjob?jk=one&utm_campaign=x"), source_key("https://sg.indeed.com/viewjob?jk=one"))


if __name__ == "__main__":
    unittest.main()
