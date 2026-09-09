import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const admin = readFileSync(new URL("../docs/community/js/pages/communityAdmin.js", import.meta.url), "utf8");

for (const text of ["현재 상태 요약", "운영 영향", "현재 문제", "지금 할 일", "추천 작업"]) {
  assert.match(admin, new RegExp(text));
}
assert.equal((admin.match(/<h3>추천 작업/g) || []).length, 1);
for (const text of ["정상", "검증 부족", "아직 지원 안 함", "운영 반영 보류"]) {
  assert.match(admin, new RegExp(text));
}
assert.match(admin, /Math\.max\(0,minimum-fixtureCount\)/);
assert.match(admin, /같은 패치 ROFL \$\{needed\}개 추가 업로드/);
assert.match(admin, /production gate/);

console.log("ROFL operator guidance checks passed");
