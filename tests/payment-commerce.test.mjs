import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const reservationPage = readFileSync(new URL("../docs/js/pages/reservationPage.js", import.meta.url), "utf8");
const reservations = readFileSync(new URL("../docs/js/reservations.js", import.meta.url), "utf8");
const business = readFileSync(new URL("../docs/business.html", import.meta.url), "utf8");
const index = readFileSync(new URL("../docs/index.html", import.meta.url), "utf8");
const studentDashboard = readFileSync(new URL("../docs/js/pages/studentDashboard.js", import.meta.url), "utf8");

assert.match(reservationPage, /result\.testMode.*실제 금액은 청구되지 않습니다/);
assert.match(business, /사업자등록번호/);
assert.match(business, /통신판매업 신고번호/);
assert.match(business, /서비스 시작 전 전액 취소/);
assert.match(business, /textContent=info\[key\]/);
assert.doesNotMatch(business, /innerHTML=.*info\[key\]/);
assert.match(index, /business\.html/);
assert.match(studentDashboard, /originalAmount.*discountAmount.*payment\.amount/s);
assert.match(reservationPage, /사용 쿠폰.*couponName/s);
assert.match(reservations, /payment\?\.orderId.*payment\?\.status/s);

console.log("payment commerce checks passed");
