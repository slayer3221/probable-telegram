// Filter state, URL serialization and matching rules.
import {
  POSITION_BY_ID, POSITION_BY_SLUG, STAKEHOLDER_BY_ID, STAKEHOLDER_BY_SLUG,
  THEME_BY_ID, THEME_BY_SLUG, VIEWS, issueLabel, gapLabel, responseTypeLabel,
} from './taxonomies.js';

export const DEFAULT_STATE = Object.freeze({
  view: 'questions', search: '', theme: 'all', stakeholder: 'all', position: 'all',
});

const VIEW_IDS = new Set(VIEWS.map((v) => v.id));

export function parseLocation(loc) {
  const params = new URLSearchParams(loc.search);
  const state = { ...DEFAULT_STATE };
  let openQuestion = null;

  const theme = params.get('theme');
  if (theme && THEME_BY_SLUG[theme]) state.theme = THEME_BY_SLUG[theme].id;
  const stakeholder = params.get('stakeholder');
  if (stakeholder && STAKEHOLDER_BY_SLUG[stakeholder]) state.stakeholder = STAKEHOLDER_BY_SLUG[stakeholder].id;
  const position = params.get('position');
  if (position && POSITION_BY_SLUG[position]) state.position = POSITION_BY_SLUG[position].id;
  const view = params.get('view');
  if (view && VIEW_IDS.has(view)) state.view = view;
  const search = params.get('search');
  if (search) state.search = search.slice(0, 120);

  const q = params.get('q');
  if (q && /^\d{1,2}$/.test(q)) openQuestion = Number(q);
  const hash = (loc.hash || '').match(/^#q(\d{1,2})$/i);
  if (hash) openQuestion = Number(hash[1]);
  if (openQuestion !== null && (openQuestion < 1 || openQuestion > 26)) openQuestion = null;
  return { state, openQuestion };
}

export function buildUrl(state, openQuestion) {
  const params = new URLSearchParams();
  if (state.view !== DEFAULT_STATE.view) params.set('view', state.view);
  if (state.theme !== 'all') params.set('theme', THEME_BY_ID[state.theme].slug);
  if (state.stakeholder !== 'all') params.set('stakeholder', STAKEHOLDER_BY_ID[state.stakeholder].slug);
  if (state.position !== 'all') params.set('position', POSITION_BY_ID[state.position].slug);
  if (state.search.trim()) params.set('search', state.search.trim());
  const query = params.toString();
  const hash = openQuestion ? `#q${openQuestion}` : '';
  return `${window.location.pathname}${query ? `?${query}` : ''}${hash}`;
}

export function isFiltering(state) {
  return state.stakeholder !== 'all' || state.position !== 'all' || state.search.trim() !== '';
}

export function buildIndex(data) {
  const commentersById = Object.fromEntries(data.commenters.map((c) => [c.id, c]));
  const submissionsById = Object.fromEntries(data.submissions.map((s) => [s.id, s]));
  const positionsById = Object.fromEntries(data.positions.map((p) => [p.id, p]));
  const positionsByQuestion = {};
  for (const q of data.questions) positionsByQuestion[q.id] = [];
  for (const p of data.positions) {
    const commenter = commentersById[p.commenter_id];
    const submission = submissionsById[p.submission_id];
    if (!commenter || !submission) continue;
    p._commenter = commenter;
    p._submission = submission;
    p._haystack = [
      commenter.display_name, commenter.organization,
      issueLabel(p.primary_issue), issueLabel(p.secondary_issue), responseTypeLabel(p.response_type),
      ...(p.gap_tags || []).map(gapLabel),
      p.public_summary,
    ].filter(Boolean).join(' ').toLowerCase();
    for (const qid of p.question_ids) {
      if (positionsByQuestion[qid]) positionsByQuestion[qid].push(p);
    }
  }
  const questionsById = Object.fromEntries(data.questions.map((q) => [q.id, q]));
  const analysesById = Object.fromEntries((data.analyses || []).map((a) => [a.question_id, a]));
  for (const q of data.questions) {
    q._haystack = `${q.short_title} ${(q.tags || []).join(' ')}`.toLowerCase();
  }
  return { ...data, commentersById, submissionsById, positionsById, positionsByQuestion, questionsById, analysesById };
}

export function positionMatches(state, position, question) {
  if (state.stakeholder !== 'all' && position._commenter.stakeholder_type !== state.stakeholder) return false;
  if (state.position !== 'all' && position.position !== state.position) return false;
  const term = state.search.trim().toLowerCase();
  if (term && !position._haystack.includes(term) && !question._haystack.includes(term)) return false;
  return true;
}

export function summarize(positions) {
  const commenters = new Set();
  const byType = {};
  const byPosition = {};
  for (const p of positions) {
    const cid = p._commenter.id;
    if (!commenters.has(cid)) {
      commenters.add(cid);
      const t = p._commenter.stakeholder_type;
      byType[t] = (byType[t] || 0) + 1;
    }
    byPosition[p.position] = (byPosition[p.position] || 0) + 1;
  }
  return { distinctCommenters: commenters.size, byType, byPosition, positions: positions.length };
}

export function tensionEligible(index, q, all) {
  const editorial = index.editorial.questions[q.id];
  if (!editorial || !editorial.tension) return false;
  const stats = summarize(all);
  const t = index.summary.thresholds || {};
  return stats.distinctCommenters >= (t.min_commenters_for_tension || 3)
    && Object.keys(stats.byType).length >= (t.min_groups_for_tension || 2);
}

export function computeView(index, state) {
  const filtering = isFiltering(state);
  const rows = index.questions.map((q) => {
    const all = index.positionsByQuestion[q.id] || [];
    const shown = filtering ? all.filter((p) => positionMatches(state, p, q)) : all;
    const hasTension = tensionEligible(index, q, all);
    return { q, all, shown, filtering, hasTension, allStats: summarize(all), shownStats: summarize(shown) };
  });
  const visible = rows.filter((r) => (state.theme === 'all' || r.q.theme === state.theme)
    && (!filtering || r.shown.length > 0)
    && (state.view !== 'tensions' || r.hasTension));
  // A position mapped to several questions is counted once.
  const distinct = new Set();
  for (const r of visible) for (const p of r.shown) distinct.add(p.id);
  return { rows, visible, filtering, totalQuestions: visible.length, totalPositions: distinct.size };
}
