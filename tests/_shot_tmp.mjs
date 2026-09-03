import { chromium } from 'playwright';
const b = await chromium.launch({ executablePath: '/opt/pw-browsers/chromium' });
const out = '/tmp/claude-0/-home-user-probable-telegram/0e2912e4-fb8e-53eb-92a2-84ae09462a2f/scratchpad';
for (const [name, w] of [['desktop', 1280], ['mobile', 390]]) {
  const page = await b.newPage({ viewport: { width: w, height: 900 } });
  await page.route(/fonts\.g(oogleapis|static)\.com/, r => r.abort());
  await page.goto('http://127.0.0.1:8124/', { waitUntil: 'networkidle' });
  await page.waitForTimeout(400);
  const top = await page.evaluate(() => document.getElementById('exec').getBoundingClientRect().top + window.scrollY - 10);
  const bottom = await page.evaluate(() => document.querySelector('.signals').getBoundingClientRect().bottom + window.scrollY + 10);
  await page.screenshot({ path: `${out}/exec-${name}.png`, fullPage: true, clip: { x: 0, y: top, width: w, height: bottom - top } });
  console.log(name, 'exec+signals height', Math.round(bottom - top), 'controls top', Math.round(await page.evaluate(() => document.getElementById('controls').getBoundingClientRect().top + window.scrollY)));
  await page.close();
}
await b.close();
