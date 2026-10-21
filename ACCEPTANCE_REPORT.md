# Workspace v2 acceptance and rollout

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
