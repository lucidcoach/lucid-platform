import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const source = readFileSync(new URL("../docs/community/js/pages/liveMatch.js", import.meta.url), "utf8");
const rankingSource = readFileSync(new URL("../docs/community/js/pages/ranking.js", import.meta.url), "utf8");
assert.doesNotMatch(source, /positionRank|keyMatchups|blueAverageMmr|킬관여|서버 .*위/);
assert.match(source, /tier-badge/);
assert.match(source, /플레이 특징 분석 중/);
assert.match(source, /mostChampions/);
assert.match(source, /recentChampions/);
assert.match(source, /totalWinRate/);
assert.match(rankingSource, /row\.winRate/);

console.log("live match readability checks passed");
