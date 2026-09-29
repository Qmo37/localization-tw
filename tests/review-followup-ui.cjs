/* Verify screenshot carry-over and portable answers in isolated browser profiles.
 * Build reports/review-followup.html first; configure Playwright as in review-ui.cjs.
 */
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const os = require('node:os');
const path = require('node:path');
const {pathToFileURL} = require('node:url');
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright');

async function main() {
  const temp = await fs.mkdtemp(path.join(os.tmpdir(), 'localization-followup-test-'));
  const report = path.join(temp, 'review-followup.html');
  await fs.copyFile(path.join(__dirname, '../reports/review-followup.html'), report);
  const browser = await chromium.launch({headless: true, ...(process.env.CHROMIUM_EXECUTABLE ? {executablePath: process.env.CHROMIUM_EXECUTABLE} : {})});
  const errors = [];
  const makePage = async () => {
    const context = await browser.newContext();
    const page = await context.newPage();
    page.on('pageerror', error => errors.push(error.message));
    return page;
  };
  const getExport = async page => {
    await page.locator('#export-json').click();
    return JSON.parse(await page.locator('#export-text').inputValue());
  };
  const selectQuestion = async (page, id) => {
    await page.locator('#filter').selectOption('all');
    await page.locator(`[data-question="${id}"]`).click();
  };
  try {
    const page = await makePage();
    await page.goto(pathToFileURL(report).href);
    assert.equal(await page.locator('#remaining-count').textContent(), '16');
    assert.equal(await page.locator('#answered-count').textContent(), '0');
    assert.equal(await page.locator('#recovered-rows > tr').count(), 52);
    assert.equal(await page.locator('input[name=choice]:checked').count(), 0);
    const initial = await getExport(page);
    assert.equal(initial.questions.length, 16);
    assert.equal(initial.questions.every(q => q.answer === null), true);
    assert.equal(initial.screenshot_transcription.rows.length, 67);
    assert.equal(initial.human_decisions_applied, false);
    for (const row of initial.screenshot_transcription.rows.filter(r => r.observed_checked_ids.length)) {
      const values = await page.locator(`[data-row="${row.number}"] input[type=checkbox]:checked`).evaluateAll(inputs => inputs.map(input => input.value));
      assert.deepEqual(values, row.observed_checked_ids, 'Original selections for row ' + row.number);
    }

    // Human selection, explicit custom wording, and partially filled notes.
    await page.locator('input[name=choice][value=option-0]').check();
    const note = 'Synthetic review: 保留分義。 </script><script>window.injected = true</script>';
    await page.locator('#answer-note').fill(note);
    await page.locator('#next-question').click();
    assert.match(await page.locator('#question-title').textContent(), /^11\./);
    await page.locator('input[name=choice][value=custom]').check();
    assert.equal(await page.locator('#answered-count').textContent(), '1');
    await page.locator('#answer-note').fill('Synthetic custom policy.');
    assert.equal(await page.locator('#answered-count').textContent(), '2');
    await page.locator('#reviewer').fill('Synthetic reviewer');
    await page.reload();
    assert.match(await page.locator('#question-title').textContent(), /^12\./);
    assert.equal(await page.locator('#answered-count').textContent(), '2');
    await page.locator('#answer-note').fill('Synthetic note without a selected decision.');
    assert.equal(await page.locator('#answered-count').textContent(), '2');

    // Amend just one recovered checkbox while retaining the original evidence.
    await page.locator('#recovered-panel > summary').click();
    await page.locator('[data-row="59"] details.record-details > summary').click();
    await page.locator('[data-row="59"] input[type=checkbox]').first().uncheck();
    await page.locator('#row-note-59').fill('Synthetic example: keep general and technical senses separate.');
    await page.locator('#recovered-panel > summary').click();
    const partial = await getExport(page);
    const row59 = partial.screenshot_transcription.rows.find(r => r.number === 59);
    assert.equal(row59.observed_checked_ids.length, 2);
    assert.equal(partial.state.overrides[row59.conflict_id].selected_ids.length, 1);
    assert.equal(partial.questions.find(q => q.number === 12).status, 'awaiting-user-response');

    // The download must contain answers independently of localStorage, including
    // special characters that must not escape the embedded JSON script element.
    const downloaded = page.waitForEvent('download');
    await page.locator('#save-html').click();
    const download = await downloaded;
    assert.equal(download.suggestedFilename(), 'review-followup-answered.html');
    const portable = path.join(temp, 'portable.html');
    await download.saveAs(portable);
    const reopened = await makePage();
    await reopened.goto(pathToFileURL(portable).href);
    assert.equal(await reopened.locator('#answered-count').textContent(), '2');
    assert.equal(await reopened.locator('#reviewer').inputValue(), 'Synthetic reviewer');
    await selectQuestion(reopened, 'row-10');
    assert.equal(await reopened.locator('#answer-note').inputValue(), note);
    assert.equal(await reopened.evaluate(() => !!window.injected), false);
    await reopened.locator('#answer-note').fill('Updated after reopening a portable snapshot.');
    await reopened.reload();
    await selectQuestion(reopened, 'row-10');
    assert.equal(await reopened.locator('#answer-note').inputValue(), 'Updated after reopening a portable snapshot.');
    const portableAgain = reopened.waitForEvent('download');
    await reopened.locator('#save-html').click();
    const twice = path.join(temp, 'portable-again.html');
    await (await portableAgain).saveAs(twice);
    const finalCopy = await makePage();
    await finalCopy.goto(pathToFileURL(twice).href);
    await selectQuestion(finalCopy, 'row-10');
    assert.equal(await finalCopy.locator('#answer-note').inputValue(), 'Updated after reopening a portable snapshot.');

    // Portable JSON recovery, and all-or-nothing validation of malformed imports.
    const restored = await makePage();
    await restored.goto(pathToFileURL(report).href);
    await restored.locator('#restore-panel > summary').click();
    await restored.locator('#restore-text').fill(JSON.stringify(partial));
    await restored.locator('#restore-button').click();
    assert.equal(await restored.locator('#answered-count').textContent(), '2');
    const invalid = structuredClone(partial);
    invalid.state.overrides[row59.conflict_id].selected_ids = ['nonexistent-source'];
    await restored.locator('#restore-text').fill(JSON.stringify(invalid));
    await restored.locator('#restore-button').click();
    assert.match(await restored.locator('#restore-status').textContent(), /現有答案未變更/);
    const afterInvalid = await getExport(restored);
    assert.deepEqual(afterInvalid.state.answers, partial.state.answers);
    assert.deepEqual(afterInvalid.state.overrides, partial.state.overrides);

    // File:// clipboard and storage failures must still leave a usable export.
    await restored.evaluate(() => {
      Storage.prototype.setItem = () => {throw Error('quota');};
      Object.defineProperty(navigator, 'clipboard', {configurable: true, value: {writeText: async () => {throw Error('denied');}}});
    });
    await restored.locator('#reviewer').fill('Synthetic unsaved reviewer');
    assert.match(await restored.locator('#save-status').textContent(), /無法自動儲存/);
    const unsaved = await getExport(restored);
    assert.equal(unsaved.state.reviewer, 'Synthetic unsaved reviewer');
    await restored.locator('#copy-json').click();
    assert.match(await restored.locator('#export-status').textContent(), /已選取全文/);
    assert.equal(await restored.locator('#export-text').evaluate(el => el.selectionEnd - el.selectionStart), (await restored.locator('#export-text').inputValue()).length);

    await page.setViewportSize({width: 390, height: 844});
    await selectQuestion(page, 'row-10');
    await page.locator('#question-evidence > summary').click();
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
    await page.screenshot({path: path.join(temp, 'mobile.png')});
    await page.setViewportSize({width: 1440, height: 1100});
    await page.evaluate(() => scrollTo(0, 0));
    await page.screenshot({path: process.env.FOLLOWUP_SCREENSHOT || path.join(temp, 'desktop.png')});

    // Completing the questionnaire preserves a defer answer as text, never as a
    // resolved source decision. Navigation must finish without an infinite loop.
    await selectQuestion(page, 'row-10');
    for (const question of initial.questions) {
      await selectQuestion(page, question.id);
      await page.locator('input[name=choice][value=option-2]').check();
    }
    await page.locator('#next-question').click();
    assert.equal(await page.locator('#remaining-count').textContent(), '0');
    assert.match(await page.locator('#question-panel').textContent(), /補答已完成/);
    const complete = await getExport(page);
    assert.equal(complete.status, 'followup-answered');
    assert.equal(complete.human_decisions_applied, false);
    assert.equal(complete.questions[0].answer.text, '全部保留待查');
    assert.deepEqual(errors, []);
    console.log('PASS: all 52 screenshot selections, 16 unanswered questions, custom answers, reload, corrections, portable HTML round trips, script escaping, JSON recovery, failed imports, storage/clipboard fallback, mobile layout, complete/deferred answers.');
  } finally {
    await browser.close();
    await fs.rm(temp, {recursive: true, force: true});
  }
}
main().catch(error => {console.error(error); process.exitCode = 1;});
