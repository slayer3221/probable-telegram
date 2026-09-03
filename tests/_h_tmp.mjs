import { chromium } from 'playwright';
const b = await chromium.launch({ executablePath: '/opt/pw-browsers/chromium' });
const page = await b.newPage({ viewport: { width: 1280, height: 900 } });
await page.route(/fonts\.g(oogleapis|static)\.com/, r => r.abort());
await page.goto('http://127.0.0.1:8124/', { waitUntil: 'networkidle' });
await page.waitForTimeout(300);
console.log(JSON.stringify(await page.evaluate(() => ({
  exec: Math.round(document.getElementById('exec').getBoundingClientRect().height),
  signals: Math.round(document.querySelector('.signals').getBoundingClientRect().height),
  controlsTop: Math.round(document.getElementById('controls').getBoundingClientRect().top + window.scrollY),
}))));
await b.close();
