import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const mileage = readFileSync(new URL("../docs/community/js/pages/mileage.js", import.meta.url), "utf8");
const app = readFileSync(new URL("../docs/community/js/app-report6.js", import.meta.url), "utf8");
for (const value of ["feedback", "reset", "cosmetic", "shortDescription", "linkedPageUrl"]) assert.match(mileage, new RegExp(value));
assert.match(mileage, /data-item-detail/);
assert.match(mileage, /💰 포인트 획득 방법/);
assert.match(mileage, /earningGuideDialog/);
assert.match(mileage, /admin\/transactions\?page=/);
assert.match(mileage, /admin\/invites\?page=/);
assert.match(mileage, /const auditRows=.*userName/);
assert.match(mileage, /const inviteRows=.*inviterName/);
assert.match(app, /moreMenu\.contains\(event\.target\)/);
assert.match(app, /event\.key==="Escape"/);

console.log("mileage shop UX checks passed");
