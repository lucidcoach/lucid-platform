import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const source = readFileSync(new URL("../docs/community/js/pages/liveMatch.js", import.meta.url), "utf8");
const summarySource = source.match(/function recentTeamRate[\s\S]+?(?=function renderList)/)?.[0];
assert.ok(summarySource, "summary functions must remain testable");
const { gameSummary, recentTeamRate } = Function(`${summarySource}; return { gameSummary, recentTeamRate };`)();

assert.equal(recentTeamRate([{ recentGames: 10, recentWinRate: 60 }, { recentGames: 5, recentWinRate: 40 }]), 160 / 3);
assert.equal(recentTeamRate([]), null);
assert.match(gameSummary({ blueAverageMmr: 2666, redAverageMmr: 2688, blue: [], red: [] }), /평균 MMR 레드 \+22/);

console.log("live match summary checks passed");
