import { chromium } from 'playwright';
const b = await chromium.launch({ executablePath: '/opt/pw-browsers/chromium' });
const page = await b.newPage({ viewport: { width: 390, height: 844 } });
await page.route(/fonts\.g(oogleapis|static)\.com/, r => r.abort());
await page.goto('http://127.0.0.1:8123/', { waitUntil: 'networkidle' });
await page.locator('.q__toggle').first().click();
await page.waitForTimeout(300);
console.log(JSON.stringify(await page.evaluate(() => {
  const out = [];
  for (const pc of document.querySelectorAll('.pc')) {
    const kids = [...pc.querySelectorAll('*')].filter(el => el.getBoundingClientRect().right > 391);
    if (kids.length) out.push({ id: pc.id, pcRight: Math.round(pc.getBoundingClientRect().right), pcDisplay: getComputedStyle(pc).display, kids: kids.map(el => [el.tagName, el.className, Math.round(el.getBoundingClientRect().left), Math.round(el.getBoundingClientRect().right), getComputedStyle(el.parentElement).gridTemplateColumns]) });
  }
  return out;
}), null, 1));
await b.close();
