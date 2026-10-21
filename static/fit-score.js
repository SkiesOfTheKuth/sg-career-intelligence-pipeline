/* Shared, evidence-first score presentation for the workspace and source inspector. */
(() => {
  'use strict';
  const el = (tag, text, cls) => {const node = document.createElement(tag); if (text !== undefined) node.textContent = text; if (cls) node.className = cls; return node;};
  function summary(job) {
    const score = job.assessment?.score;
    if (!score || score.value === null) return 'Fit score unavailable: review the source duties';
    return `Documented fit ${score.value}/100${score.provisional ? ' · provisional' : ''}${score.gates.length ? ' · required evidence missing' : ''}`;
  }
  function detail(job) {
    const root = el('div', undefined, 'fit-score'); const score = job.assessment?.score;
    root.append(el('p', summary(job), 'score-summary'));
    if (!score) return root;
    root.append(el('p', score.unavailable_reason || score.summary));
    root.append(el('p', 'This measures documented overlap, not your chance of getting hired. An unknown earns no points; it does not mean you lack the skill.', 'field-help'));
    if (score.gates.length) {
      const gates = el('div', undefined, 'notice warning'); gates.append(el('strong', 'Resolve these requirements first'));
      const list = el('ul'); for (const gate of score.gates) list.append(el('li', `${gate.reason} Source: “${gate.quote}”`)); gates.append(list); root.append(gates);
    }
    const breakdown = el('details'); breakdown.append(el('summary', 'How this score is calculated'));
    breakdown.append(el('p', score.method));
    for (const part of score.components) {
      const row = el('div', undefined, 'score-component');
      row.append(el('strong', `${part.label}: ${part.earned}/${part.maximum}`), el('p', part.basis));
      if (part.candidate_evidence) row.append(el('p', part.candidate_evidence, 'field-help'));
      breakdown.append(row);
    }
    if (score.value === null) breakdown.append(el('p', 'No total is published because the source is insufficient. Component readings below are preliminary.'));
    else breakdown.append(el('p', `Subtotal ${score.subtotal}/100. Final documented fit ${score.value}/100 after the limits below.`));
    for (const limit of score.limits) breakdown.append(el('p', `Maximum ${limit.maximum}: ${limit.reason}`, 'field-help'));
    breakdown.append(el('p', `${score.version}. Candidate evidence: ${score.candidate_source}.`, 'field-help'));
    root.append(breakdown);
    for (const [heading, rows, supportedLabel] of [['Compare responsibilities', score.duties, 'Documented overlap'], ['Check each mandatory requirement', score.requirements, 'Supported by CV'], ['Preferred requirements (no bonus points)', score.preferred, 'Supported by CV']]) {
      const group = el('details'); group.append(el('summary', `${heading} (${rows.length})`));
      if (!rows.length) group.append(el('p', 'Not clearly available in the retained source. Check the original listing.', 'field-help'));
      for (const row of rows) {
        const item = el('div', undefined, 'score-evidence');
        item.append(el('p', `“${row.quote}”`, 'score-quote'), el('strong', row.status === 'check' ? 'Needs your check' : supportedLabel), el('p', row.reason, 'field-help'));
        for (const fact of row.candidate_evidence) item.append(el('p', `CV: ${fact}`, 'field-help'));
        group.append(item);
      }
      root.append(group);
    }
    return root;
  }
  window.FitScore = {summary, detail};
})();
