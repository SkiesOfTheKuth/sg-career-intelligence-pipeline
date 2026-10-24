# Campaign continuation — 24 October 2026 (acceptance pending)

The user's corrected plan removes local robots, DNS/private-network and redirect admission restrictions and remote actor isolation verification. The official crawler's optional robots setting is false; canonical URLs continue to identify and deduplicate evidence. Prior gate descriptions below are **superseded historical observations**, not current collection prerequisites. The original campaign identity, spending ledger and **30 October 2026, 21:37:21 SGT** deadline remain unchanged.

Implementation and live rollout now cover LinkedIn, Google and career crawling with source-specific isolated validation, daily Google batches at the US$0.50 minimum, persistent bounded career discovery/extraction, production versus validation counts and inspectable leads. Historical policy-blocked unlaunched work is superseded or requeued while completed runs, reservations, checkpoints and provider failures remain. The requested full workflow remains operationally pending until the unattended-cycle, restart and deadline evidence is observed.

Pre-rollout verification on 24 October: all four pinned actor/build schemas and pricing still match live Apify metadata. A fresh production backup contains 4,927 jobs, 5,744 source-evidence rows, 2,219 campaign items, 89 batches and zero server-side applications. Additive migration, repeat migration and restoration preserve complete original table content digests; nonempty notes/drafts/snapshots/history are covered by isolated regressions. The explicit full suite passes **227 tests**; all three JavaScript syntax checks pass. A 20,000-record projected search benchmark improved from 8.845 to **1.679 seconds** by avoiding redundant copies of nested read-only evidence before pagination; scoring and filter semantics remain unchanged. Artifacts are in `output/campaign/continuation/`. Live deployment and source-validation results follow separately.

Rollout correction: the first deployment omitted the schema-version increment, so existing version-3 databases skipped the new error column and campaign status failed. The initial full-content comparison proved preservation but did not prove that column existed. Version 4 now explicitly migrates that path; the regression creates a real version-3 schema, asserts the column/version, and reads status. A new production-backup rehearsal asserts both schema and all original full-content digests. The corrected deployment restored campaign APIs without resetting dates or charges. A real disposable journey also exposed a late draft-suggestion/selection race; focused draft fields now defer unused suggestions until blur and retain entered text. The complete suite now passes **231 tests** (including the campaign browser regression); the live run is recorded in `output/campaign/continuation/full-regression-live.txt`. The real-data isolated journey passes preparation, drafts, two-browser conflict resolution, closed application preservation, import history, selected export, responsive evidence and hard-restart full application equality. A 50,000-record warm-search benchmark takes **3.390 seconds**; it repeats real descriptions with distinct identities and does not simulate 50,000 unique cold scoring inputs.

Current rollout evidence: revision **3e680cd** is live through the native Render service (`healthz` healthy, campaign and sync workers alive). The active campaign remains production mode with the immutable stop time **30 October 2026, 21:37:21 SGT**, heartbeat and existing ledger; the corrected source state has no policy block. At the captured authenticated read in `output/campaign/continuation/verify-3e680cd/status-final-live.json`, live status reported US$30.20 actor commitments, US$13.95 reported run charges, US$14.07 observed account usage, 833 production supported vacancies, 1,081 production leads, 535 duplicate outcomes, 48 production runs, and no worker or accounting error; these counters continue to advance while the campaign runs. LinkedIn validation and production imports are live; Google validation retained search-result leads without vacancy promotion; the corrected career pilot returned one supported vacancy. Earlier career batches failed distinctly as `input` because Apify required its native proxy configuration. Their 21 reservations and exact errors remain preserved, while the one-time live migration created 21 queued replacements whose payloads contain `proxyConfiguration.useApifyProxy=true`; old proxy errors are not copied into replacement inputs. One corrected pilot replacement completed successfully; the 20 production replacements remain queued because the original reservations remain committed against the US$12 career allowance. Fresh live backup `output/campaign/continuation/verify-3e680cd/production-final-live.sqlite3` was captured after migration, and current health/status evidence is in that directory. A retained-lead recovery then examined 1,082 Indeed leads and promoted 948 records using exact Singapore planning-area/subzone evidence; a second shorthand pass promoted 66 more (including returned road/district names), with both checkpoints complete and no actor spend. The 2 GB disk safety pause was resolved through Render’s documented native disk update to 4 GB (`output/campaign/disk-resize-followup.json`); the campaign resumed automatically after the safety margin became true. The final live backup `output/campaign/discovery-followup/live-v2-final.sqlite3` shows schema 4, 5,815 jobs, 68 remaining Indeed leads, and completed locality recovery. Full operational acceptance still awaits two unattended six-hour cycles, the daily discovery/crawl chain, production restart recovery, charge reconciliation and final deadline shutdown/import evidence.

Current verification must distinguish local regression results from fresh production backup/restoration comparisons, deployed source validation and charge reconciliation, real returned-record journeys at 390/768/1,440 px, disposable application editing/persistence and projected-volume performance. Two unattended six-hour cycles, a daily discovery/crawl cycle, production restart recovery and actual final paid-work shutdown/import completion remain required observed evidence. Subsequent verified results belong in this current section; the earlier snapshots below do not prove today's state.

# Historical independent workspace acceptance — 23 October 2026

Verified workspace: **https://sg-career-intelligence.onrender.com**. Release **2.2.2**, deployed revision **`ef71193d68456ea4437da4433685cbf46a81a617`**, Render deployment **`dep-dbdirnp5efls73atcgh0`**, live **09:51:47 UTC / 17:51:47 SGT**. This independent audit supersedes the reports below. No substantiated critical or major defect remains after fixes, a separate reviewer, and deployed verification.

[Canonical brief](EXECUTION_BRIEF.md) · [Requirement matrix](COMPLIANCE_AUDIT.md) · [Decisions/contracts](DECISIONS.md). The original brief remains unchanged. The checkout started clean at `09ce6cbc`; existing deployed behavior and production data were independently read rather than inferred from old reports.

## What changed

- **Concurrent import recovery:** an explicit rebase no longer resubmits an import-resolution command another editor already completed. Chosen notes/stage remain, server revision checks stay strict, and the first historical resolution remains intact. Contradictory or malformed resolution acknowledgements cannot clear recovery or claim Saved.
- **History and feedback:** first save immediately exposes history; an open history refreshes on revision changes and ignores stale responses. Accepted import review reports saved and reveals Closed outcome without replacing active input/caret.
- **Evidence and ranking:** required years remain mandatory when only industry is preferred. Equivalent headings no longer enter duty totals; gerund duties remain counted; overlapping supported domains count once. Compound degree/design, leadership/research, plural EDM/channel, interview and spending scopes cannot inherit unsupported CV credit. Exact original quotes, source payloads, 20/50/30 rubric, caps and withholding remain.
- **Exports:** accepted pasted control characters no longer crash XLSX. The existing full-text sheet retains affected values as labelled, ordered JSON-string parts with reconstruction instructions and formula protection. CSV and persisted text remain unchanged; one selected application remains one main record.

Minor first-save/history/import-feedback defects are resolved. No visual redesign, new integration, schema change, credential lifecycle action, source-schedule change or production application mutation was introduced.

## Current verification

| Environment | Result and evidence |
| --- | --- |
| Explicit local suite | **170 tests passed in 28.525s**, including 33 browser regressions. `output/independent-20261023/final-regression.log`. JS syntax and git whitespace checks pass. New defect cases failed before fixes; imports were inspected and broad discovery was never run. |
| Isolated real-data browser journey | Two authenticated contexts completed discovery/evidence → prepare/edit → clipboard rejection/manual copy → original listing navigation without stage change → explicit Applied → follow-up → conflict/explicit resolution → Closed → import resolution/history → exactly one selected export with notes/draft/history. Zero page errors. `output/playwright/independent-20261023/journey-final/journey-report.json`. Listing requests were intercepted; no employer contact. |
| Recovery/failure regressions | Independent tabs, immediate close, in-flight newer keystrokes, clean/dirty refresh, timeout/401/offline, malformed acknowledgements, corruption/quota/removal errors, stale searches and export failures preserve work/selection. `editor/audit.json`, `final-review-contradictory-import-ack.json` beneath `output/independent-20261023/`. Concurrent-import regression additionally uses actual temporary SQLite. |
| Restart persistence | Hard kill/restart retained complete application JSON including notes, drafts, snapshot and history. `output/independent-20261023/restart-performance.json`. Application mutations stayed isolated. |
| CV and retained quotations | Original two-page CV hash `c4cf734637cfe8a06a214544c500c63aa61ea5d9dc93fb25391a394e86eea14f` verified. All 17 real-corpus descriptions match exact retained payloads; supported clauses/top recommendations and defensible pairwise rankings reviewed. `evidence/scoring-review.json` and `evidence/review.md`. No target score distribution or invented candidate facts. |
| Deployed evidence parity | Five targeted live assessments and generated drafts exactly match corrected local calculation, including SG-OPP-0111 (required experience), 2507 (aligned), 2839 (leadership), 2707 (interviews), 2610 (spend). `output/independent-20261023/live-assessment-parity.json`. |
| Responsive deployed browser | 390×844, 768×1000, 1440×1000: Find/details/Sources/inspector/empty Applications, no horizontal overflow, keyboard Escape and return focus pass, zero page errors/HTTP 5xx after readiness. Phone result y=415.9 / source search y=473.5. `browser-production.json`. |
| Accessibility and zoom | Axe 4.11 zero violations across 8 exercised states. Incomplete contrast checks separately measured: body/notes 16.186:1, secondary 6.421:1, decorative arrows 4.309:1. Source links 44px, reduced motion 0s; root-text 200% at all widths. Native Chromium Appearance 200% also verified: 1440×1000 window, 713×453 viewport, DPR 1.5→3, document 705px. `a11y-final.json`, `manual-accessibility.json`, `output/playwright/independent-20261023/native-zoom.json`. This is exercised coverage, not WCAG certification or participant research. |
| Separate final review | Reviewer read original brief/CV and independently reproduced heading, compound leadership, interviewing and contradictory acknowledgement defects; all fixed/reverified. `independent-final-review.json`, `final-review-fixes.json`, `independent-review-focused.log`. Root reviewed lossless export implementation/tests and final deployed screenshots. |

A resize regression initially inspected the first frame before asynchronous MatchMedia change dispatch and failed intermittently. It now waits for the observable modal/inert state; runtime behavior passed. A few local inspection scripts initially used hidden/mismatched selectors and were corrected; these failed probes were not counted as product acceptance. No paid source call or other unintended external mutation occurred in this pass. The historical paid-probe incident remains below.

## Data protection and deployed result

Fresh production capture immediately before rollout: `migration/20261023-independent/production-predeploy.sqlite3`. Native SQLite backup/restore plus two initialization passes compared **all table values, schema, user_version and sqlite_sequence**, not only counts. Rehearsal passed: `predeploy-rehearsal.json`; independent corroboration: `persistence-rehearsal.json`. No schema change was necessary.

Final snapshot `migration/20261023-independent/production-final.sqlite3` is intact: **4,406 jobs, 4,538 source-evidence versions, 7 collection histories, 0 applications/imports**. Every business row/field/payload, schema and sequence equals predeploy. Only operational `last_backup` metadata advanced; persisted next-sync time is unchanged. `output/independent-20261023/postdeploy-preservation.json`.

Existing Render service/native Git auto-deploy, one Uvicorn worker/instance and `/var/data` disk are preserved. The live runtime plan is `1c-2g` and build plan Starter; the prior README's plan shorthand was corrected without changing the service. Health is 2.2.2, scheduler alive, all served JS/CSS match the local release. Protected pages, jobs, applications/history, audit, exports and backup reject unauthenticated reads. No production PUT/POST or manual collector trigger was used in this pass.

Complete paginated search and filtered export IDs/order match for Thai/freshness (**274**), Marketing/Full-time/disclosed monthly minimum S$3,000/salary (**220**), and Freelance/title (**25**). `final-live.json`, `deployment.json`, `postdeploy-preservation.json` under `output/independent-20261023/`.

Local warm API measurements on 4,406 retained jobs: search 25 **2.094s**, options **.703s**, Sources **.984s**, audit 20 **.954s**. Final live search pages **2.843–8.688s**, exports **3.328–7.375s**, source overview **1.640s**, consistent backup **21.875s**, during simultaneous browser verification. Interactive requests completed within the 20s UI deadline. These are service/load observations, not guarantees; the backup download is separate from interactive search.

## Real source results and limitations

The most recent scheduled MCF run, **23 October 02:35–02:36 UTC**, is **degraded**: Thai and Public Relations returned 10 each; Marketing Executive and Social Media Executive timed out. It updated 19 records, added 0. Next persisted run: **23 October 14:36:33 UTC / 22:36:33 SGT**. The bounded 12-hour/four-query/ten-result schedule is unchanged. Earlier complete/failed/interrupted histories remain distinct; no additional query was triggered to manufacture success.

This demonstrates actual partial upstream operation and truthful failure handling, not successful rechecking of every vacancy. Other sources remain retained imports. Unknown candidate/source facts remain unknown; deterministic parsing can miss future unusual wording. Participant and screen-reader research are **unperformed**, with the concrete protocol in DECISIONS. XML-invalid text requires reversible JSON representation in XLSX. These external/format/coverage limits are explicit; no unresolved minor product defect was identified in the final reviewed scope.

## Representative current screenshots

All are local private artifacts under `output/playwright/independent-20261023/`:

- [Deployed phone discovery](output/playwright/independent-20261023/production-find-390.png), [phone Sources](output/playwright/independent-20261023/production-sources-390.png), [desktop detail](output/playwright/independent-20261023/production-detail-1440.png), [source inspector](output/playwright/independent-20261023/production-source-inspector.png).
- [Isolated conflict comparison](output/playwright/independent-20261023/journey-final/conflict-1440.png), [retained import history](output/playwright/independent-20261023/journey-final/application-history-1440.png), [saved import/Closed outcome](output/playwright/independent-20261023/editor/import-resolution-outcome-1440.png).
- [Native 200% Find](output/playwright/independent-20261023/native-200-find.png), [Sources](output/playwright/independent-20261023/native-200-sources.png), [Applications](output/playwright/independent-20261023/native-200-applications.png).

```powershell
python -m unittest test_storage test_audit_qa test_evidence test_sync test_source_audit test_source_preservation test_fit_v2 test_workspace_v2 test_browser_workspace test_offline_safety test_accessibility -q
node --check static/workspace.js
node --check static/sources.js
node --check static/fit-score.js
git diff --check
```

Read `test_workspace_journey.py` before using its isolated localhost runner and required CAREER_QA settings. Later evidence/documentation-only commits use `[skip render]`; the deployed implementation revision above remains authoritative.

---

# Historical early-23-October acceptance (superseded)

Verified deployed implementation: **2.2.1**, revision **`3b8664de31376ef9c35ecd6412107697a8b9d5b0`**, Render deployment **`dep-dbdaiq0u01pc73cfuvi0`**, live at **23 October 2026 00:26:45 UTC (08:26 SGT)**. This section supersedes the historical report below. The new audit found and fixed defects that the earlier acceptance missed; passing historical tests was not treated as completion.

Specification and traceability: [execution brief](EXECUTION_BRIEF.md), [requirement audit](COMPLIANCE_AUDIT.md), [interaction contracts and decisions](DECISIONS.md). Live workspace: https://sg-career-intelligence.onrender.com.

| Area | Current verified result |
| --- | --- |
| Edits/recovery | Validated acknowledgements preserve pending work on malformed HTTP 200 responses. Corrupt entries cannot hide valid versions; quota failures explicitly offer download/manual copying without claiming persistence. Late acknowledgements cannot regress a newer server copy. Applied success waits for acknowledgement. Closed drafts remain reviewable. |
| Preparation/journey | Supported listing–CV pairs precede drafts; unresolved checks remain separate. Real isolated two-context journey passed discovery/evidence, preparation/edit, clipboard failure, listing navigation without stage change, explicit Applied, follow-up, conflict/resolution, Closed, resolved import history and exactly one selected exported application with notes/draft/history. |
| Sources/persistence | Original key presence distinguishes omitted and explicit-empty values. Omitted facts retain provenance, changed descriptions replace derived arrangements, stable MCF UUID preserves ID/original URL, and evidence/jobs/history commit atomically. Japanese requirements and restrictions survive SQLite roundtrip/omission. |
| Assessment | Actual CV and all supported clauses in nine retained listings reviewed. Mandatory/negated language, negated duties, shared actions, tool/finance/email/website/visual scope, alternative degrees and boilerplate regressions pass. The rubric remains documented-fit-v2 with 20/50/30 and existing limits/withholding. Mixed inseparable scopes remain conservatively unproven. |
| Export | Full saved job snapshots now accompany applications. XLSX text above its 32,767-character limit is retained in labelled ordered parts on a separate sheet, preserving one main application record and formula protection. |
| Accessibility | Valid detail dialog/region semantics, headings, inert background skip link, mobile Sources DOM/Tab order, focus across resizing/source selection, 44px website/endpoint targets and stronger input borders. Native controls, visible focus and reduced motion retained. |
| Performance | Bounded Thai-classification cache keys include actual source/requirement values and are warmed before readiness. Changed evidence invalidates the key. Warm audit reads fell from about eight seconds to about two seconds locally. |

The explicit suite passed **154 tests in 26.8 seconds**; the final endpoint-target refinement was reproduced as a failure, then all **11 accessibility tests** passed after correction. JavaScript syntax and whitespace checks passed. The current verification command includes `test_accessibility`; the historical command below records the prior pass. Evidence: `output/goal-20261022/final-regression.log`, `backend-review-tests.log`, `scoring-final-review.json`.

The real-data isolated journey passed with zero page errors: `output/playwright/compliance-20261023/journey/journey-report.json`. Hard termination/restart preserved the entire application JSON, including drafts/snapshot/history: `output/goal-20261022/restart-performance-final.json`. All application mutations used isolated storage; external listing requests were blocked by the journey runner. Browser fixtures cover independent tabs, immediate close, in-flight edits, timeout/401, storage denial/corruption, recovery deletion, stale searches and failed-export selection.

Current screenshots/interactions passed at **390×844, 768×1000 and 1440×1000** without horizontal page overflow. The phone's first result starts at y=415.9 and source search at y=473.5. Native Chromium Appearance zoom was set to **200%** in a temporary profile: window 1440×1000, viewport 713×453, DPR 1.5→3, document width 705. Find, Sources and Applications fit; detail Escape/return focus passed. See `output/playwright/compliance-20261023/native-zoom.json`.

Axe 4.11 reported zero violations on Find, filters, desktop/phone detail, desktop/phone Sources, inspector and Applications. Incomplete overlap/decorative-arrow checks were inspected separately: body/notes contrast 16.186:1, secondary 6.421:1, input boundary 3.758:1, focus 5.169:1, decorative arrows 4.309:1; reduced-motion duration 0s. Evidence: `a11y-final.json`, `manual-contrast-motion.json` under `output/goal-20261022`. This is tested coverage, not WCAG certification or participant/screen-reader research.

Representative current screenshots are under `output/playwright/compliance-20261023/`: [phone discovery](output/playwright/compliance-20261023/production-find-390.png), [phone Sources](output/playwright/compliance-20261023/production-sources-390.png), [desktop detail](output/playwright/compliance-20261023/production-detail-1440.png), [source inspector](output/playwright/compliance-20261023/production-source-inspector.png), [conflict comparison fixture](output/playwright/compliance-20261023/conflict-fixture-1440.png), [history](output/playwright/compliance-20261023/journey/application-history-1440.png), [native zoom](output/playwright/compliance-20261023/native-200-find.png). Quota/download proof is `output/playwright/compliance-20261022/storage-quota-recovery-fixture-1280.png`. Private artifacts remain excluded from Git.

Local warm API timings after restart: 25 search results 3.094s, options 1.235s, Sources 1.984s, 20 audit records 2.281s against 4,402 retained jobs. These vary with local load; production measurements are separate.

Fresh production backup and migration/restoration rehearsal passed: **4,406 jobs, 4,518 evidence versions, six collection-history entries, zero applications/imports**. Every original table row/field/payload and digest matched through two migration startups and restoration. This patch requires no schema change. Evidence: `migration/20261023-compliance/rehearsal.json`, with immutable predeploy/migrated/restored copies beside it.

Release remains on the existing Render service, native Git auto-deploy, one Uvicorn worker and persistent disk. Official Render/Uvicorn docs and actual service config confirmed Python's native forwarded-IP handling supports HTTPS origin checks. The first patch deployment was `4ae01fc`; final CSS correction is `3b8664d`. Final live health, authentication and same-origin HTTPS validation passed. All original persisted job/application/import/evidence/history rows and payloads remain unchanged in `production-final.sqlite3`; only operational backup metadata advanced. The schedule is unchanged and the worker is alive. Restart 502 probes are not counted as successful checks.

The retained scheduled MCF run on **22 October 14:35 UTC** succeeded on all four queries, ten results each, adding 4/updating 35. The preceding 02:34 UTC run timed out all four and remains failed. Next persisted run is **23 October 02:35 UTC**, same 12-hour/four-query/ten-result scope. No extra collector was triggered to improve this report. Other sources remain retained imports; bounded checks do not verify every vacancy. Participant validation is unperformed; `DECISIONS.md` supplies the protocol. No candidate facts were invented.

Final live evidence: `output/goal-20261022/production-final-compliance.json`, `browser-final-production.json`, `final-release-verification.json`, `final-touch-release.json`, and `deployment-final.json`. Protected pages/jobs/applications/history/export/audit/backup rejected unauthenticated requests. An invalid revision returned 422 through HTTPS same-origin validation before any transaction; production applications remain zero. Complete paginated live search/export parity passed for Thai/freshness (274 records), Marketing/Full-time/disclosed monthly minimum S$3,000/salary order (220), and Freelance/title order (25). The final CSS equals the deployed stylesheet after newline normalization; both source links measure 44px in the deployed phone browser. The full live responsive walkthrough had zero page errors or HTTP 5xx responses after service readiness.

Live API search pages took 2.8–8.8 seconds and exports 5.8–7.4 seconds while the simultaneous browser acceptance run was active; source overview took 6.39 seconds. Those requests completed within the interface timeout. This is a measured performance limit of the present service, not a guarantee of lower latency; the repeated parsing defect was removed and no unresolved timeout remained in the final pass.

The final requirement review found no remaining critical or major defect in scope. Unknown employer/candidate information, external source availability, conservative semantic interpretation and unperformed participant research remain explicitly labelled limitations, not uncompleted implementation promises.

```powershell
python -m unittest test_storage test_audit_qa test_evidence test_sync test_source_audit test_source_preservation test_fit_v2 test_workspace_v2 test_browser_workspace test_offline_safety test_accessibility -q
node --check static/workspace.js
node --check static/sources.js
node --check static/fit-score.js
git diff --check
```

The historical US$0.0191 verification incident below remains disclosed. This pass used explicit safe modules and made no paid collector calls; no credentials were rotated/revoked/deleted.

# Historical 21 October 2026 acceptance (superseded)

Verified on 21 October 2026. The deployed workspace is **2.2.0**, application revision **`aff19ec90cf03002feb2774d30ecdbb7bc9c143e`**, at https://sg-career-intelligence.onrender.com. The final observed live Render deployment was `dep-dbccqerbc2fs73c1n3rg`, completed at 14:34 UTC. Documentation-only commits after this revision do not change the deployed application.

The implementation and acceptance pass found no remaining critical or major defect in the approved scope. This report separates isolated mutation tests, deployed read-only checks, and actual upstream collection results. It does not imply every retained vacancy was freshly checked.

## Delivered behavior

- Editors bind displayed values, base snapshots and revisions together. Dirty edits survive refresh, conflicts, failed requests, immediate close and reload. Independent immutable browser recovery versions remain available across tabs; an acknowledgement cannot delete another editor's version or newer keystrokes. Legacy recovery is preserved after verified conversion.
- Authenticated, paginated application history and CSV/XLSX exports retain original imported notes and stages, resolution snapshots and dates. Existing revisions, IDs, drafts, snapshots and payloads remain compatible.
- SQLite schema v2 preserves explicit source requirements and their references separately from derived requirements. Partial responses retain omitted descriptions, employer facts and original content dates. Successful listing checks have separate dates; freshness ordering uses successful verification.
- `documented-fit-v2` retains the 20/50/30 policy while assessing independent action-and-scope clauses, showing partial support, original listing quotations and CV references. Missing source information, missing candidate evidence and documented incompatibility are distinct. Mandatory limits and withheld scores remain.
- Discovery uses compact rows, normalized employment memberships and shared search/export filtering. Details, preparation, application tracking and source inspection retain one consistent workflow. Preparation uses relevant supported evidence pairs, separates unresolved requirements and preserves user drafts. Phone Sources prioritizes collection health, source selection and search.

Scope and decisions: [execution brief](EXECUTION_BRIEF.md), [decision record](DECISIONS.md), [operation and rubric documentation](README.md).

The original execution brief guided implementation. The final artifact audit expanded that same file into one self-contained master prompt, covering the supplied design framework's expert role, screen/workflow/component contracts, alternatives, uncertainty, accessibility, execution and completion requirements. This was a documentation refinement after rollout, not a claim that new participant research or additional implementation occurred. The supplied source file remains unchanged.

## Regression and journey results

The final explicit suite passed **103 tests**: 91 backend/offline checks and 12 browser regressions. All three JavaScript files passed `node --check`; `git diff --check` passed. Evidence: `output/workspace-v2-regression.log`.

```powershell
python -m unittest test_storage test_audit_qa test_evidence test_sync test_source_audit test_source_preservation test_fit_v2 test_workspace_v2 test_browser_workspace test_offline_safety -q
node --check static/workspace.js
node --check static/sources.js
node --check static/fit-score.js
```

| Acceptance area | Verified result and evidence |
| --- | --- |
| Concurrent editing | Clean refresh updates values and revision together; dirty refresh requires resolution. Two tabs retain independent failed-save versions through acknowledgement and reload. New keystrokes during an in-flight save remain recoverable. `test_browser_workspace.py`. |
| Persistence | Immediate close/reload and a real offline browser preserve text. A separate authenticated context reads saved notes and drafts. Hard termination and restart of the isolated server preserved every application field, draft, snapshot and history entry. `output/extra-acceptance.json`, `output/applications-before-hard-restart.json`. |
| Import history | Original notes/stage, resolution and date remain accessible after resolution through authenticated pagination and CSV/XLSX exports. Older historical resolutions without a stored snapshot are explicitly identified. `test_source_preservation.py`, `test_workspace_v2.py`, browser history regression. |
| Source omissions | SQLite save/load followed by an upstream response omitting description preserves the explicit Japanese requirement, evidence reference, original provenance and assessment restriction. Fresh checks cannot refresh retained content dates. `test_source_preservation.py`. |
| Assessment | Graphics/animation, specialist tools and finance receive no unsupported topic-only credit. Compound duties expose partial support; Unicode bullets, Marketing-degree alternatives and agency boilerplate are handled. PropertyGuru geography does not become a Thai requirement. Fixed synthetic and retained-source review corpora test supported claims, gates and meaningful ranking comparisons. `test_fit_v2.py`, `test_evidence.py`, `fit_review_corpus.json`, `fit_review_real_sources.json`. |
| Search and exports | Reversed responses cannot replace newer searches. Employment membership and older combined filters work. Salary disclosure, thresholds and units remain separate. Real successful checks determine freshness. A selected-application browser export contained exactly one record and its notes. CSV/XLSX formula-injection checks pass. |
| Complete journey | Discovery → details/evidence → preparation → edited draft, notes, next action and follow-up → original listing in a separate tab → explicit Mark applied → competing authenticated edit → conflict resolution → Closed/outcome → history. Opening the listing did not mark it applied. Mouse and keyboard/Escape/focus return passed. `test_workspace_journey.py`, `output/frontend-acceptance.md`. |
| Failure states | Loading and empty states inspected; unauthorized and timed-out saves retain text with retry/recovery; partial collector failure remains degraded; clipboard rejection selects the draft and explains manual copying. No page errors in the completed isolated journey or final live pass. |

The original `CV 2026.pdf` was checked against candidate facts. Its SHA-256 is `c4cf734637cfe8a06a214544c500c63aa61ea5d9dc93fb25391a394e86eea14f`. No specialist design/tool qualification, contact detail, availability or achievement was invented.

The reproduced editor, shared-recovery, source-requirement, employment/freshness/history and scoring defects were captured as failing regressions before their fixes. All application mutation tests used isolated storage. Production contained zero applications before rollout and still contained zero at final verification.

## Responsive and browser evidence

Find, Sources and role details were inspected at **390, 768 and 1440 CSS pixels** without horizontal page overflow. In the final live 390 × 844 browser pass, the first role began at **y=416** and source search at **y=474**, both in the initial viewport. Keyboard opening, Escape and return focus passed at all three widths. Native semantic controls, visible focus, reduced-motion behavior and 44px touch-target styling were retained.

The earlier frontend report used a 720px CSS viewport to test 200%-equivalent reflow. A later check additionally set **Chromium's native zoom to 200%**: outer width 1440, inner width 713, document width 705. Find, Sources and Applications had no horizontal overflow; detail dismissal remained accessible. Metrics are in `output/native-zoom-acceptance.json`. Native Find/Sources screenshots were captured using the browser's surface because ordinary screenshots cropped incorrectly at this native zoom; those corrected images are the representative zoom evidence.

Representative screenshots (local, intentionally excluded from Git):

- [Live phone discovery](output/playwright/v2/production-find-390.png)
- [Live phone Sources](output/playwright/v2/production-sources-390.png)
- [Live desktop details](output/playwright/v2/production-detail-1440.png)
- [Live source inspector](output/playwright/v2/production-source-inspector.png)
- [Concurrent edit conflict](output/playwright/v2/conflict-1440.png)
- [Application history](output/playwright/v2/application-history-1440.png)
- [Native 200% discovery](output/playwright/v2/native-zoom-200-find.png)
- [Native 200% Sources](output/playwright/v2/native-zoom-200-sources.png)

The final live pass recorded zero page errors and zero HTTP 5xx responses. `output/production-browser-v2.json` records dimensions and outcomes.

Warm local API measurements were 1.391 seconds for 25 search results, 0.156 seconds for options, 0.422 seconds for source overview and 0.406 seconds for 20 audit records (`output/performance-v2.json`). These are measured local timings, not a production latency guarantee. Startup prepares assessment caches before readiness.

## Data protection and rollout

Production was captured through the authenticated consistent SQLite backup endpoint before deployment. Migration and restoration were rehearsed on isolated copies. Both databases passed integrity checks; all 4,397 original job IDs and original fields were preserved, the 4,398 retained source payloads were unchanged, other retained tables matched, repeated migration was identical and restoration reproduced table contents. See `migration/20261021-workspace-v2/final-migration-rehearsal.json`.

Local recovery artifacts include:

- `migration/20261021-workspace-v2/production-predeploy.sqlite3`
- `migration/20261021-workspace-v2/final-rehearsal.sqlite3`
- `migration/20261021-workspace-v2/final-restored.sqlite3`
- `migration/20261021-workspace-v2/production-final.sqlite3`

The final post-refresh backup passed SQLite integrity checks and contained **4,402 jobs, 4,478 source-evidence versions, four collection-history entries, and zero applications/import receipts/import conflicts**. Every predeployment job ID remains present and every predeployment source-payload row is byte-for-byte identical. Additional versions came from live checks. Evidence: `output/production-final-data-check.json`.

Deployment used the existing Render service and persistent disk. Restarts briefly returned 502 responses, including to the initial manual source-check request. Retained interrupted-run markers caused automatic retry after restart. The final service reports healthy 2.2.0 with the scheduler alive. Protected jobs, applications, history, audit, exports and backup routes reject unauthenticated requests. A live PropertyGuru search and filtered export contain the same two IDs in the same order, with the v2 rubric. Sources search intentionally searches title/company/ID, while discovery also searches role content. Evidence: `output/production-final-api-check.json`, `output/render-v2-deploys-final.json`.

The completion audit additionally exercised the actual `sort_by` parameter across complete paginated live results: Thai by freshness (280 records), Marketing/Full-time with disclosed monthly minimum S$3,000 by salary (223), and Freelance by title (26). Each export matched every result ID in exact order. Evidence: `output/production-filter-order-check.json`.

## Actual collection result and external limits

The earlier MyCareersFuture run timed out all four searches and remains recorded as failed. Two interrupted attempts remain recorded as interrupted. Neither is counted as a successful check.

The final deployed retry **succeeded at 2026-10-21 14:34 UTC (22:34 SGT)**: Thai, Marketing Executive, Social Media Executive and Public Relations each returned ten results, with no source errors. It added five roles and updated 35. The native scheduler remains enabled every 12 hours, four searches, ten results per search; its persisted next check is **2026-10-22 02:34 UTC (10:34 SGT)**. Evidence: `output/production-v2-source-check.json`, `output/production-v2-source-health.json`.

This verifies the bounded collector and restart recovery, not every retained vacancy or future source availability. LinkedIn, Indeed, Cultjobs and Google remain clearly labelled retained imports. Incomplete descriptions, unsupported candidate requirements and historical dates remain visible uncertainties.

## Verification incident

During verification, broad unittest discovery imported three ignored historical manual-probe scripts with top-level Apify requests. This violated the no-paid-scraping constraint. Two completed runs reported **US$0.0191** total usage (`RClICWaqFYdhb4GwD`: $0.01005; `FUcStUW1P60VuitYF`: $0.00905). The Indeed probe returned HTTP 400 without starting a run. No active runs remained when checked.

The three local probes now have `__main__` guards, and committed `test_offline_safety.py` verifies that importing them cannot issue GET/POST requests. The final suite used explicit test modules. The credential-bearing historical probes remain excluded from Git. No credentials were rotated, revoked or deleted. This incident was disclosed during the task and is retained in `output/verification-side-effect.json`.


## Historical seven-day campaign phase — 23 October 2026 (policy gates superseded; operational acceptance pending)

Implemented the native lifespan campaign worker, additive schema-v3 journal, transactional conservative budgets, current actor contracts, account references/usage checks, launch reconciliation, checkpointed imports, isolated pilot tables, stop/abort policy, discovery queue and authenticated status/pause/report controls. The campaign has not yet demonstrated two real unattended six-hour cycles or actual seven-day shutdown.

Fresh verification: 194 explicit tests passed in 36.821 seconds. A first browser pass found a new disclosure before phone record search; that placement was corrected and the full pass includes the keyboard regression. One existing draft-generation timing fixture failed in the initial parallel pass and passed both its focused rerun and the full sequential suite; no editor behavior was changed. New campaign browser fixtures at 390, 768 and 1,440 px passed pause/status/overflow checks.

A fresh production SQLite backup contained 4,406 jobs, 4,538 source-evidence rows, seven sync-history rows and zero server-side applications. Migration and restore preserved the full content digest of every original table; repeated migration was idempotent. Application preservation is additionally covered with nonempty isolated notes/drafts/history fixtures. Artifacts: output/campaign/production-before.sqlite3, migration-report.json and full-regression.txt.

Live preflight verified 33 distinct accounts, zero active runs and zero schedules. Usage limits did not establish promotional balances or expiry; only verified free-plan included capacity is admitted. Current official actor builds/inputs differ from historical scripts. LinkedIn and Google search paths are disallowed by their robots rules. Career crawling is blocked because the official actor's post-load hook cannot establish prevention of private-network/unsafe redirect navigation. Cultjobs consent remains unresolved. Therefore complete multi-source recursive coverage is **not accepted**.

Deployment, isolated paid pilot, cost reconciliation and live status will be recorded below as they occur.


### Live pilot and storage evidence — 23 October 2026

Native Render deployment 12524ce is healthy with both lifespan loops. Existing tokens were installed through the native APIFY_TOKENS_JSON secret; no keys/account settings were changed. Measured disk free space (489,611,264 bytes) fell below the 519,188,480-byte safety reserve. The existing disk was expanded from 1 GB to 2 GB, adding US$0.25/month at the plan pricing; after restart free space was 1,545,949,184 bytes. The Blueprint records the same native configuration.

Pilot run dKWkpxwZB76oQzeYo succeeded: ten returned records, nine supported Singapore vacancies in isolated pilot tables, one lead whose location was only “Geylang”. Nine normalized descriptions exactly matched the source text; original source identifiers and dates were retained. The query also returned adjacent titles, so query wording is not treated as vacancy facts. Run charge US$0.06; reconciled observed account delta US$0.060111; conservative actor commitment remains US$0.20. No production job/evidence/application/import/sync-history content changed, confirmed against a fresh full-content backup.

The campaign clock began 23 October 2026 at 21:37:21 SGT and ends 30 October 2026 at 21:37:21 SGT. Pilot evidence and full production comparisons are in output/campaign/pilot-verification.json and production-after-pilot.sqlite3. Live read-only browser journeys at 390, 768 and 1,440 px verified Sources, campaign stop/cost display, newly-discovered ordering and role details without overflow or JavaScript errors. Screenshots are output/playwright/campaign/live-*.png.

Performance: local 4,406-record warm search 2.823s; a 26,436-record synthetic presentation-volume search 16.544s. The synthetic set repeats known source text and does not establish cold assessment performance for 26,436 distinct descriptions. This is a scaling limitation; current browser source journeys were 3.75–7.88s including page/screenshot work. Unattended six-hour cycles, actual seven-day shutdown, full-source coverage and independent operational review remain unverified.


### First recurring cycle and normalization correction

Indeed production activation succeeded after pilot cost reconciliation and a restart preserved the campaign ID, immutable deadline, pilot run ID and import checkpoint. The native worker admitted two simultaneous bounded batches on separate accounts. Current LinkedIn/Google restrictions and career-crawler gate became visible blocked source outcomes.

Review of current payloads found salary and parsed posting dates present in retained raw evidence but omitted from displayed fields. Paid admissions were paused while mapping salary → advertised_salary and postingDateParsed → posted_at, preserving the original actor fields in the raw item journal. An idempotent local backfill changes only those recognized fields/provenance, without refreshing verification dates or changing application snapshots. Explicit source expiry is retained; new records without vacancy text remain leads.

The final full explicit suite passed **198 tests in 39.501 seconds**. The earlier draft-generation fixture was corrected to await the matching draft-save HTTP response, rather than a 450 ms sleep or potentially earlier stage-save status. No editor product behavior was changed. A further focused campaign pass validates the report's persisted cycle evidence.


### Operational handoff evidence (2026-10-23T13:58:09.269494+00:00)

Deployed revision **7eafd77f6af5725b1eb905315d64783e772c790a** is healthy. Campaign **720b9812a4344cf2b32c0fc10149c5f3** is **active** in production mode; MyCareersFuture and the campaign lifespan workers are both alive. It survived deployment restarts with the same campaign ID, pilot run ID, immutable deadline and completed checkpoints. After resumption the next queued Indeed batch launched autonomously. No worker/accounting error is recorded.

At this observation, reported actor charges are **US$2.460000**, observed account usage is **US$2.460711**, and conservative actor commitments are **US$3.00**. There are 207 distinct supported job identities in the campaign journal, including isolated pilot identities and refreshed existing roles; this is not a count of newly added production roles. The final preservation snapshot contains 4,500 production jobs (94 added versus the 4,406 baseline); every original ID remains. Application/import table digests remain identical. Salary/date repair version 2 is persisted and SQLite integrity passes.

Live authentication rejects unauthenticated requests to the campaign, audit and jobs APIs. The salary-filtered API/CSV both return 2,015 records; current measured filtered search is 3.812 seconds. Repaired advertised salary and returned posting dates are visible. Final 390px Sources inspection displays active state and source-block reasons without overflow or JavaScript errors. The 2 GB native disk remains within the approved maximum.

The fixed stop time remains **30 October 2026, 21:37:21 SGT**. The worker persists cycle/run timestamps, final remote terminal evidence and the evolving report at authenticated `/api/campaign/report`. **Operational acceptance is still pending:** two unattended six-hour cycles, actual seven-day shutdown/cost completion, independent operational review, and projected-volume responsiveness have not been demonstrated. Historical records retain the former robots and redirect/private-network observations as superseded policy evidence; they do not block current actor submission. Cultjobs remains a dated import pending consent. The complete requested multi-source recursive campaign is therefore not claimed as achieved.

Final artifacts: output/campaign/final-status.json, final-live-verification.json, final-preservation.json, final-production.sqlite3, final-regression.txt (198 passing tests), final-focused.txt (27 passing campaign tests), and output/playwright/campaign/live-final-campaign-390.png.
