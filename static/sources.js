/* Inspect retained evidence; collection success is never inferred from a stored date. */
(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const state = {audit: null, source: '', offset: 0, job: null, recordEpoch: 0, inspectEpoch: 0, overviewEpoch: 0, controller: null, timer: null, poll: null, checking: false};
  const leadState = {offset: 0, epoch: 0, controller: null};
  const labels = {scheduled: 'Automatic · every 12 hours', retained: 'Retained import', error: 'Last check failed', degraded: 'Check incomplete', paused: 'Automatic checks paused', checking: 'Checking source…', active: 'Campaign active', pilot: 'Pilot in progress', prepared: 'Prepared for pilot', stopped: 'Campaign ended', blocked: 'Collection blocked'};
  const number = value => Number(value || 0).toLocaleString('en-SG');
  const sourceName = value => ({linkedin: 'LinkedIn', indeed: 'Indeed', google: 'Google', careers: 'Career websites'})[value] || value;
  const money = value => value === null || value === undefined ? 'Not reported' : new Intl.NumberFormat('en-US', {style: 'currency', currency: 'USD', maximumFractionDigits: 4}).format(value);
  const counts = value => value ? `${number(value.new_count)} new; ${number(value.updated_count)} updated; ${number(value.duplicate_count)} duplicate; ${number(value.lead_count)} leads` : 'Counts not yet reported';
  const el = (tag, text, cls) => {const node = document.createElement(tag); if (text !== undefined && text !== null) node.textContent = text; if (cls) node.className = cls; return node;};
  const button = (text, action, cls) => {const node = el('button', text, cls); node.type = 'button'; node.addEventListener('click', action); return node;};
  function link(text, path, external = false) {
    const node = el('a', text); const url = new URL(path, location.origin);
    if (!['http:', 'https:'].includes(url.protocol)) return el('span', text);
    node.href = url.href;
    if (external) {node.target = '_blank'; node.rel = 'noopener noreferrer';}
    return node;
  }
  function date(value) {
    if (!value) return 'Not recorded';
    const parsed = new Date(typeof value === 'number' ? value * 1000 : value);
    if (Number.isNaN(parsed.getTime())) return 'Not recorded';
    if (typeof value === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(value)) return new Intl.DateTimeFormat('en-SG', {day:'numeric',month:'short',year:'numeric',timeZone:'Asia/Singapore'}).format(parsed) + ' (date only)';
    return new Intl.DateTimeFormat('en-SG', {day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit', timeZone: 'Asia/Singapore'}).format(parsed) + ' SGT';
  }
  async function api(path, options = {}) {
    const timeout = path === '/api/sync' ? 65000 : 20000;
    const signal = options.signal ? AbortSignal.any([options.signal, AbortSignal.timeout(timeout)]) : AbortSignal.timeout(timeout);
    const response = await fetch(path, {credentials: 'same-origin', ...options, signal});
    if (!response.ok) throw new Error(response.status === 401 ? 'Sign-in is required. Reload this page to authenticate.' : response.status === 404 ? 'No retained evidence was found for this record.' : `Couldn’t load data (${response.status}). Please retry.`);
    return response.json();
  }
  function failure(container, error, retry) {container.replaceChildren(el('p', error.message, 'audit-error'), button('Retry', retry));}
  function facts(container, pairs) {
    const dl = el('dl', null, 'inspector-facts');
    for (const [key, value] of pairs) dl.append(el('dt', key), el('dd', value ?? 'Not recorded'));
    container.append(dl);
  }
  function updateURL(replace = false) {
    const params = new URLSearchParams();
    if (state.source) params.set('source', state.source);
    if ($('record-query').value.trim()) params.set('q', $('record-query').value.trim());
    if ($('record-status').value) params.set('status', $('record-status').value);
    if (state.offset) params.set('offset', state.offset);
    if (state.job) params.set('job', state.job);
    const target = '/sources' + (params.size ? '?' + params : '');
    if (target !== location.pathname + location.search) history[replace ? 'replaceState' : 'pushState']({}, '', target);
  }
  function readURL() {
    const params = new URLSearchParams(location.search);
    state.source = params.get('source') || '';
    state.offset = Math.max(0, Number(params.get('offset')) || 0);
    $('record-query').value = params.get('q') || '';
    $('record-status').value = params.get('status') || '';
    return params.get('job');
  }
  function selectSource(id) {
    state.source = id; state.offset = 0;
    renderSelection(); scheduleRecords(0); updateURL();
  }
  async function loadOverview() {
    const epoch = ++state.overviewEpoch;
    $('refresh-overview').disabled = true;
    try {
      const audit = await api('/api/audit/sources');
      if (epoch !== state.overviewEpoch) return;
      state.audit = audit;
      $('load-feedback').replaceChildren(); $('load-feedback').hidden = true;
      $('audit-content').hidden = false;
      renderOverview(); renderSelection();
      clearTimeout(state.poll);
      if (audit.scheduler.running || ['active','pilot'].includes(audit.campaign?.state)) state.poll = setTimeout(loadOverview, 15000);
    } catch (error) {if (epoch === state.overviewEpoch) {$('load-feedback').hidden = false; failure($('load-feedback'), error, loadOverview);}}
    finally {if (epoch === state.overviewEpoch) $('refresh-overview').disabled = false;}
  }
  function renderOverview() {
    const audit = state.audit;
    const nodes = audit.sources.map(source => {
      const node = button('', () => selectSource(source.id), 'source-node'); node.dataset.source = source.id;
      const dot = el('span', null, `status-dot ${source.state}`); dot.setAttribute('aria-hidden', 'true');
      const copy = el('span', null, 'node-copy'); copy.append(el('strong', source.name), el('small', labels[source.state] || source.state));
      node.append(dot, copy, el('span', number(source.count), 'node-count'));
      node.setAttribute('aria-label', `${source.name}, ${number(source.count)} retained jobs, ${labels[source.state] || source.state}`);
      return node;
    });
    $('source-nodes').replaceChildren(...nodes);
    $('record-source').replaceChildren(new Option('All sources', ''), ...audit.sources.map(source => new Option(source.name, source.id)));
    $('record-source').value = state.source;
    const errors = audit.sources.filter(source => ['error', 'degraded'].includes(source.state));
    $('collection-health').textContent = errors.length ? errors.map(source => `${source.name}: ${labels[source.state]}`).join(' · ') : 'Collection outcomes and next runs are shown below.';
    $('engine-count').textContent = `${number(audit.total)} retained jobs`;
    $('discovery-count').textContent = `${number(audit.discovery_count)} records before your filters`;
    $('application-count').textContent = `${number(audit.applications_count)} tracked applications`;
    $('excluded-count').textContent = `${number(audit.excluded_count)} expired, closed or unavailable records are kept for history.`;
    const scheduler = audit.scheduler;
    $('schedule-summary').textContent = scheduler.running ? 'MyCareersFuture check is in progress.' : scheduler.enabled ? `MyCareersFuture is scheduled every ${scheduler.interval_hours} hours.` : 'Automatic checks are paused on this service.';
    $('schedule-detail').textContent = `Up to ${scheduler.limit_per_query} results from each of ${scheduler.queries.length} searches.${scheduler.next_check_at ? ' Next check: ' + date(scheduler.next_check_at) + '.' : ''}`;
    renderCampaign(audit.campaign);
    $('check-source').disabled = scheduler.running || state.checking;
    const history = $('history'); history.replaceChildren();
    if (!audit.history.length) history.append(el('p', 'No collection runs have been recorded. Imported source dates are shown with each record.', 'secondary'));
    for (const run of audit.history) {
      const row = el('details', null, 'history-run'); const summary = el('summary');
      summary.append(el('strong', ({success: 'Check completed', error: 'Check failed', degraded: 'Partially completed', interrupted: 'Interrupted by restart'})[run.status] || run.status), el('span', date(run.started_at || run.recorded_at)));
      row.append(summary, el('p', `${number(run.added_count)} added; ${number(run.updated_count)} updated${run.duration_seconds !== undefined ? '; ' + run.duration_seconds + ' seconds' : ''}.`));
      if (run.message) row.append(el('p', run.message));
      const outcomes = el('ul');
      for (const success of run.sources || []) outcomes.append(el('li', `${success.query || success.source}: ${number(success.returned_count)} results returned. Successful response ${date(success.checked_at)}.`));
      for (const error of run.errors || []) outcomes.append(el('li', `${error.query || error.source || 'Source'}: ${error.message} Attempted ${date(error.attempted_at)}.`, 'audit-error'));
      row.append(outcomes); history.append(row);
    }
  }
  function renderCampaign(campaign) {
    const detail = $('campaign-detail'); detail.replaceChildren();
    const active = ['active','pilot'].includes(campaign?.state);
    $('pause-campaign').hidden = !active;
    $('campaign-summary').textContent = `Seven-day campaign · ${labels[campaign?.state] || 'Not started'}`;
    if (!campaign || campaign.state === 'not_prepared') {detail.append(el('p', 'Paid collection has not started. MyCareersFuture keeps its existing schedule.')); return;}
    facts(detail, [['Automatic stop',date(campaign.stops_at)],['Reported run charges',money(campaign.reported_run_charges_usd)],
      ['Account usage since baseline',money(campaign.observed_account_usage_usd)],['Actor budget committed',`${money(campaign.actor_committed_usd)} total; ${money(campaign.rolling_actor_committed_usd)} in the rolling day`],
      ['Ceilings','US$50 per rolling 24 hours; US$350 total'],['Last worker heartbeat',date(campaign.heartbeat)]]);
    if (campaign.reason) detail.append(el('p',campaign.reason,'audit-error'));
    if (campaign.accounting_error) detail.append(el('p',`Admissions blocked: ${campaign.accounting_error}`,'audit-error'));
    if (campaign.worker_error) detail.append(el('p',`Worker needs inspection: ${campaign.worker_error.type}. Last recorded ${date(campaign.worker_error.at)}.`,'audit-error'));
    facts(detail, [['Production collection', counts(campaign.production_counts)], ['Isolated validation', counts(campaign.pilot_counts)],
      ['Distinct supported production vacancies', campaign.production_counts ? number(campaign.production_counts.unique_supported_vacancies) : 'Not yet reported'],
      ['Distinct supported validation vacancies', campaign.pilot_counts ? number(campaign.pilot_counts.unique_supported_vacancies) : 'Not yet reported'],
      ['Discovered domains', number(campaign.discovered_domains)]]);
    detail.append(el('p', 'New, updated and duplicate counts describe import outcomes. Distinct supported vacancies include existing roles checked again. Isolated validation does not add roles to Find roles.', 'field-help'));
    if (campaign.accounting_note) detail.append(el('p',campaign.accounting_note,'field-help'));
    for (const s of campaign.sources || []) {
      const group = el('section', null, 'campaign-source'); group.append(el('h3', sourceName(s.source)));
      group.append(el('p', `Production: ${counts(s.production_counts)}.`), el('p', `Isolated validation: ${counts(s.pilot_counts)}.`));
      if (s.blocked_reason) group.append(el('p', s.blocked_reason, 'audit-error'));
      group.append(el('p', active ? 'Next cycle: '+date(s.due_at) : 'Paid collection is not active.'));
      if (s.outcome) group.append(el('p', `Latest outcome: ${s.outcome}${s.error_category ? ' · '+s.error_category : ''}.`));
      detail.append(group);
    }
    detail.append(link('Open campaign report','/api/campaign/report'));
    const runs = el('details'); runs.append(el('summary','Recent paid batches'));
    if (!(campaign.runs || []).length) runs.append(el('p','No paid batch has been admitted.'));
    for (const run of (campaign.runs || []).slice(-20).reverse()) {
      const row = el('div',null,'history-run');
      row.append(el('p',`${sourceName(run.source)} · ${run.pilot ? 'Isolated validation' : 'Production'} · ${run.state} · ${date(run.reserved_at)}`),el('p',counts(run)+'.'));
      row.append(el('p', `Reserved: ${money(run.cap_usd)}. Reported charge: ${money(run.charge_usd)}.${run.error_category ? ' Failure category: '+run.error_category+'.' : ''}`));
      if (run.error) row.append(el('p',run.error,'audit-error'));
      if (run.run_id) row.append(link('Inspect Apify run ↗',`https://console.apify.com/actors/runs/${encodeURIComponent(run.run_id)}`,true));
      runs.append(row);
    }
    detail.append(runs);
  }
  function renderSelection() {
    if (!state.audit) return;
    const source = state.audit.sources.find(item => item.id === state.source);
    if (state.source && !source) {state.source = ''; updateURL(true);}
    for (const node of $('source-nodes').children) node.setAttribute('aria-pressed', String(node.dataset.source === state.source));
    $('record-source').value = state.source;
    $('all-sources').setAttribute('aria-pressed', String(!state.source));
    $('selected-heading').textContent = source?.name || 'All sources';
    const detail = $('selected-detail'); detail.replaceChildren();
    if (!source) {
      detail.append(el('p', state.audit.explanation), el('p', 'The original collectors stored a mixture of full descriptions, excerpts and inserted defaults. Inspect a record to compare the retained payload with the cleaned fields used in the workspace.'));
      facts(detail, [['Retained records', number(state.audit.total)], ['Sources', number(state.audit.sources.length)], ['Audit loaded', date(state.audit.generated_at)]]);
    } else {
      detail.append(el('p', source.scope));
      facts(detail, [['Collection method', source.method], ['Mode', labels[source.state]], ['Last attempt', date(source.last_attempt)], ['Last successful response', date(source.last_success)], ['Latest retained record date', date(source.latest_record_date)], ['Need recheck', `${number(source.needs_recheck)} of ${number(source.count)}`]]);
      if (source.home) detail.append(link('Visit source website ↗', source.home, true));
      if (source.endpoint) {const line = el('p'); line.append(el('span', 'Endpoint: '), link(source.endpoint, source.endpoint, true)); detail.append(line);}
      if (source.mode === 'scheduled') {
        detail.append(el('p', 'Queries used by this collector:'));
        const list = el('ul', null, 'query-list'); state.audit.scheduler.queries.forEach(query => list.append(el('li', query))); detail.append(list);
      }
      if (source.latest_errors.length) detail.append(el('p', `Latest failure: ${source.latest_errors[0].message}`, 'audit-error'));
      if (source.campaign?.blocked_reason) detail.append(el('p',source.campaign.blocked_reason,'audit-error'));
      if (source.campaign) facts(detail,[['Next cycle',date(source.next_check_at)],['Production collection',counts(source.campaign.production_counts)],['Isolated validation',counts(source.campaign.pilot_counts)]]);
      detail.append(el('p', 'Retained record dates can come from the original import. They do not prove that the source was checked successfully.', 'field-help'));
    }
    const bars = (source || state.audit).coverage.map((item, index) => {
      const row = el('div', null, 'coverage-row'); const line = el('div', null, 'coverage-label');
      const label = el('span', item.label); label.id = `coverage-label-${index}`;
      line.append(label, el('span', `${number(item.count)} / ${number(item.total)} (${item.percent}%)`));
      const bar = el('progress'); bar.max = item.total || 1; bar.value = item.count; bar.setAttribute('aria-labelledby', label.id);
      row.append(line, bar); return row;
    });
    $('coverage').replaceChildren(...bars);
  }
  function scheduleRecords(delay = 200) {
    clearTimeout(state.timer); state.controller?.abort(); const epoch = ++state.recordEpoch;
    $('record-count').textContent = 'Loading records…'; $('records').setAttribute('aria-busy', 'true');
    $('records').replaceChildren(el('div', 'Loading retained records…', 'loading-row'));
    $('previous-records').disabled = true; $('next-records').disabled = true;
    state.timer = setTimeout(() => loadRecords(epoch), delay);
  }
  async function loadRecords(epoch) {
    state.controller = new AbortController();
    const params = new URLSearchParams({source: state.source, q: $('record-query').value.trim(), status: $('record-status').value, offset: state.offset, limit: 20});
    try {
      const data = await api('/api/audit/records?' + params, {signal: state.controller.signal});
      if (epoch !== state.recordEpoch) return;
      $('record-count').textContent = `${number(data.total)} records${state.source ? ' from ' + (state.audit?.sources.find(s => s.id === state.source)?.name || state.source) : ''}`;
      const records = data.items.map(item => {
        const row = el('article', null, 'audit-record'); const identity = el('div');
        identity.append(el('strong', item.title || 'Untitled listing'), el('p', item.company || 'Company not recorded'), el('p', `${item.id} · ${item.source_name}`));
        const metadata = el('div'); const verified = item.verification?.last_success_at;
        metadata.append(el('p', verified ? `Last successful check: ${date(verified)}` : 'No successful listing check recorded'), el('p', ['expired', 'closed', 'unavailable'].includes(item.status) ? `Excluded: ${item.status}` : item.verification?.needs_recheck ? 'Needs recheck' : 'Checked within 24 hours'));
        const inspect = button('Inspect', () => openRecord(item.id)); inspect.setAttribute('aria-label', `Inspect source: ${item.title || item.id}`);
        row.append(identity, metadata, inspect); return row;
      });
      $('records').replaceChildren(...records);
      if (!records.length) $('records').append(el('p', 'No retained records match these filters.'), button('Clear search and filters', () => {state.source = ''; state.offset = 0; $('record-query').value = ''; $('record-status').value = ''; renderSelection(); updateURL(); scheduleRecords(0);}));
      $('record-page').textContent = data.total ? `${number(state.offset + 1)}–${number(Math.min(state.offset + data.limit, data.total))} of ${number(data.total)}` : '0 records';
      $('previous-records').disabled = state.offset === 0; $('next-records').disabled = state.offset + data.limit >= data.total;
    } catch (error) {if (epoch === state.recordEpoch && error.name !== 'AbortError') {$('record-count').textContent = 'Records couldn’t be loaded'; failure($('records'), error, () => scheduleRecords(0));}}
    finally {if (epoch === state.recordEpoch) $('records').setAttribute('aria-busy', 'false');}
  }
  async function checkSource() {
    if (state.checking || state.audit?.scheduler.running) return;
    state.checking = true; $('check-source').disabled = true; $('check-feedback').hidden = false;
    $('check-feedback').textContent = 'Checking MyCareersFuture. This can take about a minute; previous evidence stays available.';
    state.poll = setTimeout(loadOverview, 1000);
    try {
      const result = await api('/api/sync', {method: 'POST'});
      $('check-feedback').textContent = result.status === 'in_progress' ? 'A source check is already running. Its status will update here.' : result.status === 'success' ? `Check completed. ${number(result.added_count)} added; ${number(result.updated_count)} updated. Only returned listings were checked.` : 'The source check could not fully complete. Previous evidence was retained. See collection history for query errors.';
    } catch (error) {$('check-feedback').textContent = `${error.message} The server may still be checking. Reload the audit to see its recorded outcome.`;}
    finally {state.checking = false; await loadOverview(); scheduleRecords(0);}
  }
  async function loadLeads(reset = false) {
    if (reset) leadState.offset = 0;
    leadState.controller?.abort(); leadState.controller = new AbortController();
    const epoch = ++leadState.epoch;
    $('lead-count').textContent = 'Loading discovery leads…'; $('leads').setAttribute('aria-busy', 'true');
    $('previous-leads').disabled = true; $('next-leads').disabled = true;
    const params = new URLSearchParams({source: $('lead-source').value, pilot: $('lead-scope').value, offset: leadState.offset, limit: 20});
    try {
      const data = await api('/api/campaign/leads?' + params, {signal: leadState.controller.signal});
      if (epoch !== leadState.epoch) return;
      const rows = data.items.map(item => {
        const row = el('article', null, 'audit-record'); const identity = el('div');
        identity.append(el('strong', item.title || item.url || 'Untitled lead'), el('p', `${sourceName(item.source) || 'Career discovery'} · ${item.state || 'Retained lead'}`));
        const metadata = el('div'); metadata.append(el('p', item.reason || 'Vacancy evidence needs review.'), el('p', `Collected: ${date(item.discovered_at)}`));
        const inspect = button('Inspect lead', () => openLead(item)); inspect.setAttribute('aria-label', `Inspect lead: ${item.title || item.url || item.id}`);
        row.append(identity, metadata, inspect); return row;
      });
      $('leads').replaceChildren(...rows);
      if (!rows.length) $('leads').append(el('p', 'No discovery leads in this collection scope.'));
      $('lead-count').textContent = `${number(data.total)} ${$('lead-scope').value === 'true' ? 'isolated validation' : 'production'} leads`;
      $('lead-page').textContent = data.total ? `${number(leadState.offset + 1)}–${number(Math.min(leadState.offset + data.limit, data.total))} of ${number(data.total)}` : '0 leads';
      $('previous-leads').disabled = leadState.offset === 0; $('next-leads').disabled = leadState.offset + data.limit >= data.total;
    } catch (error) {
      if (epoch === leadState.epoch && error.name !== 'AbortError') {$('lead-count').textContent = 'Leads couldn’t be loaded'; failure($('leads'), error, () => loadLeads());}
    } finally {if (epoch === leadState.epoch) $('leads').setAttribute('aria-busy', 'false');}
  }
  function openLead(item) {
    ++state.inspectEpoch; state.job = null; updateURL();
    const dialog = $('record-inspector');
    if (!dialog.open) dialog.showModal(); document.body.classList.add('inspector-open');
    $('inspector-title').textContent = item.title || 'Discovery lead';
    const content = $('inspector-content'); content.replaceChildren();
    content.append(el('p', item.reason || 'The returned evidence does not yet establish a supported vacancy.', 'notice'));
    facts(content, [['Source', sourceName(item.source)], ['Collection scope', item.pilot ? 'Isolated validation' : 'Production'], ['Queue state', item.state], ['Collected', date(item.discovered_at)], ['Discovery depth', item.depth]]);
    const links = el('div', null, 'inspector-links');
    if (item.url) links.append(link('Open discovered page ↗', item.url, true));
    if (item.parent_url) links.append(link('Open parent evidence page ↗', item.parent_url, true));
    if (item.job_id && !item.pilot) links.append(link('View supported role', '/?role=' + encodeURIComponent(item.job_id)));
    content.append(links);
    const lineage = section(content, 'Collection context and parent evidence');
    lineage.append(el('pre', JSON.stringify(item.context || item.evidence || {parent_url: item.parent_url, batch_id: item.batch_id}, null, 2), 'evidence-json'));
    const payload = section(content, 'Returned source payload');
    payload.append(el('p', 'Retained source content, with credential-like values redacted for inspection. Search wording and snippets do not establish a vacancy.', 'secondary'), el('pre', JSON.stringify(item.payload ?? item.evidence ?? {}, null, 2), 'evidence-json'));
    $('inspector-title').focus({preventScroll: true});
  }
  function section(container, title) {const node = el('section'); node.append(el('h3', title)); container.append(node); return node;}
  function evidenceVersions(container, evidence) {
    for (const record of evidence.items) {
      const details = el('details', null, 'evidence-version');
      details.append(el('summary', `Version ${record.id} · stored ${date(record.captured_at)}`), el('p', record.source), el('pre', JSON.stringify(record.payload, null, 2), 'evidence-json')); container.append(details);
    }
  }
  async function openRecord(id, push = true) {
    const epoch = ++state.inspectEpoch; state.job = id;
    if (push) updateURL();
    const dialog = $('record-inspector');
    if (!dialog.open) dialog.showModal(); document.body.classList.add('inspector-open');
    $('inspector-title').textContent = 'Loading source evidence…'; $('inspector-content').replaceChildren();
    try {
      const data = await api(`/api/audit/records/${encodeURIComponent(id)}?limit=5`);
      if (epoch !== state.inspectEpoch || !dialog.open) return;
      const job = data.job; $('inspector-title').textContent = job.title || id;
      const content = $('inspector-content');
      content.append(el('p', job.company || 'Company not recorded'), el('p', data.notice, 'notice'));
      const actions = el('div', null, 'inspector-links');
      const role = link('View role', '/?role=' + encodeURIComponent(id)); role.className = 'button-link'; actions.append(role);
      if (job.url) {const original = link('Open original listing ↗', job.url, true); original.className = 'button-link'; actions.append(original);}
      content.append(actions);
      facts(content, [['Record ID', id], ['Listing status', job.status], ['First collected', date(job.discovered_at || job.collected_at)], ['Employer posting date', date(job.posted_at)], ['Last successful listing check', date(job.verification?.last_success_at)], ['Retained record date', date(job.verification?.checked_at)], ['Latest failed attempt', job.verification?.last_error ? date(job.verification?.last_attempt_at) : 'None recorded'], ['Closing date', job.deadline || 'Not stated']]);
      for (const [name, evidence] of Object.entries(job.field_provenance || {})) facts(content, [[`${name} source date`, date(evidence.checked_at || evidence.source_record_date)], [`${name} evidence version`, evidence.evidence_id || 'Not recorded']]);
      if (job.source_warning) content.append(el('p', job.source_warning, 'notice warning'));
      if (job.verification?.last_error) content.append(el('p', job.verification.last_error, 'audit-error'));
      for (const field of data.provenance) {
        if (field.field === 'Assessment') continue;
        const group = section(content, field.field); group.append(el('p', field.basis, 'secondary'));
        if (field.quality) group.append(el('p', field.quality, 'field-help'));
        const value = field.value;
        if (typeof value === 'object' && value !== null) group.append(el('pre', JSON.stringify(value, null, 2), 'evidence-value'));
        else group.append(el('p', value || 'Not available in the retained source.', 'evidence-value'));
      }
      const assessment = section(content, 'Candidate assessment');
      if (window.FitScore) assessment.append(window.FitScore.detail(job));
      else assessment.append(el('pre', JSON.stringify(job.assessment, null, 2), 'evidence-value'));
      const context = section(content, 'Collector context'); context.append(el('p', 'A search query explains how a record was found. It is not an employer requirement.', 'secondary'), el('pre', Object.keys(data.collector_context).length ? JSON.stringify(data.collector_context, null, 2) : 'No collector context retained.', 'evidence-value'));
      const versions = section(content, 'Retained evidence versions'); versions.append(el('p', `${number(data.evidence.total)} stored versions. Stored dates record capture in this database, not upstream verification.`, 'secondary'));
      evidenceVersions(versions, data.evidence);
      let offset = data.evidence.items.length;
      if (offset < data.evidence.total) {
        const more = button('Load older evidence', async () => {
          more.disabled = true;
          try {
            const next = await api(`/api/audit/records/${encodeURIComponent(id)}?offset=${offset}&limit=5`);
            if (epoch !== state.inspectEpoch) return;
            more.remove(); evidenceVersions(versions, next.evidence); offset += next.evidence.items.length;
            if (offset < next.evidence.total) versions.append(more);
            more.textContent = 'Load older evidence';
          } catch (error) {more.textContent = 'Couldn’t load older evidence. Retry';}
          finally {more.disabled = false;}
        }, 'evidence-more'); versions.append(more);
      }
      $('inspector-title').focus({preventScroll: true});
    } catch (error) {if (epoch === state.inspectEpoch) {$('inspector-title').textContent = 'Source evidence unavailable'; failure($('inspector-content'), error, () => openRecord(id, false));}}
  }
  function closeRecord(push = true) {
    ++state.inspectEpoch; state.job = null;
    if (push) updateURL();
    $('record-inspector').close(); document.body.classList.remove('inspector-open');
  }
  $('record-inspector').addEventListener('cancel', event => {event.preventDefault(); closeRecord();});
  $('close-inspector').addEventListener('click', () => closeRecord());
  $('record-source').addEventListener('change', event => selectSource(event.target.value));
  const compact = window.matchMedia('(max-width: 650px)');
  const auditSections = Object.fromEntries(Array.from($('audit-content').children, node => [node.classList[0], node]));
  function responsiveLayout() {
    // Reorder the existing sections, so reading and Tab order follow the display.
    // The controls and their values stay the same when the viewport changes.
    const focused = document.activeElement;
    const order = compact.matches
      ? ['collection-status', 'records-section', 'leads-section', 'flow-section', 'audit-detail-disclosure', 'history-section']
      : ['flow-section', 'collection-status', 'audit-detail-disclosure', 'records-section', 'leads-section', 'history-section'];
    order.forEach((name, index) => {
      const node = auditSections[name];
      if ($('audit-content').children[index] !== node) $('audit-content').insertBefore(node, $('audit-content').children[index]);
    });
    let focusTarget = focused;
    document.querySelectorAll('.responsive-disclosure').forEach(node => {
      node.open = !compact.matches;
      if (!node.open && node.contains(focused)) focusTarget = node.querySelector('summary');
    });
    if (focusTarget !== document.body && focusTarget?.isConnected && document.activeElement !== focusTarget) focusTarget.focus({preventScroll: true});
  }
  responsiveLayout(); compact.addEventListener('change', responsiveLayout);
  $('all-sources').addEventListener('click', () => selectSource(''));
  $('refresh-overview').addEventListener('click', () => {loadOverview(); scheduleRecords(0); loadLeads();});
  $('check-source').addEventListener('click', checkSource);
  $('pause-campaign').addEventListener('click', async () => {
    $('pause-campaign').disabled = true;
    $('campaign-feedback').textContent = 'Pausing paid collection…';
    try {await api('/api/campaign/pause',{method:'POST'}); $('campaign-feedback').textContent = 'Paid collection paused. Active runs are being stopped; obtained results will finish importing.'; await loadOverview();}
    catch (error) {$('campaign-feedback').textContent = error.message;}
    finally {$('pause-campaign').disabled = false;}
  });
  $('record-filters').addEventListener('submit', event => {event.preventDefault(); state.offset = 0; updateURL(); scheduleRecords(0);});
  $('record-query').addEventListener('input', () => {state.offset = 0; updateURL(true); scheduleRecords();});
  $('record-status').addEventListener('change', () => {state.offset = 0; updateURL(); scheduleRecords(0);});
  $('lead-filters').addEventListener('submit', event => {event.preventDefault(); loadLeads(true);});
  for (const id of ['lead-source', 'lead-scope']) $(id).addEventListener('change', () => loadLeads(true));
  for (const [id, step] of [['previous-leads', -20], ['next-leads', 20]]) $(id).addEventListener('click', () => {leadState.offset = Math.max(0, leadState.offset + step); loadLeads(); $('leads-heading').scrollIntoView({block: 'start'});});
  for (const [id, step] of [['previous-records', -20], ['next-records', 20]]) $(id).addEventListener('click', () => {state.offset = Math.max(0, state.offset + step); updateURL(); scheduleRecords(0); $('records-heading').scrollIntoView({block: 'start'});});
  window.addEventListener('popstate', () => {const job = readURL(); renderSelection(); scheduleRecords(0); if (job) openRecord(job, false); else closeRecord(false);});
  const initialJob = readURL(); loadOverview(); scheduleRecords(0); loadLeads(); if (initialJob) openRecord(initialJob, false);
})();
