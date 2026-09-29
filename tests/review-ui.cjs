/* Offline regression checks for draft recovery and human-review export.
 * Install Playwright separately, or set PLAYWRIGHT_MODULE to an existing module.
 * Optional: CHROMIUM_EXECUTABLE points to an already installed browser.
 * Run: node tests/review-ui.cjs
 * Every decision here is a synthetic fixture in a temporary browser profile.
 */
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const os = require('node:os');
const path = require('node:path');
const {pathToFileURL} = require('node:url');
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright');

async function main() {
  const temp = await fs.mkdtemp(path.join(os.tmpdir(), 'localization-review-test-'));
  const browser = await chromium.launch({headless: true, ...(process.env.CHROMIUM_EXECUTABLE ? {executablePath: process.env.CHROMIUM_EXECUTABLE} : {})});
  const errors = [];
  try {
    const conflicts = Array.from({length: 14}, (_, i) => ({
      id: 'c' + i, fingerprint: 'evidence-' + i, review_group: 'primary',
      kind: 'translation_choice', status: 'pending', term: '測試詞 ' + i,
      domain: '電腦資訊', reason: '測試用候選，沒有實際人工決定。',
      candidates: ['project', 'microsoft'].map(source => ({
        id: source + ':' + i, source, en: ['term ' + i], tw: [source + ' 用語'],
        cn: [], domain: '電腦資訊', pronunciations: [], definitions: [],
        url: '', source_version: 'fixture',
      })),
    }));
    const payload = {run_id: 'new-report', generated_at: 'fixture', record_count: 28, conflicts};
    const template = await fs.readFile(path.join(__dirname, '../scripts/terminology/review-template.html'), 'utf8');
    const report = path.join(temp, 'review.html');
    const writeReport = () => fs.writeFile(report, template.replace('__PAYLOAD__', JSON.stringify(payload).replace(/</g, '\\u003c')));
    await writeReport();
    const fixtureDraft = (i, values = {}) => ({fingerprint: 'evidence-' + i, action: 'select', selected_ids: ['project:' + i], scope: '電腦資訊', rationale: '', ...values});
    const legacy = {
      c0: fixtureDraft(0), c1: fixtureDraft(1), c12: fixtureDraft(12, {action: ''}),
      c2: fixtureDraft(2, {fingerprint: 'old-evidence', rationale: '舊資料的測試理由'}),
      removed: fixtureDraft(99),
    };
    const context = await browser.newContext();
    await context.addInitScript(value => {
      if (!localStorage.getItem('localization-tw-review:old-report'))
        localStorage.setItem('localization-tw-review:old-report', JSON.stringify(value));
    }, legacy);
    const page = await context.newPage();
    page.on('pageerror', error => errors.push(error.message));
    await page.goto(pathToFileURL(report).href);
    await page.waitForSelector('.card');
    assert.match(await page.locator('#message').textContent(), /找回 4 筆/);
    assert.equal(await page.locator('#conflict-c0 input[type=checkbox]').first().isChecked(), true);
    await page.locator('#next').click();
    assert.equal(await page.locator('#conflict-c12 input[type=checkbox]').first().isChecked(), true);
    await page.locator('#backup').click();
    let backup = JSON.parse(await page.locator('#export-text').inputValue());
    assert.equal(backup.kind, 'localization-tw-review-draft');
    assert.equal(Object.keys(backup.drafts).length, 4);
    assert.equal(backup.drafts.c12.action, '');
    assert.deepEqual(backup.archives[0].drafts, legacy);

    // All-incomplete selection must still produce portable data, without authoring
    // a rationale, changing an action, or turning a draft into an approval.
    await page.locator('#reviewer').fill('Synthetic UI reviewer');
    await page.locator('#export').click();
    assert.equal(JSON.parse(await page.locator('#export-text').inputValue()).kind, 'localization-tw-review-draft');
    assert.match(await page.locator('#issue-list').textContent(), /你的決定/);
    await page.locator('#issue-list button').filter({hasText: '測試詞 0：'}).click();
    await page.locator('#conflict-c0 textarea').fill('Synthetic human-entered fixture rationale.');
    await page.locator('#export').click();
    const decisions = JSON.parse(await page.locator('#export-text').inputValue());
    assert.equal(decisions.length, 1);
    assert.equal(decisions[0].conflict_id, 'c0');
    assert.equal(decisions[0].reviewed_by, 'Synthetic UI reviewer');
    assert.match(await page.locator('#export-description').textContent(), /3 筆未完成/);
    const downloaded = page.waitForEvent('download');
    await page.locator('#download').click();
    const download = await downloaded;
    assert.equal(download.suggestedFilename(), 'review-decisions.json');
    assert.deepEqual(JSON.parse(await fs.readFile(await download.path(), 'utf8')), decisions);

    await page.evaluate(() => Object.defineProperty(navigator, 'clipboard', {configurable: true, value: {writeText: async () => {throw Error('denied');}}}));
    await page.locator('#copy').click();
    assert.match(await page.locator('#export-status').textContent(), /已選取全文/);
    assert.equal(await page.locator('#export-text').evaluate(el => el.selectionEnd - el.selectionStart), (await page.locator('#export-text').inputValue()).length);

    // Rebuilding only the report must not strand the previous browser drafts.
    payload.run_id = 'rebuilt-report';
    await writeReport();
    await page.reload();
    assert.equal(await page.locator('#reviewer').inputValue(), 'Synthetic UI reviewer');
    assert.equal(await page.locator('#conflict-c0 textarea').inputValue(), 'Synthetic human-entered fixture rationale.');
    assert.match(await page.locator('#conflict-c2 .stale').textContent(), /來源證據已更新/);
    assert.equal(await page.locator('#conflict-c2 .decision select').inputValue(), '');
    await page.locator('#backup').click();
    backup = JSON.parse(await page.locator('#export-text').inputValue());
    const restoreContext = await browser.newContext();
    const restored = await restoreContext.newPage();
    restored.on('pageerror', error => errors.push(error.message));
    await restored.goto(pathToFileURL(report).href);
    await restored.locator('#restore summary').click();
    await restored.locator('#restore-text').fill(JSON.stringify(backup));
    await restored.locator('#restore-paste').click();
    assert.match(await restored.locator('#message').textContent(), /還原 4 筆/);
    assert.equal(await restored.locator('#conflict-c0 textarea').inputValue(), backup.drafts.c0.rationale);
    assert.equal(await restored.locator('#reviewer').inputValue(), backup.reviewer);
    await restored.locator('#restore-text').fill(JSON.stringify({...backup, drafts: {c0: null}}));
    await restored.locator('#restore-paste').click();
    assert.match(await restored.locator('#message').textContent(), /現有選擇未變更/);
    await restored.locator('#backup').click();
    assert.deepEqual(JSON.parse(await restored.locator('#export-text').inputValue()).drafts, backup.drafts);

    // Storage failures still allow an immediate backup of in-memory choices.
    await restored.evaluate(() => {Storage.prototype.setItem = () => {throw Error('quota');};});
    await restored.locator('#conflict-c1 textarea').fill('New unsaved fixture rationale.');
    await restored.locator('#backup').click();
    assert.match(await restored.locator('#message').textContent(), /瀏覽器無法儲存/);
    assert.equal(JSON.parse(await restored.locator('#export-text').inputValue()).drafts.c1.rationale, 'New unsaved fixture rationale.');
    await restored.setViewportSize({width: 390, height: 844});
    assert.equal(await restored.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
    // Scoped answers and assistant references do not become new form answers.
    payload.conflicts[0].source_policies = [{active:true, decision_text:'Fixture hold <script>not executable</script>', scope:'One source only.'}];
    payload.conflicts[0].candidates[0].source_review = [{active:true, use_status:'on-hold'}];
    payload.conflicts[1].assistant_review = {active:true, requires_more_evidence:false, assessment:'Fixture reference', full_reading_assessment:'Full fixture reading.', relationship_guidance:'Allow several contextual meanings.'};
    payload.scoped_source_review = {active_answers:1,held_source_count:1};
    payload.assistant_sense_review = {reference_only_cases:1};
    await writeReport();
    const annotatedContext = await browser.newContext();
    const annotated = await annotatedContext.newPage();
    annotated.on('pageerror', error => errors.push(error.message));
    await annotated.goto(pathToFileURL(report).href);
    assert.equal(await annotated.locator('#conflict-c0').count(), 0);
    assert.equal(await annotated.locator('#conflict-c1').count(), 0);
    assert.match(await annotated.locator('#review-summary').textContent(), /1 筆已補答.*1 條來源配對暫停.*1 筆複核參考/);
    await annotated.locator('#work').selectOption('answered');
    assert.equal(await annotated.locator('.card').count(), 1);
    assert.match(await annotated.locator('.scoped-answer').textContent(), /Fixture hold <script>/);
    assert.equal(await annotated.locator('.scoped-answer script').count(), 0);
    assert.match(await annotated.locator('.source-policy').textContent(), /已暫停/);
    assert.match(await annotated.locator('.card .badge').first().textContent(), /整組判定：待覆核/);
    await annotated.locator('#backup').click();
    assert.deepEqual(JSON.parse(await annotated.locator('#export-text').inputValue()).drafts, {});
    await annotated.locator('#work').selectOption('reference');
    assert.equal(await annotated.locator('.card').count(), 1);
    assert.match(await annotated.locator('#conflict-c1').textContent(), /未代填成人工核准/);
    payload.conflicts[0].source_policies[0].active=false;
    payload.conflicts[0].candidates[0].source_review[0]={active:false,use_status:'stale-policy-not-applied'};
    payload.conflicts[1].assistant_review.active=false;
    await writeReport();
    await annotated.reload();
    assert.equal(await annotated.locator('#conflict-c0').count(), 1);
    assert.equal(await annotated.locator('#conflict-c1').count(), 1);
    assert.match(await annotated.locator('#conflict-c0 .scoped-answer').textContent(), /未套用/);
    payload.conflicts[2].candidates.push({id:'moe-revised:fixture',source:'moe-revised',en:[],tw:['行程'],cn:[],
      domain:'一般用語',source_version:'fixture-version',url:'https://example.invalid/dictionary',
      data_url:'https://example.invalid/pinned.json.xz',usage_note:'兼收古今義項；《簡編本》優先。',
      pronunciations:[{order:1,bopomofo:'注音一',pinyin:'reading-one'},{order:2,bopomofo:'注音二',pinyin:'reading-two'}],
      definitions:[{text:'義項一',display:'讀音 1・義項 1\n釋義：義項一\n引文：<script>fixture</script>\n例句：完整例句'},
                   {text:'義項二',display:'讀音 2・義項 1\n釋義：義項二\n參見：另一詞'}]});
    await writeReport();
    await annotated.reload();
    const revisedSource = annotated.locator('#conflict-c2 .source').last();
    assert.match(await revisedSource.textContent(), /重編本.*補充（g0v）/s);
    for (const text of ['reading-one','reading-two','完整例句','另一詞','<script>fixture</script>','fixture-version'])
      assert.ok((await revisedSource.textContent()).includes(text));
    assert.equal(await revisedSource.locator('script').count(), 0);
    await revisedSource.locator('details summary').click();
    assert.equal(await revisedSource.getByRole('link', {name:'固定版本的 g0v 資料', exact:true}).getAttribute('href'), 'https://example.invalid/pinned.json.xz');
    await annotated.setViewportSize({width:390,height:844});
    assert.equal(await annotated.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
    assert.deepEqual(errors, []);
    console.log('PASS: legacy recovery, incomplete/cross-page backup, partial export/download, clipboard fallback, rebuild persistence, stale evidence, restore validation, storage failure, mobile layout, scoped answers and stale references.');
  } finally {
    await browser.close();
    await fs.rm(temp, {recursive: true, force: true});
  }
}
main().catch(error => {console.error(error);process.exitCode = 1;});
