"""Durable, single-workspace storage using Python's native SQLite driver.

Writes use explicit transactions and optimistic application revisions. Backups
use sqlite3.Connection.backup, never a copy of a live WAL database file.
https://docs.python.org/3/library/sqlite3.html
"""

from contextlib import contextmanager
from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile


STAGES = ("Saved", "Preparing", "Applied", "Interviewing", "Offer", "Closed")
_DRAFT_FIELDS = {"recruiter_message", "cover_letter"}
_TEXT_FIELDS = {"notes", "next_action", "outcome"}
_APPLICATION_FIELDS = _TEXT_FIELDS | {
    "expected_revision", "stage", "follow_up_date", "drafts", "applied_at",
    "resolve_import_conflicts",
}
_TABLES = ("jobs", "applications", "import_receipts", "import_conflicts",
           "source_evidence", "sync_history", "metadata")


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _job_id(job):
    value = job.get("id") or job.get("col_01_id") or job.get("job_id")
    if not isinstance(value, str) or not value.strip():
        raise ValueError("A non-empty job ID is required")
    return value


def _timestamp(value, field):
    if value in (None, ""):
        return None
    if not isinstance(value, str):
        raise ValueError(f"{field} must be an ISO timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError("Timezone required")
    except ValueError as exc:
        raise ValueError(f"{field} must be an ISO timestamp with a timezone") from exc
    return parsed.isoformat(timespec="milliseconds")


class Conflict(Exception):
    """The server version is newer; the caller must retain the unsaved edit."""

    def __init__(self, current):
        self.current = current
        super().__init__("This application changed elsewhere. Review both versions before saving.")


class Store:
    def __init__(self, path):
        if str(path) == ":memory:":
            raise ValueError("Store requires a filesystem path for durable storage")
        self.path = Path(path).resolve()

    @contextmanager
    def _connection(self, write=False):
        connection = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 30000")
        connection.execute("PRAGMA synchronous = FULL")
        try:
            if write:
                connection.execute("BEGIN IMMEDIATE")
            yield connection
            if write:
                connection.commit()
        except BaseException:
            if write:
                connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connection() as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.executescript("""
                BEGIN IMMEDIATE;
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY, data_json TEXT NOT NULL, updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS applications (
                    job_id TEXT PRIMARY KEY, revision INTEGER NOT NULL,
                    stage TEXT NOT NULL, data_json TEXT NOT NULL, updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS applications_stage ON applications(stage);
                CREATE TABLE IF NOT EXISTS import_receipts (
                    fingerprint TEXT PRIMARY KEY, job_id TEXT NOT NULL,
                    result TEXT NOT NULL, imported_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS import_conflicts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, job_id TEXT NOT NULL,
                    fingerprint TEXT UNIQUE NOT NULL, data_json TEXT NOT NULL,
                    created_at TEXT NOT NULL, resolved_at TEXT
                );
                CREATE TABLE IF NOT EXISTS source_evidence (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, job_id TEXT NOT NULL,
                    source TEXT NOT NULL, data_json TEXT NOT NULL, captured_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS evidence_job ON source_evidence(job_id);
                CREATE TABLE IF NOT EXISTS sync_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, data_json TEXT NOT NULL,
                    recorded_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS metadata (
                    key TEXT PRIMARY KEY, value_json TEXT NOT NULL
                );
                COMMIT;
            """)
        with self._connection(write=True) as connection:
            version = connection.execute('PRAGMA user_version').fetchone()[0]
            if version > 5:
                raise ValueError('Database schema is newer than this application supports')
            if version < 2:
                columns = {row['name'] for row in connection.execute('PRAGMA table_info(import_conflicts)')}
                if 'resolution_json' not in columns:
                    connection.execute('ALTER TABLE import_conflicts ADD COLUMN resolution_json TEXT')
                self._backfill_source_fields(connection)
                connection.execute('PRAGMA user_version = 2')
            if version < 4:
                from campaign_store import initialize as initialize_campaign
                initialize_campaign(connection)
                connection.execute('PRAGMA user_version = 4')
            if version < 5:
                from campaign_bursts import initialize as initialize_bursts
                initialize_bursts(connection)
                connection.execute('PRAGMA user_version = 5')
        return self

    @staticmethod
    def _backfill_source_fields(connection):
        """Recover explicit fields from retained payloads, never derived requirements.

        Old jobs omitted raw_evidence on persistence. Source payload versions are
        the authority for explicit requirements and their original content dates.
        Missing historical evidence stays unknown rather than being dated today.
        """
        from evidence import plain_text
        for row in connection.execute('SELECT id,data_json FROM jobs').fetchall():
            job = json.loads(row['data_json'])
            if not job.get('evidence_version'):
                continue
            records = []
            for evidence in connection.execute('SELECT id,data_json FROM source_evidence WHERE job_id=? ORDER BY id DESC', (row['id'],)):
                payload = json.loads(evidence['data_json'])
                raw = payload.get('record', payload) if isinstance(payload, dict) else {}
                if isinstance(raw, dict):
                    records.append((raw, evidence['id']))
            raw = job.get('raw_evidence')
            if isinstance(raw, dict):
                records.insert(0, (raw, None))
            provenance = job.setdefault('field_provenance', {})
            for field in ('description', 'requirements'):
                expected = (job.get('description') if field == 'description' else
                            job.get('source_requirements', job.get('retained_requirements_source')))
                retained = next(((raw, evidence_id) for raw, evidence_id in records if raw.get(field)
                                 and (not expected or plain_text(raw[field]) == plain_text(expected))), None)
                if field == 'requirements' and 'source_requirements' not in job:
                    job['source_requirements'] = (job.get('retained_requirements_source')
                                                  or (retained[0].get(field) if retained else None))
                    job['source_requirement_evidence'] = (retained[0].get('requirements_evidence') or []) if retained else []
                if field not in provenance:
                    raw, evidence_id = retained or ({}, None)
                    provenance[field] = {'url': raw.get('url') or job.get('url'),
                                         'checked_at': raw.get('verified_at') or raw.get('checked_at'),
                                         'source_record_date': raw.get('source_record_date') or
                                             (job.get('verification', {}).get('checked_at')
                                              if not job.get('verification', {}).get('last_success_at') else None),
                                         'evidence_id': evidence_id}
            if not records and not job.get('source_requirements') and (job.get('requirements') or {}).get('mandatory'):
                # Some records lack their original payload. Preserve their existing
                # derived requirements until actual source text can be recovered.
                job['requirements_source_unknown'] = True
            connection.execute('UPDATE jobs SET data_json=? WHERE id=?', (_json(job), row['id']))

    def _write_jobs(self, jobs, replace):
        statement = ("INSERT INTO jobs(id,data_json,updated_at) VALUES(?,?,?) "
                     + ("ON CONFLICT(id) DO UPDATE SET data_json=excluded.data_json, "
                        "updated_at=excluded.updated_at" if replace else "ON CONFLICT(id) DO NOTHING"))
        now = _now()
        rows = [(_job_id(job), _json({k: v for k, v in job.items() if k != 'raw_evidence'}), now) for job in jobs]
        with self._connection(write=True) as connection:
            before = connection.total_changes
            connection.executemany(statement, rows)
            return connection.total_changes - before

    def seed_jobs(self, jobs):
        """Insert missing seed IDs without replacing newer collected records."""
        return self._write_jobs(jobs, replace=False)

    def upsert_jobs(self, jobs):
        return self._write_jobs(jobs, replace=True)

    def record_source_batch(self, records):
        """Capture initial evidence in one durable transaction, not thousands of fsyncs."""
        now = _now()
        rows = [(job_id, source, _json(payload), now) for job_id, source, payload in records]
        with self._connection(write=True) as connection:
            connection.executemany(
                'INSERT INTO source_evidence(job_id,source,data_json,captured_at) VALUES(?,?,?,?)', rows)

    def commit_source_refresh(self, jobs, records, result):
        """Commit source versions, current job fields and the run in one transaction.

        A crash or failed write leaves the prior complete state. The lifespan's
        interrupted-run marker makes a hard restart retry the bounded check.
        """
        now = _now()
        rows = [(_job_id(job), _json({k: v for k, v in job.items() if k != 'raw_evidence'}), now) for job in jobs]
        evidence = [(job_id, source, _json(payload), now) for job_id, source, payload in records]
        with self._connection(write=True) as connection:
            connection.executemany('INSERT INTO source_evidence(job_id,source,data_json,captured_at) VALUES(?,?,?,?)', evidence)
            connection.executemany('INSERT INTO jobs(id,data_json,updated_at) VALUES(?,?,?) '
                                   'ON CONFLICT(id) DO UPDATE SET data_json=excluded.data_json,updated_at=excluded.updated_at', rows)
            connection.execute('INSERT INTO sync_history(data_json,recorded_at) VALUES(?,?)', (_json(result), now))

    def list_jobs(self):
        with self._connection() as connection:
            return [json.loads(row[0]) for row in connection.execute("SELECT data_json FROM jobs ORDER BY id")]

    def count_jobs(self):
        with self._connection() as connection:
            return connection.execute('SELECT COUNT(*) FROM jobs').fetchone()[0]

    def get_job(self, job_id):
        with self._connection() as connection:
            row = connection.execute("SELECT data_json FROM jobs WHERE id=?", (job_id,)).fetchone()
            return json.loads(row[0]) if row else None

    @staticmethod
    def _application(connection, job_id):
        row = connection.execute("SELECT data_json FROM applications WHERE job_id=?", (job_id,)).fetchone()
        if row is None:
            return None
        application = json.loads(row[0])
        application["import_conflicts"] = [
            {"id": item["id"], "created_at": item["created_at"], "incoming": json.loads(item["data_json"])}
            for item in connection.execute(
                "SELECT * FROM import_conflicts WHERE job_id=? AND resolved_at IS NULL ORDER BY id", (job_id,)
            )
        ]
        return application

    def get_application(self, job_id):
        with self._connection() as connection:
            return self._application(connection, job_id)

    def get_application_history(self, job_id, offset=0, limit=25):
        """Application events and retained browser versions, newest first.

        limit=None returns every item for an authenticated export. Older resolved
        imports have an unknown resolution snapshot, explicitly marked as such.
        """
        offset = max(0, int(offset))
        limit = None if limit is None else max(1, min(int(limit), 100))
        with self._connection() as connection:
            application = self._application(connection, job_id)
            if application is None:
                return None
            items = list(application.get('history', []))
            for row in connection.execute('SELECT * FROM import_conflicts WHERE job_id=? ORDER BY id', (job_id,)):
                resolution = json.loads(row['resolution_json']) if row['resolution_json'] else None
                items.append({'type': 'import_version', 'id': row['id'], 'at': row['resolved_at'] or row['created_at'],
                              'created_at': row['created_at'], 'resolved_at': row['resolved_at'],
                              'incoming': json.loads(row['data_json']), 'resolution': resolution,
                              'resolution_status': 'resolved' if row['resolved_at'] else 'unresolved',
                              'resolution_snapshot_available': resolution is not None})
        items.sort(key=lambda item: (item.get('at') or '', item.get('revision', 0), item.get('id', 0)), reverse=True)
        return {'job_id': job_id, 'total': len(items), 'offset': offset, 'limit': limit,
                'items': items[offset:] if limit is None else items[offset:offset + limit]}

    application_history = get_application_history

    def list_applications(self, stage=None):
        if stage and stage not in STAGES:
            raise ValueError("Unknown application stage")
        with self._connection() as connection:
            query = "SELECT job_id FROM applications"
            arguments = ()
            if stage:
                query += " WHERE stage=?"
                arguments = (stage,)
            query += " ORDER BY updated_at DESC, job_id"
            return [self._application(connection, row[0]) for row in connection.execute(query, arguments).fetchall()]

    @staticmethod
    def _new_application(connection, job_id, now, snapshot=None):
        row = connection.execute("SELECT data_json FROM jobs WHERE id=?", (job_id,)).fetchone()
        return {
            "job_id": job_id, "revision": 0, "stage": "Saved", "notes": "",
            "next_action": "", "follow_up_date": "", "outcome": "", "drafts": {},
            "applied_at": None, "created_at": now, "updated_at": now, "history": [],
            "job_snapshot": json.loads(row[0]) if row else (snapshot or {
                "id": job_id, "col_01_id": job_id, "title": "Listing unavailable", "unavailable": True,
            }),
        }

    @staticmethod
    def _persist_application(connection, application):
        stored = {key: value for key, value in application.items() if key != "import_conflicts"}
        connection.execute(
            "INSERT INTO applications(job_id,revision,stage,data_json,updated_at) VALUES(?,?,?,?,?) "
            "ON CONFLICT(job_id) DO UPDATE SET revision=excluded.revision,stage=excluded.stage,"
            "data_json=excluded.data_json,updated_at=excluded.updated_at",
            (stored["job_id"], stored["revision"], stored["stage"], _json(stored), stored["updated_at"]),
        )

    @staticmethod
    def _validate_payload(payload):
        if not isinstance(payload, dict):
            raise ValueError("Application changes must be an object")
        if type(payload.get("expected_revision")) is not int or payload["expected_revision"] < 0:
            raise ValueError("expected_revision must be a non-negative integer")
        if set(payload) - _APPLICATION_FIELDS:
            raise ValueError("Unsupported application fields: " + ", ".join(sorted(set(payload) - _APPLICATION_FIELDS)))
        result = dict(payload)
        if "stage" in result and result["stage"] not in STAGES:
            raise ValueError("Unknown application stage")
        for field in _TEXT_FIELDS:
            if field in result and not isinstance(result[field], str):
                raise ValueError(f"{field} must be text")
        if "follow_up_date" in result:
            value = result["follow_up_date"]
            if value is None:
                result["follow_up_date"] = ""
            elif value != "":
                if not isinstance(value, str):
                    raise ValueError("follow_up_date must use YYYY-MM-DD")
                try:
                    if date.fromisoformat(value).isoformat() != value:
                        raise ValueError("Non-canonical date")
                except ValueError as exc:
                    raise ValueError("follow_up_date must use YYYY-MM-DD") from exc
        if "drafts" in result:
            drafts = result["drafts"]
            if not isinstance(drafts, dict) or set(drafts) - _DRAFT_FIELDS or not all(isinstance(v, str) for v in drafts.values()):
                raise ValueError("drafts accepts recruiter_message and cover_letter text")
        if "applied_at" in result:
            result["applied_at"] = _timestamp(result["applied_at"], "applied_at")
        if "resolve_import_conflicts" in result:
            values = result["resolve_import_conflicts"]
            if not isinstance(values, list) or not all(type(value) is int for value in values):
                raise ValueError("resolve_import_conflicts must be a list of conflict IDs")
        return result

    def put_application(self, job_id, payload):
        _job_id({"id": job_id})
        changes = self._validate_payload(payload)
        now = _now()
        with self._connection(write=True) as connection:
            current = self._application(connection, job_id)
            if changes["expected_revision"] != (current["revision"] if current else 0):
                raise Conflict(current)
            application = current or self._new_application(connection, job_id, now)
            previous_stage = application["stage"] if current else None
            changed_fields = []
            for key, value in changes.items():
                if key in {"expected_revision", "resolve_import_conflicts"}:
                    continue
                if key == "drafts":
                    value = {**application["drafts"], **value}
                if application.get(key) != value:
                    changed_fields.append(key)
                application[key] = value
            if changes.get("stage") == "Applied" and not application["applied_at"]:
                application["applied_at"] = now
                changed_fields.append("applied_at")
            resolved = changes.get("resolve_import_conflicts", [])
            for conflict_id in resolved:
                resolution = {key: application.get(key) for key in
                              ('stage', 'notes', 'drafts', 'next_action', 'follow_up_date', 'outcome', 'applied_at')}
                resolution.update(revision=application['revision'] + 1, resolved_at=now,
                                  method='reviewed_application', changed_fields=sorted(set(changed_fields)))
                cursor = connection.execute(
                    "UPDATE import_conflicts SET resolved_at=?,resolution_json=? WHERE id=? AND job_id=? AND resolved_at IS NULL",
                    (now, _json(resolution), conflict_id, job_id),
                )
                if not cursor.rowcount:
                    raise ValueError("Import conflict is missing or already resolved")
            application["revision"] += 1
            application["updated_at"] = now
            application["history"].append({
                "at": now, "type": "created" if current is None else "updated",
                "revision": application["revision"], "from_stage": previous_stage,
                "stage": application["stage"], "changed_fields": sorted(set(changed_fields)),
                **({"resolved_import_conflicts": resolved} if resolved else {}),
            })
            self._persist_application(connection, application)
            return self._application(connection, job_id)

    def import_applications(self, records):
        """Import browser data once per content hash; preserve conflicts verbatim."""
        if isinstance(records, dict):
            entries = list(records.items())
        elif isinstance(records, list):
            entries = [((item.get("job_id") or item.get("id")) if isinstance(item, dict) else None, item) for item in records]
        else:
            raise ValueError("Import requires an ID mapping or a list of applications")
        result = {"imported": 0, "unchanged": 0, "conflicts": [], "errors": []}
        for job_id, record in entries:
            try:
                _job_id({"id": job_id})
                if not isinstance(record, dict):
                    raise ValueError("Imported application must be an object")
                fingerprint = hashlib.sha256(_json({"job_id": job_id, "record": record}).encode("utf-8")).hexdigest()
                incoming = self._normalize_import(record)
            except (ValueError, TypeError) as exc:
                result["errors"].append({"job_id": job_id, "message": str(exc)})
                continue
            now = _now()
            with self._connection(write=True) as connection:
                receipt = connection.execute("SELECT result FROM import_receipts WHERE fingerprint=?", (fingerprint,)).fetchone()
                if receipt:
                    result["unchanged"] += 1
                    if receipt[0] == "conflict":
                        conflict = connection.execute("SELECT id,data_json FROM import_conflicts WHERE fingerprint=? AND resolved_at IS NULL", (fingerprint,)).fetchone()
                        if conflict:
                            result["conflicts"].append({"id": conflict[0], "job_id": job_id, "incoming": json.loads(conflict[1])})
                    continue
                current = self._application(connection, job_id)
                if current is None:
                    snapshot = record.get("job_snapshot")
                    if not isinstance(snapshot, dict):
                        snapshot = None
                    application = self._new_application(connection, job_id, now, snapshot)
                    application.update(incoming)
                    application.update({"revision": 1, "created_at": incoming.pop("created_at", now), "updated_at": now})
                    application["history"] = [{"at": now, "type": "imported", "revision": 1,
                                               "stage": application["stage"], "legacy_status": record.get("status")}]
                    self._persist_application(connection, application)
                    outcome = "imported"
                    result["imported"] += 1
                elif all(current.get(key) == value for key, value in incoming.items() if key != "created_at"):
                    outcome = "unchanged"
                    result["unchanged"] += 1
                else:
                    # Importing another browser cannot overwrite the server, even when
                    # its savedAt is newer: that date does not establish edit ordering.
                    conflict_payload = {"application": incoming, "original": record}
                    cursor = connection.execute(
                        "INSERT INTO import_conflicts(job_id,fingerprint,data_json,created_at) VALUES(?,?,?,?)",
                        (job_id, fingerprint, _json(conflict_payload), now),
                    )
                    current["revision"] += 1
                    current["updated_at"] = now
                    current["history"].append({"at": now, "type": "import_conflict", "revision": current["revision"], "conflict_id": cursor.lastrowid})
                    self._persist_application(connection, current)
                    outcome = "conflict"
                    result["conflicts"].append({"id": cursor.lastrowid, "job_id": job_id, "incoming": conflict_payload})
                connection.execute("INSERT INTO import_receipts VALUES(?,?,?,?)", (fingerprint, job_id, outcome, now))
        return result

    @staticmethod
    def _normalize_import(record):
        legacy_stage = record.get("stage") or record.get("status") or "Saved"
        stage = {"Ready": "Preparing", "Drafted": "Preparing", "Rejected": "Closed",
                 "Withdrawn": "Closed", "Archived": "Closed"}.get(legacy_stage, legacy_stage)
        if stage not in STAGES:
            raise ValueError(f"Unrecognized imported stage: {legacy_stage}")
        payload = {"expected_revision": 0, "stage": stage}
        for key in (_TEXT_FIELDS | {"follow_up_date", "drafts", "applied_at"}):
            if key in record:
                payload[key] = record[key]
        payload.setdefault("notes", "")
        if legacy_stage in {"Rejected", "Withdrawn", "Archived"}:
            payload.setdefault("outcome", legacy_stage)
        incoming = Store._validate_payload(payload)
        incoming.pop("expected_revision")
        saved_at = record.get("created_at") or record.get("savedAt")
        if saved_at:
            incoming["created_at"] = _timestamp(saved_at, "savedAt")
        return incoming

    def get_meta(self, key, default=None):
        with self._connection() as connection:
            row = connection.execute("SELECT value_json FROM metadata WHERE key=?", (key,)).fetchone()
            return json.loads(row[0]) if row else default

    def set_meta(self, key, value):
        with self._connection(write=True) as connection:
            connection.execute("INSERT INTO metadata VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json", (key, _json(value)))

    def record_sync(self, payload):
        with self._connection(write=True) as connection:
            return connection.execute("INSERT INTO sync_history(data_json,recorded_at) VALUES(?,?)", (_json(payload), _now())).lastrowid

    def get_sync_history(self, limit=100):
        with self._connection() as connection:
            return [{**json.loads(row["data_json"]), "id": row["id"], "recorded_at": row["recorded_at"]}
                    for row in connection.execute("SELECT * FROM sync_history ORDER BY id DESC LIMIT ?", (max(1, min(int(limit), 1000)),))]

    def record_source_evidence(self, job_id, source, payload):
        with self._connection(write=True) as connection:
            return connection.execute("INSERT INTO source_evidence(job_id,source,data_json,captured_at) VALUES(?,?,?,?)", (job_id, source, _json(payload), _now())).lastrowid

    def get_source_evidence(self, job_id):
        with self._connection() as connection:
            return [{"id": row["id"], "source": row["source"], "payload": json.loads(row["data_json"]), "captured_at": row["captured_at"]}
                    for row in connection.execute("SELECT * FROM source_evidence WHERE job_id=? ORDER BY id DESC", (job_id,))]

    def get_source_evidence_page(self, job_id, offset=0, limit=10):
        with self._connection() as connection:
            total = connection.execute('SELECT COUNT(*) FROM source_evidence WHERE job_id=?',(job_id,)).fetchone()[0]
            items = [{'id':row['id'],'source':row['source'],'payload':json.loads(row['data_json']),'captured_at':row['captured_at']}
                     for row in connection.execute('SELECT * FROM source_evidence WHERE job_id=? ORDER BY id DESC LIMIT ? OFFSET ?', (job_id,limit,offset))]
            return {'total':total,'items':items,'offset':offset,'limit':limit}

    @staticmethod
    def verify_database(path):
        """Read-only integrity and logical content manifest for restore verification."""
        uri = Path(path).resolve().as_uri() + "?mode=ro"
        connection = sqlite3.connect(uri, uri=True)
        try:
            integrity = [row[0] for row in connection.execute("PRAGMA integrity_check")]
            if integrity != ["ok"]:
                raise ValueError("SQLite integrity check failed: " + "; ".join(integrity))
            counts, digests = {}, {}
            tables = [row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
            for table in tables:
                # Include future additive tables in full-content restore checks.
                quoted = table.replace('"', '""')
                digest = hashlib.sha256()
                count = 0
                for row in connection.execute(f'SELECT * FROM "{quoted}" ORDER BY ' + ','.join(str(i+1) for i in range(len(connection.execute(f'PRAGMA table_info("{quoted}")').fetchall())))):
                    digest.update(_json(tuple(row)).encode("utf-8"))
                    digest.update(b'\n')
                    count += 1
                counts[table] = count
                digests[table] = digest.hexdigest()
            return {"integrity": "ok", "counts": counts, "digests": digests}
        finally:
            connection.close()

    @staticmethod
    def restore_backup(source, destination):
        """Restore to a new path and compare every persisted table with the backup.

        Refusing to overwrite an existing database prevents replacing an active
        server's database beneath open connections. Restore deployment is explicit.
        """
        source, destination = Path(source).resolve(), Path(destination).resolve()
        expected = Store.verify_database(source)
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("xb"):
            pass
        src = sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)
        dst = sqlite3.connect(destination)
        try:
            src.backup(dst)
        finally:
            src.close()
            dst.close()
        actual = Store.verify_database(destination)
        if actual != expected:
            raise ValueError("Restored database does not match the backup")
        return {**actual, "path": str(destination), "restoration_verified": True}

    def backup(self, path):
        """Create a consistent backup and rehearse its restoration to a temp DB."""
        destination = Path(path).resolve()
        if destination == self.path:
            raise ValueError("Backup destination must differ from the live database")
        destination.parent.mkdir(parents=True, exist_ok=True)
        # Backups are immutable snapshots; callers select their retention policy.
        with destination.open("xb"):
            pass
        with self._connection() as src:
            dst = sqlite3.connect(destination)
            try:
                src.backup(dst)
            finally:
                dst.close()
        with tempfile.TemporaryDirectory(prefix="career-restore-") as temporary:
            result = self.restore_backup(destination, Path(temporary) / "restored.sqlite3")
        return {**result, "path": str(destination)}
