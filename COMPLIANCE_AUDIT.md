# Independent compliance audit — 23 October 2026

Canonical specification: [EXECUTION_BRIEF.md](EXECUTION_BRIEF.md). Implementation **2.2.2**, revision **ef71193d68456ea4437da4433685cbf46a81a617**. Existing workspace: https://sg-career-intelligence.onrender.com. This audit supersedes prior completion claims. Deployment verification is P/B below; all application mutations used isolated storage.

## Evidence register

Private artifacts are excluded from Git. Paths are relative to this repository. Each test supplies its stimulus/assertions; JSON reports distinguish actual outcomes from intended behavior. The baseline was clean commit `09ce6cbc`, with deployed `3b8664d`. Current implementation is the revision above. Official FastAPI lifespan, Python 3.12 SQLite backup, MDN storage events, Playwright contexts, Render disks/deploys, XML and Python parsing references were inspected before changes. No repository AGENTS.md exists; `C:/Users/Study/AGENTS.md` and user-supplied global instructions apply.

| Key | Current evidence and scope |
| --- | --- |
| R | `output/independent-20261023/final-regression.log`: **170 explicit tests pass, 28.525s**, current final implementation. All three JS syntax checks and git diff whitespace check pass. Tests use isolated SQLite/memory and mocked collection; imports inspected. Test names and assertions are the executable requirement stimuli. |
| E | `output/independent-20261023/editor/audit.json`, `final-review-contradictory-import-ack.json`: failing-before/fixed editor cases, actual SQLite concurrent import rebase, validated acknowledgement, current 33-browser-test suite. Includes immutable recovery, independent tabs, immediate close, in-flight edits, clean/dirty refresh, 401/timeout/offline/storage failure and stale search cases. |
| J | `output/playwright/independent-20261023/journey-final/journey-report.json`: real retained SG-OPP-2507 on isolated `127.0.0.1:8771`, two authenticated contexts, complete prepare/edit/apply/follow-up/conflict/close/import-history/one-selected-export journey, zero page errors. External listing navigation intercepted; no employer contact. |
| H | `output/independent-20261023/restart-performance.json`: hard kill/restart preserves entire application JSON, including drafts/history/snapshot. 4,406-job isolated dataset; search 25 2.094s, options .703s, Sources .984s, audit20 .954s. Environment-specific observations, not latency guarantees. |
| S | `output/independent-20261023/evidence/scoring-review.json`, `review.md`, fixed JSON corpora and `test_fit_v2.py`: 17 real retained corpus records; original two-page CV SHA256 `c4cf734637cfe8a06a214544c500c63aa61ea5d9dc93fb25391a394e86eea14f`; exact retained payload matching, supported claims, top recommendations, clause quotes, generated drafts and meaningful rankings. Reviewer supplement `final-review-fixes.json`. No live vacancy claim from retained text. |
| X | `output/independent-20261023/persistence/report.json`, `safe-test-review.json`: isolated API/storage/source/export review, failing-before XLSX character regression and lossless reconstruction. CSV/database unchanged; selected XLSX remains one main record. |
| M | `migration/20261023-independent/predeploy-rehearsal.json`: fresh production SQLite snapshot, initialize twice, restore; **every table value, schema and sequence equal**, integrity ok. 4,406 jobs, 4,538 evidence rows, seven sync histories, zero applications/imports. Independent earlier rehearsal `persistence-rehearsal.json` corroborates. No schema migration required. |
| A | `output/independent-20261023/a11y-final.json`: axe 4.11 zero violations across eight Find/filter/detail/Sources/inspector/Applications states. `manual-accessibility.json` resolves incomplete contrast checks: body/notes 16.186:1, secondary 6.421:1, decorative arrows 4.309:1; reduced motion 0s, source links 44px, 200% root-text resize at all three widths. R measures focus/control boundaries and keyboard states. |
| Z | `output/playwright/independent-20261023/native-zoom.json`: native Chromium 145 Appearance `zoomLevel=2` in disposable profile, window 1440×1000, viewport 713×453, DPR 1.5→3, document 705px; Find/Sources/Applications no horizontal overflow, detail Escape/return focus passes. Native surface screenshots inspected, distinct from resized viewport tests. |
| P | `output/independent-20261023/final-live.json`, `deployment.json`, `postdeploy-preservation.json`: final deployed reads, auth, five assessment/draft comparisons (`live-assessment-parity.json`), exact filtered search/export IDs/order, source status/schedule, served-asset equality and fresh full-data postdeploy comparison. No application write or manual collection trigger. |
| B | `output/independent-20261023/browser-production.json`: final deployed read-only Chromium at 390×844, 768×1000, 1440×1000; discovery/details/Sources/inspector/empty Applications, keyboard return, no overflow/page errors/5xx after readiness. Screenshots in `output/playwright/independent-20261023/`. |
| I | `output/independent-20261023/independent-final-review.json`, `independent-review-focused.log`, `final-review-fixes.json`: separate reviewer read original brief/CV, scanned supported scopes and invalid saves, reproduced four additional findings, then independently verified fixes. Root also reviewed export diff/reconstruction tests. |

## Requirement matrix

All rows below were evaluated against current files/runtime. PASS means the stated exercised outcome, not universal guarantees for future input. Source outages and participant research are explicitly qualified.

| Brief requirement | Expected / actual current evidence |
| --- | --- |
| §1 Whole private journey; one candidate; inspect current repo/deployment/CV | PASS R/J/S/P/B. Original baseline not checked out; supplied CV verified, no candidate facts invented. |
| §1–2 FastAPI/plain JS/SQLite/auth, IDs/URLs/payloads/snapshots/notes/drafts/history, native worker/disk | PASS M/P compare complete persisted data. Render API confirms existing Singapore service, one worker/instance, `/var/data`; live runtime plan `1c-2g`, Starter build plan preserved. Older README plan shorthand corrected. |
| §2 Revision-checked PUT/409; distinction between facts/derived/user decisions; no assumed salary/probability | PASS R/E/J/S. Server concurrency unchanged; caps/unknowns and separate evidence visible. |
| §2 No paid/new integrations/keys/wrappers/employer messages; isolated application mutations | PASS inspected explicit modules, X/J/P. No collector triggered, no lifecycle action, no production application created. Historical paid-probe incident remains disclosed in acceptance history. |
| §2/4/6 Bounded MCF four named searches × 10 every 12h; retained imports; absence not closure | PASS R/P. Latest actual run is **degraded**, two successes/two timeouts; previous successes and failures preserved. Scope/schedule unchanged. |
| §3 Find search→count/order/export→compact facts/fit/reason; missing pay/type; useful loading/empty/retry | PASS R/B; long evidence in detail, filters disclosed, first phone result visible. |
| §3 Detail facts/listing first, requirements/fit/notes/prep reachable, pane/mobile modal, unavailable snapshot | PASS J/B/R/Z; role/direct/app/source entry, Escape/focus/context and retained closed snapshot. |
| §3 Preparation supported pairs→editable draft→separate unresolved checks | PASS S/J/R; clipboard rejection selects text; no regeneration over intentional empty/edited draft. |
| §3 Applications stage/action/date/notes/history/selection; Closed remains reviewable | PASS J/H/R/E. Same editor ownership/retry/recovery from all entry points. |
| §3 Sources desktop flow, phone health/source/search, disclosure, source scope/errors/fields/payload versions | PASS B/A/Z/R/P; DOM and keyboard order agree; escaped payload inspector, actual success/attempt dates. |
| §3/7 Purpose/entry/exit/actions/data/states/responsive/keyboard component contracts | PASS current `DECISIONS.md` surface, state, component tables and independent corrections. No decorative mockup/new design layer. |
| §4 Discover stale response suppression, search/filter/selection/scroll/focus, empty/error retry | PASS R/J/B; reversed responses, pagination retry, keyboard return, no reset of failed export selection. |
| §4 First note Saved; persist local patch before debounce; actual base; Saved only on acknowledgement | PASS R/E/J; invalid200 and contradictory import resolution acknowledgements rejected, recovery retained. |
| §4 Clean refresh changes displayed/base/revision together; dirty preserves base; explicit comparison/rebase | PASS R/E/J. Major consumed-import-ID rebase fixed without weakening server; newer keystrokes survive late acknowledgement. |
| §4 All role/browser recovery versions; own ack only; verify replacement before remove; legacy retained | PASS R/E; two tabs through other acknowledgement/reload, immediate close, corrupt/quota/denied/removal cases, explicit recovery review never auto-submits another editor. |
| §4 Preparing/listing/explicit Applied, clipboard failure | PASS J/R. External listing navigation alone does not advance stage; explicit acknowledgement required. |
| §4 Six stages, follow-up/outcome, corrections/history/snapshot, validation preserves text | PASS J/H/R. Import Closed selection now reveals Outcome, history immediately available and refreshed in place. |
| §4 Import receipts idempotent, different versions retained, dated original/resolution snapshots/pagination/full exports | PASS J/E/R/X. Old missing historical resolution explicitly labelled. First resolution preserved after concurrent rebase. |
| §4 Refresh single-flight/partial/failed/interrupted/last success/persisted schedule/restart | PASS R/P. Actual retained degraded run not relabelled success; isolated lifecycle/rollback/overdue/interruption coverage; deployed scheduler alive after native restart. |
| §4 Exports normalized set/order, one selected app, all fields/history/snapshot, formula protection/failure selection | PASS P/J/R/X. XLSX long/invalid-XML text reconstructs exactly from labelled parts; CSV intact. |
| §4 Explicit editor states and inFlight/pending ownership; usable retry/busy states | PASS DECISIONS/R/E/J. Dirty/saving/saved/error/conflict/recovery differentiated; no false persisted claim on storage failure. |
| §5 documented-fit-v2 20/50/30, formula/caps/withholding/reasons/shared server presentation | PASS S/R/P. Same read-time assessment in search/detail/audit/export; no salary/prestige/geography/freshness credit. |
| §5 Action/scope, compound literal clauses/full original quote, partial support, distinct groups | PASS S/R/I. Duplicate domain combinations corrected; comma leadership/research split; interviews/EDMs/website/design/tool/finance scope unproven. |
| §5 Unicode/bullets/degrees/preferences/boilerplate/PropertyGuru | PASS S/R/I. Optional industry cannot waive required duration; degree+skill separated; alternate headings equivalent; geographic Thai inference prohibited. |
| §5 Missing source/candidate/incompatibility distinct, mandatory cap/withhold, preferred separate | PASS S/R. Unsupported is not incapable; incomplete descriptions withhold; documented residency mismatch separate. |
| §5 Fixed synthetic+real corpus/top/adjacent/language/finance/creative/degree/boilerplate/incomplete/rankings | PASS S/R/I. Exact retained quotations matched to source payloads and CV; representative aligned role outranks adjacent finance/event/mixed specialist roles for documented reasons. No desired distribution. |
| §6 Raw source intact, explicit vs derived requirements/references, omission vs explicit empty/provenance | PASS R/M/P/X. Japanese requirement roundtrip/omission and employer facts/date restrictions retained; changed derived arrangements recomputed. |
| §6 Listing success vs attempts/errors/source/content dates, safe URLs/redaction/escaped text | PASS R/S/B/P. Recent order uses successful checks, unverified last. Source evidence versions/payloads inspectable. |
| §6 Normalized employment/mixed/missing/legacy query parameters | PASS R/P. Shared search/export including sort_by and old combined values. |
| §6 Salary disclosure independent of threshold; SGD advertised minimum, annual conversion, hourly/daily/foreign/unknown | PASS R/P. No invented salary threshold or currency equivalence. |
| §6 Authenticated history pagination and complete exports; additive/idempotent storage/backfills/restore | PASS R/J/M/P. Full content/schema/sequence comparisons, not just row counts; this patch changes no stored schema/source data. |
| §7 Calm blue existing tokens/type/compact rows/facts hierarchy; states/labels/retry/no color-only meaning | PASS inspected B/J/Z/A and unchanged existing CSS. Stable labels, 44px controls, truthful save/recovery text. Reuse existing components. |
| §8 Landmarks/labels/names/keyboard/focus/modal/announcements/contrast/touch/reduced motion | PASS R/A/J/B/Z. Axe incomplete nodes separately measured; actual native zoom and root text resize. No WCAG certification or screen-reader participant claim. |
| §8 390/768/1440 and native 200%; initial phone result/search; no clipping | PASS B/Z/A. Phone result y=415.9, source search y=473.5; viewport heights and zoom method recorded. |
| §9 Consequential alternatives/trade-offs, facts/assumptions, actual research only | PASS DECISIONS explains inline update vs rerender, command filtering vs server relaxation, literal scoring vs opaque matching, JSON encoding vs loss/rejection. Source/CV/walkthrough evidence used. |
| §9 Participant protocol if unavailable | N/A actual participant study; explicitly **unperformed**. Concrete candidate tasks retained in DECISIONS. No invented interviews or metrics. |
| §10 Protect→correct evidence→journey→audit→rehearse→deploy; inspect scripts/explicit modules | PASS E/S/J/R/M/P/I. Fail-before tests precede fixes. Native Git auto-deploy existing service only. Later docs use documented skip-render commit. |
| §11 Failure/performance/acceptance command/environment/artifacts | PASS R/E/J/H/P/B; local versus live timing separated. Brief resize test race reproduced as asynchronous MatchMedia dispatch; assertion waits for resulting state rather than arbitrary first frame. No product change for test timing. |
| §12 Brief/implementation/tests/decisions/corpora/screenshots/report/live URL/final independent review | PASS current files and evidence above, acceptance report links. Brief remains canonical unchanged. No remaining substantiated critical/major defect after I and final verification. |

## Findings resolved and remaining limits

Reproduced before fixes: consumed import commands blocked explicit conflict recovery; contradictory acknowledgements falsely confirmed review; first-save/open history and import outcome feedback stayed stale; valid copied controls broke XLSX; optional industry waived years; compound/gerund/channel/degree scopes and duplicate task groups distorted evidence. Independent review added matching heading boundaries, comma-separated leadership/research, interview method, and contradictory acknowledgement checks. All pass after fixes. Minor history/outcome feedback issues are resolved, not hidden.

Latest real MCF check (23 October 02:35–02:36 UTC) succeeded Thai and Public Relations (10 each), timed out Marketing Executive and Social Media Executive, updated 19 and added 0. Next persisted check is 23 October 14:36:33 UTC. This is partial live evidence. The prior four-query success remains historical; no extra collection was triggered to manufacture acceptance. Other sources remain retained imports. Missing candidate facts, incomplete sources, unusual future wording and participant/screen-reader research remain explicit limitations. Deterministic corpus coverage does not certify all semantics.

## Repeatable commands and artifacts

```powershell
python -m unittest test_storage test_audit_qa test_evidence test_sync test_source_audit test_source_preservation test_fit_v2 test_workspace_v2 test_browser_workspace test_offline_safety test_accessibility -q
node --check static/workspace.js
node --check static/sources.js
node --check static/fit-score.js
git diff --check
```

Use the inspected `test_workspace_journey.py` only with explicit isolated localhost storage and its required CAREER_QA settings. Never use broad unittest discovery. Representative screenshots: `production-find-390.png`, `production-detail-1440.png`, `production-sources-390.png`, `production-source-inspector.png`, `native-200-find.png`, `native-200-sources.png`, `native-200-applications.png`, `journey-final/conflict-1440.png`, `journey-final/application-history-1440.png`, and `editor/import-resolution-outcome-1440.png` beneath `output/playwright/independent-20261023/`.


## Authorized campaign phase — 23 October 2026

| Requirement | Implemented evidence | Acceptance limit |
| --- | --- | --- |
| Shared budgets and 168-hour stop | Integer-money transactional reservations, account usage checks, pinned native Apify maxTotalChargeUsd/timeouts, stop/abort/import tests | Live pilot/reconciliation and actual seven-day observation still required |
| Restart and duplicate safety | Durable launch intents, unique run reconciliation, idempotent page checkpoints and atomic imports | Real service restart and two unattended six-hour cycles still required |
| Source truth and preserved work | Exact payload journal; identity/partial-field regressions; isolated pilot tables | Blocked sources are not claimed as collected |
| Source access and crawl scope | Robots/DNS/redirect checks; cycles/depth queue; explicit fail-closed remote crawler gate | LinkedIn/Google restricted; career isolation unverified; Cultjobs consent unresolved |
| Recovery | Fresh production backup: 4,406 jobs, 4,538 evidence rows; all original table digests unchanged after migration; idempotence and restoration verified | Runtime rollout preservation checked separately |
| UI/authentication | 194 explicit tests passed, including campaign auth/CSRF and responsive 390/768/1440 browser fixtures | Fixture evidence is not live or participant acceptance |

Current artifacts: output/campaign/migration-report.json, full-regression.txt, and output/playwright/campaign/status-fixture-*.png. The earlier 2.2.2 acceptance remains historical; it does not accept this campaign.


Final campaign deployment: `7eafd77f6af5725b1eb905315d64783e772c790a`; active Indeed collection, preserved MCF; 198-test full pass and 27-test focused campaign pass. Fresh live auth/filter-export/field-repair/mobile checks and full original-ID/application-table preservation passed. See the latest operational handoff in ACCEPTANCE_REPORT.md. Multi-source coverage, two unattended six-hour cycles, actual deadline shutdown, independent review and projected-volume performance remain explicit acceptance gaps.
