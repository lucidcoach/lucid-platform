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
assert.match(admin, /researchV13\|\|data\.researchV12/);
assert.match(admin, /v1\.3 연구기/);
for (const text of ["Fixture 원본 검증 데이터", "ROFL", "Match-V5", "Timeline", "마지막 수집", "재수집"]) {
  assert.match(admin, new RegExp(text));
}
assert.match(admin, /\/api\/community\/admin\/rofl-ground-truth\/collect/);
for (const text of ["수정 승인", "배포 승인", "지시문 보기", "Handoff ZIP", "Validation bundle", "평상시 Codex/LLM은 사용하지 않습니다."]) {
  assert.match(admin, new RegExp(text));
}
assert.match(admin, /"approve-fix"/);
assert.match(admin, /"approve-deploy"/);
assert.match(admin, /\/workflow\/\$\{encodeURIComponent\(build\)\}/);

console.log("ROFL operator guidance checks passed");
