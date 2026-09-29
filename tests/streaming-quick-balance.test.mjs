import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { balanceQuickPlayers, QUICK_TIERS } from "../docs/streaming/quick-balance.js";

const page = readFileSync(new URL("../docs/streaming/index.html", import.meta.url), "utf8");
const script = readFileSync(new URL("../docs/streaming/streaming.js", import.meta.url), "utf8");
const players = Array.from({ length: 10 }, (_, index) => ({ name: `P${index + 1}`, score: index, tier: "테스트" }));
const result = balanceQuickPlayers(players);

assert.equal(QUICK_TIERS.find((tier) => tier.label === "골드 4")?.score, 1250);
assert.equal(QUICK_TIERS.at(-1)?.score, 3800);
assert.equal(result.blue.length, 5);
assert.equal(result.red.length, 5);
assert.equal(result.difference, 1);
assert.deepEqual(new Set([...result.blue, ...result.red]), new Set(players));
assert.throws(() => balanceQuickPlayers(players.slice(1)), /ten_players_required/);
assert.match(page, /data-view="quick"[^>]*>빠른 팀 나누기/);
assert.match(page, /id="quickStart"[^>]*>비로그인으로 계속하기/);
assert.match(page, /DB 저장 없음/);
assert.match(script, /balanceQuickPlayers\(players\)/);

console.log("streaming anonymous quick balance checks passed");
