/* The regional-usage questionnaire records answers and exports them with evidence fingerprints. */
const assert = require('node:assert/strict');
const path = require('node:path');
const {pathToFileURL} = require('node:url');
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright');

async function main() {
  const browser = await chromium.launch({headless:true, ...(process.env.CHROMIUM_EXECUTABLE ? {executablePath:process.env.CHROMIUM_EXECUTABLE} : {})});
  const errors = [];
  try {
    for (const viewport of [{width:1280,height:900}, {width:390,height:800}]) {
      const context = await browser.newContext({viewport});
      const page = await context.newPage();
      page.on('pageerror', e => errors.push(e.message));
      await page.goto(pathToFileURL(path.join(__dirname, '../reports/glossary-regional-review.html')).href);
      const total = Number(await page.locator('#total').textContent());
      assert.ok(total > 0);
      assert.equal(await page.locator('article.card').count(), total);
      assert.ok(await page.locator('.form.flag').count() >= total);
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
      await page.locator('article.card').first().locator('input[value="block"]').check();
      await page.locator('article.card').first().locator('textarea').fill('測試備註');
      assert.equal(await page.locator('#answered').textContent(), '1');
      const exported = JSON.parse(await page.locator('#export-text').inputValue());
      assert.equal(exported.answers.length, 1);
      assert.equal(exported.answers[0].choice, 'block');
      assert.equal(exported.answers[0].note, '測試備註');
      assert.ok(exported.answers[0].blocked_forms.length > 0);
      assert.ok(Object.keys(exported.answers[0].fingerprints).length > 0);
      await page.reload();
      assert.equal(await page.locator('#answered').textContent(), '1');
      await context.close();
    }
  } finally {
    await browser.close();
  }
  assert.deepEqual(errors, []);
  console.log('glossary review UI passed (desktop and mobile)');
}
main().catch(e => { console.error(e); process.exit(1); });
