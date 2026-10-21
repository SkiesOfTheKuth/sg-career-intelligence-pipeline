import concurrent.futures
from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest

from storage import Conflict, Store


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / "workspace.sqlite3"
        self.store = Store(self.path).initialize()
        self.job = {"col_01_id": "SG-OPP-1", "col_03_title": "Communications specialist",
                    "col_15_direct_url": "https://example.test/jobs/1", "description": "Full original description."}
        self.store.seed_jobs([self.job])

    def test_seed_preserves_newer_collected_jobs_and_ids(self):
        updated = {**self.job, "description": "A corrected complete description"}
        self.store.upsert_jobs([updated, {"id": "production-only", "title": "New role"}])
        self.assertEqual(self.store.seed_jobs([self.job]), 0)
        self.assertEqual(self.store.get_job("SG-OPP-1"), updated)
        self.assertEqual(len(self.store.list_jobs()), 2)
        self.assertEqual(self.store.get_job("production-only")["id"], "production-only")

    def test_first_note_saves_and_survives_new_store(self):
        saved = self.store.put_application("SG-OPP-1", {"expected_revision": 0, "notes": "Follow up next week. ภาษาไทย"})
        restarted = Store(self.path).initialize()
        actual = restarted.get_application("SG-OPP-1")
        self.assertEqual(actual, saved)
        self.assertEqual(actual["stage"], "Saved")
        self.assertEqual(actual["revision"], 1)
        self.assertIsNone(actual["applied_at"])

    def test_conflict_does_not_overwrite_current_notes_or_stage(self):
        self.store.put_application("SG-OPP-1", {"expected_revision": 0, "notes": "Browser A"})
        other_browser = Store(self.path)
        with self.assertRaises(Conflict) as raised:
            other_browser.put_application("SG-OPP-1", {"expected_revision": 0, "notes": "Browser B", "stage": "Applied"})
        self.assertEqual(raised.exception.current["notes"], "Browser A")
        self.assertEqual(raised.exception.current["revision"], 1)
        self.assertEqual(self.store.get_application("SG-OPP-1")["stage"], "Saved")

    def test_simultaneous_writes_only_one_wins(self):
        self.store.put_application("SG-OPP-1", {"expected_revision": 0})

        def write(note):
            try:
                return Store(self.path).put_application("SG-OPP-1", {"expected_revision": 1, "notes": note})
            except Conflict:
                return None

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(write, ["One", "Two"]))
        self.assertEqual(sum(item is not None for item in results), 1)
        self.assertEqual(self.store.get_application("SG-OPP-1")["revision"], 2)

    def test_snapshot_and_history_survive_changed_listing_and_closed_stage(self):
        self.store.put_application("SG-OPP-1", {"expected_revision": 0, "notes": "Original notes"})
        self.store.upsert_jobs([{**self.job, "description": "Listing removed", "closed": True}])
        closed = self.store.put_application("SG-OPP-1", {"expected_revision": 1, "stage": "Closed", "outcome": "Role withdrawn"})
        self.assertEqual(closed["job_snapshot"], self.job)
        self.assertEqual(closed["notes"], "Original notes")
        self.assertEqual(closed["outcome"], "Role withdrawn")
        self.assertEqual([event["stage"] for event in closed["history"]], ["Saved", "Closed"])
        self.assertEqual(self.store.list_applications("Closed"), [closed])
        self.assertEqual(self.store.list_applications("Applied"), [])

    def test_draft_partial_updates_preserve_other_edits(self):
        self.store.put_application("SG-OPP-1", {"expected_revision": 0, "drafts": {
            "recruiter_message": "My own edited message", "cover_letter": "My own letter"}})
        edited = self.store.put_application("SG-OPP-1", {"expected_revision": 1, "drafts": {"cover_letter": "Updated letter"},
                                                                    "next_action": "Review requirements", "follow_up_date": "2026-10-25"})
        self.assertEqual(edited["drafts"], {"recruiter_message": "My own edited message", "cover_letter": "Updated letter"})
        self.assertEqual(Store(self.path).get_application("SG-OPP-1")["follow_up_date"], "2026-10-25")

    def test_only_explicit_applied_stage_records_application_date(self):
        saved = self.store.put_application("SG-OPP-1", {"expected_revision": 0, "stage": "Preparing"})
        self.assertIsNone(saved["applied_at"])
        applied = self.store.put_application("SG-OPP-1", {"expected_revision": 1, "stage": "Applied"})
        self.assertTrue(applied["applied_at"])
        updated = self.store.put_application("SG-OPP-1", {"expected_revision": 2, "notes": "Sent yesterday"})
        self.assertEqual(updated["applied_at"], applied["applied_at"])

    def test_import_is_idempotent_even_after_later_user_edits(self):
        legacy = {"SG-OPP-1": {"status": "Drafted", "notes": "Old browser note", "savedAt": "2026-10-18T10:00:00Z"}}
        self.assertEqual(self.store.import_applications(legacy)["imported"], 1)
        imported = self.store.get_application("SG-OPP-1")
        self.assertEqual(imported["stage"], "Preparing")
        self.assertEqual(imported["created_at"], "2026-10-18T10:00:00.000+00:00")
        self.store.put_application("SG-OPP-1", {"expected_revision": 1, "notes": "New server edit"})
        repeated = self.store.import_applications(legacy)
        self.assertEqual(repeated["unchanged"], 1)
        self.assertEqual(repeated["conflicts"], [])
        self.assertEqual(self.store.get_application("SG-OPP-1")["notes"], "New server edit")

    def test_import_conflict_preserves_both_versions_and_can_be_reviewed(self):
        self.store.put_application("SG-OPP-1", {"expected_revision": 0, "stage": "Applied", "notes": "Server note"})
        legacy = {"SG-OPP-1": {"status": "Ready", "notes": "Other browser note"}}
        first = self.store.import_applications(legacy)
        second = self.store.import_applications(legacy)
        self.assertEqual(len(first["conflicts"]), 1)
        self.assertEqual(first["conflicts"], second["conflicts"])
        application = self.store.get_application("SG-OPP-1")
        self.assertEqual(application["notes"], "Server note")
        self.assertEqual(application["stage"], "Applied")
        self.assertEqual(application["revision"], 2)
        self.assertEqual(application["import_conflicts"][0]["incoming"]["original"]["notes"], "Other browser note")
        merged = self.store.put_application("SG-OPP-1", {
            "expected_revision": 2, "notes": "Server note\nOther browser note",
            "resolve_import_conflicts": [first["conflicts"][0]["id"]],
        })
        self.assertEqual(merged["import_conflicts"], [])
        self.assertEqual(self.store.import_applications(legacy)["conflicts"], [])
        self.assertIn("Other browser note", Store(self.path).get_application("SG-OPP-1")["notes"])

    def test_unavailable_import_keeps_notes_without_guessing_application_date(self):
        imported = self.store.import_applications({"missing-job": {"status": "Applied", "notes": "I applied through the portal"}})
        self.assertEqual(imported["imported"], 1)
        application = self.store.get_application("missing-job")
        self.assertTrue(application["job_snapshot"]["unavailable"])
        self.assertEqual(application["stage"], "Applied")
        self.assertIsNone(application["applied_at"])

    def test_bad_import_record_does_not_discard_valid_records(self):
        result = self.store.import_applications({"broken": {"status": "Unexpected", "notes": "Keep in browser"},
                                                "SG-OPP-1": {"status": "Saved", "notes": "Valid"}})
        self.assertEqual(result["imported"], 1)
        self.assertEqual(result["errors"][0]["job_id"], "broken")
        self.assertIsNone(self.store.get_application("broken"))

    def test_invalid_revision_stage_and_fields_leave_storage_unchanged(self):
        for changes in [{"notes": "Missing revision"}, {"expected_revision": True},
                        {"expected_revision": 0, "stage": "Ready"}, {"expected_revision": 0, "follow_up_date": "2026-02-30"},
                        {"expected_revision": 0, "drafts": {"unknown": "Text"}}, {"expected_revision": 0, "notes": {"bad": "type"}}]:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.store.put_application("SG-OPP-1", changes)
        self.assertEqual(self.store.list_applications(), [])

    def test_bad_job_batch_is_atomic(self):
        with self.assertRaises(ValueError):
            self.store.upsert_jobs([{"id": "valid"}, {"title": "Missing ID"}])
        self.assertIsNone(self.store.get_job("valid"))

    def test_bound_parameters_keep_sql_as_user_text(self):
        job_id = "x'; DROP TABLE applications;--"
        notes = "'); DELETE FROM jobs; --"
        self.store.put_application(job_id, {"expected_revision": 0, "notes": notes})
        self.assertEqual(self.store.get_application(job_id)["notes"], notes)
        self.assertEqual(self.store.get_job("SG-OPP-1"), self.job)

    def test_backup_restoration_preserves_every_table_and_immutable_backup(self):
        self.store.put_application("SG-OPP-1", {"expected_revision": 0, "notes": "Durable application"})
        self.store.import_applications({"SG-OPP-1": {"status": "Saved", "notes": "Conflicting imported note"}})
        self.store.record_source_evidence("SG-OPP-1", "employer", {"description": "Full employer wording"})
        self.store.record_sync({"status": "failed", "source": "employer", "error": "Upstream timeout"})
        self.store.set_meta("next_sync_at", "2026-10-22T01:00:00Z")
        backup_path = Path(self.temporary.name) / "backups" / "snapshot.sqlite3"
        backup = self.store.backup(backup_path)
        self.assertEqual(backup["integrity"], "ok")
        self.assertTrue(backup["restoration_verified"])
        self.assertEqual(backup["counts"]["applications"], 1)
        with self.assertRaises(FileExistsError):
            self.store.backup(backup_path)
        with self.assertRaises(FileExistsError):
            Store.restore_backup(backup_path, self.path)
        restored_path = Path(self.temporary.name) / "restore.sqlite3"
        restored = Store.restore_backup(backup_path, restored_path)
        self.assertEqual(restored["digests"], backup["digests"])
        restored_store = Store(restored_path).initialize()
        self.assertEqual(restored_store.get_application("SG-OPP-1"), self.store.get_application("SG-OPP-1"))
        self.assertEqual(restored_store.get_source_evidence("SG-OPP-1"), self.store.get_source_evidence("SG-OPP-1"))
        self.assertEqual(restored_store.get_sync_history()[0]["status"], "failed")
        self.assertEqual(restored_store.get_meta("next_sync_at"), "2026-10-22T01:00:00Z")

    def test_wal_and_integrity_survive_multiple_store_instances(self):
        with closing(sqlite3.connect(self.path)) as connection:
            self.assertEqual(connection.execute("PRAGMA journal_mode").fetchone()[0], "wal")
        for index in range(3):
            Store(self.path).initialize().set_meta("counter", index)
        self.assertEqual(self.store.get_meta("counter"), 2)
        self.assertEqual(Store.verify_database(self.path)["integrity"], "ok")


if __name__ == "__main__":
    unittest.main()
