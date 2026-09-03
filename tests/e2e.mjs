// Lightweight end-to-end checks against a local static server.
// Usage: node tests/e2e.mjs [baseUrl]   (default http://127.0.0.1:8123)
import { chromium } from 'playwright';
import path from 'node:path';
import fs from 'node:fs';

const BASE = process.argv[2] || 'http://127.0.0.1:8123';
// Data-aware: the dataset may be empty (before the first refresh) or live.
const positions = JSON.parse(fs.readFileSync('data/positions.json', 'utf8')).positions;
const perQuestion = {};
for (const p of positions) for (const q of p.question_ids) perQuestion[q] = (perQuestion[q] || 0) + 1;
const richest = Object.entries(perQuestion).sort((a, b) => b[1] - a[1])[0];
const HAS_DATA = positions.length > 0;
const Q = richest ? richest[0] : 'q1';
const SEC = richest ? (Object.entries(perQuestion).sort((a, b) => a[1] - b[1])[0][0]) : 'q2';
const editorial = JSON.parse(fs.readFileSync('editorial/vahana-read.json', 'utf8')).questions;
const gaps = JSON.parse(fs.readFileSync('data/gaps.json', 'utf8')).gaps;
const HAS_GAP_EXAMPLES = gaps.some((g) => g.examples.length > 0);
const stakeholders = [...new Set(positions.map((p) => p.commenter_id))];
const commenters = JSON.parse(fs.readFileSync('data/commenters.json', 'utf8')).commenters;
const firstType = commenters.find((c) => stakeholders.includes(c.id))?.stakeholder_type || 'health_system_provider';
const SHOTS = path.resolve('tests/screenshots');
fs.mkdirSync(SHOTS, { recursive: true });
let failures = 0;
const results = [];
function check(name, ok, detail = '') {
  results.push(`${ok ? 'PASS' : 'FAIL'} ${name}${detail ? ` — ${detail}` : ''}`);
  if (!ok) failures += 1;
}

const browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH || undefined });
const errors = [];
const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
const page = await context.newPage();
page.on('pageerror', (e) => errors.push(String(e)));
page.on('requestfailed', (r) => { if (!/fonts\.g(oogleapis|static)\.com/.test(r.url())) errors.push(`request failed: ${r.url()}`); });
page.on('console', (m) => { if (m.type() === 'error' && !/Failed to load resource/.test(m.text())) errors.push(m.text()); });

await page.goto(`${BASE}/index.html`, { waitUntil: 'networkidle' });
await page.waitForSelector('.q');
check('page renders 26 question cards', (await page.locator('.q').count()) === 26);
check('four signal cards', (await page.locator('.signal').count()) === 4);
check('six hero metrics', (await page.locator('.metric').count()) === 6);
check('nine gap cards', (await page.locator('.gap').count()) === 9);
check('four sections', (await page.locator('#tracker .section').count()) === 4);
check('no horizontal scroll desktop', await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth));
await page.screenshot({ path: `${SHOTS}/desktop.png`, fullPage: false });

// Accordion open/close via keyboard and mouse
const toggle = page.locator(`#${Q}-toggle`);
await toggle.click();
check('accordion opens', (await toggle.getAttribute('aria-expanded')) === 'true');
check('panel shows FDA question text', (await page.locator(`#${Q}-panel .q__fda`).innerText()).length > 40);
check(`hash updated to #${Q}`, page.url().endsWith(`#${Q}`));
if (HAS_DATA) check('panel shows commenter cards', (await page.locator(`#${Q}-panel .pc`).count()) >= 1);
if (HAS_DATA) {
  // One card per commenter per question; every position on the question appears as a point inside its commenter's card.
  const qPositions = positions.filter((p) => p.question_ids.includes(Q));
  const qCommenters = new Set(qPositions.map((p) => p.commenter_id));
  check('one card per commenter', (await page.locator(`#${Q}-panel .pc`).count()) === qCommenters.size);
  check('every position rendered as a point', (await page.locator(`#${Q}-panel .pc__point`).count()) === qPositions.length);
}
if (editorial[Q] && editorial[Q].tension) check('tension block rendered', (await page.locator(`#${Q}-panel .tension`).count()) === 1);
if (editorial[Q] && editorial[Q].vahana_read) check('vahana read rendered', (await page.locator(`#${Q}-panel .vahana`).count()) === 1);
check('no review/verification text', !(await page.content()).match(/human verified|ai classified|review status/i));
await page.screenshot({ path: `${SHOTS}/desktop-expanded.png`, fullPage: false });
await toggle.focus();
await page.keyboard.press('Enter');
check('accordion closes with Enter', (await toggle.getAttribute('aria-expanded')) === 'false');
check('focus retained on toggle after re-render', await page.evaluate((id) => document.activeElement && document.activeElement.id === id, `${Q}-toggle`));

if (HAS_DATA) {
  // Grouped card: a commenter with several distinct points on one question
const multi = (() => {
  const counts = {};
  for (const p of positions) for (const q of p.question_ids) { counts[q] = counts[q] || {}; counts[q][p.commenter_id] = (counts[q][p.commenter_id] || 0) + 1; }
  for (const q of Object.keys(counts)) for (const c of Object.keys(counts[q])) if (counts[q][c] > 1) return { q, c, n: counts[q][c] };
  return null;
})();
if (multi) {
  if (multi.q !== Q) { await page.locator(`#${multi.q}-toggle`).click(); await page.waitForTimeout(150); }
  const card = page.locator(`#${multi.q}-panel .pc[data-commenter="${multi.c}"]`);
  check('grouped card renders once', (await card.count()) === 1);
  check('grouped card lists each distinct point', (await card.locator('.pc__point').count()) === multi.n);
  check('grouped card announces point count', (await card.locator('.pc__type').innerText()).includes(`${multi.n} distinct points`));
  if (multi.q !== Q) await page.locator(`#${multi.q}-toggle`).click();
}

// Evidence drawer
  await toggle.click();
  const evidenceBtn = page.locator(`#${Q}-panel .pc button[data-action="evidence"]`).first();
  await evidenceBtn.click();
  check('evidence drawer opens', !(await page.locator('#evidence-drawer').isHidden()));
  check('evidence drawer has excerpt', (await page.locator('#evidence-drawer .evidence__quote').count()) === 1);
  check('evidence drawer has 5 meta rows', (await page.locator('#evidence-drawer .evidence__row').count()) === 5);
  check('evidence source link present', (await page.locator('#evidence-drawer a.evidence__link').getAttribute('href') || '').includes('regulations.gov'));
  check('focus moved into drawer', await page.evaluate(() => document.getElementById('evidence-drawer').contains(document.activeElement)));
  await page.keyboard.press('Escape');
  check('escape closes evidence drawer', await page.locator('#evidence-drawer').isHidden());
  check('focus returned to evidence button', await page.evaluate(() => document.activeElement && document.activeElement.dataset.action === 'evidence'));
  await toggle.click();
}

// Filters
const resultText = async () => page.locator('#result-line').innerText();
await page.locator(`#filter-rows .chip[data-key="stakeholder"][data-value="${firstType}"]`).click();
const afterStakeholder = await resultText();
check('stakeholder filter changes result line', /^\d+ questions? · \d+ positions?$/.test(afterStakeholder), afterStakeholder);
check('stakeholder filter in URL', page.url().includes('stakeholder='));
if (HAS_DATA) {
  await page.locator('#tracker .q__toggle').first().click();
  const types = await page.locator('#tracker .pc__type').allInnerTexts();
  check('visible commenters match the stakeholder filter', types.length > 0 && types.every((t) => t.split(' · ')[0] === types[0].split(' · ')[0]), types.join(' / '));
}
await page.locator('#filter-rows .chip[data-key="position"][data-value="support_with_modification"]').click();
check('position filter in URL', page.url().includes('position=modify'));
const badges = await page.locator('#tracker .badge').allInnerTexts();
check('combined filter shows only modify badges', badges.every((b) => b === 'Support with modification'));
await page.locator('#filter-rows .chip[data-key="theme"][data-value="postmarket"]').click();
check('theme filter in URL', page.url().includes('theme=postmarket'));
check('theme filter shows one section', (await page.locator('#tracker .section').count()) === 1);
await page.locator('.controls [data-action="reset"]').click();
check('reset restores 26 questions', (await resultText()).startsWith('26 questions'));
check('reset clears URL', !page.url().includes('?'));

// Search
await page.fill('#search', 'zzzz-no-match');
await page.waitForTimeout(300);
check('empty state renders', (await page.locator('.empty-state').count()) === 1);
await page.fill('#search', '');
await page.waitForTimeout(300);

// Views
await page.locator('.view-btn[data-view="tensions"]').click();
check('tensions view shows only questions with tension blocks', (await page.locator('.q').count()) === (await page.locator('.q__preview').count()));
await page.locator('.view-btn[data-view="missed"]').click();
check('missed view hides tracker', await page.locator('#tracker').isHidden());
check('missed view keeps gaps visible', await page.locator('#gaps').isVisible());
if (await page.locator('#gaps .gap__links button').count()) {
  await page.locator('#gaps .gap__links button').first().click();
  check('gap link jumps back to questions view', (await page.locator('.view-btn[data-view="questions"]').getAttribute('aria-pressed')) === 'true');
  check('gap link opens target question', (await page.locator('.q[data-open="true"]').count()) >= 1);
} else {
  await page.locator('.view-btn[data-view="questions"]').click();
}
if (HAS_GAP_EXAMPLES) {
  await page.locator('.view-btn[data-view="missed"]').click();
  await page.locator('#gaps .gap__source button').first().click();
  check('gap example opens evidence drawer', !(await page.locator('#evidence-drawer').isHidden()));
  await page.locator('#evidence-close').click();
}

// Deep links
await page.goto(`${BASE}/index.html?q=24`, { waitUntil: 'networkidle' });
await page.waitForSelector('#q24-panel:not([hidden])');
check('?q=24 expands question', (await page.locator('#q24-toggle').getAttribute('aria-expanded')) === 'true');
await page.waitForTimeout(600);
const q24Top = await page.evaluate(() => document.getElementById('q24').getBoundingClientRect().top);
check('?q=24 scrolls to question', q24Top > 0 && q24Top < 300, `top=${Math.round(q24Top)}`);
await page.goto(`${BASE}/index.html#q13`, { waitUntil: 'networkidle' });
await page.waitForSelector('#q13-panel:not([hidden])');
check('#q13 expands question', true);
await page.goto(`${BASE}/index.html?stakeholder=health-systems&theme=postmarket&position=modify`, { waitUntil: 'networkidle' });
await page.waitForSelector('.controls');
check('filter URL restores stakeholder chip', (await page.locator('#filter-rows .chip[data-value="health_system_provider"]').getAttribute('aria-pressed')) === 'true');
check('filter URL restores theme chip', (await page.locator('#filter-rows .chip[data-value="postmarket"]').getAttribute('aria-pressed')) === 'true');
check('filter URL restores position chip', (await page.locator('#filter-rows .chip[data-value="support_with_modification"]').getAttribute('aria-pressed')) === 'true');

// External links
await page.goto(`${BASE}/index.html`, { waitUntil: 'networkidle' });
const hrefs = await page.locator('#hero-links a').evaluateAll((as) => as.map((a) => a.href));
check('hero links to FDA paper and docket', hrefs.some((h) => h.includes('fda.gov')) && hrefs.some((h) => h.includes('regulations.gov')));
check('methodology copy present', (await page.locator('#methodology').innerText()).includes('The underlying public submission is authoritative.'));

// Tablet
await page.setViewportSize({ width: 820, height: 1100 });
await page.waitForTimeout(200);
check('no horizontal scroll tablet', await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth));
await page.screenshot({ path: `${SHOTS}/tablet.png` });

// Mobile
await page.setViewportSize({ width: 390, height: 844 });
await page.waitForTimeout(200);
check('no horizontal scroll mobile', await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth));
check('filter rows hidden on mobile', await page.locator('#filter-rows').isHidden());
await page.locator('#filter-toggle').click();
check('mobile filter drawer opens', !(await page.locator('#filter-drawer').isHidden()));
await page.locator('#filter-drawer .chip[data-key="stakeholder"][data-value="academic_research"]').click();
check('drawer chip applies filter', page.url().includes('stakeholder=researchers'));
await page.locator('#filter-drawer .chip[data-key="stakeholder"][data-value="all"]').click();
await page.locator('#filter-drawer [data-action="close-filters"]').first().click();
check('mobile filter drawer closes', await page.locator('#filter-drawer').isHidden());
await page.screenshot({ path: `${SHOTS}/mobile.png` });
await page.locator('.q__toggle').first().click();
await page.waitForTimeout(200);
check('no horizontal scroll mobile expanded', await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth));
await page.screenshot({ path: `${SHOTS}/mobile-expanded.png` });

check('no console/page errors', errors.length === 0, errors.join(' | '));
await browser.close();
console.log(results.join('\n'));
console.log(failures ? `\n${failures} check(s) failed` : '\nAll checks passed');
process.exit(failures ? 1 : 0);
