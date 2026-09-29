/* Focused review: exact scope, intact evidence, and portable answers. */
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const os = require('node:os');
const path = require('node:path');
const {pathToFileURL} = require('node:url');
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright');

async function main() {
  const temp = await fs.mkdtemp(path.join(os.tmpdir(), 'localization-human-only-test-'));
  const report = path.join(temp, 'review-human-only.html');
  await fs.copyFile(path.join(__dirname, '../reports/review-human-only.html'), report);
  const original = JSON.parse(await fs.readFile(path.join(__dirname, '../reports/screenshot-review.json'), 'utf8'));
  const browser = await chromium.launch({headless:true, ...(process.env.CHROMIUM_EXECUTABLE ? {executablePath:process.env.CHROMIUM_EXECUTABLE} : {})});
  const errors = [];
  const makePage = async () => {
    const context = await browser.newContext();
    const page = await context.newPage();
    page.on('pageerror', error => errors.push(error.message));
    return page;
  };
  const selectQuestion = async (page, id) => {
    await page.locator('#filter').selectOption('all');
    await page.locator(`[data-question="${id}"]`).click();
  };
  const exported = page => page.evaluate(() => exportBundle());
  try {
    const page = await makePage();
    await page.goto(pathToFileURL(report).href);
    assert.equal(await page.locator('#remaining-count').textContent(), '9');
    assert.equal(await page.locator('#answered-count').textContent(), '0');
    assert.equal(await page.locator('[data-reference-row]').count(), 58);
    assert.equal(await page.locator('#reference-panel').getAttribute('open'), null);
    assert.equal(await page.locator('[data-moe-entry]').count(), 65);
    assert.equal(await page.locator('input[name=choice]:checked').count(), 0);
    assert.equal(await page.locator('#reference-panel input[type=radio], #reference-panel input[type=checkbox]').count(), 0);
    const initial = await exported(page);
    const numbers = [2,6,7,10,12,33,63,64,67];
    assert.deepEqual(initial.questions.map(q => q.number), numbers);
    assert.equal(initial.questions.every(q => q.answer === null), true);
    assert.deepEqual(initial.screenshot_transcription, original);
    assert.equal(initial.human_decisions_applied, false);
    assert.equal(initial.reassessment.cases.every(c => c.human_decision === null), true);
    assert.deepEqual([...numbers, ...initial.reference_numbers].sort((a,b) => a-b), Array.from({length:67}, (_,i) => i+1));
    assert.equal(initial.screenshot_transcription.rows.filter(r => r.observed_checked_ids.length).length, 52);

    // Relevant full dictionary evidence, including synonyms, stays accessible.
    assert.ok((await page.locator('[data-reference-row="59"]').textContent()).includes('相似詞：[似]消息'));
    assert.ok((await page.locator('[data-reference-row="59"]').textContent()).includes('消息'));
    for (const q of initial.questions) {
      await selectQuestion(page, q.id);
      const displayed = await page.locator('#focus-evidence [data-source-id]').evaluateAll(nodes => nodes.map(n => n.dataset.sourceId));
      assert.deepEqual(displayed, q.focus_ids);
      assert.equal(await page.locator('input[name=choice]:checked').count(), 0);
    }
    await selectQuestion(page, 'row-33');
    assert.equal(await page.locator('#focus-evidence [data-source-id="microsoft:30904_1567776_1585134"]').count(), 0);
    await selectQuestion(page, 'row-6');
    const sourceLink = await page.locator('#focus-evidence a').getAttribute('href');
    assert.match(sourceLink, /^https:\/\/learn\.microsoft\.com\//);

    // No answer is inferred from a note or an empty custom response.
    await selectQuestion(page, 'row-2');
    await page.locator('input[value="retain-context"]').check();
    const note = 'Synthetic: </script><script>window.injected=true</script> 多對多';
    await page.locator('#answer-note').fill(note);
    await page.locator('#next-question').click();
    assert.match(await page.locator('#question-title').textContent(), /^6\./);
    await page.locator('input[value="custom"]').check();
    assert.equal(await page.locator('#answered-count').textContent(), '1');
    await page.locator('#answer-note').fill('Synthetic: 原譯名保留，僅查來源表述。');
    assert.equal(await page.locator('#answered-count').textContent(), '2');
    await page.locator('#next-question').click();
    await page.locator('#answer-note').fill('Synthetic note without decision');
    assert.equal(await page.locator('#answered-count').textContent(), '2');
    await page.locator('#reviewer').fill('Synthetic reviewer');
    await page.reload();
    assert.equal(await page.locator('#answered-count').textContent(), '2');

    // A downloaded HTML contains full evidence and answers without browser storage.
    const event = page.waitForEvent('download');
    await page.locator('#save-html').click();
    const download = await event;
    assert.equal(download.suggestedFilename(), 'review-human-only-answered.html');
    const portable = path.join(temp, 'portable.html');
    await download.saveAs(portable);
    const reopened = await makePage();
    await reopened.goto(pathToFileURL(portable).href);
    assert.equal(await reopened.locator('#answered-count').textContent(), '2');
    assert.equal(await reopened.locator('#reviewer').inputValue(), 'Synthetic reviewer');
    await selectQuestion(reopened, 'row-2');
    assert.equal(await reopened.locator('#answer-note').inputValue(), note);
    assert.equal(await reopened.evaluate(() => !!window.injected), false);
    await reopened.locator('#answer-note').fill('Synthetic edited portable answer');
    await reopened.reload();
    await selectQuestion(reopened, 'row-2');
    assert.equal(await reopened.locator('#answer-note').inputValue(), 'Synthetic edited portable answer');
    const secondEvent = reopened.waitForEvent('download');
    await reopened.locator('#save-html').click();
    const secondFile = path.join(temp, 'portable-again.html');
    await (await secondEvent).saveAs(secondFile);
    const again = await makePage();
    await again.goto(pathToFileURL(secondFile).href);
    await selectQuestion(again, 'row-2');
    assert.equal(await again.locator('#answer-note').inputValue(), 'Synthetic edited portable answer');

    // Import validates every answer before applying any; no old questions sneak in.
    const before = await exported(again);
    const bad = JSON.parse(JSON.stringify(before));
    bad.state.answers['row-2'].note = 'MUST NOT APPLY';
    bad.state.answers['row-59'] = {choice:'defer', note:''};
    await again.locator('#restore-panel > summary').click();
    await again.locator('#restore-text').fill(JSON.stringify(bad));
    await again.locator('#restore-button').click();
    assert.match(await again.locator('#restore-status').textContent(), /無法載入/);
    assert.deepEqual((await exported(again)).state, before.state);
    const incoming = JSON.parse(JSON.stringify(before));
    incoming.state.answers = {'row-7':{choice:'defer',note:'Synthetic pending context'}};
    await again.locator('#restore-text').fill(JSON.stringify(incoming));
    await again.locator('#restore-button').click();
    assert.equal(await again.locator('#answered-count').textContent(), '3');
    assert.deepEqual((await exported(again)).deferred_question_ids, ['row-7']);
    assert.equal((await exported(again)).state.answers['row-2'].note, 'Synthetic edited portable answer');

    // A fully answered questionnaire can still have unresolved source questions.
    for (const q of initial.questions) {
      await selectQuestion(again, q.id);
      await again.locator('input[value="defer"]').check();
    }
    await again.locator('#next-question').click();
    assert.equal(await again.locator('#remaining-count').textContent(), '0');
    const completed = await exported(again);
    assert.equal(completed.status, 'followup-answered');
    assert.equal(completed.deferred_question_ids.length, 9);
    assert.equal(completed.human_decisions_applied, false);
    assert.deepEqual(completed.screenshot_transcription, original);
    assert.equal(completed.reassessment.cases.every(c => c.human_decision === null), true);

    // Search and full evidence remain usable on a narrow display.
    await page.setViewportSize({width:390,height:844});
    await page.locator('#jump-reference').click();
    await page.locator('#reference-search').fill('音訊');
    assert.equal(await page.locator('[data-reference-row="59"]').isVisible(), true);
    assert.equal(await page.locator('[data-reference-row="2"]').count(), 0);
    await page.locator('[data-reference-row="59"] > td:last-child > details > summary').click();
    await page.locator('[data-reference-row="59"] .moe-reading > summary').click();
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), true);
    await page.locator('#reference-search').fill('');
    assert.equal(await page.locator('[data-reference-row]:visible').count(), 58);
    await page.setViewportSize({width:1360,height:1000});
    await page.evaluate(() => window.scrollTo(0,0));
    await page.screenshot({path:path.join(temp,'desktop.png')});

    // Quota and clipboard failure still leave a copyable, complete export.
    const fallback = await makePage();
    await fallback.addInitScript(() => {
      Storage.prototype.setItem = () => {throw Error('Synthetic quota failure');};
      Object.defineProperty(navigator,'clipboard',{value:{writeText:async()=>{throw Error('Synthetic permission denial');}}});
    });
    await fallback.goto(pathToFileURL(report).href);
    await fallback.locator('input[value="defer"]').check();
    assert.match(await fallback.locator('#save-status').textContent(), /無法自動儲存/);
    await fallback.locator('#export-json').click();
    await fallback.locator('#copy-json').click();
    assert.match(await fallback.locator('#export-status').textContent(), /已選取全文/);
    assert.equal(JSON.parse(await fallback.locator('#export-text').inputValue()).state.answers['row-2'].choice, 'defer');
    assert.deepEqual(errors, []);
    console.log('PASS: 9 focused questions, 58 references, 52 original selections, full MOE, portable HTML/JSON, restore, deferred status, and mobile.');
    console.log('Preview: '+path.join(temp,'desktop.png'));
  } finally {
    await browser.close();
  }
}
main().catch(error => {console.error(error); process.exitCode=1;});
