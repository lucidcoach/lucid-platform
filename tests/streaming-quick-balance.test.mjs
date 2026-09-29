import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { balanceQuickPlayers, balanceRolePlayers, QUICK_ROLES, QUICK_TIERS } from "../docs/streaming/quick-balance.js";

const page = readFileSync(new URL("../docs/streaming/index.html", import.meta.url), "utf8");
const script = readFileSync(new URL("../docs/streaming/streaming.js", import.meta.url), "utf8");
const players = Array.from({ length: 10 }, (_, index) => ({ name: `P${index + 1}`, score: index, tier: "테스트", role: QUICK_ROLES[Math.floor(index / 2)] }));
const result = balanceQuickPlayers(players);

assert.equal(QUICK_TIERS.find((tier) => tier.label === "골드 4")?.score, 1250);
assert.equal(QUICK_TIERS.at(-1)?.score, 3800);
assert.equal(result.blue.length, 5);
assert.equal(result.red.length, 5);
assert.equal(result.difference, 1);
assert.deepEqual(new Set([...result.blue, ...result.red]), new Set(players));
assert.deepEqual(result.blue.map((player) => player.role), QUICK_ROLES);
assert.deepEqual(result.red.map((player) => player.role), QUICK_ROLES);
assert.throws(() => balanceQuickPlayers(players.slice(1)), /ten_players_required/);
assert.throws(() => balanceQuickPlayers(players.map((player) => ({ ...player, role: "탑" }))), /two_per_role_required/);
const rolePlayers = players.map((player) => ({ name: player.name, choices: [{ role: player.role, tier: player.tier, score: player.score }] }));
const roleResult = balanceRolePlayers(rolePlayers);
assert.deepEqual(roleResult.blue.map((player) => player.role), QUICK_ROLES);
assert.deepEqual(roleResult.red.map((player) => player.role), QUICK_ROLES);
assert.equal(roleResult.difference, 1);
assert.equal(roleResult.preference, 0);
const threeRolePlayers = rolePlayers.map((player, index) => index === 1 ? { ...player, choices: [{ role: "정글", tier: "테스트", score: 1 }, { role: "미드", tier: "테스트", score: 1 }, { role: "탑", tier: "테스트", score: 1 }] } : player);
assert.equal(balanceRolePlayers(threeRolePlayers).preference, 2);
assert.throws(() => balanceRolePlayers(rolePlayers.map((player) => ({ ...player, choices: [{ role: "탑", score: 1 }] }))), /roles_unavailable/);
assert.match(page, /data-view="quick"[^>]*>빠른 팀 나누기/);
assert.match(page, /id="quickStart"[^>]*>비로그인으로 계속하기/);
assert.match(page, /DB 저장 없음/);
assert.match(page, /data-quick-mode="basic"[^>]*>간편 설정/);
assert.match(page, /data-quick-mode="roles"[^>]*>포지션별 설정/);
assert.match(script, /balanceQuickPlayers\(players\)/);
assert.match(script, /balanceRolePlayers\(players\)/);

console.log("streaming anonymous quick balance checks passed");
