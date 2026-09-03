import { chromium } from 'playwright';
const b = await chromium.launch({ executablePath: '/opt/pw-browsers/chromium' }); 
const page = await b.newPage({ viewport: { width: 390, height: 844 } });
await page.route(/fonts\.g(oogleapis|static)\.com/, r => r.abort());
await page.goto('http://127.0.0.1:8123/', { waitUntil: 'networkidle' });
await page.locator('.q__toggle').first().click();
await page.waitForTimeout(300);
const out = await page.evaluate(() => {
  const w = window.innerWidth; const res = [];
  for (const el of document.querySelectorAll('body *')) {
    const r = el.getBoundingClientRect();
    if (r.right > w + 1 && r.width < 5000) res.push({ tag: el.tagName, cls: el.className && String(el.className).slice(0,60), right: Math.round(r.right), text: (el.textContent||'').trim().slice(0,80) });
  }
  return { sw: document.documentElement.scrollWidth, w, res: res.slice(0, 12) };
});
console.log(JSON.stringify(out, null, 1));
await b.close();
