# Execution-brief compliance audit — 23 October 2026

Current release: **2.2.1**, application commit **`3b8664de31376ef9c35ecd6412107697a8b9d5b0`**, Render deployment **`dep-dbdaiq0u01pc73cfuvi0`**, live at **2026-10-23 00:26:45 UTC**. Workspace: https://sg-career-intelligence.onrender.com.

This is the requirement-to-evidence record for all twelve sections of [the canonical execution brief](EXECUTION_BRIEF.md). It supersedes this file's earlier pending audit. Results below distinguish fixture tests, real-data isolated mutations, deployed reads and actual upstream responses. [The acceptance report](ACCEPTANCE_REPORT.md) gives the delivery narrative; [DECISIONS.md](DECISIONS.md) specifies the surfaces/components/transitions and alternatives.

## Evidence key and scope

Paths below are local private artifacts excluded from Git unless they are repository source/tests/docs. These identifiers make each requirement's proof explicit without repeating large reports.

| Key | Evidence and exercised environment |
| --- | --- |
| R | `output/goal-20261022/final-regression.log`: 154 explicit tests passed in 26.796s on the implementation deployed as `4ae01fc`. Final commit changes only the source-link CSS selector and its target test; all 11 accessibility tests passed after that refinement. `test_storage`, `test_audit_qa`, `test_evidence`, `test_sync`, `test_source_audit`, `test_source_preservation`, `test_fit_v2`, `test_workspace_v2`, `test_browser_workspace`, `test_offline_safety`, `test_accessibility` supply executable stimuli/assertions. JavaScript syntax and whitespace checks passed. |
| J | `output/playwright/compliance-20261023/journey/journey-report.json`: real retained role SG-OPP-2507, isolated `http://127.0.0.1:8769`, two authenticated contexts; prepare/edit → explicit Applied → competing edit/conflict resolution → Closed/draft → import resolution/history → exactly one selected exported record. All steps passed, zero page errors. External listing requests were intercepted; no employer submission or production application mutation. |
| P | `output/goal-20261022/production-final-compliance.json`: deployed 2.2.1 authenticated reads, unauthorized 401s, safe same-origin invalid write validation 422, complete paginated search/export ID-order comparisons (Thai/freshness 274; Marketing/Full-time/disclosed minimum S$3,000/salary 220; Freelance/title 25), source state and database preservation. No application was created. These checks preceded the final CSS-only correction; API/JS are unchanged. |
| F | `output/goal-20261022/final-release-verification.json`, `deployment-final.json`, `final-touch-release.json`: final commit is live, served CSS matches it; healthy 2.2.1/scheduler alive, database integrity ok and preserved table data, same persisted schedule. Both live source website and endpoint links measure 44px; no page errors. |
| B | `output/goal-20261022/browser-final-production.json`: deployed reads at 390×844, 768×1000, 1440×1000; no horizontal overflow, keyboard detail return passed; source inspector/Applications empty passed, zero page errors/5xx. First phone result y=415.9; source search y=473.5. |
| Z | `output/playwright/compliance-20261023/native-zoom.json`: native Chromium Appearance zoomLevel=2 in temporary profile, window 1440×1000; viewport 713×453, DPR 1.5→3, document width 705. Find/Sources/Applications fit; detail Escape/return focus passed. This is native zoom, not a resized-viewport substitute. |
| A | `output/goal-20261022/a11y-final.json`, `manual-contrast-motion.json`: axe 4.11 zero violations on Find/filters/desktop+phone detail/desktop+phone Sources/inspector/Applications. Overlap/decorative-arrow incompletes inspected separately: body/notes 16.186:1, secondary 6.421:1, control boundary 3.758:1, focus 5.169:1, decorative arrows 4.309:1; reduced-motion transition 0s. `touch-targets.json` records the reproduced endpoint target defect before its final correction in F. Combined with R/B/Z/F and inspected screenshots; not WCAG certification or screen-reader/participant research. |
| S | `output/goal-20261022/scoring-final-review.json`, `fit_review_corpus.json`, `fit_review_real_sources.json`, `test_fit_v2.py`: original two-page CV inspected; SHA256 `c4cf734637cfe8a06a214544c500c63aa61ea5d9dc93fb25391a394e86eea14f`; all supported clauses in nine real retained listings and targeted synthetic duties reviewed. |
| M | `migration/20261023-compliance/rehearsal.json`: consistent production backup → two migration startups → restore, integrity/content/digest/idempotence all pass. 4,406 jobs, 4,518 evidence versions, six collection runs, zero applications/imports; original fields/payloads equal. F additionally proves preservation after final deployment. |
| H | `output/goal-20261022/restart-performance-final.json`: hard termination/restart of isolated server preserves complete application JSON, including drafts/snapshot/history. Local warm HTTP search 25=3.094s/options 1.235s/Sources 1.984s/audit 20=2.281s on 4,402 retained jobs. P records separate live timings, including filtered export 5.797–7.391s and backup 17.782s; measurements are not latency guarantees. |

## 1. Mission and working context

| Requirement | Verified proof / qualification |
| --- | --- |
| Whole discovery→assessment→sources→preparation→tracking for one private candidate | J exercises the complete application workflow; B/P/F verify deployed discovery/source/app surfaces. No separate application layer was introduced. |
| Current repository/service/auth/stack/worker/persistent disk; preserve existing work | Current README/render.yaml/source and native Render configuration review; M/F prove retained production data across rollout. Historical baseline 601ff7d was not checked out or treated as defect proof. |
| Candidate facts from actual CV; unknown facts remain unknown | S and inspected preparation pairs/checklists; no invented qualifications/contact/availability/achievements. Source/candidate/derived/user facts remain distinct. |
| Verify current facts rather than inherit historical acceptance | Fresh backup M, current tests R, deployed P/B/F and final CSS hash. Older 2.2.0 report is explicitly historical. |

## 2. Scope, priorities and boundaries

| Requirement | Verified proof / qualification |
| --- | --- |
| Preserve IDs/original URLs/payloads/snapshots/notes/drafts/history and older queries | M/F compare original tables/fields/payloads; R covers MCF stable UUID/original URL, snapshots, drafts, stage history and legacy query memberships; J/H prove retained application work. |
| Revision-checked PUT and409 unchanged; no silent overwrite | R browser/storage/API regressions and J real competing contexts/resolution. Client base/revision ownership corrected; server checks remain. |
| Distinct facts/uncertainty, no assumed salary or invented candidate facts, no score distribution target | S/R; visible score method/caps and separate source/requirement/checklist presentation in J/B. |
| No paid collectors/new integrations/key lifecycle/wrappers/unrelated scope | This pass used explicit safe modules and offline-safety guards, existing platform/source/native entry points. No paid call or credential lifecycle change in this pass. Historical US$0.0191 incident remains disclosed in the acceptance report. |
| MCF 12h/four named queries/max 10, retained imports labelled, bounded absence not closure | P/F preserve interval 12h/Thai/Marketing Executive/Social Media Executive/Public Relations/max 10; source scopes/labels and R absent-result tests. |
| No employer message/submission; only explicit action Applied | J intercepted external listing navigation, verified no stage change on opening and Applied only after explicit action. R verifies failed Applied never announces success. |
| Isolated mutation tests, production backup/rehearsal before rollout | J/H mutation environments isolated; M precedes rollout; P/F production applications/imports remain zero. |

## 3. Experience architecture and screen contracts

| Required surface/outcome | Verified proof |
| --- | --- |
| Find search-first/optional filters, compact title/company/pay/type/check/score/reason, missing values, long quotes in detail | Current shared presentation/rows; R normalized filters/empty/retry/stale requests; B phone initial-result position and responsive images. |
| Detail facts/listing first, direct requirements/score/notes/preparation; desktop pane/phone full-screen; return search/selection/scroll/focus and unavailable snapshot | J/B/Z/R, including keyboard entry/Escape/return and unavailable application snapshot regressions. |
| Preparation supported pairs → editable drafts → separate unresolved checklist; preserve edits/copy fallback | S/J/R, including late suggestions versus user edits and clipboard rejection. |
| Applications one list, stage/action/date/notes/history, same persistence/conflict/recovery, Closed remains reviewable | J/H/R; B verifies deployed empty state without production mutation. |
| Sources desktop requested→processing→outputs; phone health→source→search/disclosures; inspect scope/errors/fields/payload versions | B/A/R and actual DOM reordering/focus regressions; P confirms source coverage/state. |
| Per-surface purpose/entry/exit/order/actions/data/loading/empty/error/responsive/keyboard contracts | DECISIONS surface table, verified against current scripts and J/B/R. |

## 4. Workflow and state contracts

| Required behavior | Verified proof |
| --- | --- |
| Discover/inspect rejects obsolete results, preserves context; empty/reset/failure/retry | R reversed-response/append-retry tests; J/B detail keyboard return, B screenshots. |
| First note saves, immediate recovery before debounce, actual base, Saved only on valid ack | R first-note/immediate-close/invalid200/storage tests; J/H complete persisted field equality. |
| Clean vs dirty refresh, explicit conflict/rebase, in-flight/newer keystrokes/late acknowledgements | R refresh/base/dirty/inFlight/late-ack tests; J independent contexts and explicit resolution. |
| Recovery all roles/versions/base/patch; ack only own saved version; legacy retained/verified; no auto-submit other tab | R two-tab failed drafts through save/reload, all-job menu, immutable ack ownership, legacy conversion, corrupt/quota/deletion failures. Recovery screenshot listed in§12. |
| Prepare/copy/listing/explicit Apply; failures preserve work | J clipboard/navigation/explicit Applied and R failed-save/late-generation guards. |
| Follow-up/close/correct decisions without erasing fields/history | J stage/action/date/outcome/Closed draft; H restart equality; R snapshots/history. |
| Import idempotence, originals/resolution/date, paginated review and complete export; old absent snapshot explicit | J resolved import/history/export; R API/browser pagination/import/export/older-resolution limitation tests. |
| Refresh success/error/partial/interrupted/single-flight/persisted schedule/restart recovery | R sync/lifespan/rollback/overdue/interrupted tests; P/F live persisted schedule after actual deploy restarts. Successful and failed upstream histories remain distinct. |
| Export normalized filters/order/current selection; one selected record; formula protection; preserve failed selection | P complete ID-order parity, J one selected application+notes/draft/history, R CSV/XLSX injection/long-text continuation/failed export tests. |
| Explicit editor states, inFlight/pending ownership, retries/busy semantics | DECISIONS state table and R named browser regressions; J conflict/failed clipboard; truthful quota/download screenshot. |

## 5. Evidence and documented fit

| Requirement | Verified proof / limitation |
| --- | --- |
| Version documented-fit-v2, 20/50/30, exact quote/CV support, distinct supported groups | S/R; shared server presentation inspected in P/J/source inspector. No salary/prestige/geography/freshness bonus. |
| Action+scope, independently assessable clauses/partial credit; no topic-only graphics/animation/video/tools/finance | S/R targeted creative/specialist/negated/shared-action/tool/email/website/visual/concatenated prose tests. Original source_quote retained. Mixed inseparable noun scopes conservatively withheld. |
| Unicode/bullets, genuine degree alternatives, no company history/recruiter/application instructions, PropertyGuru geography | S/R specific regressions. Marketing alternatives supported; unrelated exact degrees unproven. |
| Missing source/candidate/incompatibility distinct, mandatory caps/withholding, preferred separate | S/R states/gates/components; J requirements/score evidence inspection. Unsupported evidence never claims incapability. |
| Relevant responsibility–CV preparation pairs; unresolved requirements separate; existing draft authoritative | S/J/R, including intentionally empty and edited drafts/late suggestions. |
| Fixed top/aligned/adjacent/language/finance/creative/degree/boilerplate/incomplete synthetic+real corpus; defensible ranking | Two fixed corpora and S/R. No arbitrary target percentage; corpus does not prove semantics for all future wording. |

## 6. Sources, persistence and API compatibility

| Requirement | Verified proof |
| --- | --- |
| Raw payloads intact; explicit vs derived requirements/evidence; omission vs explicit value/original provenance | R Japanese requirement SQLite roundtrip/omission/restriction, employer-field and original payload key tests; M/F full preservation. |
| Successful listing/attempt/error/content dates distinct; actual verified order; redacted escaped versions/safe URLs | R provenance/freshness/redaction and safe renderer tests; J/B source inspector; P source history does not relabel failures. |
| Derived arrangement reflects changed description but explicit/omitted arrangement preserved | R three provenance/recompute regressions; shared source-field implementation. |
| Employment memberships/mixed/missing/legacy; concise summaries/clause evidence/field dates shared across outputs | R shared presentation and membership tests; P normalized complete export/search order parity; B rendered detail/inspector. |
| salary_only independent of minimum; known SGD monthly minimum, annual conversion, daily/hourly/foreign/unknown units preserved; sort_by compatible | R salary/filter/export tests and P full paginated comparisons. No salary minimum default. |
| PUT/409, authenticated history offset/limit, complete retained export history | R authenticated API/pagination/export tests and J resolved original+resolution export/history. P all protected paths return 401 unauthenticated. |
| Additive/versioned/idempotent SQLite backfills; compare original content/restore not only counts | M twice-started migration and restoration/digests; F postdeploy table preservation. This patch needs no new schema. |
| Native documented config/worker/disk, official docs before changes/no wrappers | Current README/render.yaml and actual Render/Uvicorn config review; P same-origin validation 422 proves HTTPS write passed origin guard without persisting a mutation. F native restart health/schedule. |

## 7. Visual system, components and writing

| Requirement | Verified proof |
| --- | --- |
| Calm blue identity, readable fixed type, compact rows, facts before advice, token consistency/wrapping | Current CSS/templates, DECISIONS component/appearance contracts and visually inspected B/J/Z screenshots. No new framework/design platform. |
| Component purpose/anatomy/data/variants/states/events/name/keyboard/responsive contracts | DECISIONS inventory: nav/search/rows/detail/fields/status/conflict/recovery/evidence/history/inspector/export; matches current implementation. |
| Hover/focus/active/selected/disabled/loading/error, stable labels, understandable disabled/retry, preserve data/selection | R failure/loading/selection/focus tests; A computed focus/contrast; J edits/conflict; source and native controls inspected at B/Z widths. |
| Concrete truthful Saved/storage/conflict/empty/check/clipboard messages; diagnostics confined to inspection | R malformed ack/storage denial/401/timeout/failed Applied; J clipboard and conflict; quota recovery screenshot. |
| Fixed readable scale, multilingual/long URLs wrapping, explicit status labels/reduced motion | B/Z overflow and action checks, A transition 0s/contrast, R long XLSX content preservation. No color-only meaning or essential animation dependency. |

## 8. Accessibility and responsive behavior

| Requirement | Verified proof / scope |
| --- | --- |
| Semantic landmarks/headings/labels/names/states, logical keyboard order, visible focus, meaningful announcements | A/R/B/J: valid region/dialog, heading, inert skip link, actual source DOM order, focus on selection/resize, modal entry/Tab/Escape/return; desktop nonmodal. |
| Text 4.5:1/large 3:1, perceivable boundary/focus, no color-only status | A manual computed ratios resolve axe incomplete nodes; body 16.186, secondary 6.421, boundary 3.758, focus 5.169. Labels accompany colors. Not a WCAG certification. |
| 44px targets including checkbox/disclosures, long/error content/text resizing, no invisible focus | R/A target/focus checks plus B/Z long responsive layouts; F final website and endpoint links 44px on live CSS. |
| 390×844/768×1000/1440×1000, phone first result/source search initial viewport, no overflow/inaccessible action | B figures and current screenshots; source DOM/keyboard order agrees with display. |
| Native 200% zoom with method/window/height/browser metrics, distinct from resized viewports | Z native Appearance setting in temporary Chromium profile, viewport 713×453/document705; screenshots and detail dismissal/return. |

## 9. Alternatives, research and decision quality

| Requirement | Verified proof / qualification |
| --- | --- |
| Diverge/evaluate/converge/validate real uncertainty; compare task/effort/evidence/recovery/access/compatibility/performance/maintenance | DECISIONS compares editor ownership/recovery granularity, provenance, clause scoring, contextual evidence, mobile order and long export strategies; alternatives tied to reproduced problems and R/J/B/A/M validation. Settled architecture not reopened. |
| Source inspection/walkthrough/heuristics, facts vs assumptions, no invented participant findings | S original CV/source review, current tests/screenshots/journeys and explicit limitations. |
| Candidate task protocol when participation unavailable | DECISIONS protocol covers find/explain evidence/check requirement/edit-recover/follow up. Participant validation **unperformed**, not required to fabricate completion. No interviews/times/satisfaction/conversion claims. |

## 10. Dependency-aware execution

| Ordered phase / constraint | Verified proof |
| --- | --- |
| Baseline/docs/runtime/CV before reliance | Initial production backup/current worktree and official-document review; S; historical baseline separated from current release. |
| Protect data with failing regression then fix, correct evidence, complete experience | R reproduced acknowledgement/storage/presence/transaction/scoring/accessibility failures before fixes; S semantic review; J/B current complete journeys. |
| Audit→fix→focused checks→final regression, not mockup/test-only acceptance | R 154 + final target regression 11; J/B/Z/A real browser and P/F deployed/data checks. Final CSS-only diff inspected so valid prior API/JS proofs are reused proportionally. |
| Consistent backup/migrate/restore before native deploy, inspect content, verify auth/records/parity/source/scheduler/restart | M before deployment; P/F after; native Git auto-deploy existing service/disk, same persisted schedule/alive scheduler. |
| Explicit inspected safe modules; isolated mutations; no blindly run probes/paid calls | R offline-safety guards and explicit command below; J/H isolated; production application count 0. Historical incident remains disclosed. |

## 11. Acceptance evidence and commands

All nine acceptance groups have direct evidence: concurrent editing/recovery R/J; durable work J/H; source preservation R/M/F; assessment S/R; search/export R/J/P; complete journey J/B/Z; responsive accessibility A/B/Z/F; failures/performance R/J/H/P; migration/rollout M/P/F. Tests cover their explicit fixtures; browser and live checks cover the actual exercised dataset/flows, not all possible future source wording or availability.

```powershell
python -m unittest test_storage test_audit_qa test_evidence test_sync test_source_audit test_source_preservation test_fit_v2 test_workspace_v2 test_browser_workspace test_offline_safety test_accessibility -q
node --check static/workspace.js
node --check static/sources.js
node --check static/fit-score.js
git diff --check
```

Never use broad discovery: historical credential-bearing probe scripts are ignored and import-guarded. The journey runner is `test_workspace_journey.py`; read it before running and require isolated storage plus `CAREER_QA_ISOLATED=1`, `CAREER_QA_URL`, `CAREER_QA_PASSWORD`, optional username. No credentials in reports. Screenshots live under ignored `output/playwright/`; backups under `migration/`. No tool-absence substitute was counted as runtime success.

Live MCF evidence in P: scheduled 22 October 14:35 UTC run succeeded four×10, added 4/updated 35. Preceding 02:34 UTC four timeouts remain failed; old interrupted runs remain interrupted. F preserves next run 23 October 02:35 UTC, 12h/four-query/max 10 scope. No extra collection was triggered for acceptance. Other sources remain retained imports; none of these results verifies every stored vacancy or future source availability. Live reads were measured separately from local H; deployment restart 502 probes are failures, not successful source checks.

## 12. Required deliverables and completion review

| Required output | Current authoritative evidence |
| --- | --- |
| One reusable canonical brief/master prompt | `EXECUTION_BRIEF.md`. |
| Implemented workspace preserving architecture/data and focused regressions | Deployed commit 3b8664d plus R/J/M/P/F; native stack/auth/disk retained. |
| Concise decisions/alternatives/compatibility/date/screen/component/transition contracts | `DECISIONS.md`. |
| Fixed corpora/exact commands/safe isolated runner | Both fit JSON corpora, `test_fit_v2.py`, command block and `test_workspace_journey.py`. |
| Representative discovery/details/Sources/recovery-conflict/history responsive and zoom images | `output/playwright/compliance-20261023/production-find-390.png`, `production-sources-390.png`, `production-detail-1440.png`, `production-source-inspector.png`; explicit fixture `conflict-fixture-1440.png` and isolated J `application-history-1440.png`; `native-200-find.png`, `native-200-sources.png`, `native-200-applications.png`. Quota recovery: `output/playwright/compliance-20261022/storage-quota-recovery-fixture-1280.png`. B/J/Z/A/F label environments/dimensions/interaction checks. |
| Acceptance report with actual tests/browser/rollout/source/data/performance/side effects and external limits | `ACCEPTANCE_REPORT.md` current 23 October section, supported by R/J/P/F/B/Z/A/S/M/H; 21 October section explicitly historical. Historical US$0.0191 incident retained. |
| Verified existing deployed workspace and concise delivery links | F deployment/health/data/CSS, P auth/parity/sources, B read-only browser. URL above; root's user-facing delivery links the brief/decisions/report. |

The inspected current evidence identifies **no remaining critical or major defect or unverified mandatory technical gate in scope**. Participant/screen-reader research was not performed and is not claimed; source outages/incomplete retained descriptions and unproven candidate requirements remain explicit product uncertainties. Final acceptance/report consistency and user-facing delivery are root-owned documentation/communication steps. Nothing here changes the original scope or relabels failed collection as success.
