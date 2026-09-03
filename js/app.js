// Bootstrap: load static JSON, own state and DOM, wire interactions.
import { DEFAULT_STATE, buildIndex, buildUrl, computeView, parseLocation } from './filters.js';
import {
  renderEvidence, renderExecutive, renderFilterGroups, renderFraming, renderGaps, renderLenses, renderMetrics,
  renderSections, renderSignals, renderVahanaLinks, renderViews, resultLine,
} from './tracker.js';

const DATA_FILES = {
  questions: 'data/questions.json',
  commenters: 'data/commenters.json',
  submissions: 'data/submissions.json',
  positions: 'data/positions.json',
  gaps: 'data/gaps.json',
  summary: 'data/site-summary.json',
  editorial: 'editorial/vahana-read.json',
  executive: 'editorial/executive-read.json',
};

const $ = (id) => document.getElementById(id);
const el = {
  metrics: $('metrics'), heroNote: $('hero-note'), heroLinks: $('hero-links'), heroKicker: $('hero-kicker'),
  execFraming: $('exec-framing'), execList: $('exec-list'), lenses: $('lenses'), vahanaLinks: $('vahana-links'),
  signals: $('signals'), views: $('views'), search: $('search'), filterRows: $('filter-rows'),
  resultLine: $('result-line'), tracker: $('tracker'), gaps: $('gaps'), gapsGrid: $('gaps-grid'),
  methodNote: $('method-note'), filterDrawer: $('filter-drawer'), filterDrawerGroups: $('filter-drawer-groups'),
  evidenceDrawer: $('evidence-drawer'), evidencePanel: $('evidence-panel'), controls: $('controls'),
};

let index = null;
let state = { ...DEFAULT_STATE };
const openSet = new Set();
let lastOpened = null;
let drawerReturnFocus = null;

async function loadJson(path) {
  const res = await fetch(path, { cache: 'no-cache' });
  if (!res.ok) throw new Error(`${path}: ${res.status}`);
  return res.json();
}

async function loadData() {
  const entries = await Promise.all(Object.entries(DATA_FILES).map(async ([key, path]) => [key, await loadJson(path)]));
  const raw = Object.fromEntries(entries);
  return buildIndex({
    questions: raw.questions.questions,
    questionSource: raw.questions.source,
    commenters: raw.commenters.commenters,
    submissions: raw.submissions.submissions,
    positions: raw.positions.positions,
    gaps: raw.gaps.gaps,
    summary: raw.summary,
    editorial: raw.editorial,
    executive: raw.executive,
  });
}

function stickyOffset() {
  return (el.controls ? el.controls.getBoundingClientRect().height : 0) + 24;
}

function scrollToQuestion(qid) {
  const target = document.getElementById(qid);
  if (!target) return;
  const top = target.getBoundingClientRect().top + window.scrollY - stickyOffset();
  window.scrollTo({ top, behavior: 'smooth' });
}

function syncUrl() {
  const url = buildUrl(state, lastOpened && openSet.has(lastOpened) ? Number(lastOpened.replace('q', '')) : null);
  history.replaceState(null, '', url);
}

function renderStatic() {
  const s = index.summary;
  el.metrics.innerHTML = renderMetrics(s);
  el.signals.innerHTML = renderSignals(s.signals || []);
  el.execFraming.innerHTML = renderFraming(s);
  el.execList.innerHTML = renderExecutive(index);
  el.lenses.innerHTML = renderLenses(index);
  el.vahanaLinks.innerHTML = renderVahanaLinks(index);
  const docket = s.docket || {};
  if (docket.docket_id) el.heroKicker.textContent = `Public comment tracker · Docket ${docket.docket_id}`;
  const paper = el.heroLinks.querySelector('[data-link="paper"]');
  const docketLink = el.heroLinks.querySelector('[data-link="docket"]');
  if (paper && docket.discussion_paper_url) paper.href = docket.discussion_paper_url;
  if (docketLink && docket.docket_url) docketLink.href = docket.docket_url;
  const synthetic = s.dataset_kind === 'synthetic';
  el.heroNote.hidden = !synthetic;
  el.heroNote.textContent = synthetic ? 'Demo data · synthetic' : '';
  el.methodNote.textContent = synthetic
    ? `Demonstration dataset · all commenters and excerpts are synthetic · updated ${s.metrics.last_updated}`
    : `Source: Regulations.gov docket ${docket.docket_id} · updated ${s.metrics.last_updated}`;
  el.gapsGrid.innerHTML = renderGaps(index);
  el.search.value = state.search;
}

function renderControls() {
  el.views.innerHTML = renderViews(state);
  const groups = renderFilterGroups(state);
  el.filterRows.innerHTML = groups;
  el.filterDrawerGroups.innerHTML = groups;
  if (el.search.value !== state.search) el.search.value = state.search;
}

function render(focusId) {
  const view = computeView(index, state);
  renderControls();
  el.tracker.innerHTML = renderSections(index, view, state, openSet);
  el.tracker.hidden = state.view === 'missed';
  el.resultLine.textContent = resultLine(view, state);
  syncUrl();
  if (focusId) {
    const target = document.getElementById(focusId);
    if (target) target.focus({ preventScroll: true });
  }
}

function setState(patch) {
  state = { ...state, ...patch };
  render();
}

function toggleQuestion(qid, { forceOpen = false, scroll = false } = {}) {
  const willOpen = forceOpen || !openSet.has(qid);
  if (willOpen) { openSet.add(qid); lastOpened = qid; } else { openSet.delete(qid); if (lastOpened === qid) lastOpened = null; }
  render(`${qid}-toggle`);
  if (scroll) requestAnimationFrame(() => scrollToQuestion(qid));
}

function jumpToQuestion(qid) {
  const question = index.questionsById[qid];
  if (!question) return;
  const patch = {};
  if (state.view === 'missed') patch.view = 'questions';
  if (state.view === 'tensions') {
    const row = computeView(index, { ...state, ...patch }).visible.find((r) => r.q.id === qid);
    if (!row) patch.view = 'questions';
  }
  if (state.theme !== 'all' && state.theme !== question.theme) patch.theme = 'all';
  // If active filters hide this question, clear them so the jump lands somewhere visible.
  const probe = computeView(index, { ...state, ...patch });
  if (!probe.visible.some((r) => r.q.id === qid)) Object.assign(patch, { stakeholder: 'all', position: 'all', search: '' });
  state = { ...state, ...patch };
  toggleQuestion(qid, { forceOpen: true, scroll: true });
}

// Drawers ---------------------------------------------------------------
const FOCUSABLE = 'a[href], button:not([disabled]), input, select, textarea, [tabindex]:not([tabindex="-1"])';

function openDrawer(backdrop, opener) {
  drawerReturnFocus = opener || document.activeElement;
  backdrop.hidden = false;
  document.body.classList.add('drawer-open');
  const first = backdrop.querySelector(FOCUSABLE);
  if (first) first.focus();
}

function closeDrawers() {
  let closed = false;
  for (const d of [el.evidenceDrawer, el.filterDrawer]) {
    if (!d.hidden) { d.hidden = true; closed = true; }
  }
  if (!closed) return;
  document.body.classList.remove('drawer-open');
  if (drawerReturnFocus && document.contains(drawerReturnFocus)) drawerReturnFocus.focus({ preventScroll: true });
  drawerReturnFocus = null;
}

function openEvidence(positionId, qid, opener) {
  const position = index.positionsById[positionId];
  if (!position) return;
  el.evidencePanel.innerHTML = renderEvidence(index, position, qid || position.question_ids[0]);
  openDrawer(el.evidenceDrawer, opener);
}

function trapFocus(event) {
  const open = [el.evidenceDrawer, el.filterDrawer].find((d) => !d.hidden);
  if (!open) return;
  if (event.key === 'Escape') { event.preventDefault(); closeDrawers(); return; }
  if (event.key !== 'Tab') return;
  const items = Array.from(open.querySelectorAll(FOCUSABLE));
  if (!items.length) return;
  const first = items[0];
  const last = items[items.length - 1];
  if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
  else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
}

// Events ----------------------------------------------------------------
function onClick(event) {
  const stop = event.target.closest('[data-stop]');
  const actionEl = event.target.closest('[data-action]');
  if (!actionEl) return;
  // Clicks inside a drawer panel must not trigger the backdrop's close action.
  if (stop && !stop.contains(actionEl)) return;
  if (stop && actionEl.contains(stop)) return;
  const { action } = actionEl.dataset;
  switch (action) {
    case 'toggle': toggleQuestion(actionEl.dataset.q); break;
    case 'jump': jumpToQuestion(actionEl.dataset.q); break;
    case 'view': {
      setState({ view: actionEl.dataset.view });
      if (actionEl.dataset.view === 'missed') requestAnimationFrame(() => {
        const top = el.gaps.getBoundingClientRect().top + window.scrollY - stickyOffset();
        window.scrollTo({ top, behavior: 'smooth' });
      });
      break;
    }
    case 'filter': setState({ [actionEl.dataset.key]: actionEl.dataset.value }); break;
    case 'reset': setState({ theme: 'all', stakeholder: 'all', position: 'all', search: '' }); break;
    case 'open-filters': openDrawer(el.filterDrawer, actionEl); break;
    case 'close-filters': case 'close-evidence': closeDrawers(); break;
    case 'evidence': openEvidence(actionEl.dataset.position, actionEl.dataset.q, actionEl); break;
    default: break;
  }
}

let searchTimer = null;
function onSearch(event) {
  clearTimeout(searchTimer);
  const value = event.target.value;
  searchTimer = setTimeout(() => setState({ search: value }), 120);
}

function applyDeepLink(openQuestion) {
  if (!openQuestion) return;
  const qid = `q${openQuestion}`;
  if (!index.questionsById[qid]) return;
  openSet.add(qid);
  lastOpened = qid;
  render();
  setTimeout(() => scrollToQuestion(qid), 250);
}

async function init() {
  const parsed = parseLocation(window.location);
  state = parsed.state;
  try {
    index = await loadData();
  } catch (err) {
    el.tracker.innerHTML = `<p class="status" role="alert">The docket data could not be loaded (${err.message}). If you opened this file directly, serve it over HTTP: <code>python3 -m http.server</code>.</p>`;
    return;
  }
  renderStatic();
  render();
  applyDeepLink(parsed.openQuestion);
  document.addEventListener('click', onClick);
  document.addEventListener('keydown', trapFocus);
  el.search.addEventListener('input', onSearch);
  window.addEventListener('hashchange', () => {
    const { openQuestion } = parseLocation(window.location);
    if (openQuestion && !openSet.has(`q${openQuestion}`)) applyDeepLink(openQuestion);
  });
}

init();
