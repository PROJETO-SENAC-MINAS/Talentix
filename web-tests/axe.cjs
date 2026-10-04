const AxeBuilder = require('@axe-core/playwright').default;
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const OUT = process.env.TEST_RESULTS_DIR || path.join(__dirname, '../test-results');
const reports = [];
async function audit(page, name) {
  await page.evaluate(() => document.fonts.ready);
  const result = await new AxeBuilder({page})
    .withTags(['wcag2a','wcag2aa','wcag21a','wcag21aa','wcag22aa','best-practice']).analyze();
  reports.push({name, url:page.url(), violations:result.violations, incomplete:result.incomplete,
    passes:result.passes.map(rule=>rule.id)});
  fs.mkdirSync(OUT,{recursive:true});
  fs.writeFileSync(path.join(OUT, `accessibility-${process.env.A11Y_REPORT || 'browser'}.json`), JSON.stringify(reports,null,2));
  assert.deepEqual(result.violations.map(v=>({rule:v.id,nodes:v.nodes.map(n=>({target:n.target,summary:n.failureSummary}))})), [], name);
}
module.exports = {audit};
