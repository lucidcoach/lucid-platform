import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = (path) => readFileSync(new URL(path, import.meta.url), "utf8");
const admin = read("../docs/js/pages/adminDashboard.js");
const coach = read("../docs/js/pages/coachSelf.js");
const recruitment = read("../docs/community/js/pages/recruitment.js");
const inquiries = read("../docs/community/js/pages/communityAdmin.js");

for (const label of ["오늘 처리할 일", "코칭 점검 모드", "실패·대기 작업"]) assert.match(admin, new RegExp(label));
for (const label of ["공개 전 체크", "공개 미리보기", "초안으로 저장"]) assert.match(coach, new RegExp(label));
assert.match(recruitment, /모집 일정을 불러오지 못했습니다/);
assert.match(recruitment, /Discord에서 참가/);
for (const field of ["assignedTo", "dueAt", "adminReply", "사용자 답변 초안"]) assert.match(inquiries, new RegExp(field));

console.log("operations UX checks passed");
