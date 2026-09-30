import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { QUICK_ROLES, QUICK_TIERS } from "../docs/streaming/quick-balance.js";

const page = readFileSync(new URL("../docs/streaming/index.html", import.meta.url), "utf8");
const script = readFileSync(new URL("../docs/streaming/streaming.js", import.meta.url), "utf8");
assert.equal(QUICK_TIERS.find((tier) => tier.label === "골드 4")?.score, 1250);
assert.equal(QUICK_TIERS.at(-1)?.score, 3800);
assert.deepEqual(QUICK_ROLES, ["탑", "정글", "미드", "원딜", "서폿"]);
assert.match(page, /data-view="quick"[^>]*>빠른 팀 나누기/);
assert.match(page, /id="quickStart"[^>]*>비로그인으로 계속하기/);
assert.match(page, /DB 저장 없음/);
assert.match(page, /data-quick-mode="basic"[^>]*>간편 설정/);
assert.match(page, /data-quick-mode="roles"[^>]*>포지션별 설정/);
assert.equal((script.match(/\/api\/streaming\/quick-balance/g) || []).length, 2);
assert.match(script, /평균 티어 \$\{escapeHtml\(result\.blueAvgTier\)\} vs \$\{escapeHtml\(result\.redAvgTier\)\}/);
assert.doesNotMatch(script, /평균 MMR 차이/);
assert.match(script, /data-match-action/);
assert.match(script, /matches\/\$\{id\}\/\$\{name\}/);
assert.match(script, /MMR 변동/);
assert.match(script, /beforeMmr.*afterMmr.*mmrDelta/);
assert.match(script, /role_bottleneck/);
assert.match(script, /textContent=errorText\(error\)/);
assert.doesNotMatch(readFileSync(new URL("../docs/streaming/quick-balance.js", import.meta.url), "utf8"), /function balance/);

console.log("streaming anonymous quick balance checks passed");
