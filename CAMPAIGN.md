# Authorized seven-day collection campaign

The user-approved plan of 23 October 2026 supersedes the previous paid-collection/new-source restriction for this campaign only. It authorizes deployment to the existing Render service, native secret configuration, a US$3 isolated pilot, up to US$50 per rolling 24 hours and US$350 overall, and disk growth only when needed, at most 10 GB. It does not authorize messages, applications, account upgrades, cash overages, credential rotation or bypassing source restrictions.

The immutable 168-hour clock begins when the first paid pilot launch intent is committed. A failed or ambiguous launch cannot reset that clock. The first reservation therefore starts the clock conservatively even if the remote launch ultimately fails. The native Apify run timeout is capped at the remaining campaign time (with a five-second margin); the worker also requests aborts after pause/expiry. Obtained datasets continue importing after paid collection stops. MyCareersFuture continues independently.

## Native architecture and accounting

FastAPI lifespan owns one campaign loop on the existing Render service and persistent SQLite disk. No desktop scheduler, Apify schedule, extra cron service, launch wrapper or separate service accesses the disk. SQLite transactions persist the scheduler lease, due times, immutable account references, launch intents, reservations, remote run IDs, raw dataset items, import checkpoints, discovery edges and counts. Application tables are never changed by this collector.

Apify tokens are read only from Render's native `APIFY_TOKENS_JSON` secret environment variable (a JSON array of the existing tokens). The database retains SHA-256 references and verified account IDs, never tokens. Account identity is deduplicated. Current usage, current free-plan included credits and hard limits are checked before admission. A configured usage limit is **not** a credit balance. Unverified promotional balances and expiry dates remain unknown. The code never changes an account, subscription, payment method or limit.

Money uses integer millionths of a US dollar. The transaction that commits launch intent first reserves the batch cap, at most US$2. The API receives `maxTotalChargeUsd`, a pinned build, bounded actor inputs, a finite timeout and `restartOnError=false`. Two paid runs can be outstanding globally and one per account. Uncertain launches retain their reservation and account slot until a unique remote actor/time/cap/INPUT match establishes the outcome. Missing or multiple matches never cause an automatic relaunch.

Actor commitments are limited to US$45 per rolling day, US$315 over the campaign, and initial source allowances of US$8 LinkedIn, US$22 Indeed, US$3 Google and US$12 career pages. US$35 of the overall ceiling remains for ancillary charges. Pilot actor commitments are at most US$2.50, with US$0.50 held for ancillary charges inside its US$3 limit. Completed batches retain their original cap in admission accounting: unused caps are deliberately not recycled. Outstanding commitments never age out of the rolling window; completed commitments age out 24 hours after completion. Reported run charges and observed account usage are separate, visibly labelled values. All observed account usage above known run charges counts as ancillary or unreconciled usage, including unrelated activity on shared accounts. Accounting failures block admissions.

Disk checks reserve at least 256 MiB, or three database sizes plus 128 MiB, whichever is larger, beyond existing files. This protects room for backups, restoration, WAL and application writes. Low capacity pauses collection and imports. Disk expansion uses Render's native disk API outside the application, after measuring current capacity, never beyond the authorized 10 GB.

## Source contracts and current gates

`campaign_contracts.json` captures the official current input schemas and pricing inspected on 23 October. Before use, the actor metadata, pinned build schema and pricing must still match. Historical collector payloads are not reused blindly.

| Source | Bound | Current eligibility |
| --- | --- | --- |
| MyCareersFuture | Existing four queries × ten results, every 12 hours | Preserved |
| LinkedIn | Four core plus four rotating historical Singapore queries every six hours; `limitPerSource=100`; company enrichment off | Search path disallowed by current public robots directives; blocked |
| Indeed | Same eight-query cycle; `country=SG`, `location=Singapore`, `maxItemsPerSearch=100`; company enrichment/apply redirects off | Search robots allow the path; requires a successful isolated pilot before activation |
| Google | Up to 40 distinct daily role/employer/agency queries, three pages each; optional AI, content and contact enrichment off | Search path disallowed by current public robots directives; blocked |
| Career websites | Queue designed for 20 domains/day, depth two, 50 pages/domain; priority saved applications then oldest checks | Official crawler lacks a documented pre-navigation private-IP/redirect guard; crawling is blocked pending that prerequisite |
| Cultjobs | Dated import | Consent requirement unresolved; no campaign crawling |

The crawler input contract uses the official Website Content Crawler with robots enabled, no AI, cookies, proxy bypass, files or screenshots, and depth zero per separately vetted page. Recursive admission belongs to the durable queue. The public actor schema only exposes a **post-load** page function, which cannot establish prevention of unsafe navigation. The service therefore does not launch this actor while that safety prerequisite is unresolved. No claim of live recursive discovery is made. These gates are visible source outcomes, not silent failures.

The local URL admission implementation canonicalizes URLs, excludes credentials/private destinations/nonstandard ports and pins DNS for each HTTP connection. Redirects are revalidated individually. Robots denial, unavailable directives and unsupported crawl delays block access. These local checks do not claim to establish the remote actor's network isolation.

Source omissions preserve retained facts and original field provenance. Source identifiers or canonical listing URLs preserve existing IDs. Possible title/company matches are flagged, not merged. Non-Singapore/ambiguous results and search snippets are retained as leads, never promoted by a search query alone. Raw payloads are exact JSON values in checkpointed journals; promoted vacancies also retain source evidence versions. Discovery dates have their own ordering and do not affect employer posting dates or documented-fit scores. Missing results never close a listing.

## Authenticated controls and rollout

`GET /api/campaign`, `/api/campaign/report`, `/api/campaign/leads`, and `/api/campaign/pilot-evidence` expose bounded, credential-redacted evidence. `POST /api/campaign/pause` pauses paid admissions and requests active-run aborts while imports continue. Sources exposes the stop time, heartbeat, source due times, blocked reasons, new/updated/duplicate/lead counts and separate charge/commitment totals. The campaign disclosure follows record search on phones. Newly discovered ordering is available in Find roles and shared export filters.

The administrative lifecycle is `POST /api/campaign/prepare`, then `/api/campaign/pilot`, then `/api/campaign/activate` with a verified pilot evidence reference. Preparation performs only reads. Pilot results are isolated in `campaign_pilot_jobs` and `campaign_items`, not production jobs/evidence tables. Activation requires a successful imported pilot with vacancy evidence, recorded run cost, a verified backup and matching actor contracts. Only pilot-validated sources are eligible. Repeating preparation or a request after a lost response cannot create a second campaign or duplicate its pilot.

Tests: `python -m unittest test_campaign -q`. These use temporary databases and a fake API, covering concurrency, budgets, account exhaustion/unknown accounting, ambiguous launches/restart recovery, checkpoint replay, rollback, partial payloads, preserved applications, source restrictions, DNS/private URLs, cycles/depth, low disk, seven-day abort/import behavior, authentication and migration/restore. They do not establish two real six-hour unattended cycles or actual seven-day shutdown. Those remain live acceptance requirements recorded in the campaign report and `ACCEPTANCE_REPORT.md`.

## Authoritative references inspected

- Apify run API: https://docs.apify.com/api/v2/act-runs-post
- Apify account usage: https://docs.apify.com/api/v2/users-me-usage-monthly-get
- Apify limits: https://docs.apify.com/api/v2/users-me-limits-get
- Actor schemas: https://apify.com/curious_coder/linkedin-jobs-scraper/input-schema ; https://apify.com/misceres/indeed-scraper/input-schema ; https://apify.com/apify/google-search-scraper/input-schema ; https://apify.com/apify/website-content-crawler/input-schema
- FastAPI lifespan: https://fastapi.tiangolo.com/advanced/events/
- SQLite transactions/backup: https://docs.python.org/3/library/sqlite3.html
- Render native secrets and disks: https://render.com/docs/configure-environment-variables ; https://render.com/docs/disks
- Render environment API: https://api-docs.render.com/reference/update-env-var
