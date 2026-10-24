/* One private workspace. All employer and candidate text is rendered as text. */
(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const STAGES = ['Saved', 'Preparing', 'Applied', 'Interviewing', 'Offer', 'Closed'];
  const RECOVERY_KEY = 'sg_career_recovery_v1';
  const RECOVERY_PREFIX = 'sg_career_recovery_v2:';
  const editorId = crypto.randomUUID();
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
      node.append(paragraph(`${session.conflict ? 'Edits need review' : 'Couldn’t save edits'}: ${job.title || 'Saved role'}. ${recoveryMessage(session)}`));
      node.append(button('Review edits', () => openRole(id)));
      fragment.append(node);
    }
    const recoveredJobs = new Set(Object.values(state.recovery).filter(record => record.editor_id !== editorId).map(record => String(record.job_id)));
    if (recoveredJobs.size > 1) {
      const choices = el('details', 'notice warning'); choices.append(el('summary', '', 'Choose a role to recover'));
      for (const id of recoveredJobs) choices.append(button(getJob(id).title || id, () => openRole(id)));
      fragment.append(choices);
    }
    $('global-notices').replaceChildren(fragment);
  }
  async function api(path, options = {}) {
    const signal = options.signal ? AbortSignal.any([options.signal, AbortSignal.timeout(20000)]) : AbortSignal.timeout(20000);
    const response = await fetch(path, { credentials: 'same-origin', ...options, signal, headers: { Accept: 'application/json', ...(options.body ? { 'Content-Type': 'application/json' } : {}), ...options.headers } });
    let data;
    try { data = await response.json(); } catch (error) { if (['AbortError', 'TimeoutError'].includes(error.name)) throw error; data = null; }
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
  function getJob(id) { return state.jobs.get(String(id)) || state.applications.get(String(id))?.job || state.applications.get(String(id))?.job_snapshot || Object.values(state.recovery).find(record => String(record.job_id) === String(id))?.job_snapshot || { id, title: 'Unavailable listing', company: '' }; }
  function effectiveApplication(id) {
    const saved = state.applications.get(String(id));
    const session = state.sessions.get(String(id));
    if (!saved && !hasKeys(session?.pending) && !hasKeys(session?.inFlight)) return null;
    return mergePatch(mergePatch(session?.base || saved || { job_id: id, stage: 'Saved', revision: 0, notes: '' }, session?.inFlight), session?.pending);
  }
  function verificationText(job) {
    const verification = job.verification || {};
    const checked = date(verification.last_success_at || verification.checked_at);
    const closed = ['closed', 'expired', 'unavailable'].includes(String(job.status || '').toLowerCase());
    if (closed) return `${job.status === 'expired' ? 'Deadline has passed' : 'Listing unavailable'}${verification.last_success_at ? `. Last verified ${date(verification.last_success_at)}` : ''}`;
    if (!checked) return 'Source verification unavailable';
    if (!verification.last_success_at) return `Source record dated ${checked}. No successful check recorded`;
    return `Last verified ${checked}${verification.needs_recheck || ['failed', 'degraded'].includes(verification.status) ? '. Needs recheck' : ''}`;
  }
  function roleMetadata(job) {
    const node = el('div', 'role-metadata');
    node.append(el('span', 'salary', job.salary?.display || 'Salary not disclosed'));
    node.append(el('span', '', (job.employment_types?.length ? job.employment_types : [job.employment_type || 'Not stated']).join(' · ')));
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
      const reason = job.assessment_summary || listValues(assessment.reasons)[0];
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

  // Immutable records are scoped to one editor, job and version. A malformed
  // record cannot prevent independently valid records from being recovered.
  function readRecovery() {
    const records = {};
    let unreadable = false;
    try {
      try {
        const legacyRaw = localStorage.getItem(RECOVERY_KEY);
        if (legacyRaw && localStorage.getItem('sg_career_recovery_v2_imported') !== legacyRaw) {
          const legacy = JSON.parse(legacyRaw);
          if (!legacy || typeof legacy !== 'object' || Array.isArray(legacy)) throw new Error('Invalid legacy recovery');
          for (const [id, record] of Object.entries(legacy)) {
            if (!record || !hasKeys(record.patch)) continue;
            const raw = JSON.stringify({...record, job_id: id, editor_id: 'legacy'});
            // Retry a partially completed conversion without duplicating copies.
            let existing = false;
            for (let i = 0; i < localStorage.length; i += 1) {
              const key = localStorage.key(i);
              if (key?.startsWith(RECOVERY_PREFIX + 'legacy:') && localStorage.getItem(key) === raw) { existing = true; break; }
            }
            if (!existing) {
              const key = RECOVERY_PREFIX + 'legacy:' + crypto.randomUUID();
              localStorage.setItem(key, raw);
              if (localStorage.getItem(key) !== raw) throw new Error('Recovery verification failed');
            }
          }
          // Retain the original map after verified conversion.
          localStorage.setItem('sg_career_recovery_v2_imported', legacyRaw);
        }
      } catch { unreadable = true; }
      for (let i = 0; i < localStorage.length; i += 1) {
        const key = localStorage.key(i);
        if (!key?.startsWith(RECOVERY_PREFIX)) continue;
        try {
          const record = JSON.parse(localStorage.getItem(key));
          if (!record?.job_id || !record.patch || typeof record.patch !== 'object' || Array.isArray(record.patch)) throw new Error('Invalid recovery record');
          if (hasKeys(record.patch)) records[key] = record;
        } catch { unreadable = true; }
      }
      state.recovery = records;
    } catch { unreadable = true; }
    if (unreadable) notice('storage-read', 'Some browser recovery records could not be read. Original records are retained; readable versions remain available. Keep unsaved edits open until they save.');
    else clearNotice('storage-read');
  }
  function recoveryMessage(session) {
    return session?.recoveryFailed ? 'Your unsaved edits are only on this page. Download or copy them before leaving.' : 'Your edits are kept in this browser for retry.';
  }
  function downloadUnsaved(id) {
    const session = sessionFor(id);
    const record = {job_id: id, expected_revision: session.revision, base: session.base, patch: mergePatch(session.inFlight, session.pending), job_snapshot: getJob(id)};
    const url = URL.createObjectURL(new Blob([JSON.stringify(record, null, 2)], {type: 'application/json'}));
    const link = el('a'); link.href = url; link.download = 'unsaved-application.json'; document.body.append(link); link.click(); link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  function persistRecovery(id) {
    const session = state.sessions.get(id);
    const patch = mergePatch(session?.inFlight, session?.pending);
    try {
      const previous = session.recoveryKey;
      if (hasKeys(patch)) {
        const key = RECOVERY_PREFIX + editorId + ':' + encodeURIComponent(id) + ':' + crypto.randomUUID();
        const record = {job_id: id, editor_id: editorId, expected_revision: session.revision, base: session.base, patch, job_snapshot: getJob(id), updated_at: new Date().toISOString()};
        const raw = JSON.stringify(record);
        localStorage.setItem(key, raw);
        if (localStorage.getItem(key) !== raw) throw new Error('Recovery verification failed');
        state.recovery[key] = record; session.recoveryKey = key;
      } else session.recoveryKey = null;
      if (previous) { localStorage.removeItem(previous); delete state.recovery[previous]; }
      session.recoveryFailed = false;
      clearNotice(`storage:${id}`);
    } catch {
      session.recoveryFailed = hasKeys(patch);
      notice(`storage:${id}`, 'Browser recovery could not be stored. Keep this page open until server saving succeeds.', () => openRole(id), 'Review unsaved edits');
    }
  }
  function sessionFor(id) {
    id = String(id);
    if (!state.sessions.has(id)) {
      const base = state.applications.get(id) || {job_id: id, stage: 'Saved', notes: '', revision: 0};
      state.sessions.set(id, {base, revision: Number(base.revision), pending: {}, inFlight: {}, saving: false, error: null, conflict: null, timer: null, recoveryKey: null, recoveryFailed: false});
    }
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
      const acknowledgedPatch = session.inFlight;
      const matches = Object.entries(acknowledgedPatch).every(([key, value]) => {
        if (key === 'resolve_import_conflicts') return Array.isArray(saved?.import_conflicts)
          && saved.import_conflicts.every(conflict => Number.isInteger(conflict?.id) && !value.includes(conflict.id));
        if (key === 'drafts') return Object.entries(value).every(([name, text]) => saved?.drafts?.[name] === text);
        return saved?.[key] === value;
      });
      if (String(saved?.job_id) !== id || !Number.isInteger(saved?.revision) || saved.revision <= session.revision || !STAGES.includes(saved.stage) || typeof saved.notes !== 'string' || !matches) throw new Error('The server did not confirm these edits. Your pending text is preserved; retry saving.');
      const observed = state.applications.get(id);
      const latest = Number(observed?.revision || 0) > saved.revision ? observed : saved;
      session.base = saved;
      session.revision = saved.revision;
      state.applications.set(id, latest);
      session.inFlight = {};
      session.error = null;
      session.saving = false;
      if (latest !== saved) {
        if (hasKeys(session.pending)) session.conflict = latest;
        else { session.base = latest; session.revision = latest.revision; }
      }
      persistRecovery(id);
      if (latest !== saved && state.activeId === id) renderDetail(getJob(id), false);
      if (acknowledgedPatch.stage === 'Applied' && latest.stage === 'Applied' && !hasKeys(session.pending)) toast('Application marked applied.');
      renderNotices();
      updateImportNotice();
      updateSaveFeedback(id);
      updateDetailActions(id);
      updateAcknowledgedDetail(id, acknowledgedPatch);
      if (state.view === 'applications') renderApplications();
      else refreshRowStage(id);
      if (hasKeys(session.pending)) flushWrite(id);
    } catch (error) {
      session.pending = mergePatch(session.inFlight, session.pending);
      session.inFlight = {};
      session.saving = false;
      session.error = error.message;
      const observed = state.applications.get(id);
      if (error.status === 409) session.conflict = error.data?.detail?.current || error.data?.current || { revision: session.revision };
      if (Number(observed?.revision || 0) > Math.max(session.revision, Number(session.conflict?.revision || 0))) session.conflict = observed;
      persistRecovery(id);
      updateSaveFeedback(id);
      renderNotices();
      announce(`${session.conflict ? 'Another browser changed this application.' : 'Couldn’t save.'} ${recoveryMessage(session)}`);
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
    if (session?.conflict) { status.textContent = `Changes need review. ${recoveryMessage(session)}`; status.classList.add('is-error'); }
    else if (session?.error) { status.textContent = `Couldn’t save. ${recoveryMessage(session)}`; status.classList.add('is-error'); }
    else if (session?.saving || hasKeys(session?.pending)) status.textContent = 'Saving…';
    else if (application?.revision) { status.textContent = 'Saved'; status.classList.add('is-saved'); }
    else status.textContent = 'Writing a note also saves this role.';
    container.replaceChildren(status);
    if (session?.recoveryFailed) container.append(paragraph(recoveryMessage(session), 'field-help'), button('Download unsaved edits', () => downloadUnsaved(id)));
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
  function updateAcknowledgedDetail(id, patch) {
    if (state.activeId !== id) return;
    const application = effectiveApplication(id);
    const outcome = $('application-outcome')?.closest('label');
    if (outcome) outcome.hidden = application?.stage !== 'Closed';
    for (const conflictId of patch.resolve_import_conflicts || []) {
      const review = [...$('role-detail').querySelectorAll('[data-import-conflict]')].find(node => node.dataset.importConflict === String(conflictId));
      if (review) review.replaceChildren(paragraph('Review saved. The original entry and chosen version are retained in application history.'));
    }
    updateApplicationHistory(id);
  }
  function updateApplicationHistory(id) {
    if (state.activeId !== id || !effectiveApplication(id)?.revision) return;
    let section = $('application-history');
    if (!section) {
      section = el('details', 'detail-section'); section.id = 'application-history';
      section.append(el('summary', '', 'Application history'));
      section.addEventListener('toggle', () => {
        if (section.open && !section.querySelector('.history-content')) updateApplicationHistory(id);
      });
      $('role-detail').append(section);
    }
    const revision = String(effectiveApplication(id).revision);
    if (section.dataset.revision === revision && section.querySelector('.history-content')) return;
    const previous = section.querySelector('.history-content');
    const focusInside = previous?.contains(document.activeElement);
    previous?.remove(); // Detached containers also invalidate any older history response.
    section.dataset.revision = revision;
    if (section.open) {
      const content = el('div', 'history-content'); section.append(content);
      if (focusInside) section.querySelector('summary').focus({preventScroll: true});
      loadApplicationHistory(id, content);
    }
  }
  function resolveConflict(id, keepEdits) {
    const session = sessionFor(id);
    const current = session.conflict;
    if (!current || !Number.isFinite(Number(current.revision))) { toast('The server version is unavailable. Refresh applications and retry.'); return; }
    state.applications.set(id, current);
    session.base = current;
    session.revision = Number(current.revision);
    session.conflict = null;
    session.error = null;
    if (!keepEdits) { session.pending = {}; session.inFlight = {}; }
    else if (Array.isArray(current.import_conflicts) && session.pending.resolve_import_conflicts) {
      // Resolution commands are one-time events. Another accepted write may have
      // resolved them already; the user's explicitly rebased field edits remain.
      const unresolved = new Set(current.import_conflicts.map(conflict => conflict.id));
      session.pending.resolve_import_conflicts = session.pending.resolve_import_conflicts.filter(conflictId => unresolved.has(conflictId));
      if (!session.pending.resolve_import_conflicts.length) delete session.pending.resolve_import_conflicts;
    }
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
        const current = state.applications.get(id) || {job_id: id, revision: 0};
        if (!session.saving && !hasKeys(session.pending) && !session.conflict) {
          session.base = current; session.revision = Number(current.revision);
        } else if (!session.saving && Number(current.revision) !== session.revision) {
          session.conflict = current; clearTimeout(session.timer);
        }
      }
      restoreRecovery();
      if (state.activeId) renderDetail(getJob(state.activeId), false);
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
    readRecovery();
    const other = Object.entries(state.recovery).filter(([, record]) => record.editor_id !== editorId);
    if (other.length) notice('recovery', `${other.length} browser recovery versions are available. Review before applying saved text.`, () => openRole(String(other[0][1].job_id)), 'Review recovery', 'warning');
    else clearNotice('recovery');
    renderNotices();
  }
  function renderRecovery(id, container) {
    const records = Object.entries(state.recovery).filter(([, record]) => String(record.job_id) === id && record.editor_id !== editorId);
    if (!records.length) return;
    const section = el('details', 'detail-section'); section.open = true;
    section.append(el('summary', '', `Browser recovery (${records.length} versions)`));
    section.append(paragraph('Each version retains its original base revision. Saving this editor does not discard another editor’s copy.', 'field-help'));
    for (const [key, record] of records) {
      const version = el('details'); version.open = true;
      version.append(el('summary', '', `Saved ${record.updated_at ? new Date(record.updated_at).toLocaleString('en-SG') : 'date unknown'} · base revision ${record.expected_revision || 0}`));
      version.append(el('pre', 'conflict-copy', printableApplication(mergePatch(record.base, record.patch))));
      version.append(button('Load this recovery for review', () => {
        const session = sessionFor(id);
        if (session.saving || hasKeys(session.pending)) { toast('Save or resolve your pending changes before loading recovery.'); return; }
        session.base = record.base || state.applications.get(id) || {job_id: id, revision: 0};
        session.revision = Number(record.expected_revision || 0); session.pending = record.patch;
        session.conflict = state.applications.get(id) || {job_id: id, revision: 0};
        persistRecovery(id); renderDetail(getJob(id), false); renderNotices();
      }));
      version.append(button('Discard this recovery copy', () => {
        try { localStorage.removeItem(key); delete state.recovery[key]; restoreRecovery(); renderDetail(getJob(id), false); }
        catch { version.append(paragraph('This recovery copy could not be removed. It remains available; retry discarding when browser storage is accessible.', 'field-help')); }
      }, 'text-button'));
      section.append(version);
    }
    container.append(section);
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
    document.querySelector('.skip-link').inert = modal;
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
    sessionFor(id); // Bind displayed values before the first edit.
    const pane = $('role-detail');
    const previousScroll = pane.scrollTop;
    const previousFocusId = pane.contains(document.activeElement) ? document.activeElement.id : null;
    const previousSelection = previousFocusId && ['TEXTAREA', 'INPUT'].includes(document.activeElement.tagName) ? [document.activeElement.selectionStart, document.activeElement.selectionEnd] : null;
    const fragment = document.createDocumentFragment();
    const closeRow = el('div', 'detail-close-row');
    closeRow.append(button('← Back to roles', () => closeRole(), 'text-button'));
    closeRow.firstChild.textContent = state.view === 'applications' ? '← Back to applications' : '← Back to roles';
    if (application) closeRow.append(el('span', 'row-stage', application.stage));
    fragment.append(closeRow);
    const header = el('div', 'detail-header');
    const title = el('h2', '', job.title || 'Unavailable listing'); title.id = 'detail-title'; title.tabIndex = -1;
    header.append(title, paragraph(job.company || 'Company not stated', 'company'), roleMetadata(job));
    const facts = el('dl', 'detail-facts');
    for (const [label, value] of [['Work arrangement', job.work_arrangement], ['Thai relevance', job.thai_relevance], ['First collected', date(job.discovered_at || job.collected_at)], ['Employer posting date', date(job.posted_at)], ['Deadline', date(job.deadline)]]) {
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
        review.dataset.importConflict = String(conflict.id);
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
          $('application-outcome').closest('label').hidden = effectiveApplication(id)?.stage !== 'Closed';
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
    renderRecovery(id, fragment);
    const preparation = el('div'); preparation.id = 'preparation'; fragment.append(preparation);
    pane.replaceChildren(fragment);
    updateDetailEvidence(job);
    updateDetailActions(id);
    updateSaveFeedback(id);
    renderPreparation(id);
    updateApplicationHistory(id);
    pane.scrollTop = previousScroll;
    if (focus) title.focus({ preventScroll: true });
    else if (previousFocusId) {
      const input = $(previousFocusId); input?.focus({ preventScroll: true });
      if (previousSelection && previousSelection[0] !== null && input?.setSelectionRange) input.setSelectionRange(...previousSelection);
    }
  }
  async function loadApplicationHistory(id, container, offset = 0) {
    const progress = paragraph('Loading application history…', 'field-help'); container.append(progress);
    try {
      const data = await api(`/api/applications/${encodeURIComponent(id)}/history?offset=${offset}&limit=25`);
      if (!container.isConnected) return;
      progress.remove();
      if (!data.total) container.append(paragraph('No history recorded yet.', 'field-help'));
      for (const event of data.items || []) {
        const row = el('div', 'history-event');
        row.append(paragraph(`${date(event.at || event.created_at) || 'Date not recorded'} · ${(event.type || event.action || 'Application updated').replaceAll('_', ' ')}${event.stage ? ' · ' + event.stage : ''}`));
        if (event.changed_fields?.length) row.append(paragraph(event.changed_fields.map(field => field.replaceAll('_', ' ')).join(', '), 'field-help'));
        if (event.type === 'import_version') {
          row.append(paragraph(`Import ${event.resolution_status}. Original entry retained ${date(event.created_at) || 'date unknown'}${event.resolved_at ? '. Resolved ' + date(event.resolved_at) : ''}.`, 'field-help'));
          const original = el('details'); original.append(el('summary', '', 'Original browser notes and stage'), el('pre', 'conflict-copy', printableApplication(event.incoming?.application || event.incoming)));
          row.append(original);
          if (event.resolution) {
            const resolved = el('details'); resolved.append(el('summary', '', 'Resolution saved to application'), el('pre', 'conflict-copy', printableApplication(event.resolution))); row.append(resolved);
          } else if (event.resolution_status === 'resolved') row.append(paragraph('The resolution predates retained resolution snapshots. The original entry is available above.', 'field-help'));
        }
        container.append(row);
      }
      const next = offset + (data.items || []).length;
      if (next < data.total) container.append(button('Load older application history', event => { event.currentTarget.remove(); loadApplicationHistory(id, container, next); }));
    } catch (error) {
      if (!container.isConnected) return;
      progress.remove(); const retry = el('div', 'notice warning');
      retry.append(paragraph(error.message), button('Retry application history', () => {retry.remove(); loadApplicationHistory(id, container, offset);})); container.append(retry);
    }
  }
  function fieldProvenance(job, name, container) {
    const evidence = job.field_provenance?.[name] || {};
    const available = name === 'requirements' ? Boolean(job.source_requirements) : Boolean(job.description);
    const retained = available ? date(evidence.checked_at || evidence.source_record_date) : null;
    container.append(paragraph(`${name === 'description' ? 'Description retained' : name === 'requirements' ? 'Explicit requirements retained' : 'Description-derived requirements retained'}: ${retained || 'not recorded'}. Listing checks do not refresh retained content.`, 'field-help'));
    if (safeURL(evidence.url)) { const link = el('a', 'button-link', 'Open field source'); link.href = safeURL(evidence.url); link.target = '_blank'; link.rel = 'noopener noreferrer'; container.append(link); }
  }
  function updateDetailEvidence(job) {
    const container = $('detail-evidence');
    if (!container) return;
    const responsibilities = detailSection('Role description');
    responsibilities.append(paragraph(job.description || 'The source does not provide a complete role description.', 'source-description'));
    fieldProvenance(job, 'description', responsibilities);
    const requirements = detailSection('Employer requirements');
    requirements.id = 'employer-requirements'; requirements.tabIndex = -1;
    if (listValues(job.requirements?.mandatory).length) { requirements.append(el('h3', '', 'Mandatory')); appendList(requirements, job.requirements.mandatory); }
    else requirements.append(paragraph('Mandatory requirements are not available in the retained source.', 'field-help'));
    if (listValues(job.requirements?.preferred).length) { requirements.append(el('h3', '', 'Preferred')); appendList(requirements, job.requirements.preferred); }
    fieldProvenance(job, 'requirements', requirements);
    if (job.field_provenance?.derived_requirements) fieldProvenance(job, 'derived_requirements', requirements);
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
      toast('Saving Applied stage…');
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
    if (!application || (!['Preparing', 'Applied', 'Interviewing', 'Offer'].includes(application.stage) && !hasKeys(application.drafts))) return;
    const section = el('details', 'detail-section'); section.open = application.stage === 'Preparing';
    section.append(el('summary', '', 'Application preparation'));
    section.append(paragraph('Review and edit these drafts before using them. They use documented candidate facts and the available role evidence.', 'field-help'));
    const generated = state.drafts.get(id);
    appendSupportedPairs(section, generated?.supported_pairs);
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
    const checklist = el('details'); checklist.id = 'preparation-checklist'; checklist.append(el('summary', '', 'Requirements to resolve before applying'));
    appendList(checklist, state.drafts.get(id)?.requirements_to_check || getJob(id).assessment?.gaps, 'Review the original listing and confirm any requirements not established by your CV.');
    section.append(checklist);
    container.append(section);
    updateSaveFeedback(id);
    if (generated?.error) {
      const retry = el('div', 'notice warning');
      retry.append(paragraph(`Draft suggestions couldn’t be loaded. Your edits are retained. ${generated.error}`), button('Retry draft suggestions', () => { retry.remove(); loadDrafts(id); }));
      container.append(retry);
    }
    if (application.stage === 'Interviewing' && generated?.interview_prep) {
      const interview = detailSection('Interview preparation'); appendList(interview, generated.interview_prep); container.append(interview);
    }
    if (!state.drafts.has(id) && ['Preparing', 'Applied', 'Interviewing', 'Offer'].includes(application.stage)) loadDrafts(id);
  }

  function appendSupportedPairs(container, pairs) {
    container.querySelector('.supported-pairs')?.remove();
    if (!Array.isArray(pairs) || !pairs.length) return;
    const section = detailSection('Supported evidence for this role');
    section.classList.add('supported-pairs');
    section.append(paragraph('These listing responsibilities have specific supporting CV evidence. Use the quotations as prompts and keep your own wording truthful.', 'field-help'));
    const list = el('ul');
    for (const pair of pairs) {
      const item = el('li');
      item.append(el('strong', '', `Listing: “${pair.quote || 'Responsibility not quoted'}”`));
      const evidence = Array.isArray(pair.candidate_evidence) ? pair.candidate_evidence.filter(Boolean) : [];
      item.append(paragraph(evidence.length ? `CV evidence: ${evidence.join(' ')}` : 'CV evidence is not recorded.', 'field-help'));
      list.append(item);
    }
    section.append(list);
    const anchor = container.querySelector('.save-status');
    if (anchor) container.insertBefore(section, anchor);
    else container.append(section);
  }
  async function loadDrafts(id) {
    state.drafts.set(id, { loading: true });
    try {
      const data = await api(`/api/drafts/${encodeURIComponent(id)}`);
      state.drafts.set(id, data);
      const current = effectiveApplication(id)?.drafts || {};
      const patch = {};
      for (const name of ['recruiter_message', 'cover_letter']) {
        const input = state.activeId === id ? $(`draft-${name}`) : null;
        // Focus establishes editing intent before the first input event. A late
        // suggestion must not replace the selection beneath a user's keystroke.
        if (input && document.activeElement === input) continue;
        if (!Object.prototype.hasOwnProperty.call(current, name) && typeof data[name] === 'string') patch[name] = data[name];
      }
      if (hasKeys(patch)) queueWrite(id, { drafts: patch });
      // Do not replace draft inputs the user is currently editing.
      if (state.activeId === id) {
        const checklist = $('preparation-checklist');
        if (checklist) { checklist.replaceChildren(el('summary', '', 'Requirements to resolve before applying')); appendList(checklist, data.requirements_to_check, 'Review the original listing before applying.'); }
        const preparation = $('preparation');
        const section = preparation?.querySelector('.detail-section');
        if (section) appendSupportedPairs(section, data.supported_pairs);
        for (const [name, value] of Object.entries(patch)) { const input = $(`draft-${name}`); if (input) input.value = value; }
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
      const response = await fetch(path, { credentials: 'same-origin', signal: AbortSignal.timeout(20000) });
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
  window.addEventListener('storage', event => {
    if (event.key?.startsWith(RECOVERY_PREFIX)) restoreRecovery();
  });
  window.addEventListener('online', () => {
    for (const [id, session] of state.sessions) if (session.error && !session.conflict) { session.error = null; flushWrite(id); }
  });
  // beforeunload is only needed when browser recovery itself failed.
  window.addEventListener('beforeunload', event => {
    if ([...state.sessions.values()].some(session => session.recoveryFailed && (session.saving || hasKeys(session.pending)))) { event.preventDefault(); event.returnValue = ''; }
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
