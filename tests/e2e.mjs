// Lightweight end-to-end checks against a local static server.
// Usage: node tests/e2e.mjs [baseUrl]   (default http://127.0.0.1:8123)
import { chromium } from 'playwright';
import path from 'node:path';
import fs from 'node:fs';

const BASE = process.argv[2] || 'http://127.0.0.1:8123';
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
const toggle = page.locator('#q19-toggle');
await toggle.click();
check('accordion opens', (await toggle.getAttribute('aria-expanded')) === 'true');
check('panel shows commenter cards', (await page.locator('#q19-panel .pc').count()) >= 5);
check('hash updated to #q19', page.url().endsWith('#q19'));
check('tension block rendered for q19', (await page.locator('#q19-panel .tension').count()) === 1);
check('vahana read rendered for q19', (await page.locator('#q19-panel .vahana').count()) === 1);
check('no review/verification text', !(await page.content()).match(/human verified|ai classified|review status/i));
await page.screenshot({ path: `${SHOTS}/desktop-expanded.png`, fullPage: false });
await page.locator('#q19-toggle').focus();
await page.keyboard.press('Enter');
check('accordion closes with Enter', (await page.locator('#q19-toggle').getAttribute('aria-expanded')) === 'false');
check('focus retained on toggle after re-render', await page.evaluate(() => document.activeElement && document.activeElement.id === 'q19-toggle'));

// Evidence drawer
await page.locator('#q7-toggle').click();
const evidenceBtn = page.locator('#q7-panel .pc button[data-action="evidence"]').first();
await evidenceBtn.click();
check('evidence drawer opens', !(await page.locator('#evidence-drawer').isHidden()));
check('evidence drawer has excerpt', (await page.locator('#evidence-drawer .evidence__quote').count()) === 1);
check('evidence drawer has 5 meta rows', (await page.locator('#evidence-drawer .evidence__row').count()) === 5);
check('evidence source link present', (await page.locator('#evidence-drawer a.evidence__link').getAttribute('href') || '').includes('regulations.gov'));
check('focus moved into drawer', await page.evaluate(() => document.getElementById('evidence-drawer').contains(document.activeElement)));
await page.keyboard.press('Escape');
check('escape closes evidence drawer', await page.locator('#evidence-drawer').isHidden());
check('focus returned to evidence button', await page.evaluate(() => document.activeElement && document.activeElement.dataset.action === 'evidence'));

// Filters
const resultText = async () => page.locator('#result-line').innerText();
await page.locator('#filter-rows .chip[data-key="stakeholder"][data-value="health_system_provider"]').click();
const afterStakeholder = await resultText();
check('stakeholder filter narrows results', /^\d+ questions? · \d+ positions?$/.test(afterStakeholder) && !afterStakeholder.startsWith('26 '), afterStakeholder);
check('stakeholder filter in URL', page.url().includes('stakeholder=health-systems'));
await page.locator('#tracker .q__toggle').first().click();
const badTypes = await page.locator('#tracker .pc__type').allInnerTexts();
check('all visible commenters are health systems', badTypes.length > 0 && badTypes.every((t) => t.startsWith('Health Systems')), badTypes.join(' / '));
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
await page.fill('#search', 'telemetry');
await page.waitForTimeout(300);
const searchResult = await resultText();
check('search narrows', !searchResult.startsWith('26 '), searchResult);
await page.fill('#search', 'zzzz-no-match');
await page.waitForTimeout(300);
check('empty state renders', (await page.locator('.empty-state').count()) === 1);
await page.fill('#search', '');
await page.waitForTimeout(300);

// Views
await page.locator('.view-btn[data-view="tensions"]').click();
check('tensions view shows previews', (await page.locator('.q__preview').count()) > 0);
check('tensions view only questions with tension', (await page.locator('.q').count()) === (await page.locator('.q__preview').count()));
await page.locator('.view-btn[data-view="missed"]').click();
check('missed view hides tracker', await page.locator('#tracker').isHidden());
check('missed view keeps gaps visible', await page.locator('#gaps').isVisible());
await page.locator('#gaps .gap__links button').first().click();
check('gap link jumps back to questions view', (await page.locator('.view-btn[data-view="questions"]').getAttribute('aria-pressed')) === 'true');
check('gap link opens target question', (await page.locator('.q[data-open="true"]').count()) >= 1);
await page.locator('#gaps .gap__source button').first().click();
check('gap example opens evidence drawer', !(await page.locator('#evidence-drawer').isHidden()));
await page.locator('#evidence-close').click();

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
await page.waitForSelector('.q');
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
