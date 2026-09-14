import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const source = readFileSync(new URL("../docs/community/js/pages/ranking.js", import.meta.url), "utf8");
const css = readFileSync(new URL("../docs/community/css/ranking.css", import.meta.url), "utf8");

assert.match(source, /const PAGE_SIZE = 10/);
assert.match(source, /rows\.slice\(\(page - 1\) \* PAGE_SIZE, page \* PAGE_SIZE\)/);
assert.match(source, /data-ranking-page/);
assert.match(source, /kind = button\.dataset\.rankingKind[\s\S]+page = 1/);
assert.match(source, /role = button\.dataset\.rankingRole[\s\S]+page = 1/);
assert.match(source, /종합은 보유한 라인 MMR 평균/);
for (const selector of ["ranking-tier-cutoffs", "ranking-table-head", "ranking-position", "ranking-player", "ranking-tier", "ranking-value"]) {
  assert.match(css, new RegExp(`\\.${selector}\\{[^}]*font-weight:400`));
}

console.log("ranking pagination checks passed");
