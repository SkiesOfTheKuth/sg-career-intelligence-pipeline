# Workspace execution brief

## Purpose and acceptance

Dechsurang uses this private workspace to find worthwhile Singapore roles, inspect employer and CV evidence, prepare truthful applications, and retain work through failures and concurrent editing. The approved implementation plan is the scope. Starting revision: `601ff7d` (clean working tree verified 21 October 2026).

Keep FastAPI, plain JavaScript, SQLite, existing authentication, and the existing Render service. Preserve IDs, URLs, source payloads, application snapshots, notes and drafts. No paid scraping, additional integrations, credential lifecycle changes, invented candidate facts, or salary floor.

## Design decisions

Use the existing restrained blue product interface with readable system typography and compact role rows. Employer facts precede advice. A row supplies title, company, pay, employment types, verification, documented fit and one concise evidenced reason; detailed quotations belong in the inspector. Search and the first useful result must be visible on a phone. Sources retains its sources → processing → outputs view on desktop; collection health, source choice and record search take priority on mobile. Native controls, visible focus, reduced motion and 44px targets apply throughout.

One candidate and one workspace. Applications remain one list with stages, next actions, follow-up dates, notes, preparation and inspectable history. Opening an external listing does not mean an application was submitted.

## Ordered implementation

1. Protect data. Write regressions for stale editor revisions, independent tab recovery, retained import resolutions and partial-source preservation before fixes. Store base revision with displayed editor values and pending patches. Use separate recovery records per editor/job/version; acknowledge only the saved version. Retain legacy recovery until verified conversion. Add paginated authenticated history and exports. Use additive, idempotent SQLite migrations. Distinguish listing checks from retained description and requirement provenance.
2. Correct evidence. Version the 20/50/30 rubric as `documented-fit-v2`. Assess independent action/scope clauses, preserve exact source quotations, and cite specific CV evidence. Keep unknown source data, unsupported candidate evidence and incompatibility distinct. Preserve mandatory caps and score withholding. Normalize punctuation; parse alternative degrees; exclude company history, recruiter licences and application instructions. Add a fixed review corpus with meaningful claim and ranking comparisons.
3. Improve journeys. Normalize employment types and membership filters with backward-compatible query values. Use shared server presentation and filtering for search and export. Keep search, selection, scroll and focus on detail return. Draft from relevant supported responsibility–CV pairs with separate unresolved-requirement checklist. Preserve user edits. Align save/conflict/offline/recovery states and surface failures without losing text.
4. Verify and iterate. Run targeted regression checks, then the full suite. Exercise concurrent browser contexts, immediate close/reload, failed writes, server restart, history, source omissions, reversed search responses, salary units and selected exports. Complete discovery → evidence → preparation → listing → explicit Mark applied → follow-up → closure → history with mouse and keyboard. Inspect 390px, 768px, 1440px and 200% zoom; capture representative screenshots. Test loading, empty, unauthorized, timeout, partial refresh, conflict and clipboard failure. Fix critical/major failures and repeat affected checks.
5. Roll out. Capture current production SQLite using its consistent backup endpoint; migrate and restore an isolated copy and verify data preservation before deployment. Mutating QA uses isolated storage. Deploy the existing Render service through its documented native APIs/Git integration. Check authentication, retained records, filter/export parity, source health and scheduler recovery on deployment. Report external source outages separately.

## Verification records and deliverables

`ACCEPTANCE_REPORT.md` will distinguish checks actually run, results, evidence files and external limitations. `DECISIONS.md` records material choices and compatibility. Regression tests are committed; local browser screenshots and production backups remain under ignored `output/` and `migration/`. Do not interpret historical reports or existing test counts as current acceptance.

## Source references

- Project architecture and operation: `README.md`, `PRODUCT.md`, `render.yaml`.
- Design framework: local Impeccable `SKILL.md` and `reference/product.md`.
- FastAPI lifespan: https://fastapi.tiangolo.com/advanced/events/
- SQLite transactions and backup: https://docs.python.org/3/library/sqlite3.html
- Browser storage event: https://developer.mozilla.org/en-US/docs/Web/API/Window/storage_event
- Render disks: https://render.com/docs/disks
- Render deploy API: https://api-docs.render.com/reference/create-deploy
- Playwright browser contexts: https://playwright.dev/docs/browser-contexts

The MyCareersFuture refresh remains every 12 hours, four searches, at most ten results per search. Other sources stay labelled retained imports. A failed or partial upstream check cannot make older content fresh.
