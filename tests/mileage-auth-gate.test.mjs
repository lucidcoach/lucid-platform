import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const source = readFileSync(new URL("../docs/community/js/pages/mileage.js", import.meta.url), "utf8");
const entry = readFileSync(new URL("../docs/community/js/app-report6.js", import.meta.url), "utf8");
assert.match(source, /const linked=Boolean\(user\?\.discordConnected/);
assert.match(source, /if\(!linked\).*상품을 보려면 로그인 및 디스코드 연동이 필요합니다\./s);
assert.match(source, /최근 7일 획득 범위/);
assert.match(source, /weeklyEarnedMin/);
for (const tab of ["내전 진행","친구 초대","서버 활동","내전 레벨","환경설정"]) assert.match(source, new RegExp(tab));
assert.match(source, /듀오게임 보상/);
assert.doesNotMatch(source, /동반게임 최소 시간/);
assert.match(source, /scrim_xp_per_match/);
assert.match(source, /duo_match_count/);
assert.match(entry, /pages\/mileage\.js\?v=20260911quest1/);

console.log("mileage auth gate checks passed");
