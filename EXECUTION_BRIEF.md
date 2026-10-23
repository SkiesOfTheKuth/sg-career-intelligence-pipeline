# SG Career Intelligence — Complete Workspace Design and Implementation Master Prompt

Act as a principal product designer and workflow architect who can implement and verify a private, evidence-based career workspace. Apply supporting expertise in information architecture, accessible interaction design, frontend engineering, transactional persistence and source-data quality. Use each discipline to improve a real user task. Produce working changes, precise interaction contracts and observable acceptance evidence.

## Authorized seven-day collection campaign — 23 October 2026

The user-approved campaign plan supersedes the paid-collection and new-source restrictions in section 2, items 5–6, solely for the 168-hour campaign beginning at the first paid pilot. All identity, evidence, authentication, application-preservation and deployment safeguards remain in force. The campaign policy, implemented bounds and explicit source gates are recorded in [CAMPAIGN.md](CAMPAIGN.md). MyCareersFuture retains its four queries × ten results every 12 hours. No claim of unattended or seven-day acceptance is established by implementation tests.

## 1. Mission and working context

Improve the **whole SG Career Intelligence workspace**: discovery → assessment → source inspection → preparation → application tracking. Enable Dechsurang to identify worthwhile Singapore roles, understand the evidence and uncertainty, prepare truthful applications, and retain work through failures and concurrent editing. Treat this as a production improvement of an existing application, not a new dashboard or a visual concept exercise.

The primary user is one candidate in one private workspace. The product supports repeated searching, comparing, writing and following up, with interruption and return. Design for desktop keyboard/mouse use and phone touch use. Device capability, network reliability and assistive-technology needs vary; do not assume a specific impairment, technical proficiency, interview result or observed user habit without evidence. No research participants or usability findings are supplied.

Project locations and compatibility anchors:

- Repository: `C:\Users\Study\sg-career-intelligence`; Git remote: `https://github.com/SkiesOfTheKuth/sg-career-intelligence-pipeline.git`.
- Existing live workspace: `https://sg-career-intelligence.onrender.com`; existing Render service: `srv-dbb3dfnf3r2c73848abg`.
- Keep FastAPI, plain JavaScript, SQLite, existing authentication, the existing Render service, one native Uvicorn worker and the persistent disk. Read `README.md`, `PRODUCT.md`, `render.yaml`, current application/storage code and applicable repository instructions before changes.
- The original improvement baseline was `601ff7d`. It is historical context, not a checkout target or proof of present defects. Inspect the current revision, dirty files, tests and runtime. Keep already completed functionality and user changes.
- Candidate facts must come from the user's actual CV and verified profile evidence. The original CV reference is `C:\Users\Study\Downloads\CV 2026.pdf`. Locate the supplied evidence if paths differ; unavailable evidence means an unresolved fact, not permission to invent it.

This prompt defines requirements for execution. Existing reports describe past observations; independently verify the prerequisites for each new action. Distinguish requirements, verified current facts, low-risk assumptions, proposed behavior and unverified hypotheses in the work record. Ask a narrow question only if missing information materially prevents a correct action; continue independent work while awaiting the answer.

## 2. Scope, priorities and boundaries

Execute in this order: **protect edits and source evidence → correct assessment → improve the complete journey → verify and iterate → rehearse and deploy**. A working screen cannot compensate for lost notes, misleading evidence or unsafe migration.

Mandatory invariants:

1. Preserve existing job IDs, original URLs, source payloads, application snapshots, notes, user-written drafts and stage history. Keep existing query parameters and older employment-type values compatible.
2. Preserve revision-checked `PUT /api/applications/{job_id}` writes and `409` conflicts. Correct client revision handling; never weaken the server's concurrency check.
3. Keep source facts, candidate facts, derived assessments and user decisions visibly distinct. Missing information remains unknown. A location, search query or company history does not establish a candidate requirement.
4. No assumed salary minimum, fabricated contact details, availability, qualifications or achievements. Scores are documented overlap, never hiring probabilities. Do not tune them to create an attractive distribution.
5. Paid collection and new-source admission are permitted only within the authorized seven-day campaign above; outside it, the previous paid/new-source restriction remains. No credential lifecycle changes, unrelated dashboards, custom launch wrappers or new operational rituals. Do not revoke, rotate, delete or invalidate keys. Inspect test imports before execution so historical probe scripts cannot initiate network work.
6. MyCareersFuture checks remain every 12 hours: Thai, Marketing Executive, Social Media Executive and Public Relations, up to ten results per search. Other sources remain clearly labelled retained imports unless admitted and verified by the authorized campaign. A bounded search cannot verify or close every stored listing.
7. Do not submit applications or send messages to employers. Opening an original listing is navigation; only an explicit user action records an application as Applied.
8. Test application mutations against isolated storage. Capture production data and rehearse migration/restoration before deploying code that changes it.

Optional refinements must resolve an observed task, accessibility or clarity problem within these boundaries. Do not introduce accounts, teams, onboarding funnels, analytics dashboards, new scraping services or a separate design-system platform.

## 3. Experience architecture and screen contracts

Keep **Find roles**, **Applications** and **Sources** as task destinations. Search is the main discovery entry point. Role details and preparation remain contextual to a selected role. Source provenance is available without forcing the user to leave a decision unfinished.

Use consistent names for employer, advertised salary, employment type, verification, documented fit, requirements, notes, next action, follow-up and stage. Keep the distinctions between source dates and successful verification, evidence gaps and incompatibility, and browsing and applying visible. Avoid repeated status badges and internal field names in ordinary user controls.

| Surface | Entry, purpose and content hierarchy | Main actions and state requirements |
| --- | --- | --- |
| Find roles | Main navigation or retained search URL. Search and filters → result count/order/export → compact role rows. Rows show title, company, advertised pay, employment type, verification, documented fit and one concise evidenced reason. | Search, filter, order, inspect, save and export. Show useful loading feedback, actionable empty state, retry on failure and explicit missing types/pay. Keep lengthy quotations in details. |
| Role details | Selected result, application, direct role URL or source inspector. Employer facts and original listing first; requirements, assessment evidence, notes and preparation directly reachable. | Desktop pane and phone full-screen detail. Preserve search, selection, scroll and focus when returning. Show unavailable-listing history without discarding its saved snapshot. |
| Preparation | Selected role's preparation action or application draft. Supported responsibility–CV pairs → editable drafts → separate unresolved-requirement checklist. | Preserve user edits, copy text with failure recovery, navigate to the original listing and explicitly Mark applied. Never regenerate over a user draft during refresh. |
| Applications | Main navigation or saved role. One list with stage, next action, follow-up, notes and preserved history. | Stage filtering, detail editing, selection and exports. Use identical save/conflict/offline/recovery behavior from every editor entry point. Closed records remain reviewable. |
| Sources | Main navigation or a role's evidence context. Desktop: requested sources → processing/evidence → outputs. Phone: collection health → source selection → record search. | Inspect source scope, successful/failed attempts, retained records, cleaned fields, exact quotations and payload versions. Put expanded flow and coverage behind phone disclosures. Failures never masquerade as successful checks. |

For each changed surface, record its purpose, entry/exit, content order, primary/secondary actions, data dependencies, loading/empty/error behavior, responsive transformation and keyboard behavior. Use these contracts to guide implementation rather than generating separate decorative mockups that do not match the application.

## 4. Workflow and state contracts

The user remains responsible for deciding whether to apply. The application preserves evidence and work, explains uncertainty and records explicit decisions. The collector owns only the bounded refresh; the assessment derives only from retained source and verified candidate evidence.

| Workflow and trigger | Preconditions, actions and completion | Exceptions and recovery |
| --- | --- | --- |
| Discover and inspect | Authenticated user searches, evaluates compact rows, opens details, inspects requirements and CV evidence, then returns to the same context. | Ignore obsolete search responses; preserve filters, selection, scroll and focus. An empty result offers clearing/revising filters. A failed request retains useful context and offers retry. |
| Save and resume | Saving a role or writing the first note creates a Saved application. Persist the pending patch locally before a debounced request can be lost. Submit with its actual base revision; show Saved only on acknowledgement. | Network failure, timeout, sign-in expiry or immediate close preserves the draft and its base. Do not falsely promise server persistence or full offline search. Explain where recovery is available. |
| Compare concurrent versions | Two editors may modify the same application. Clean refresh replaces displayed values and base revision together. Dirty refresh keeps the written-against base and exposes a conflict when the server changes. | Show current server and local versions with an explicit resolution. Rebase only after the user chooses. Never silently choose the newest timestamp or overwrite dirty text. Preserve newer keystrokes typed while a save was in flight. |
| Recover browser work | Present all affected roles and competing browser versions, with original base revision and pending changes. Loading a recovery opens it for review. | Acknowledgement removes only the corresponding saved editor/version. Other tabs' records remain. Verify replacements before removing that editor's previous record; preserve legacy maps until conversion is verified. Do not auto-submit another tab's work. |
| Prepare and apply | User enters Preparing, reviews supported pairs and unresolved checks, edits a draft and visits the listing. An explicit Mark applied action sets Applied. | A failed clipboard request leaves selectable text and copying instructions. A listing navigation does not advance stage. Missing source/CV facts remain in the checklist, never filler claims. |
| Follow up and close | Preserve the stages Saved, Preparing, Applied, Interviewing, Offer and Closed. User records next action/date, changes stage deliberately and closes with an outcome where supplied. | Allow correction of decisions without erasing previous history. Retain notes, drafts and snapshot when a listing expires or an application closes. Validate inputs without clearing them. |
| Import and review history | Legacy imports use existing duplicate-prevention receipts. Different notes/stages remain retained versions; resolution records the original, selected result and date. | Repeated imports do not duplicate work. Resolved versions remain available in paginated history and complete exports. State explicitly when old data never contained a historical resolution snapshot. |
| Refresh evidence | Scheduled or explicit MyCareersFuture check records per-query responses, updates returned records and preserves omitted fields. | Keep failed, partial and interrupted outcomes distinct. Prevent duplicate in-flight work, preserve last success and schedule, and recover interrupted runs after restart. Absence from a limited search is not closure. |
| Export | User exports the current normalized search/order or selected applications/stage. Include notes, drafts, follow-up, snapshots/links and retained history as appropriate. | Exactly one selected application yields one record. Protect every CSV/XLSX cell from formula execution; report failures without changing selection or stored data. |

Represent editor states explicitly as clean, dirty, saving, saved, failed/offline, conflict and recovery available. Specify allowed transitions, ownership of in-flight versus newer patches, acknowledgement behavior and retry behavior. Apply semantic busy/disabled states only while an action cannot be repeated safely; keep cancellation, navigation and recovery understandable. Prefer inline state and comparison views over unnecessary confirmations.

## 5. Evidence and documented-fit requirements

Keep the visible rubric version **`documented-fit-v2`** and its **20-point role family, 50-point responsibility, 30-point mandatory-requirement** structure. Document the calculation, caps, withholding and reasons. Reuse the same server presentation in discovery, details, source inspection and exports.

- Match an action and its scope, not a topic word. Social-media management cannot prove graphic design, animation, video production, specialist finance or named-tool proficiency.
- Split compound duties into independently assessable clauses while retaining their complete original source quotation. Expose partial support and award credit only for supported clauses. Keep specific CV evidence inspectable and avoid duplicate credit for repeated supported task groups.
- Normalize bullets and Unicode punctuation for comparison while preserving displayed quotations. Parse alternative degree subjects so Marketing in a genuine alternative can be supported; do not turn an unrelated exact degree into Marketing.
- Exclude identifiable company history, recruiter licences and application instructions from candidate requirements. PropertyGuru's geographical coverage must never become a Thai-language requirement.
- Distinguish missing source information, missing candidate evidence and documented incompatibility. Unsupported evidence is not proof of incapability. Keep existing mandatory-requirement limits and withholding for insufficient descriptions; explain their effect rather than hiding the score's uncertainty.
- Do not add fit points for salary, prestige, geographical presence or verification freshness. Preferred requirements are separate from mandatory evidence. Correct a rubric defect with evidence and regression coverage, not a desired score percentile.
- Preparation must cite relevant supported responsibility–CV pairs. Present unresolved requirements separately so the user can investigate or supply truthful evidence. Existing draft text remains authoritative until the user edits it.

Maintain a fixed review corpus with representative top recommendations, aligned and adjacent roles, language restrictions, specialist finance, compound creative duties, alternative degrees, boilerplate and incomplete sources. Test claims and defensible pairwise ranking comparisons. Include real retained quotations alongside synthetic regressions; do not claim the corpus proves semantic correctness for all future wording.

## 6. Sources, persistence and API compatibility

Keep original collector payloads intact. Store explicit source requirements and their evidence references separately from requirements derived from description text. A response omitting a field preserves its retained value and original provenance; distinguish omission from an explicitly supplied value according to the upstream contract. Never attribute old content to a newly received payload just because it is newest.

Separate successful listing checks, latest attempts/errors, retained record dates, description dates and requirement dates. “Recently verified” orders by actual successful verification with unverified records last. The source inspector exposes field provenance and retained versions with credential-like keys redacted. Render source content as escaped text and allow only safe original-listing URLs.

Extend existing interfaces rather than introducing an application layer:

- Job presentation adds normalized employment memberships, concise assessment summaries, clause-level evidence and field-specific provenance dates. Missing employment is explicit. Mixed freelance/employment listings appear in each appropriate view; older combined filter values stay compatible.
- Search and `/api/export/filtered` share normalized filters and order, including the existing `sort_by` parameter. Salary disclosure and minimum thresholds remain independent. Use advertised SGD monthly minimums; normalize annual amounts, retain daily/hourly units and exclude unknown units/currencies from monthly threshold claims.
- Preserve revision-checked application writes and their `409` current-server response. Add/retain authenticated `GET /api/applications/{job_id}/history?offset=0&limit=25`; export complete retained import/resolution history, not only the current page.
- Use additive, versioned SQLite migrations with idempotent backfills. Keep existing IDs, snapshots and payloads. Compare original fields and table contents before and after migration/restoration; row counts alone cannot establish preservation.
- Keep normal native entry points, documented configuration and Render's persistent disk. Avoid wrapper chains, background watchers or instructions requiring users to remember special launch rules.

Read official documentation before configuration or troubleshooting. Relevant references include FastAPI lifespan (`https://fastapi.tiangolo.com/advanced/events/`), SQLite transactions/backup (`https://docs.python.org/3/library/sqlite3.html`), browser storage events (`https://developer.mozilla.org/en-US/docs/Web/API/Window/storage_event`), Render disks/deploys (`https://render.com/docs/disks`, `https://render.com/docs/deploys`) and Playwright browser contexts (`https://playwright.dev/docs/browser-contexts`). Check current versions and actual service configuration before relying on a historical example.

## 7. Visual system, interaction components and writing

Preserve the established calm blue identity: accent `#2563EB`, dark ink, white/neutral surfaces, restrained separators and readable system sans-serif typography. Reuse the current CSS tokens and components; inspect their current values before editing. Prefer compact rows to nested cards or metric tiles. Employer facts receive visual priority; assessment and actions remain easy to scan without overwhelming the listing.

Maintain a small shared component vocabulary in plain HTML/CSS/JavaScript: navigation, labelled search/filter controls, role/application rows, detail pane, form fields, save feedback, conflict/recovery comparison, evidence disclosures, history, source inspector and export selection. For each changed component document purpose, anatomy/data inputs, variants, states, events, keyboard behavior, accessible name and responsive adaptation. Do not create a framework or library solely to document this inventory.

Specify each control's relevant default, hover, focus, active, selected, disabled, loading and error states. Keep its label and position stable while processing. A disabled control must have an understandable reason; a retryable error must expose a usable next action. Preserve selected/exported items and entered form values when requests fail.

Use existing color, type, spacing, sizing, radius, layering and breakpoint tokens consistently. Keep long prose comfortably readable, allow long titles/URLs and multilingual quotations to wrap, and use fixed readable product type scales. Reserve accent for actions and selection. Pair status colors with explicit labels. Transitions should communicate state quickly and respect reduced motion; content must remain visible without animation.

Write concrete feedback tied to the user's next action. Examples to adapt to the actual state:

- “Saved” only after acknowledgement; “Saving…” during a request.
- “Your edits are kept in this browser. Retry save.” after a failed write when recovery was actually persisted.
- “This application changed elsewhere. Compare versions.” for a revision conflict.
- “No roles match these filters” with a clear reset action.
- “No successful listing check recorded” when only an import date exists.
- “Requirements need checking” for unresolved evidence, with an explanation of what is missing.
- “Clipboard access failed. Select and copy the text.” when automatic copying fails.

Do not claim recovery succeeded if browser storage itself failed. Explain the specific failure and preserve accessible text for manual copying. Keep backend field names and diagnostic details inside relevant source/technical inspection rather than the ordinary application flow.

## 8. Accessibility and responsive behavior

Use applicable WCAG 2.2 AA criteria as the design baseline. Test relevant criteria rather than asserting certification from a screenshot. Require semantic landmarks/headings, explicit labels, logical keyboard order, visible focus, accessible names/states, descriptive links, and status/error announcements that do not announce every keystroke. Text contrast must meet 4.5:1 for ordinary text and 3:1 for large text; important control boundaries and focus indicators must remain perceivable. Do not use color alone.

Maintain at least 44px touch targets, including associated checkbox labels and disclosure actions. Test long content, zoom, text resizing, error text and keyboard-only use. Dialog/detail focus must enter predictably, remain within a modal when appropriate, dismiss with Escape and return to the invoking control. Do not trap focus in a desktop nonmodal pane or leave an invisible control focused.

At 390px, keep the first discovery result and Sources record search reachable in the initial phone viewport. Put optional filters, the expanded source-flow diagram and coverage behind clear disclosures. At 768px and 1440px, preserve the useful reading hierarchy and desktop evidence flow without clipping actions. Verify actual 200% browser zoom in addition to viewport tests; a resized screenshot alone is not proof of native zoom behavior. Document the tested viewport height, browser, zoom method and any tool limitation.

## 9. Alternatives, research and decision quality

Where a verified problem leaves meaningful uncertainty, use **diverge → evaluate → converge → validate**. Briefly compare two or three substantively different solutions to that same problem: for example, inline versus separate evidence review, competing-version recovery presentation, or phone disclosure placement. Do not reopen settled stack, navigation or data-preservation constraints merely to generate alternatives.

Evaluate alternatives qualitatively against task effectiveness, cognitive effort, evidence visibility, error recovery, keyboard/touch access, compatibility, performance and maintenance cost. Record the problem, alternatives, selected approach, rationale, trade-off, risk and validation needed. Avoid invented numerical precision or combining incompatible patterns. Recognition, progressive disclosure and fewer interruptions are useful only when essential facts and recovery remain discoverable.

Use source inspection, task walkthroughs, heuristic review and available runtime evidence. Clearly label assumptions and proposed behavior. If the candidate is available for usability review, use concrete tasks: locate a worthwhile role, explain why it is or is not supported, find an unresolved requirement, edit and recover a draft, and set a follow-up. Record observed completion/errors only with actual participation. Otherwise provide that protocol and label participant validation unperformed; never invent interviews, satisfaction scores or conversion metrics.

## 10. Dependency-aware execution

1. **Establish the baseline.** Read authoritative project/upstream documentation, inspect the current worktree and runtime, map screens/data flows, and identify defects against this prompt. Confirm source/candidate facts needed for the next decision. Separate product failures from unavailable upstream services. Treat historic test counts as leads, not proof.
2. **Protect data first.** Turn reproduced revision/recovery/provenance/import-history defects into failing regressions. Correct ownership and persistence at their cause, add migrations/backfills where needed, and verify isolated roundtrips before touching the production database.
3. **Correct evidence.** Implement clause/action/scope scoring and preparation pairs against the fixed corpus. Preserve exact quotations, provenance, gates, withheld scores and documented incompatibility. Review recommendations semantically as well as running tests.
4. **Complete the experience.** Apply shared presentation/filtering and the screen/workflow/component contracts across discovery, details, preparation, applications and Sources. Resolve meaningful design uncertainty with the short comparison process. Verify responsive layouts and interaction states in a real browser.
5. **Audit, fix, verify.** Complete the acceptance cases below. Fix unresolved critical/major failures, run focused checks after each change, then run the final relevant regression suite. Broaden testing only when a new change or unresolved concern warrants it. Do not stop at a plan, attractive mockup or test-only patch.
6. **Rehearse and roll out.** Capture a consistent production backup. Rehearse migration and restoration on isolated copies and inspect preservation evidence. Deploy through the existing native Render flow within authorization, then verify authentication, persisted records, search/export parity, source status and scheduler recovery. Brief disk restarts must not lose work or collection history. Use documented skip-deploy commit syntax for later documentation-only changes when appropriate.

Inspect any manual scripts or test modules before importing/executing them. Use explicit test modules; prohibit paid collector calls in tests and isolate network effects. Never run an old deployment or probe script blindly because its filename sounds relevant.

## 11. Acceptance evidence and verification commands

Maintain requirement-to-evidence traceability. For every check record the environment/revision, stimulus, expected result, actual result and artifact or test. Distinguish fixture regressions, isolated real-data journeys, deployed reads and live upstream responses. Tests are evidence only for behavior they actually cover.

| Required acceptance | Observable proof |
| --- | --- |
| Concurrent editing and recovery | Two contexts edit one application without silent replacement. Clean and dirty refresh behavior differs correctly. Two tabs retain failed drafts across another tab's acknowledgement and reload. Immediate-close and in-flight-keystroke tests preserve text/base. |
| Durable application work | Notes/drafts/history survive failed writes, a second authenticated browser and hard restart against isolated storage. Resolved imported originals and resolutions remain reviewable and exportable. |
| Partial source preservation | SQLite roundtrip followed by a response omitting description retains explicit Japanese language requirements, evidence references, original dates and assessment restriction. Omitted employer facts remain. |
| Trustworthy assessment | Unsupported graphics/animation/tool/finance scope earns no credit; boilerplate excluded; supported Marketing alternatives recognized; PropertyGuru geography never produces a Thai requirement. Fixed-corpus claims and ranking comparisons pass. |
| Search and export consistency | Older responses cannot replace newer results. Employment membership/legacy values, salary disclosure/thresholds/units and actual verification ordering pass. Search and export return identical IDs/order for identical normalized filters. One selected application exports one record with notes; formula-injection fixtures stay text. |
| Complete user journey | With mouse and keyboard: discover → inspect source/CV evidence → prepare/edit → open original listing without changing stage → explicitly Mark applied → follow-up → closure → history. Clipboard failure, return focus/search/scroll and unavailable-role snapshots work. |
| Responsive accessibility | Inspect screenshots/interactions at 390px, 768px, 1440px and actual 200% zoom. No horizontal page overflow or inaccessible action. First phone result and source search are initially reachable. Labels, focus, contrast, targets and reduced motion are checked. |
| Failure and performance | Exercise loading, empty, unauthorized, timeout, offline save, conflict, partial refresh and clipboard failure without losing work. Measure search/source responsiveness with the actual retained dataset; record local versus live timings and investigate timeouts/blocking. |
| Migration and rollout | Consistent backup, additive/idempotent migration, restoration integrity and original-field/payload comparisons pass. Live auth, records, filters/exports, bounded source scope and persisted schedule/restart recovery verified. Failed upstream attempts remain failures. |

Current repository verification entry points, to verify against the current checkout before execution:

```powershell
python -m unittest test_storage test_audit_qa test_evidence test_sync test_source_audit test_source_preservation test_fit_v2 test_workspace_v2 test_browser_workspace test_offline_safety test_accessibility -q
node --check static/workspace.js
node --check static/sources.js
node --check static/fit-score.js
git diff --check
```

The browser tests require Python Playwright and its Chromium browser. Read `test_workspace_journey.py` before running it. Its mutating runner requires an isolated database and explicit `CAREER_QA_ISOLATED=1`, `CAREER_QA_URL`, `CAREER_QA_PASSWORD` and, if needed, `CAREER_QA_USERNAME`; never point it at production. Do not print credentials. Keep screenshots under `output/playwright/` and backups/rehearsals under `migration/` with private artifacts excluded from Git.

If a required tool is unavailable, use a truthful substitute: precise interaction specifications without a graphical design tool, static review plus an executable test protocol without a browser, or a documented deployment blocker without service access. Do not label the corresponding runtime/design validation complete. Continue independent work; report the smallest actual remaining dependency.

## 12. Required outputs and completion

Produce one coherent set of deliverables, scaled to this existing application:

1. This project-specific execution brief as the reusable master prompt; maintain it as the single canonical instruction artifact.
2. Implemented workspace changes and focused regression coverage preserving the existing architecture and data.
3. `DECISIONS.md`: concise consequential choices, alternatives/trade-offs where needed, compatibility and evidence/date policies. Include the changed screen/component/transition contracts there or beside their implementation when that makes them easier to maintain.
4. Fixed scoring-review corpora and exact verification commands; safe isolated journey runner where needed.
5. Representative discovery, details, Sources, recovery/conflict and history screenshots, including responsive and zoom evidence. Label environment and dimensions.
6. `ACCEPTANCE_REPORT.md`: requirement coverage, actual test/browser/rollout results, source outcomes, migration/restoration evidence, measured performance, deployment revision/URL and remaining external limitations. Report any unintended side effects candidly. Link artifacts; do not expose credentials.
7. The verified deployed workspace through the existing Render service and a concise user-facing delivery with links to the prompt, decisions and acceptance report.

Completion requires current evidence for every applicable mandatory outcome and no unresolved critical/major defect in scope. A critical defect loses/corrupts data, bypasses authentication or falsely claims a consequential action; a major defect blocks a core journey, materially misstates evidence or prevents recovery/access. Classify less severe issues honestly instead of silently redefining the requirement. External outages may be reported separately, but cannot be called successful checks or used as proof of live collection acceptance.

Before finishing, audit the original objective and all listed deliverables against the current files, tests, rendered experience and runtime. Keep design requirements distinct from completed implementation, and past acceptance distinct from current evidence. Reuse valid current-task checks; do not redo a completed system or create extra artifacts merely to appear thorough.

**Execute the ordered work against the current workspace. Protect user work first, make evidence inspectable, complete every core journey, and repeat audit → fix → verify until the required outcome is demonstrated. Deliver concrete changes and honest acceptance evidence, not a generic design essay or promises of later implementation.**
