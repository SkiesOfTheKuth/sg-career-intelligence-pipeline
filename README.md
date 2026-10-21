# SG Career Intelligence

Private Singapore job discovery and application tracking for Dechsurang. FastAPI serves a plain HTML/CSS/JavaScript workspace; SQLite is the authoritative store.

## Run

Install `requirements.txt`, set `AUTH_USERNAME`, `AUTH_PASSWORD`, and optionally `DATABASE_PATH`, then run `uvicorn app:app --host 127.0.0.1 --port 8000 --workers 1`. Existing login defaults are preserved for compatibility. The local database defaults to `data/career.sqlite3`.

First startup imports every ID in `processed_master_jobs.json`, repairing facts against retained source URLs and identifiers in `mcf_jobs_raw.json`, `apify_jobs_raw.json`, and `cultjobs_raw.json`. Source text remains complete where retained; partial search snippets and unmatched excerpts are identified. The legacy input remains an archival migration source, not presentation data. Subsequent startups use SQLite without overwriting collected updates.

## Render

`render.yaml` records the native single-instance setup: Starter service, Singapore, one Uvicorn worker, 1 GB disk mounted at `/var/data`, and `DATABASE_PATH=/var/data/career.sqlite3`. The existing Render service is `srv-dbb3dfnf3r2c73848abg`. A persistent disk requires a brief stop/start during deployment. Live configuration is managed through Render's documented service, environment-variable, and disk APIs.

## Data and recovery

Applications use revision-checked writes. `409` responses include the current server copy; browser edits remain in local recovery until acknowledgement. A first note creates a Saved application. Closed applications preserve notes, outcome, job snapshot, drafts, and stage history. Existing `sg_career_shortlist_v2` browser data imports automatically using content-hash receipts; differing notes/stages are preserved for review.

SQLite uses WAL, FULL synchronous writes, and explicit write transactions. A consistent backup and a full restore rehearsal run on initial migration, after each 12-hour refresh, on graceful shutdown, and through authenticated `GET /api/backup`. Three recent snapshots are retained under `/var/data/backups`; the disk itself also has Render's daily snapshots. SQLite backups are the database recovery source. `Store.restore_backup(source, new_destination)` refuses to overwrite an existing database, restores via SQLite's backup API, and compares row counts and content digests of every table. To restore a service, place the verified restored database on its persistent disk, set Render's native `DATABASE_PATH` to that new path, and redeploy.

The refresh schedule is stored in SQLite and owned by the FastAPI lifespan. Overdue work resumes after restart. Only the free MyCareersFuture API is refreshed automatically; existing LinkedIn, Indeed, Cultjobs, and search-result evidence remains labelled for recheck. A limited search result cannot establish closure of an absent listing. Failed checks preserve prior facts and successful verification times, and record source errors. No paid scraping is introduced.

## Sources audit

The authenticated `/sources` page maps sources → retained evidence and assessment → discovery and applications. Counts come from SQLite, not raw import file sizes. Select a source to inspect collection method, scope, dates and failures. Coverage shows exact counts for retained descriptions, requirements, salary and successful checks within 24 hours. Search, filter and paginate records; open an inspector for cleaned fields, original URLs, collector query context, the score breakdown and paginated retained payload versions. Historical collector records can contain inserted defaults; the inspector explicitly distinguishes them from employer facts. Payloads render as text and credential-like keys are redacted.

`GET /api/audit/sources`, `GET /api/audit/records` and `GET /api/audit/records/{job_id}` require the existing login. The last 100 collection runs expose per-query success/error evidence. Manual checks use the same `POST /api/sync` path as automatic work: four MyCareersFuture searches (Thai, Marketing Executive, Social Media Executive, Public Relations), up to ten results per search. This is not continuous monitoring or a recheck of all stored vacancies. An in-flight task survives request cancellation; graceful shutdown waits for it, and an interrupted-run marker triggers a retry after a hard restart.

## Assessment and exports

Assessments are reading aids grounded in the verified résumé. Relevant requires supported family alignment and mandatory requirements. Unknown requirements and incomplete source text remain Check requirements; unsupported mandatory language and specialist accounting requirements prevent top recommendations. Company geography and search queries cannot imply Thai requirements. Historical fixed check dates are identified as source-record dates, not new verification.

The `documented-fit-v1` score in `fit_score.py` uses a visible policy: role family 20 points, distinct documented responsibility overlap 50, explicitly supported mandatory requirements 30. Every supported duty/requirement quotes the listing and cites CV evidence. Repeated supported task groups count once. Unknowns earn no points, which means unproven rather than incapable. Missing required language/qualification/experience or seniority evidence caps the total at 39; unresolved/missing mandatory requirements, unclear duty sections or an adjacent family cap it at 59. Incomplete descriptions or no identifiable duties withhold the score. Preferred qualifications are listed without adding points. Pay, prestige, geography and freshness never increase fit. Scores are provisional where evidence is unresolved, are not empirically calibrated hiring probabilities, and can miss nuances in unusual source wording. The breakdown exposes that uncertainty for review. Recommendation order uses fit groups then documented score; all APIs and exports derive the same current version at read time without modifying retained source payloads.

FastAPI lifespan prepares bounded in-memory assessment caches before readiness. This keeps the first user's search from paying the full initial assessment cost. Cache keys include the source text and requirements; changed source evidence is assessed again automatically.

Salary thresholds use advertised SGD minimums. Annual pay including `/yr` is normalized to monthly equivalents. Daily/hourly rates remain in their original units; unverified currencies and units cannot satisfy a monthly SGD filter. No minimum salary is assumed.

Search and export use one server filter function. Application export supports selected IDs and stage, and includes notes, next action, follow-up date, original link, drafts, outcome, and history. All CSV and Excel exports protect against formula injection. `generate_workbook.py` creates offline exports through the same presentation/export code.

## Verification

Run `python -m unittest test_storage test_audit_qa test_evidence test_sync test_source_audit -q` plus `node --check` on `static/workspace.js`, `static/sources.js`, and `static/fit-score.js`. Tests cover access control, source repair, scored evidence and unknowns, misleading language/finance matches, nonstandard headings, salary units, export selection/injection, source failure and upserts, lifecycle recovery, revision conflicts, idempotent migration, snapshots, and backup restoration. Browser QA artifacts are local under `output/playwright/` and are not committed.

Official references: [FastAPI lifespan](https://fastapi.tiangolo.com/advanced/events/), [SQLite backup](https://docs.python.org/3/library/sqlite3.html#sqlite3.Connection.backup), [Render disks](https://render.com/docs/disks), [Render Blueprint specification](https://render.com/docs/blueprint-spec), [Render disk API](https://api-docs.render.com/reference/add-disk).
