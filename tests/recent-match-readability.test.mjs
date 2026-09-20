import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { aiRank, aiStanding } from "../docs/community/js/components/scoreboard.js";
import { playerMatchCard } from "../docs/community/js/components/playerMatchCard.js";

const players = Array.from({ length: 10 }, (_, index) => ({
  userId: String(index + 1), name: `player${index + 1}`, champion: index ? "Ahri" : "LeeSin",
  team: index < 5 ? "blue" : "red", result: "win", aiScore: 100 - index * 10,
  kills: 1, deaths: 1, assists: 1, kda: 2, cs: 100, csm: 5, items: [],
}));
const match = { matchId: "match", guildId: "guild", time: new Date().toISOString(), players };

assert.deepEqual(aiRank(match, players[4]), { rank: 5, total: 10 });
assert.equal(aiStanding(players[4], aiRank(match, players[4])), '<small class="ai-standing">5위</small>');
assert.match(playerMatchCard(match, "5"), /ai-standing">5위/);

players[0].award = "MVP";
const mvp = playerMatchCard(match, "1");
assert.match(mvp, /ai-standing mvp">👑 MVP/);
assert.doesNotMatch(mvp, /ai-standing">1위/);
players[0].award = "ACE";
assert.match(playerMatchCard(match, "1"), /ai-standing ace">♛ ACE/);

const css = readFileSync(new URL("../docs/community/styles.css", import.meta.url), "utf8");
assert.match(css, /personal-match\.win[\s\S]+background:color-mix/);
assert.match(css, /data-theme="light"[^\n]+personal-match\.win/);
assert.match(css, /champion-stats-page[\s\S]+grid-template-columns:minmax\(220px,1fr\) 90px 150px 100px/);
assert.match(css, /max-width:620px[\s\S]+grid-template-columns:minmax\(96px,1fr\) 42px 82px 42px/);

console.log("recent match readability checks passed");
