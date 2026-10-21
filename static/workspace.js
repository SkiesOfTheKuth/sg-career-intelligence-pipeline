/* One private workspace. All employer and candidate text is rendered as text. */
(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const STAGES = ['Saved', 'Preparing', 'Applied', 'Interviewing', 'Offer', 'Closed'];
  const RECOVERY_KEY = 'sg_career_recovery_v1';
  const LEGACY_KEY = 'sg_career_shortlist_v2';
  const IMPORT_KEY = 'sg_career_shortlist_v2_imported';
  const mobile = window.matchMedia('(max-width: 1023px)');
  const state = {
    view: 'find', jobs: new Map(), results: [], total: 0, applications: new Map(),
    sessions: new Map(), selected: new Set(), activeId: null, detailEpoch: 0,
    searchEpoch: 0, searchAbort: null, searchTimer: null, returnFocus: null, returnScroll: 0,
    notices: new Map(), recovery: {}, drafts: new Map(), applicationsLoaded: false,
    applicationsError: null, applicationEpoch: 0, toastTimer: null,
  };

  function el(tag, className, text) {
    const element = document.createElement(tag);
    if (className) element.className = className;
    if (text !== undefined && text !== null) element.textContent = String(text);
    return element;
  }
  function button(text, action, className = '') {
    const node = el('button', className, text);
    node.type = 'button';
    node.addEventListener('click', action);
    return node;
  }
  function paragraph(text, className = '') { return el('p', className, text); }
  function date(value) {
    if (!value) return null;
    const parsed = new Date(String(value).length === 10 ? `${value}T12:00:00` : value);
    return Number.isNaN(parsed.getTime()) ? null : new Intl.DateTimeFormat('en-SG', { day: 'numeric', month: 'short', year: 'numeric' }).format(parsed);
  }
  function listValues(values) {
    if (typeof values === 'string') return values.trim() ? [values] : [];
    return Array.isArray(values) ? values.map(value => typeof value === 'string' ? value : value?.text || value?.evidence || '').filter(Boolean) : [];
  }
  function safeURL(value) {
    try { const url = new URL(value); return ['http:', 'https:'].includes(url.protocol) ? url.href : null; }
    catch { return null; }
  }
  function mergePatch(base = {}, patch = {}) {
    const result = { ...base, ...patch };
    if (base.drafts || patch.drafts) result.drafts = { ...base.drafts, ...patch.drafts };
    if (base.resolve_import_conflicts || patch.resolve_import_conflicts) result.resolve_import_conflicts = [...new Set([...(base.resolve_import_conflicts || []), ...(patch.resolve_import_conflicts || [])])];
    return result;
  }
  function hasKeys(value) { return Boolean(value && Object.keys(value).length); }
  function announce(message) { $('announcement').textContent = message; }
  function toast(message) {
    clearTimeout(state.toastTimer);
    $('toast').textContent = message;
    $('toast').hidden = false;
    state.toastTimer = setTimeout(() => { $('toast').hidden = true; }, 6500);
  }
  function notice(key, message, action, actionLabel, kind = 'error') {
    state.notices.set(key, { message, action, actionLabel, kind });
    renderNotices();
  }
  function clearNotice(key) { state.notices.delete(key); renderNotices(); }
  function renderNotices() {
    const fragment = document.createDocumentFragment();
    for (const item of state.notices.values()) {
      const node = el('div', `notice ${item.kind}`);
      node.append(paragraph(item.message));
      if (item.action) node.append(button(item.actionLabel || 'Retry', item.action));
      fragment.append(node);
    }
    for (const [id, session] of state.sessions) {
      if (!session.error && !session.conflict) continue;
      const job = getJob(id);
      const node = el('div', 'notice warning');
      node.append(paragraph(`${session.conflict ? 'Edits need review' : 'Couldn’t save edits'}: ${job.title || 'Saved role'}. Your text is retained in this browser.`));
      node.append(button('Review edits', () => openRole(id)));
      fragment.append(node);
    }
    $('global-notices').replaceChildren(fragment);
  }
  async function api(path, options = {}) {
    const response = await fetch(path, { credentials: 'same-origin', ...options, headers: { Accept: 'application/json', ...(options.body ? { 'Content-Type': 'application/json' } : {}), ...options.headers } });
    let data;
    try { data = await response.json(); } catch { data = null; }
    if (!response.ok) {
      const error = new Error(response.status === 401 ? 'Your session needs authentication. Reload this page to sign in.' : (typeof data?.detail === 'string' ? data.detail : data?.detail?.message || `The request failed (${response.status}). Please retry.`));
      error.status = response.status;
      error.data = data;
      throw error;
    }
    return data;
  }
  function loadingRows(container) {
    container.replaceChildren();
    for (let i = 0; i < 3; i += 1) {
      const row = el('div', 'loading-row'); row.setAttribute('aria-hidden', 'true');
      row.append(el('div', 'loading-line'), el('div', 'loading-line short'), el('div', 'loading-line long'));
      container.append(row);
    }
  }
  function empty(container, title, message, action, label) {
    const node = el('div', 'empty-state');
    node.append(el('h2', '', title), paragraph(message));
    if (action) node.append(button(label, action));
    container.replaceChildren(node);
  }
  const filterNames = ['q', 'category', 'fit', 'thai_relevance', 'employment_type', 'opportunity_type', 'min_salary', 'salary_only', 'sort_by'];
  function filters() {
    const values = new URLSearchParams();
    for (const name of filterNames) {
      const input = $('search-form').elements.namedItem(name);
      const value = input.type === 'checkbox' ? (input.checked ? 'true' : '') : input.value.trim();
      if (value) values.set(name, value);
    }
    return values;
  }
  function updateURL(replace = false) {
    const params = filters();
    if (state.view === 'applications') params.set('view', 'applications');
    if ($('stage-filter').value) params.set('stage', $('stage-filter').value);
    if (state.activeId) params.set('role', state.activeId);
    const target = `${location.pathname}?${params.toString()}`;
    if (target !== `${location.pathname}${location.search}`) history[replace ? 'replaceState' : 'pushState']({}, '', target);
  }
  function readURL() {
    const params = new URLSearchParams(location.search);
    for (const name of filterNames) {
      const input = $('search-form').elements.namedItem(name);
      const value = params.get(name) || (name === 'opportunity_type' ? 'salaried' : name === 'sort_by' ? 'recommended' : '');
      if (input.type === 'checkbox') input.checked = value === 'true';
      else {
        if (input.tagName === 'SELECT' && value && !Array.from(input.options).some(option => option.value === value)) input.append(new Option(value, value));
        input.value = value;
      }
    }
    $('stage-filter').value = STAGES.includes(params.get('stage')) ? params.get('stage') : '';
    state.view = params.get('view') === 'applications' ? 'applications' : 'find';
    return params.get('role');
  }
  function updateFilterCount() {
    const values = filters();
    const count = [...values].filter(([key, value]) => !['q', 'sort_by'].includes(key) && !(key === 'opportunity_type' && value === 'salaried')).length;
    $('filter-count').textContent = count ? `(${count})` : '';
  }
  function showView(view, push = true, focus = true) {
    closeRole(false, false);
    state.view = view;
    $('find-view').hidden = view !== 'find';
    $('applications-view').hidden = view !== 'applications';
    $('nav-find').removeAttribute('aria-current');
    $('nav-applications').removeAttribute('aria-current');
    $(`nav-${view === 'find' ? 'find' : 'applications'}`).setAttribute('aria-current', 'page');
    const label = view === 'find' ? 'Find roles' : 'Applications';
    $('workspace-heading').textContent = label;
    $('workspace-intro').textContent = view === 'find' ? 'Singapore opportunities for Dechsurang.' : 'Your next actions, notes and application history.';
    document.title = `${label} · SG Career Intelligence`;
    if (view === 'applications') renderApplications();
    if (push) updateURL();
    if (push) window.scrollTo({ top: 0, behavior: 'instant' });
    if (focus) $('workspace-heading').focus({ preventScroll: true });
  }
  function scheduleSearch(delay = 250, push = true) {
    clearTimeout(state.searchTimer);
    state.searchAbort?.abort();
    const epoch = ++state.searchEpoch; // Invalidate before debounce, not when the next request starts.
    state.results = [];
    state.total = 0;
    $('results-status').textContent = 'Loading roles…';
    $('job-list').setAttribute('aria-busy', 'true');
    $('load-more').hidden = true;
    $('export-search').disabled = true;
    loadingRows($('job-list'));
    updateFilterCount();
    state.searchTimer = setTimeout(() => {
      if (push) updateURL();
      loadJobs(epoch, false);
    }, delay);
  }
  async function loadJobs(epoch, append) {
    const controller = new AbortController();
    state.searchAbort = controller;
    const params = filters();
    params.set('limit', '25');
    params.set('offset', append ? String(state.results.length) : '0');
    $('load-more').disabled = true;
    try {
      const data = await api(`/api/jobs?${params}`, { signal: controller.signal });
      if (epoch !== state.searchEpoch) return;
      const items = data.items || [];
      for (const job of items) state.jobs.set(String(job.id), job);
      state.results = append ? [...state.results, ...items] : items;
      state.total = Number(data.total || 0);
      renderJobs();
      $('results-status').textContent = `${state.total.toLocaleString()} ${state.total === 1 ? 'role' : 'roles'}${state.results.length < state.total ? `, showing ${state.results.length}` : ''}`;
      $('load-more').hidden = state.results.length >= state.total;
      $('export-search').disabled = !state.total;
    } catch (error) {
      if (epoch !== state.searchEpoch || error.name === 'AbortError') return;
      $('results-status').textContent = 'Roles couldn’t be loaded';
      if (append) {
        toast(error.message);
        $('load-more').textContent = 'Retry loading more';
      } else empty($('job-list'), 'Couldn’t load roles', error.message, () => scheduleSearch(0, false), 'Retry');
    } finally {
      if (epoch === state.searchEpoch) { $('job-list').setAttribute('aria-busy', 'false'); $('load-more').disabled = false; }
    }
  }
  function getJob(id) { return state.jobs.get(String(id)) || state.applications.get(String(id))?.job || state.applications.get(String(id))?.job_snapshot || state.recovery[id]?.job_snapshot || { id, title: 'Unavailable listing', company: '' }; }
  function effectiveApplication(id) {
    const saved = state.applications.get(String(id));
    const session = state.sessions.get(String(id));
    if (!saved && !session) return null;
    return mergePatch(mergePatch(saved || { job_id: id, stage: 'Saved', revision: 0, notes: '' }, session?.inFlight), session?.pending);
  }
  function verificationText(job) {
    const verification = job.verification || {};
    const checked = date(verification.checked_at);
    const closed = ['closed', 'expired', 'unavailable'].includes(String(job.status || '').toLowerCase());
    if (closed) return `${job.status === 'expired' ? 'Deadline has passed' : 'Listing unavailable'}${verification.last_success_at ? `. Last verified ${date(verification.last_success_at)}` : ''}`;
    if (!checked) return 'Source verification unavailable';
    if (!verification.last_success_at) return `Source record dated ${checked}. No successful check recorded`;
    return `Last verified ${checked}${verification.needs_recheck || ['failed', 'degraded'].includes(verification.status) ? '. Needs recheck' : ''}`;
  }
  function roleMetadata(job) {
    const node = el('div', 'role-metadata');
    node.append(el('span', 'salary', job.salary?.display || 'Salary not disclosed'));
    if (job.employment_type) node.append(el('span', '', job.employment_type));
    if (job.location) node.append(el('span', '', job.location));
    return node;
  }
  function titleButton(job, className = 'role-title') {
    const node = button(job.title || 'Untitled role', () => openRole(String(job.id), node), className);
    node.dataset.roleId = String(job.id);
    node.setAttribute('aria-label', `View role: ${job.title || 'Untitled role'}`);
    return node;
  }
  function renderJobs() {
    if (!state.results.length) {
      empty($('job-list'), 'No roles match these filters', 'Try a different keyword or clear the filters to explore more opportunities.', clearFilters, 'Clear search and filters');
      return;
    }
    const fragment = document.createDocumentFragment();
    for (const job of state.results) {
      const id = String(job.id);
      const application = effectiveApplication(id);
      const row = el('article', `role-row${id === state.activeId ? ' is-selected' : ''}`);
      row.dataset.jobId = id;
      const heading = el('h2'); heading.append(titleButton(job));
      row.append(heading, paragraph(job.company || 'Company not stated', 'company'), roleMetadata(job));
      const assessment = job.assessment || {};
      const fit = assessment.fit || 'Check requirements';
      const reason = listValues(assessment.reasons)[0];
      const line = paragraph('', 'assessment-line');
      line.append(el('strong', fit === 'Relevant' ? 'fit-relevant' : fit === 'Check requirements' ? 'fit-check' : '', fit));
      if (reason) line.append(document.createTextNode(` — ${reason}`));
      row.append(line, paragraph(verificationText(job), 'verification-line'));
      if (window.FitScore) row.append(paragraph(window.FitScore.summary(job), 'score-line'));
      const actions = el('div', 'row-actions');
      actions.append(button('View role', event => openRole(id, event.currentTarget), 'text-button'));
      if (application) actions.append(el('span', 'row-stage', application.stage));
      else actions.append(button('Save', () => { queueWrite(id, { stage: 'Saved' }, true); renderJobs(); }, ''));
      row.append(actions);
      fragment.append(row);
    }
    $('job-list').replaceChildren(fragment);
    $('load-more').textContent = 'Load more roles';
  }
  function clearFilters() {
    $('search-form').reset();
    scheduleSearch(0);
    $('search-query').focus();
  }
  async function loadOptions() {
    try {
      const options = await api('/api/options');
      for (const [id, values] of [['category-filter', options.categories || options.category], ['employment-filter', options.employment_types || options.employment_type]]) {
        const input = $(id); const selected = input.value;
        for (const value of values || []) {
          const actual = typeof value === 'string' ? value : value.value || value.name;
          if (actual && !Array.from(input.options).some(option => option.value === actual)) input.append(new Option(typeof value === 'string' ? value : value.label || actual, actual));
        }
        input.value = selected;
      }
      clearNotice('options');
    } catch (error) { notice('options', `Filter choices couldn’t be loaded. ${error.message}`, loadOptions, 'Retry filters'); }
  }

  // Local recovery is written synchronously on each edit, before any network request.
  function readRecovery() {
    try {
      const raw = JSON.parse(localStorage.getItem(RECOVERY_KEY) || '{}');
      state.recovery = raw && typeof raw === 'object' && !Array.isArray(raw) ? raw : {};
    } catch { notice('storage', 'Browser recovery could not be read. New edits will still be sent to the server.'); }
  }
  function persistRecovery(id) {
    const session = state.sessions.get(id);
    const patch = mergePatch(session?.inFlight, session?.pending);
    if (hasKeys(patch)) state.recovery[id] = { job_id: id, expected_revision: session.revision, patch, job_snapshot: getJob(id), updated_at: new Date().toISOString() };
    else delete state.recovery[id];
    try { localStorage.setItem(RECOVERY_KEY, JSON.stringify(state.recovery)); clearNotice('storage'); }
    catch { notice('storage', 'Browser recovery could not be stored. Server saving is still available; unsaved text remains on this page.'); }
  }
  function sessionFor(id) {
    id = String(id);
    if (!state.sessions.has(id)) state.sessions.set(id, { revision: Number(state.applications.get(id)?.revision || 0), pending: {}, inFlight: {}, saving: false, error: null, conflict: null, timer: null });
    return state.sessions.get(id);
  }
  function queueWrite(id, patch, immediate = false) {
    id = String(id);
    const session = sessionFor(id);
    session.pending = mergePatch(session.pending, patch);
    persistRecovery(id);
    clearTimeout(session.timer);
    updateSaveFeedback(id);
    if (!session.conflict && !session.error) session.timer = setTimeout(() => flushWrite(id), immediate ? 0 : 300);
  }
  async function flushWrite(id) {
    const session = sessionFor(id);
    clearTimeout(session.timer);
    if (session.saving || session.conflict || !hasKeys(session.pending)) return;
    session.inFlight = session.pending;
    session.pending = {};
    session.saving = true;
    session.error = null;
    persistRecovery(id);
    updateSaveFeedback(id);
    try {
      const saved = await api(`/api/applications/${encodeURIComponent(id)}`, { method: 'PUT', body: JSON.stringify({ ...session.inFlight, expected_revision: session.revision }) });
      session.revision = Number(saved.revision);
      state.applications.set(id, saved);
      session.inFlight = {};
      session.error = null;
      session.saving = false;
      persistRecovery(id);
      renderNotices();
      updateImportNotice();
      updateSaveFeedback(id);
      updateDetailActions(id);
      if (state.view === 'applications') renderApplications();
      else refreshRowStage(id);
      if (hasKeys(session.pending)) flushWrite(id);
    } catch (error) {
      session.pending = mergePatch(session.inFlight, session.pending);
      session.inFlight = {};
      session.saving = false;
      session.error = error.message;
      if (error.status === 409) session.conflict = error.data?.detail?.current || error.data?.current || { revision: session.revision };
      persistRecovery(id);
      updateSaveFeedback(id);
      renderNotices();
      announce(session.conflict ? 'Another browser changed this application. Your edits are preserved for review.' : 'Couldn’t save. Your edits are retained for retry.');
    }
  }
  function refreshRowStage(id) {
    for (const row of $('job-list').querySelectorAll('[data-job-id]')) {
      if (row.dataset.jobId !== id) continue;
      const actions = row.querySelector('.row-actions');
      const old = actions.querySelector('.row-stage');
      const application = effectiveApplication(id);
      if (old) old.textContent = application?.stage || '';
      else if (application) {
        const save = Array.from(actions.querySelectorAll('button')).find(node => node.textContent === 'Save');
        save?.remove(); actions.append(el('span', 'row-stage', application.stage));
      }
    }
  }
  function updateSaveFeedback(id) {
    if (state.activeId !== id) return;
    const container = $('save-feedback');
    if (!container) return;
    const session = state.sessions.get(id);
    const application = effectiveApplication(id);
    const status = el('p', 'save-status');
    status.setAttribute('role', 'status'); status.setAttribute('aria-live', 'polite');
    if (session?.conflict) { status.textContent = 'Changes need review. Your edits are preserved.'; status.classList.add('is-error'); }
    else if (session?.error) { status.textContent = 'Couldn’t save. Your edits are retained for retry.'; status.classList.add('is-error'); }
    else if (session?.saving || hasKeys(session?.pending)) status.textContent = 'Saving…';
    else if (application?.revision) { status.textContent = 'Saved'; status.classList.add('is-saved'); }
    else status.textContent = 'Writing a note also saves this role.';
    container.replaceChildren(status);
    const draftStatus = $('draft-save-status');
    if (draftStatus) { draftStatus.textContent = status.textContent; draftStatus.className = status.className; }
    if (session?.conflict) {
      const conflict = el('div', 'notice warning');
      conflict.append(paragraph('This application changed in another browser. Compare the current server copy with your edits before saving.'));
      const details = el('details'); details.append(el('summary', '', 'Compare versions'));
      details.append(el('h3', '', 'Current server copy'), el('pre', 'conflict-copy', printableApplication(session.conflict)));
      details.append(el('h3', '', 'Your edits'), el('pre', 'conflict-copy', printableApplication(effectiveApplication(id))));
      conflict.append(details);
      const actions = el('div', 'notice-actions');
      actions.append(button('Save my edits over this version', () => resolveConflict(id, true)), button('Keep server version', () => resolveConflict(id, false)));
      conflict.append(actions); container.append(conflict);
    } else if (session?.error) {
      container.append(paragraph(session.error, 'field-help'), button('Retry save', () => { session.error = null; flushWrite(id); }, 'text-button'));
    }
  }
  function printableApplication(application) {
    return [`Stage: ${application?.stage || 'Saved'}`, `Next action: ${application?.next_action || ''}`, `Follow-up: ${application?.follow_up_date || ''}`, `Outcome: ${application?.outcome || ''}`, `Notes:\n${application?.notes || ''}`, `Recruiter message:\n${application?.drafts?.recruiter_message || ''}`, `Cover letter:\n${application?.drafts?.cover_letter || ''}`].join('\n\n');
  }
  function resolveConflict(id, keepEdits) {
    const session = sessionFor(id);
    const current = session.conflict;
    if (!current || !Number.isFinite(Number(current.revision))) { toast('The server version is unavailable. Refresh applications and retry.'); return; }
    state.applications.set(id, current);
    session.revision = Number(current.revision);
    session.conflict = null;
    session.error = null;
    if (!keepEdits) { session.pending = {}; session.inFlight = {}; }
    persistRecovery(id);
    renderNotices();
    renderDetail(getJob(id), false);
    if (keepEdits) flushWrite(id);
    else { renderApplications(); refreshRowStage(id); }
  }
  async function loadApplications() {
    const epoch = ++state.applicationEpoch;
    $('application-list').setAttribute('aria-busy', 'true');
    $('refresh-applications').disabled = true;
    try {
      const data = await api('/api/applications');
      if (epoch !== state.applicationEpoch) return;
      const refreshed = new Map((data.items || []).map(item => [String(item.job_id), item]));
      for (const [id, current] of state.applications) {
        if (Number(current.revision) > Number(refreshed.get(id)?.revision || 0)) refreshed.set(id, current);
      }
      state.applications = refreshed;
      state.applicationsLoaded = true;
      state.applicationsError = null;
      for (const [id, session] of state.sessions) {
        if (!session.saving && !hasKeys(session.pending) && !session.conflict) session.revision = Number(state.applications.get(id)?.revision || 0);
      }
      restoreRecovery();
      renderApplications();
      refreshAllRowStages();
      updateImportNotice();
      clearNotice('applications');
    } catch (error) {
      state.applicationsError = error.message;
      renderApplications();
      notice('applications', `Applications couldn’t be loaded. ${error.message}`, loadApplications, 'Retry applications');
    } finally { $('application-list').setAttribute('aria-busy', 'false'); $('refresh-applications').disabled = false; }
  }
  function restoreRecovery() {
    for (const [id, recovered] of Object.entries(state.recovery)) {
      if (state.sessions.has(id) || !hasKeys(recovered.patch)) continue;
      const session = sessionFor(id);
      session.pending = recovered.patch;
      session.revision = Number(recovered.expected_revision || 0);
      const current = state.applications.get(id);
      if (Number(current?.revision || 0) !== session.revision) {
        // A lost acknowledgement may have saved these exact edits; avoid a false conflict.
        const alreadySaved = Object.entries(session.pending).every(([key, value]) => key === 'drafts' ? Object.entries(value).every(([name, text]) => current?.drafts?.[name] === text) : current?.[key] === value);
        if (alreadySaved) { session.pending = {}; session.revision = Number(current.revision); persistRecovery(id); }
        else { session.conflict = current || { job_id: id, revision: 0 }; session.error = 'Recovered edits differ from the server copy.'; }
      } else flushWrite(id);
    }
    renderNotices();
  }
  function refreshAllRowStages() { for (const job of state.results) refreshRowStage(String(job.id)); }
  function filteredApplications() {
    const ids = new Set([...state.applications.keys(), ...state.sessions.keys()]);
    const stage = $('stage-filter').value;
    return [...ids].map(id => effectiveApplication(id)).filter(item => item && (!stage || item.stage === stage)).sort((a, b) => {
      const dateA = a.follow_up_date || '9999', dateB = b.follow_up_date || '9999';
      return dateA.localeCompare(dateB) || String(b.updated_at || '').localeCompare(String(a.updated_at || ''));
    });
  }
  function renderApplications() {
    const items = filteredApplications();
    const visible = new Set(items.map(item => String(item.job_id)));
    state.selected = new Set([...state.selected].filter(id => visible.has(id)));
    $('applications-status').textContent = `${items.length} ${items.length === 1 ? 'application' : 'applications'}`;
    updateApplicationExport();
    if (!state.applicationsLoaded && !state.applicationsError) { loadingRows($('application-list')); $('applications-status').textContent = 'Loading applications…'; return; }
    if (state.applicationsError && !items.length) { empty($('application-list'), 'Couldn’t load applications', state.applicationsError, loadApplications, 'Retry'); return; }
    if (!items.length) {
      empty($('application-list'), $('stage-filter').value ? `No ${$('stage-filter').value.toLowerCase()} applications` : 'Your applications start here', $('stage-filter').value ? 'Choose another stage to see your tracked roles.' : 'Save a role or write a note while browsing. Your notes and next actions will be kept here.', () => { if ($('stage-filter').value) { $('stage-filter').value = ''; updateURL(); renderApplications(); } else showView('find'); }, $('stage-filter').value ? 'Show all stages' : 'Find roles');
      return;
    }
    const fragment = document.createDocumentFragment();
    for (const application of items) {
      const id = String(application.job_id);
      const job = getJob(id);
      const row = el('article', `role-row${state.activeId === id ? ' is-selected' : ''}`);
      const head = el('div', 'application-head');
      const selectLabel = el('label', 'application-select');
      const checkbox = document.createElement('input'); checkbox.type = 'checkbox'; checkbox.checked = state.selected.has(id);
      checkbox.setAttribute('aria-label', `Select ${job.title || 'application'} for export`);
      checkbox.addEventListener('change', () => { if (checkbox.checked) state.selected.add(id); else state.selected.delete(id); updateApplicationExport(); });
      selectLabel.append(checkbox);
      const title = el('div', 'application-title'); const heading = el('h2'); heading.append(titleButton({ ...job, id }));
      title.append(heading, paragraph(job.company || 'Company not stated', 'company'));
      head.append(selectLabel, title); row.append(head);
      const fields = el('div', 'application-fields');
      fields.append(el('strong', '', application.stage), el('span', '', `Next: ${application.next_action || 'No next action set'}`));
      if (application.follow_up_date) fields.append(el('span', '', `Follow up ${date(application.follow_up_date) || application.follow_up_date}`));
      if (application.stage === 'Closed' && application.outcome) fields.append(el('span', '', `Outcome: ${application.outcome}`));
      row.append(fields);
      if (application.notes) row.append(paragraph(application.notes, 'application-note'));
      if (['closed', 'expired', 'unavailable'].includes(String(job.status).toLowerCase())) row.append(paragraph('Listing unavailable. Your application history is retained.', 'verification-line'));
      row.append(button('View role', event => openRole(id, event.currentTarget), 'text-button'));
      fragment.append(row);
    }
    $('application-list').replaceChildren(fragment);
  }
  function updateApplicationExport() {
    const count = state.selected.size;
    $('export-applications').textContent = count ? `Export selected (${count})` : 'Export shown applications';
    $('export-applications').disabled = !filteredApplications().length;
  }
  function updateImportNotice() {
    const count = [...state.applications.values()].reduce((sum, application) => sum + (application.import_conflicts?.length || 0), 0);
    if (count) notice('import', `${count} previous shortlist ${count === 1 ? 'entry needs' : 'entries need'} review. Both versions are retained. Open the application to compare notes and stages.`, () => showView('applications'), 'Review applications', 'warning');
    else clearNotice('import');
  }
  async function importLegacy() {
    let raw, records;
    try {
      raw = localStorage.getItem(LEGACY_KEY);
      if (!raw || localStorage.getItem(IMPORT_KEY) === raw) return;
      records = JSON.parse(raw);
      if (!records || typeof records !== 'object' || !Object.keys(records).length) return;
    } catch { notice('import', 'Your previous browser shortlist could not be read. It has been retained for recovery.'); return; }
    try {
      const result = await api('/api/applications/import', { method: 'POST', body: JSON.stringify({ records }) });
      const conflicts = Array.isArray(result.conflicts) ? result.conflicts : [];
      if (result.errors?.length) {
        notice('import-errors', `${result.errors.length} previous shortlist entries could not be imported. The complete original shortlist is retained in this browser.`, () => {
          const blob = new Blob([raw], { type: 'application/json' });
          const url = URL.createObjectURL(blob); const link = el('a'); link.href = url; link.download = 'previous-shortlist-recovery.json'; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
        }, 'Download recovery copy', 'warning');
      }
      if (conflicts.length) {
        notice('import', `${conflicts.length} previous shortlist ${conflicts.length === 1 ? 'entry has' : 'entries have'} conflicting notes or stages. Both versions are retained. Open Applications to review their history.`, () => showView('applications'), 'Review applications', 'warning');
      } else {
        if (!result.errors?.length) try { localStorage.setItem(IMPORT_KEY, raw); } catch { /* The import endpoint is idempotent; retrying is safe. */ }
        clearNotice('import');
        if (result.imported) toast('Your previous shortlist is now saved in Applications.');
      }
    } catch (error) { notice('import', `Your previous shortlist is retained in this browser. Import couldn’t finish. ${error.message}`, async () => { await importLegacy(); await loadApplications(); }, 'Retry import'); }
  }

  function detailMode() {
    const isOpen = Boolean(state.activeId);
    const modal = isOpen && mobile.matches;
    $('main-content').inert = modal;
    $('site-header').inert = modal;
    document.body.classList.toggle('detail-mobile-open', modal);
    $('role-detail').setAttribute('role', modal ? 'dialog' : 'region');
    if (modal) $('role-detail').setAttribute('aria-modal', 'true');
    else $('role-detail').removeAttribute('aria-modal');
  }
  function closeRole(update = true, focus = true) {
    const previous = state.activeId;
    if (!previous) return;
    state.activeId = null;
    state.detailEpoch += 1;
    $('role-detail').hidden = true;
    $('workspace').classList.remove('has-detail');
    detailMode();
    if (update) updateURL(true);
    for (const row of document.querySelectorAll('.role-row.is-selected')) row.classList.remove('is-selected');
    if (focus) {
      window.scrollTo({ top: state.returnScroll, behavior: 'instant' });
      const fallback = [...document.querySelectorAll('[data-role-id]')].find(node => node.dataset.roleId === previous && !node.closest('[hidden]'));
      (state.returnFocus?.isConnected ? state.returnFocus : fallback || $('workspace-heading')).focus({ preventScroll: true });
    }
  }
  async function openRole(id, source, push = true) {
    id = String(id);
    if (!state.activeId) state.returnScroll = window.scrollY;
    state.returnFocus = source || document.activeElement;
    state.activeId = id;
    const epoch = ++state.detailEpoch;
    $('role-detail').hidden = false;
    $('workspace').classList.add('has-detail');
    detailMode();
    if (push) updateURL();
    const cached = getJob(id);
    renderDetail(cached, true);
    $('role-detail').scrollTop = 0;
    try {
      const result = await api(`/api/jobs/${encodeURIComponent(id)}`);
      if (epoch !== state.detailEpoch || state.activeId !== id) return;
      const job = result.job || result;
      state.jobs.set(id, { ...job, id });
      // Do not replace an editor once the user has started typing into it.
      const focused = document.activeElement;
      if (!$('role-detail').contains(focused) || !['INPUT', 'TEXTAREA', 'SELECT'].includes(focused.tagName)) renderDetail({ ...job, id }, false);
      else updateDetailEvidence(job);
    } catch (error) {
      if (epoch !== state.detailEpoch || state.activeId !== id) return;
      const noticeNode = el('div', 'notice warning');
      if (error.status === 404 && effectiveApplication(id)) {
        noticeNode.append(paragraph('This listing is no longer available. The saved role snapshot and your application history are shown below.'));
      } else {
        noticeNode.append(paragraph(`The latest listing couldn’t be loaded. ${error.message}`));
        noticeNode.append(button('Retry listing', () => openRole(id, state.returnFocus, false)));
      }
      $('detail-source-notice')?.replaceChildren(noticeNode);
    }
  }
  function detailSection(title) {
    const section = el('section', 'detail-section');
    section.append(el('h3', '', title));
    return section;
  }
  function appendList(container, values, unknown) {
    const items = listValues(values);
    if (!items.length) { if (unknown) container.append(paragraph(unknown, 'field-help')); return; }
    const list = el('ul');
    items.forEach(item => list.append(el('li', '', item)));
    container.append(list);
  }
  function inputField(labelText, name, value, id, type = 'text') {
    const label = el('label'); label.append(document.createTextNode(labelText));
    const input = document.createElement(type === 'textarea' ? 'textarea' : 'input');
    if (type !== 'textarea') input.type = type;
    input.name = name;
    input.id = `application-${name}`;
    input.value = value || '';
    input.addEventListener('input', () => queueWrite(id, { [name]: input.value }));
    label.append(input);
    return label;
  }
  function renderDetail(job, focus) {
    const id = String(job.id || state.activeId);
    const application = effectiveApplication(id);
    const pane = $('role-detail');
    const previousScroll = pane.scrollTop;
    const previousFocusId = pane.contains(document.activeElement) ? document.activeElement.id : null;
    const fragment = document.createDocumentFragment();
    const closeRow = el('div', 'detail-close-row');
    closeRow.append(button('← Back to roles', () => closeRole(), 'text-button'));
    closeRow.firstChild.textContent = state.view === 'applications' ? '← Back to applications' : '← Back to roles';
    if (application) closeRow.append(el('span', 'row-stage', application.stage));
    fragment.append(closeRow);
    const header = el('header', 'detail-header');
    const title = el('h2', '', job.title || 'Unavailable listing'); title.id = 'detail-title'; title.tabIndex = -1;
    header.append(title, paragraph(job.company || 'Company not stated', 'company'), roleMetadata(job));
    const facts = el('dl', 'detail-facts');
    for (const [label, value] of [['Work arrangement', job.work_arrangement], ['Thai relevance', job.thai_relevance], ['Deadline', date(job.deadline)]]) {
      if (value && value !== 'None' && value !== 'Unknown') facts.append(el('dt', '', label), el('dd', '', value));
    }
    if (facts.children.length) header.append(facts);
    header.append(paragraph(verificationText(job), 'verification-line'));
    const actions = el('div', 'detail-actions'); actions.id = 'detail-actions'; header.append(actions);
    const jumps = el('div', 'row-actions');
    jumps.append(button('Requirements', () => { $('employer-requirements')?.scrollIntoView({ block: 'start' }); $('employer-requirements')?.focus({ preventScroll: true }); }, 'text-button'));
    jumps.append(button('Fit score & evidence', () => { $('fit-score-detail')?.scrollIntoView({block: 'start'}); $('fit-score-detail')?.focus({preventScroll: true}); }, 'text-button'));
    jumps.append(button('Your notes', () => { $('application-notes')?.focus(); }, 'text-button'));
    header.append(jumps);
    fragment.append(header);
    const sourceNotice = el('div'); sourceNotice.id = 'detail-source-notice';
    if (['closed', 'expired', 'unavailable'].includes(String(job.status).toLowerCase())) sourceNotice.append(paragraph('This vacancy is closed or past its deadline. Application notes and history remain available.', 'notice warning'));
    else if (job.verification?.last_error) sourceNotice.append(paragraph('The most recent source check failed. Earlier source evidence is shown; availability needs rechecking.', 'notice warning'));
    fragment.append(sourceNotice);
    const evidence = el('div'); evidence.id = 'detail-evidence'; fragment.append(evidence);
    const tracking = detailSection('Your application');
    const form = el('div', 'detail-form');
    const stageLabel = el('label'); stageLabel.append(document.createTextNode('Stage'));
    const stage = document.createElement('select'); stage.id = 'application-stage';
    for (const value of STAGES) stage.append(new Option(value, value));
    stage.value = application?.stage || 'Saved';
    stage.addEventListener('change', () => {
      queueWrite(id, { stage: stage.value }, true);
      const outcome = $('application-outcome')?.closest('label');
      if (outcome) outcome.hidden = stage.value !== 'Closed';
      updateDetailActions(id);
      renderPreparation(id);
    });
    stageLabel.append(stage); form.append(stageLabel);
    form.append(inputField('Follow-up date', 'follow_up_date', application?.follow_up_date, id, 'date'));
    const next = inputField('Next action', 'next_action', application?.next_action, id); next.classList.add('full-width'); form.append(next);
    const notes = inputField('Notes', 'notes', application?.notes, id, 'textarea'); notes.classList.add('full-width'); form.append(notes);
    const outcome = inputField('Outcome', 'outcome', application?.outcome, id); outcome.classList.add('full-width'); outcome.hidden = application?.stage !== 'Closed'; form.append(outcome);
    tracking.append(form);
    if (application?.import_conflicts?.length) {
      for (const conflict of application.import_conflicts) {
        const incoming = conflict.incoming?.application || conflict.incoming || {};
        const review = el('div', 'notice warning');
        review.append(paragraph('A previous browser shortlist contains different notes or a different stage. The original entry is retained for review.'));
        const versions = el('details'); versions.append(el('summary', '', 'Review previous shortlist entry'), el('pre', 'conflict-copy', printableApplication(incoming)));
        review.append(versions);
        const controls = el('div', 'notice-actions');
        controls.append(button('Merge previous notes', () => {
          const current = effectiveApplication(id);
          const merged = [current.notes, incoming.notes ? `Previous browser notes:\n${incoming.notes}` : ''].filter(Boolean).join('\n\n');
          queueWrite(id, { notes: merged, resolve_import_conflicts: [conflict.id] }, true);
          $('application-notes').value = merged;
          review.replaceChildren(paragraph('Previous notes merged. The current stage is unchanged. Saving…'));
        }));
        controls.append(button('Use previous notes and stage', () => {
          const patch = { notes: incoming.notes || '', resolve_import_conflicts: [conflict.id] };
          if (STAGES.includes(incoming.stage)) patch.stage = incoming.stage;
          queueWrite(id, patch, true);
          $('application-notes').value = patch.notes;
          if (patch.stage) $('application-stage').value = patch.stage;
          updateDetailActions(id); renderPreparation(id);
          review.replaceChildren(paragraph('Previous notes and stage selected. Saving…'));
        }));
        controls.append(button('Keep current version', () => {
          queueWrite(id, { resolve_import_conflicts: [conflict.id] }, true);
          review.replaceChildren(paragraph('Current version kept. The original import remains in history. Saving…'));
        }));
        review.append(controls); tracking.append(review);
      }
    }
    const feedback = el('div', 'save-feedback'); feedback.id = 'save-feedback'; tracking.append(feedback);
    fragment.append(tracking);
    const preparation = el('div'); preparation.id = 'preparation'; fragment.append(preparation);
    if (application?.history?.length) {
      const section = el('details', 'detail-section'); section.append(el('summary', '', 'Application history'));
      const list = el('ul', 'history-list');
      for (const event of [...application.history].reverse()) {
        const text = typeof event === 'string' ? event : `${date(event.at || event.created_at || event.timestamp) || ''}${event.stage ? ` — ${event.stage}` : ''}${event.action || event.type ? ` — ${event.action || event.type.replaceAll('_', ' ')}` : ''}${event.changed_fields?.length ? `: ${event.changed_fields.map(field => field.replaceAll('_', ' ')).join(', ')}` : ''}${event.note ? `: ${event.note}` : ''}`;
        const item = el('li', '', text || 'Application updated');
        if (event && typeof event === 'object' && (event.conflict || event.imported || event.incoming || event.legacy)) {
          const details = el('details'); details.append(el('summary', '', 'Retained import details'), el('pre', 'conflict-copy', JSON.stringify(event.conflict || event.imported || event.incoming || event.legacy, null, 2))); item.append(details);
        }
        list.append(item);
      }
      section.append(list); fragment.append(section);
    }
    pane.replaceChildren(fragment);
    updateDetailEvidence(job);
    updateDetailActions(id);
    updateSaveFeedback(id);
    renderPreparation(id);
    pane.scrollTop = previousScroll;
    if (focus) title.focus({ preventScroll: true });
    else if (previousFocusId) $(previousFocusId)?.focus({ preventScroll: true });
  }
  function updateDetailEvidence(job) {
    const container = $('detail-evidence');
    if (!container) return;
    const responsibilities = detailSection('Role description');
    responsibilities.append(paragraph(job.description || 'The source does not provide a complete role description.', 'source-description'));
    const requirements = detailSection('Employer requirements');
    requirements.id = 'employer-requirements'; requirements.tabIndex = -1;
    if (listValues(job.requirements?.mandatory).length) { requirements.append(el('h3', '', 'Mandatory')); appendList(requirements, job.requirements.mandatory); }
    else requirements.append(paragraph('Mandatory requirements are not available in the retained source.', 'field-help'));
    if (listValues(job.requirements?.preferred).length) { requirements.append(el('h3', '', 'Preferred')); appendList(requirements, job.requirements.preferred); }
    const consider = detailSection('Why consider this');
    consider.append(paragraph(job.assessment?.fit || 'Check requirements'));
    if (window.FitScore) {const score = window.FitScore.detail(job); score.id = 'fit-score-detail'; score.tabIndex = -1; consider.append(score);}
    if (!window.FitScore) appendList(consider, job.assessment?.reasons, 'There is not enough source evidence to establish a fit.');
    const gaps = detailSection('Requirements to check');
    appendList(gaps, job.assessment?.gaps, 'No further requirements are documented in the assessment. Review the original listing before applying.');
    const source = detailSection('Source evidence');
    source.append(paragraph(verificationText(job), 'field-help'));
    const auditLink = el('a', 'button-link', 'Inspect retained source evidence'); auditLink.href = `/sources?job=${encodeURIComponent(job.id)}`; source.append(auditLink);
    const sources = Array.isArray(job.sources) && job.sources.length ? job.sources : [{ name: 'Original listing', url: job.url }];
    for (const item of sources) {
      const url = safeURL(item.url);
      if (!url) continue;
      const link = el('a', 'button-link', item.name || 'Original listing'); link.href = url; link.target = '_blank'; link.rel = 'noopener noreferrer';
      link.setAttribute('aria-label', `${item.name || 'Original listing'} (opens in a new tab)`);
      const row = paragraph(''); row.append(link);
      if (item.checked_at) row.append(document.createTextNode(` Recorded ${date(item.checked_at) || 'date unavailable'}`));
      source.append(row);
    }
    container.replaceChildren(responsibilities, requirements, consider, gaps, source);
  }
  function updateDetailActions(id) {
    if (state.activeId !== id || !$('detail-actions')) return;
    const application = effectiveApplication(id);
    const actions = $('detail-actions'); actions.replaceChildren();
    if (!application) actions.append(button('Save', () => { queueWrite(id, { stage: 'Saved' }, true); updateDetailActions(id); refreshRowStage(id); }));
    if (!application || application.stage === 'Saved') actions.append(button('Prepare application', () => {
      queueWrite(id, { stage: 'Preparing' }, true);
      $('application-stage').value = 'Preparing';
      updateDetailActions(id); renderPreparation(id);
      $('preparation').scrollIntoView({ block: 'start', behavior: 'auto' });
    }, 'primary'));
    if (application && ['Saved', 'Preparing'].includes(application.stage)) actions.append(button('Mark applied', () => {
      queueWrite(id, { stage: 'Applied' }, true);
      $('application-stage').value = 'Applied'; updateDetailActions(id); renderPreparation(id);
      toast('Application marked applied.');
    }));
    const url = safeURL(getJob(id).url);
    if (url) {
      const link = el('a', 'button-link', 'View original listing'); link.href = url; link.target = '_blank'; link.rel = 'noopener noreferrer'; link.setAttribute('aria-label', 'View original listing (opens in a new tab)'); actions.append(link);
    }
    const stageText = $('role-detail').querySelector('.detail-close-row .row-stage');
    if (stageText && application) stageText.textContent = application.stage;
  }
  function renderPreparation(id) {
    if (state.activeId !== id || !$('preparation')) return;
    const application = effectiveApplication(id);
    const container = $('preparation'); container.replaceChildren();
    if (!application || !['Preparing', 'Applied', 'Interviewing', 'Offer'].includes(application.stage)) return;
    const section = el('details', 'detail-section'); section.open = application.stage === 'Preparing';
    section.append(el('summary', '', 'Application preparation'));
    section.append(paragraph('Review and edit these drafts before using them. They use documented candidate facts and the available role evidence.', 'field-help'));
    const draftStatus = paragraph('', 'save-status'); draftStatus.id = 'draft-save-status'; draftStatus.setAttribute('role', 'status'); section.append(draftStatus);
    const drafts = application.drafts || {};
    for (const [name, title] of [['recruiter_message', 'Recruiter message'], ['cover_letter', 'Cover letter']]) {
      const field = el('div', `draft-field ${name === 'cover_letter' ? 'cover-letter' : ''}`);
      const label = el('label'); label.append(document.createTextNode(title));
      const input = document.createElement('textarea'); input.id = `draft-${name}`; input.value = drafts[name] || ''; input.setAttribute('aria-describedby', 'draft-save-hint');
      input.addEventListener('input', () => queueWrite(id, { drafts: { [name]: input.value } })); label.append(input);
      field.append(label, button(`Copy ${title.toLowerCase()}`, async () => {
        try { await navigator.clipboard.writeText(input.value); toast(`${title} copied.`); }
        catch { input.focus(); input.select(); toast('Clipboard access failed. The draft is selected so you can copy it.'); }
      }, 'text-button'));
      section.append(field);
    }
    const hint = paragraph('Edits save automatically with your application.', 'field-help'); hint.id = 'draft-save-hint'; section.append(hint);
    container.append(section);
    updateSaveFeedback(id);
    const generated = state.drafts.get(id);
    if (generated?.error) {
      const retry = el('div', 'notice warning');
      retry.append(paragraph(`Draft suggestions couldn’t be loaded. Your edits are retained. ${generated.error}`), button('Retry draft suggestions', () => { retry.remove(); loadDrafts(id); }));
      container.append(retry);
    }
    if (application.stage === 'Interviewing' && generated?.interview_prep) {
      const interview = detailSection('Interview preparation'); appendList(interview, generated.interview_prep); container.append(interview);
    }
    if (!state.drafts.has(id)) loadDrafts(id);
  }
  async function loadDrafts(id) {
    state.drafts.set(id, { loading: true });
    try {
      const data = await api(`/api/drafts/${encodeURIComponent(id)}`);
      state.drafts.set(id, data);
      const current = effectiveApplication(id)?.drafts || {};
      const patch = {};
      for (const name of ['recruiter_message', 'cover_letter']) {
        if (!Object.prototype.hasOwnProperty.call(current, name) && typeof data[name] === 'string') patch[name] = data[name];
      }
      if (hasKeys(patch)) queueWrite(id, { drafts: patch });
      // Do not replace draft inputs the user is currently editing.
      if (state.activeId === id) {
        for (const [name, value] of Object.entries(patch)) { const input = $(`draft-${name}`); if (input && document.activeElement !== input) input.value = value; }
        if (effectiveApplication(id)?.stage === 'Interviewing' && !$('preparation').querySelector('.interview-preparation')) {
          const interview = detailSection('Interview preparation'); interview.classList.add('interview-preparation'); appendList(interview, data.interview_prep); $('preparation').append(interview);
        }
      }
    } catch (error) {
      state.drafts.set(id, { error: error.message });
      if (state.activeId === id) {
        const retry = el('div', 'notice warning'); retry.append(paragraph(`Draft suggestions couldn’t be loaded. Your edits are retained. ${error.message}`), button('Retry draft suggestions', () => { retry.remove(); loadDrafts(id); })); $('preparation').append(retry);
      }
    }
  }
  async function download(path, filename, source) {
    source.disabled = true;
    try {
      const response = await fetch(path, { credentials: 'same-origin' });
      if (!response.ok) throw new Error(`Export failed (${response.status}). Please retry.`);
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const link = el('a'); link.href = url; link.download = filename; document.body.append(link); link.click(); link.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      toast('Export downloaded.');
    } catch (error) { toast(error.message || 'Export couldn’t be downloaded. Please retry.'); }
    finally { source.disabled = false; }
  }

  $('nav-find').addEventListener('click', event => { event.preventDefault(); showView('find'); });
  $('nav-applications').addEventListener('click', event => { event.preventDefault(); showView('applications'); });
  $('search-form').addEventListener('submit', event => { event.preventDefault(); scheduleSearch(0); });
  $('search-query').addEventListener('input', () => scheduleSearch());
  for (const name of filterNames.filter(value => value !== 'q')) $('search-form').elements.namedItem(name).addEventListener('change', () => scheduleSearch(0));
  $('clear-filters').addEventListener('click', clearFilters);
  $('load-more').addEventListener('click', () => loadJobs(state.searchEpoch, true));
  $('stage-filter').addEventListener('change', () => { state.selected.clear(); updateURL(); renderApplications(); });
  $('refresh-applications').addEventListener('click', loadApplications);
  $('export-search').addEventListener('click', event => download(`/api/export/filtered?${filters()}`, 'singapore-roles.csv', event.currentTarget));
  $('export-applications').addEventListener('click', async event => {
    const ids = state.selected.size ? [...state.selected] : filteredApplications().map(item => String(item.job_id));
    if (!ids.length) return;
    const source = event.currentTarget;
    await Promise.all(ids.map(id => flushWrite(id)));
    if (ids.some(id => { const session = state.sessions.get(id); return session?.saving || session?.error || session?.conflict || hasKeys(session?.pending); })) {
      toast('Some application edits have not saved yet. Finish or retry saving before exporting.');
      return;
    }
    const params = new URLSearchParams({ ids: ids.join(',') });
    if ($('stage-filter').value) params.set('stage', $('stage-filter').value);
    download(`/api/export/applications?${params}`, 'applications.csv', source);
  });
  mobile.addEventListener('change', () => { detailMode(); if (state.activeId && mobile.matches) $('detail-title')?.focus({ preventScroll: true }); });
  document.addEventListener('keydown', event => {
    if (!state.activeId) return;
    if (event.key === 'Escape') { event.preventDefault(); closeRole(); }
    if (event.key === 'Tab' && mobile.matches) {
      const focusable = [...$('role-detail').querySelectorAll('button:not(:disabled), a[href], input:not(:disabled), textarea:not(:disabled), select:not(:disabled), summary')].filter(node => node.getClientRects().length);
      const first = focusable[0], last = focusable.at(-1);
      if (event.shiftKey && (document.activeElement === first || document.activeElement === $('detail-title'))) { event.preventDefault(); last?.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
    }
  });
  window.addEventListener('popstate', () => {
    const id = readURL(); const view = state.view;
    showView(view, false, false); scheduleSearch(0, false);
    if (id) openRole(id, null, false);
  });
  window.addEventListener('online', () => {
    for (const [id, session] of state.sessions) if (session.error && !session.conflict) { session.error = null; flushWrite(id); }
  });
  // beforeunload is only needed when browser recovery itself failed.
  window.addEventListener('beforeunload', event => {
    if (state.notices.has('storage') && [...state.sessions.values()].some(session => session.saving || hasKeys(session.pending))) { event.preventDefault(); event.returnValue = ''; }
  });
  async function start() {
    readRecovery();
    const role = readURL();
    showView(state.view, false, false);
    scheduleSearch(0, false);
    loadOptions();
    await importLegacy();
    await loadApplications();
    if (role) openRole(role, null, false);
  }
  start();
})();
