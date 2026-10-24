# Authorized seven-day collection campaign

## One-day incremental burst — 24 October 2026

The current approved burst adds an **incremental US$150 actor-charge target**, with a **US$200 soft ceiling on retained reservations plus observed ancillary usage**, during the current Asia/Singapore calendar day. It retains campaign `720b9812a4344cf2b32c0fc10149c5f3`, its original ledger, US$350 overall ceiling (US$315 actor commitments), and **30 October 2026, 21:37:21 SGT** deadline. The day ends at **25 October 2026, 00:00 SGT**. The launch baseline is captured transactionally; the earlier US$15.48 estimate is historical, not the incremental baseline.

| Source | Initial target allocation | Initial soft allocation |
| --- | ---: | ---: |
| Indeed | US$70 | US$95 |
| LinkedIn | US$64 | US$84 |
| Google | US$1 | US$1 |
| Career validation/rechecks | US$15 | US$20 |

These allocations are ceilings, not spending obligations. Existing `APIFY_TOKENS_JSON` credentials only are permitted, deduplicated by verified account ID. No new credentials, upgrades, changed account limits or cash overages. Live free-plan credit capacity, prior retained reservations, ancillary usage and a US$0.15 account buffer establish the hard admission limit. The fresh 24 October preflight found 33 distinct accounts with approximately US$83.95 positive raw credit headroom; conservative commitments reduce usable capacity further. The US$150 target can underfill and must never cause an overage.

Schema v5 adds `campaign_bursts`, source allocations, immutable tranche outcomes, allocation events, query identities, and nullable burst tags on batches. Exact inputs, raw responses, original IDs, application snapshots, fit scores and import checkpoints are preserved. `POST /api/campaign/burst` takes only `{"burst_id":"one-day-20261024"}` under existing authentication and same-origin controls. Repeating that ID returns the same burst; a second burst for the campaign is rejected. `/api/campaign/report` and Sources expose actual incremental actor charges, retained exposure, ancillary/shared-account usage, capacity, shortfall, source outcomes and reallocation evidence separately.

Two queries form a LinkedIn/Indeed tranche. Inputs interleave unused role-family, skill, industry, seniority, employer and agency combinations. A normalized identity journal prevents repeated searches across history and restarts. Each query remains capped at 100 results and optional enrichments stay disabled. After two exploratory tranches per source, the latest completed tranche ranks sources by new supported vacancies per charged dollar, then duplicate/lead ratio. Two consecutive completed tranches with zero new supported vacancies and over 80% duplicate/lead outcomes stop that source; only its uncommitted target/soft allocation transfers to the other eligible role source. Beyond a source target, new expansion needs fresh supported vacancies in its latest tranche. At US$150 charged, queued work may finish and new expansions require the same fresh-evidence rule; total exposure stays below US$200.

Google remains bounded to two production batches of at most 20 distinct queries and three pages per query per SGT day, including earlier campaign work. Both production batches were already consumed on 24 October, so this burst adds no Google calls that day. Its discovery allocation is preserved. A minimum US$2 career-validation slice is protected when useful queued work exists. Career crawling keeps the existing 20-new-domain/day, depth-two and 50-page/domain bounds; saved non-closed applications precede oldest checks, then discovered pages. Unlaunched durable career batches can join the burst without changing their exact payload or checkpoint. Returned career links retain parent evidence in the queue. Search snippets remain leads.

The native lifespan worker enforces two outstanding runs globally, one per account, at most US$2 per batch, and a finite timeout bounded by the earlier of burst midnight and campaign deadline. Account failures, verified capacity, overall/soft limits or window expiry stop new paid burst launches; obtained datasets continue importing. Completed caps stay committed. While the burst day is open, ordinary paid admissions wait; after the window the original rolling US$45 actor/US$50 total and source policies apply automatically, including retained burst commitments until they age out normally. No deployment, restart or idempotent call resets a clock or ledger. Ancillary observations cover the burst window and can include unrelated shared-account usage; they are not described as actor charges.

The user-approved plan of 23 October 2026, corrected on 24 October, supersedes the previous paid-collection/new-source restriction for this campaign only. It authorizes deployment to the existing Render service, native secret configuration, a US$3 isolated pilot allowance, up to US$50 per rolling 24 hours and US$350 overall, and disk growth only when needed, at most 10 GB. It does not authorize messages, applications, account upgrades, cash overages or credential rotation.

The correction removes source-access/robots admission restrictions, private-network/redirect rejection, and the prerequisite to verify remote actor network isolation. Local robots, DNS and redirect admission checks and the unconditional career-crawler block are removed. The official crawler's optional `respectRobotsTxtFile` input is `false`. URL canonicalization serves identity and deduplication only. Previous observations of these gates are superseded historical records; they cannot block current actor submission. Provider authentication, invalid input, access denial and runtime failures remain real outcomes and are recorded separately.

The immutable 168-hour clock began with the first paid pilot launch intent on **23 October 2026, 21:37:21 SGT** and stops on **30 October 2026, 21:37:21 SGT**. Neither supplemental validation, a failed or ambiguous launch, migration nor restart resets the clock or spending ledger. The native Apify run timeout is capped at the remaining campaign time (with a five-second margin); the worker also requests aborts after pause/expiry. Obtained datasets continue importing after paid collection stops. MyCareersFuture continues independently.

## Native architecture and accounting

FastAPI lifespan owns one campaign loop on the existing Render service and persistent SQLite disk. No desktop scheduler, Apify schedule, extra cron service, launch wrapper or separate service accesses the disk. SQLite transactions persist the scheduler lease, due times, immutable account references, launch intents, reservations, remote run IDs, raw dataset items, import checkpoints, discovery edges and counts. Application tables are never changed by this collector.

Apify tokens are read only from Render's native `APIFY_TOKENS_JSON` secret environment variable (a JSON array of the existing tokens). The database retains SHA-256 references and verified account IDs, never tokens. Account identity is deduplicated. Current usage, current free-plan included credits and hard limits are checked before admission. A configured usage limit is **not** a credit balance. Unverified promotional balances and expiry dates remain unknown. The code never changes an account, subscription, payment method or limit.

Money uses integer millionths of a US dollar. The transaction that commits launch intent first reserves the batch cap, at most US$2. The API receives `maxTotalChargeUsd`, a pinned build, bounded actor inputs, a finite timeout and `restartOnError=false`. Two paid runs can be outstanding globally and one per account. Uncertain launches retain their reservation and account slot until a unique remote actor/time/cap/INPUT match establishes the outcome. Missing or multiple matches never cause an automatic relaunch.

Actor commitments are limited to US$45 per rolling day, US$315 over the campaign, and initial source allowances of US$8 LinkedIn, US$22 Indeed, US$3 Google and US$12 career pages. US$35 of the overall ceiling remains for ancillary charges. Pilot actor commitments are at most US$2.50, with US$0.50 held for ancillary charges inside its US$3 limit. Completed batches retain their original cap in admission accounting: unused caps are deliberately not recycled. Outstanding commitments never age out of the rolling window; completed commitments age out 24 hours after completion. Reported run charges and observed account usage are separate, visibly labelled values. All observed account usage above known run charges counts as ancillary or unreconciled usage, including unrelated activity on shared accounts. Accounting failures block admissions.

Disk checks reserve at least 256 MiB, or three database sizes plus 128 MiB, whichever is larger, beyond existing files. This protects room for backups, restoration, WAL and application writes. Low capacity pauses collection and imports. Disk expansion uses Render's native disk API outside the application, after measuring current capacity, never beyond the authorized 10 GB.

## Source contracts and collection paths

`campaign_contracts.json` captures the official current input schemas and pricing inspected on 23 October. Before use, the actor metadata, pinned build schema and pricing must still match. Historical collector payloads are not reused blindly.

| Source | Bound | Validation and scheduling |
| --- | --- | --- |
| MyCareersFuture | Existing four queries × ten results, every 12 hours | Preserved |
| LinkedIn | Four core plus four rotating historical Singapore queries every six hours; at most 100 results/query; company enrichment off | Source-specific isolated validation before recurring activation |
| Indeed | Same eight-query cycle; `country=SG`, `location=Singapore`, `maxItemsPerSearch=100`; company enrichment/apply redirects off | Existing validated callers and activation remain compatible |
| Google | Up to 40 distinct daily role/employer/agency queries, three pages each; two batches of at most 20 queries, US$0.50 reserved each; optional AI, content and contact enrichment off | Isolated validation requires returned search-result evidence, not vacancies; US$0.50 satisfies the actor minimum |
| Career websites | Up to 20 new domains/day, discovery depth two, 50 pages/domain; batch by domain/depth, at most US$0.50/run | Official Website Content Crawler; source-specific isolated validation before recurring activation |
| Cultjobs | Dated import | Consent requirement unresolved; no campaign crawling |

The crawler uses documented output links and page evidence, with optional robots handling disabled and optional AI, files and screenshots disabled. The durable SQLite queue owns recursion, domain/page allowances and parent evidence across restarts. Listing rechecks prioritize non-closed saved applications, then rotate other listings by oldest successful check within the same source allowances. Google results lead to career pages; returned career links feed later depth batches. Only returned evidence supplying the role, employer, Singapore location and vacancy description supports promotion. Search snippets and ambiguous pages remain inspectable leads.

Migration supersedes only unlaunched historical search batches blocked solely by the removed policy and schedules one current cycle; career entries blocked for that reason return to the queue. Completed runs, reservations, import checkpoints and genuine provider failures remain unchanged. Historical policy reasons remain labelled superseded, rather than erased or mistaken for provider failures.

Source omissions preserve retained facts and original field provenance. Source identifiers or canonical listing URLs preserve existing IDs. Possible title/company matches are flagged, not merged. Non-Singapore/ambiguous results and search snippets are retained as leads, never promoted by a search query alone. Raw payloads are exact JSON values in checkpointed journals; promoted vacancies also retain source evidence versions. Discovery dates have their own ordering and do not affect employer posting dates or documented-fit scores. Missing results never close a listing.

## Authenticated controls and rollout

`GET /api/campaign`, `/api/campaign/report`, `/api/campaign/leads`, and `/api/campaign/pilot-evidence` expose bounded, credential-redacted evidence. `POST /api/campaign/pause` pauses paid admissions and requests active-run aborts while imports continue. Sources exposes the stop time, heartbeat, source due times and outcomes, production counts separately from isolated validation, inspectable leads and parent evidence, and separate charge/commitment totals. The campaign disclosure follows record search on phones. Newly discovered ordering is available in Find roles and shared export filters; collection and employer posting dates remain separate.

The administrative lifecycle is `POST /api/campaign/prepare`, then `/api/campaign/pilot`, then `/api/campaign/activate` with a verified pilot evidence reference. Pilot and activation accept a source; omitting it preserves existing Indeed callers. Supplemental validation uses the existing pilot allowance and campaign budget without changing an active production campaign into pilot mode. Validation results remain isolated in `campaign_pilot_jobs` and `campaign_items`; they do not become production jobs/evidence or production queue work. Activation requires a successful imported validation with source-appropriate evidence, reconciled recorded cost, a verified backup and matching actor contracts. Only validated sources are eligible. Repeating preparation or a request after a lost response cannot create a second campaign or duplicate its pilot.

Verification must cover explicit removed-gate submission regressions, source-specific validation, Google's minimum cap, career extraction/recursive bounds, duplicate imports, restart recovery, budget/deadline enforcement and authenticated responsive evidence inspection. Capture a fresh production backup and rehearse full-content restoration of applications, notes, drafts, snapshots and history before deployment. Isolated tests cannot establish live provider acceptance, two unattended six-hour cycles, a daily discovery/crawl cycle, restart recovery in production or the final deadline shutdown. These remain evidence-based acceptance requirements in `ACCEPTANCE_REPORT.md`; the campaign is not complete until the full requested workflow is demonstrated.

## Authoritative references inspected

- Apify run API: https://docs.apify.com/api/v2/act-runs-post
- Apify account usage: https://docs.apify.com/api/v2/users-me-usage-monthly-get
- Apify limits: https://docs.apify.com/api/v2/users-me-limits-get
- Actor schemas: https://apify.com/curious_coder/linkedin-jobs-scraper/input-schema ; https://apify.com/misceres/indeed-scraper/input-schema ; https://apify.com/apify/google-search-scraper/input-schema ; https://apify.com/apify/website-content-crawler/input-schema
- FastAPI lifespan: https://fastapi.tiangolo.com/advanced/events/
- SQLite transactions/backup: https://docs.python.org/3/library/sqlite3.html
- Render native secrets and disks: https://render.com/docs/configure-environment-variables ; https://render.com/docs/disks
- Render environment API: https://api-docs.render.com/reference/update-env-var
