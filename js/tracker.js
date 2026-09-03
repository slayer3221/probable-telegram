// Rendering. Every function returns an HTML string; app.js owns the DOM.
import {
  GAPS, POSITIONS, POSITION_BY_ID, STAKEHOLDERS, STAKEHOLDER_BY_ID, THEMES, THEME_BY_ID,
  VAHANA_FIELDS, VIEWS, gapLabel, issueLabel, positionLabel, stakeholderLabel,
} from './taxonomies.js';

export function esc(value) {
  return String(value ?? '')
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

const qnum = (qid) => Number(String(qid).replace(/^q/, ''));
const qcode = (qid) => `Q${qnum(qid)}`;
const plural = (n, word) => `${n} ${word}${n === 1 ? '' : 's'}`;

function formatDate(iso) {
  if (!iso) return '';
  const [y, m, d] = iso.split('-').map(Number);
  if (!y || !m || !d) return iso;
  const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  return `${months[m - 1]} ${d}, ${y}`;
}

export function renderMetrics(summary) {
  const m = summary.metrics;
  const cell = (value, label, cls = '') =>
    `<div class="metric"><dd class="metric__value ${cls}">${esc(value)}</dd><dt class="metric__label">${esc(label)}</dt></div>`;
  return [
    cell(m.comments_analyzed, 'Comments analyzed'),
    cell(m.commenters_represented, 'Commenters represented'),
    cell(m.positions_identified, 'Positions identified'),
    cell(m.questions_tracked, 'FDA questions tracked', 'metric__value--brand'),
    cell(formatDate(m.comment_deadline), 'Comment deadline', 'metric__value--text'),
    cell(formatDate(m.last_updated), 'Last updated', 'metric__value--text'),
  ].join('');
}

export function renderSignals(signals) {
  return signals.map((s) => `
    <button class="signal" type="button" data-action="jump" data-q="${esc(s.target_question_id)}">
      <span class="signal__label">${esc(s.label)}</span>
      <span class="signal__headline">${esc(s.headline)}</span>
      <span class="signal__detail">${esc(s.detail)}</span>
      <span class="signal__evidence">${esc(s.evidence)}</span>
    </button>`).join('');
}

// Executive layer. Copy comes from editorial/executive-read.json; counts come
// from the live site summary so the framing never carries a stale number.
export function renderFraming(summary) {
  const m = summary.metrics || {};
  if (!m.positions_identified) {
    return 'This is not a yes/no docket. Once public submissions are classified, this line reports how many distinct positions, recommendations and concerns they contain across FDA\u2019s 26 questions.';
  }
  return `This is not a yes/no docket. ${esc(m.commenters_represented)} commenters have put <strong>${esc(m.positions_identified)} distinct positions</strong> on the record across FDA\u2019s ${esc(m.questions_tracked)} questions. So far, the argument is mostly over terms, not direction.`;
}

function questionLinks(qids, index) {
  return qids.filter((qid) => index.questionsById[qid]).map((qid) =>
    `<button class="btn-outline btn-outline--tiny" type="button" data-action="jump" data-q="${esc(qid)}" title="${esc(index.questionsById[qid].short_title)}">${qcode(qid)}</button>`).join('');
}

export function renderExecutive(index) {
  const takeaways = (index.executive && index.executive.takeaways) || [];
  return takeaways.map((t, i) => `
    <li class="exec__item" id="exec-${esc(t.id)}">
      <span class="exec__num" aria-hidden="true">${String(i + 1).padStart(2, '0')}</span>
      <h3>${esc(t.title)}</h3>
      <p class="exec__text">${esc(t.text)}</p>
      <div class="exec__links"><span class="label">Drawn from</span> ${questionLinks(t.question_ids || [], index)}</div>
    </li>`).join('');
}

export function renderLenses(index) {
  const lenses = (index.executive && index.executive.lenses) || [];
  return lenses.map((l) => `
    <div class="lens" id="lens-${esc(l.id)}">
      <div class="lens__role">${esc(l.role)}</div>
      <p class="lens__q">${esc(l.question)}</p>
      <ul class="lens__themes">${(l.themes || []).map((t) => `<li>${esc(t)}</li>`).join('')}</ul>
    </div>`).join('');
}

export function renderVahanaLinks(index) {
  const qids = Object.keys((index.editorial && index.editorial.questions) || {})
    .filter((qid) => index.questionsById[qid] && index.editorial.questions[qid].vahana_read)
    .sort((a, b) => qnum(a) - qnum(b));
  if (!qids.length) return '';
  return `<span>Vahana commercialization and deployment reads on</span> ${questionLinks(qids, index)}`;
}

export function renderViews(state) {
  return VIEWS.map((v) => `
    <button class="view-btn" type="button" data-action="view" data-view="${v.id}" aria-pressed="${state.view === v.id}">${esc(v.label)}</button>`).join('');
}

function chip(key, value, label, active) {
  return `<button class="chip" type="button" data-action="filter" data-key="${key}" data-value="${esc(value)}" aria-pressed="${active}">${esc(label)}</button>`;
}

export function renderFilterGroups(state) {
  const groups = [
    { label: 'Theme', key: 'theme', options: [['all', 'All'], ...THEMES.map((t) => [t.id, t.filterLabel])] },
    { label: 'Stakeholder', key: 'stakeholder', options: [['all', 'All'], ...STAKEHOLDERS.map((s) => [s.id, s.label])] },
    { label: 'Position', key: 'position', options: [['all', 'All'], ...POSITIONS.map((p) => [p.id, p.filterLabel])] },
  ];
  return groups.map((g) => `
    <div class="filter-group" role="group" aria-label="${esc(g.label)}">
      <span class="filter-group__label">${esc(g.label)}</span>
      <div class="chips">${g.options.map(([v, l]) => chip(g.key, v, l, state[g.key] === v)).join('')}</div>
    </div>`).join('');
}

function mixLine(byType) {
  return STAKEHOLDERS.filter((s) => byType[s.id]).map((s) => `${byType[s.id]} ${s.label}`).join(' · ');
}

function positionCounts(byPosition) {
  return POSITIONS.filter((p) => byPosition[p.id]).map((p) => `
    <span class="pos-count"><i class="pos-dot" style="background:var(${p.cssVar})" aria-hidden="true"></i>${esc(p.short)} ${byPosition[p.id]}</span>`).join('');
}

function tagList(tags, cls = 'tag') {
  return tags.filter(Boolean).map((t) => `<span class="${cls}">${esc(t)}</span>`).join('');
}

function renderPoint(p, qid, showBadge) {
  const s = p._submission;
  const tags = [issueLabel(p.primary_issue), issueLabel(p.secondary_issue), ...(p.gap_tags || []).map(gapLabel)];
  const otherQs = p.question_ids.filter((x) => x !== qid).map(qcode);
  const meta = otherQs.length ? `<span class="pc__point-meta">Also addresses ${esc(otherQs.join(', '))}</span>` : '';
  const head = showBadge || meta
    ? `<div class="pc__point-head">${showBadge ? `<span class="badge badge--${esc(p.position)}">${esc(positionLabel(p.position))}</span>` : ''}${meta}</div>`
    : '';
  return `
      <li class="pc__point" id="${esc(p.id)}-${esc(qid)}">
        ${head}
        <p class="pc__summary">${esc(p.public_summary)}</p>
        <div class="pc__grid">
          <div><span class="label">Main concern</span><div class="pc__text">${esc(p.stakeholder_concern)}</div></div>
          <div><span class="label">What they want FDA to do</span><div class="pc__text">${esc(p.requested_fda_action)}</div></div>
        </div>
        <div class="pc__foot">
          <div class="pc__tags">${tagList(tags)}</div>
          <div class="pc__actions">
            <button class="btn-outline" type="button" data-action="evidence" data-position="${esc(p.id)}" data-q="${esc(qid)}" aria-haspopup="dialog">View evidence</button>
            <a href="${esc(s.source_url)}" target="_blank" rel="noopener">Original comment ↗</a>
          </div>
        </div>
      </li>`;
}

// One card per commenter per question. A commenter who makes several distinct
// points on the same question gets one card with those points listed inside it.
function renderCommenterCard(positions, qid) {
  const c = positions[0]._commenter;
  const labels = POSITIONS.filter((pos) => positions.some((p) => p.position === pos.id));
  const multi = positions.length > 1;
  const typeLine = `${stakeholderLabel(c.stakeholder_type)}${multi ? ` · ${positions.length} distinct points on ${qcode(qid)}` : ''}`;
  const otherQs = multi ? [] : positions[0].question_ids.filter((x) => x !== qid).map(qcode);
  return `
    <article class="pc" id="${esc(c.id)}-${esc(qid)}" data-commenter="${esc(c.id)}" aria-label="${esc(c.display_name)} on ${qcode(qid)}">
      <div class="pc__head">
        <div>
          <div class="pc__org">${esc(c.display_name)}</div>
          <div class="pc__type">${esc(typeLine)}${otherQs.length ? ` · also addresses ${esc(otherQs.join(', '))}` : ''}</div>
        </div>
        <div class="pc__badges">${labels.map((pos) => `<span class="badge badge--${esc(pos.id)}">${esc(pos.label)}</span>`).join('')}</div>
      </div>
      <ol class="pc__points${multi ? ' pc__points--multi' : ''}">
        ${positions.map((p) => renderPoint(p, qid, labels.length > 1)).join('')}
      </ol>
    </article>`;
}

function groupByCommenter(positions) {
  const groups = new Map();
  for (const p of positions) {
    const cid = p._commenter.id;
    if (!groups.has(cid)) groups.set(cid, []);
    groups.get(cid).push(p);
  }
  return Array.from(groups.values());
}

function renderTension(editorial, row) {
  if (!row.hasTension) return '';
  const t = editorial.tension;
  return `
    <div class="tension">
      <span class="label">Where stakeholders differ</span>
      <div class="tension__grid">
        ${t.groups.map((g) => `<div class="tension__cell"><div class="tension__group">${esc(g.label)}</div><div class="tension__text">${esc(g.text)}</div></div>`).join('')}
      </div>
      <div class="tension__synth"><span class="label">The tension</span><p>${esc(t.synthesis)}</p></div>
    </div>`;
}

function renderVahana(editorial) {
  const read = editorial && editorial.vahana_read;
  if (!read) return '';
  const items = VAHANA_FIELDS.filter(([key]) => read[key] && read[key].trim());
  if (!items.length) return '';
  return `
    <aside class="vahana" aria-label="Vahana read, editorial interpretation">
      <div class="vahana__head">
        <span class="vahana__title">Vahana read</span>
        <span class="vahana__meta">Editorial interpretation · not a commenter position</span>
      </div>
      <dl class="vahana__list">
        ${items.map(([key, label]) => `<div class="vahana__item"><dt>${esc(label)}</dt><dd>${esc(read[key])}</dd></div>`).join('')}
      </dl>
    </aside>`;
}

function renderPanel(index, row) {
  const { q, shown, all, filtering } = row;
  const editorial = index.editorial.questions[q.id] || {};
  const n = q.question_number;
  const fda = q.question_text && q.question_text.trim()
    ? `<p class="q__fda editorial">${esc(q.question_text)}</p>`
    : `<p class="q__fda q__fda--pending">Exact question text is pending import from the FDA discussion paper. The tracker does not paraphrase FDA wording; read question ${n} at the source link below.</p>`;
  const about = q.about && q.about.trim()
    ? q.about
    : 'FDA is asking how existing device expectations translate to systems whose behavior is generated rather than fixed. Commenter positions below address that translation directly.';
  const shownLine = filtering
    ? `Showing ${shown.length} of ${all.length} under current filters`
    : `${plural(all.length, 'position')} from ${plural(row.allStats.distinctCommenters, 'commenter')}`;
  return `
    <span class="label">FDA asked</span>
    ${fda}
    <a class="q__sublink" href="${esc(q.source_url)}" target="_blank" rel="noopener">Discussion paper, question ${n} ↗</a>
    <span class="label label--gap">What this is really about</span>
    <p class="q__about">${esc(about)}</p>
    <div class="q__saying"><span class="label">What commenters are saying</span><span class="q__shown">${esc(shownLine)}</span></div>
    <div class="positions">
      ${shown.length ? groupByCommenter(shown).map((group) => renderCommenterCard(group, q.id)).join('') : '<p class="section__empty">No positions on this question match the current filters.</p>'}
    </div>
    ${renderTension(editorial, row)}
    ${renderVahana(editorial)}`;
}

export function renderQuestion(index, row, state, isOpen) {
  const { q, all, shown, filtering, allStats, shownStats } = row;
  const stats = filtering ? shownStats : allStats;
  const editorial = index.editorial.questions[q.id];
  const preview = state.view === 'tensions' && row.hasTension && editorial ? editorial.tension.synthesis : '';
  const countLine = filtering
    ? `${shownStats.distinctCommenters} of ${allStats.distinctCommenters} commenters`
    : plural(allStats.distinctCommenters, 'commenter');
  return `
    <article class="q" id="${esc(q.id)}" data-open="${isOpen}">
      <h3 class="visually-hidden">Question ${q.question_number}: ${esc(q.short_title)}</h3>
      <button class="q__toggle" type="button" id="${esc(q.id)}-toggle" data-action="toggle" data-q="${esc(q.id)}" aria-expanded="${isOpen}" aria-controls="${esc(q.id)}-panel">
        <div class="q__row">
          <span class="q__code" aria-hidden="true">Q${q.question_number}</span>
          <div class="q__body">
            <div class="q__titlerow">
              <span class="q__title">${esc(q.short_title)}</span>
              ${q.high_impact ? '<span class="q__impact">High-impact question</span>' : ''}
            </div>
            <p class="q__ask">${esc(q.summary_ask)}</p>
            <div class="q__counts">
              <span class="q__count">${esc(countLine)}</span>
              <span class="q__mix">${esc(mixLine(stats.byType))}</span>
            </div>
            <div class="q__positions" aria-label="Position distribution">${positionCounts(stats.byPosition)}</div>
            <div class="q__tags">${tagList(q.tags || [])}</div>
            ${preview ? `<p class="q__preview">${esc(preview)}</p>` : ''}
          </div>
          <span class="q__state" aria-hidden="true">${isOpen ? 'Collapse −' : 'Expand +'}</span>
        </div>
      </button>
      <div class="q__panel" id="${esc(q.id)}-panel" role="region" aria-labelledby="${esc(q.id)}-toggle" ${isOpen ? '' : 'hidden'}>
        ${isOpen ? renderPanel(index, row) : ''}
      </div>
    </article>`;
}

export function renderSections(index, view, state, openSet) {
  if (state.view === 'missed') return '';
  const themes = THEMES.filter((t) => state.theme === 'all' || t.id === state.theme);
  const sections = themes.map((t) => {
    const rows = view.visible.filter((r) => r.q.theme === t.id);
    return `
      <section class="section" id="section-${esc(t.slug)}" aria-labelledby="section-${esc(t.slug)}-title">
        <div class="section__head">
          <h2 id="section-${esc(t.slug)}-title">${esc(t.label)}</h2>
          <span class="section__meta">${esc(t.range)} · ${rows.length} shown</span>
        </div>
        <p class="section__blurb">${esc(t.blurb)}</p>
        ${rows.length
          ? rows.map((r) => renderQuestion(index, r, state, openSet.has(r.q.id))).join('')
          : '<p class="section__empty">No questions in this section match the current filters.</p>'}
      </section>`;
  });
  if (view.visible.length === 0) {
    const why = state.view === 'tensions'
      ? 'No question currently has enough comments from different stakeholder groups to show a tension block under these filters.'
      : 'No positions match the current filters.';
    return `<div class="empty-state" role="status">${esc(why)}<button class="btn-text" type="button" data-action="reset">Reset filters</button></div>${sections.join('')}`;
  }
  return sections.join('');
}

export function renderGaps(index) {
  const threshold = (index.summary.thresholds || {}).min_commenters_for_conclusion || 5;
  return index.gaps.map((g) => {
    const groups = g.stakeholder_types.map(stakeholderLabel);
    const stats = g.distinct_commenters >= threshold
      ? `${plural(g.question_ids.length, 'FDA question')} · ${g.distinct_commenters} commenters raising related concerns`
      : `${plural(g.question_ids.length, 'FDA question')} · Limited data: ${plural(g.distinct_commenters, 'commenter')} so far`;
    return `
      <article class="gap" id="gap-${esc(g.id)}">
        <h3 class="gap__title">${esc(g.title)}</h3>
        <p class="gap__body">${esc(g.explanation)}</p>
        <div class="gap__stats">${esc(stats)}</div>
        <div class="gap__groups">Raised by: ${groups.length ? esc(groups.join(' · ')) : 'no commenters yet'}</div>
        ${g.examples.length ? `<div class="gap__quotes">${g.examples.map((e) => `
          <div>
            <p class="gap__quote">“${esc(e.excerpt)}”</p>
            <div class="gap__source"><button type="button" data-action="evidence" data-position="${esc(e.position_id)}" data-q="${esc(e.question_id)}" aria-haspopup="dialog">${esc(e.display_name)} · ${qcode(e.question_id)}</button></div>
          </div>`).join('')}</div>` : ''}
        <div class="gap__links">${g.question_ids.map((qid) => `<button class="btn-outline btn-outline--tiny" type="button" data-action="jump" data-q="${esc(qid)}">${qcode(qid)}</button>`).join('')}</div>
      </article>`;
  }).join('');
}

export function renderEvidence(index, position, qid) {
  const c = position._commenter;
  const s = position._submission;
  const rows = [
    ['FDA question mapping', position.question_ids.map(qcode).join(', ')],
    ['Position classified', positionLabel(position.position)],
    ['Primary issue', issueLabel(position.primary_issue) || '—'],
    ['Submitted', s.received_date ? `${formatDate(s.received_date)} · Regulations.gov` : 'Regulations.gov'],
    ['Regulations.gov ID', s.regulations_gov_comment_id],
  ];
  return `
    <div class="drawer__head">
      <span class="label" id="evidence-title">Evidence</span>
      <button class="btn-plain" type="button" data-action="close-evidence" id="evidence-close">Close</button>
    </div>
    <h2 class="evidence__org">${esc(c.display_name)}</h2>
    <div class="evidence__type">${esc(stakeholderLabel(c.stakeholder_type))} · position on ${qcode(qid)}</div>
    <span class="label">Supporting excerpt</span>
    <blockquote class="evidence__quote">“${esc(position.supporting_text)}”</blockquote>
    <dl class="evidence__meta">
      ${rows.map(([k, v]) => `<div class="evidence__row"><dt>${esc(k)}</dt><dd>${esc(v)}</dd></div>`).join('')}
    </dl>
    <a class="evidence__link" href="${esc(s.source_url)}" target="_blank" rel="noopener">Open original submission on Regulations.gov ↗</a>
    <p class="evidence__disclaimer">This excerpt is the source basis for the interpretation shown on the tracker. Classifications and summaries are AI-assisted interpretations; the full submission is authoritative.</p>`;
}

export function resultLine(view, state) {
  if (state.view === 'missed') return `${Object.keys(GAPS).length} cross-cutting issues`;
  return `${plural(view.totalQuestions, 'question')} · ${plural(view.totalPositions, 'position')}`;
}
