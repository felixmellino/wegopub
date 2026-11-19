/* Optional local content-preview QA; no live accounts or Supabase calls. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {chromium} = require(process.argv[2] ? path.resolve(process.argv[2]) : 'playwright');
const output = path.resolve('.venv', 'quiz-content-qa');
fs.mkdirSync(output, {recursive: true});

(async () => {
  const launch = {headless: true};
  if (!fs.existsSync(chromium.executablePath())) launch.channel = 'msedge';
  const browser = await chromium.launch(launch);
  try {
    for (const width of [390, 1280]) {
      const page = await browser.newPage({viewport: {width, height: 844}});
      await page.goto('http://127.0.0.1:8769');
      await page.getByRole('button', {name: 'Generate another pack', exact: true}).waitFor();
      const savedPack = () => page.getByText(/^Shared saved pack · /).textContent();
      const firstPack = await savedPack();
      await page.getByText('2 · Multiplication', {exact: true}).click();
      await page.getByRole('heading', {name: 'Math', exact: true}).waitFor();
      assert.equal(await savedPack(), firstPack);
      await page.getByText('3 · Logic', {exact: true}).click();
      await page.getByRole('heading', {name: 'Logic', exact: true}).waitFor();
      assert.equal(await savedPack(), firstPack);
      const mode = page.getByTestId('stRadio').first();
      await mode.getByText('Multiplication', {exact: true}).click();
      for (const name of ['First factor', 'Second factor']) {
        const input = page.getByRole('spinbutton', {name, exact: true});
        await input.fill('10');
        await input.press('Enter');
      }
      await page.getByText('What is 10 × 10?', {exact: true}).waitFor();
      assert.equal(await page.getByRole('button', {name: /^[ABCD]\. 100$/}).count(), 1);
      await page.screenshot({path: path.join(output, `math-${width}.png`)});
      await mode.getByText('Logic', {exact: true}).click();
      await page.getByTestId('stSelectbox').click();
      await page.getByRole('option', {name: 'boxes', exact: true}).click();
      await page.getByText(/^Exactly one of four boxes/).waitFor();
      assert.equal(await page.getByTestId('stException').count(), 0);
      assert(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth));
      await page.screenshot({path: path.join(output, `logic-${width}.png`)});
      await mode.getByText('General knowledge', {exact: true}).click();
      await page.getByText('Which country has Lisbon as its capital?', {exact: true}).waitFor();
      await page.getByText('Review answer and explanation', {exact: true}).click();
      await page.getByText(/^Correct: [ABCD] · Portugal$/).waitFor();
      assert.equal(await page.getByTestId('stException').count(), 0);
      await page.close();
    }
    console.log('PASS: 390px/1280px: saved pack stable across rounds; 10x10 has one correct option; logic puzzle wraps; general answer/source review works.');
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
