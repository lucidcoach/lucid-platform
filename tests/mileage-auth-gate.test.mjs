import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const source = readFileSync(new URL("../docs/community/js/pages/mileage.js", import.meta.url), "utf8");
const entry = readFileSync(new URL("../docs/community/js/app-report6.js", import.meta.url), "utf8");
assert.match(source, /const linked=Boolean\(user\?\.discordConnected/);
assert.match(source, /if\(!linked\).*상품을 보려면 로그인 및 디스코드 연동이 필요합니다\./s);
assert.match(source, /최근 7일 획득 범위/);
assert.match(source, /weeklyEarnedMin/);
assert.match(entry, /pages\/mileage\.js\?v=20260911trend1/);

console.log("mileage auth gate checks passed");
