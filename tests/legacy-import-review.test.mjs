import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = (path) => readFileSync(new URL(path, import.meta.url), "utf8");
const page = read("../docs/index.html");
const app = read("../docs/app.js");
const service = read("../docs/js/coachService.js");
const review = read("../docs/js/pages/legacyImport.js");
const css = read("../docs/css/ui-overhaul.css");

assert.match(page, /data-admin-view="legacyImport"/);
assert.match(page, /id="legacyImportView"/);
assert.match(app, /createLegacyImportPage/);
assert.match(service, /\/api\/admin\/legacy-imports/);
assert.match(review, /안전한 항목.*일괄 승인/);
assert.match(review, /최종 반영 Preview/);
assert.match(review, /회원 다시 선택/);
assert.match(review, /coach-mireu", "정미르"/);
assert.match(review, /캘린더 단독 기록/);
assert.match(review, /수업으로 복원/);
assert.match(review, /calendar_table_matched/);
assert.match(review, /data-legacy-event-type/);
assert.match(service, /confirmBatchId/);
assert.match(css, /\.legacy-summary/);
assert.match(css, /\.legacy-calendar-actions/);

console.log("legacy import review checks passed");
