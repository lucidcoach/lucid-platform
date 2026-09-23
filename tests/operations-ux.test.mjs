import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = (path) => readFileSync(new URL(path, import.meta.url), "utf8");
const admin = read("../docs/js/pages/adminDashboard.js");
const coach = read("../docs/js/pages/coachSelf.js");
const recruitment = read("../docs/community/js/pages/recruitment.js");
const inquiries = read("../docs/community/js/pages/communityAdmin.js");
const market = read("../docs/js/pages/market.js");
const reservations = read("../docs/js/pages/reservationPage.js");

for (const label of ["미처리 업무", "코칭 점검 모드", "data-operation-target"]) assert.match(admin, new RegExp(label));
for (const label of ["공개 전 체크", "공개 미리보기", "초안으로 저장", "저장하지 않은 코치센터", "하루 전체 가능"]) assert.match(coach, new RegExp(label));
for (const label of ["lucid-coaching-booking-draft", "renderReviewsMarkup", "가장 빠른 시간"]) assert.match(market, new RegExp(label));
for (const label of ["정산 계좌 미등록", "settlementStatusFilter", "data-copy-payout"]) assert.match(reservations, new RegExp(label));
assert.match(recruitment, /모집 일정을 불러오지 못했습니다/);
assert.match(recruitment, /Discord에서 참가/);
for (const field of ["assignedTo", "dueAt", "adminReply", "사용자 답변 초안", "replySent", "inquiryQueueFilter", "답변 복사"]) assert.match(inquiries, new RegExp(field));
assert.match(inquiries, /new Date\(dueAt\)\.toISOString\(\)/);

console.log("operations UX checks passed");
