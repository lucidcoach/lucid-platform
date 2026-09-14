import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = path => readFileSync(new URL(path, import.meta.url), "utf8");
const entry = read("../docs/community/js/app-report6.js");
const recent = read("../docs/community/js/pages/recentMatches.js");
const card = read("../docs/community/js/components/matchCard.js");
const playerCard = read("../docs/community/js/components/playerMatchCard.js");
const playerSearch = read("../docs/community/js/pages/playerSearch.js");
const css = read("../docs/community/css/matches.css");

assert.doesNotMatch(entry, /Promise\.all\(\[loadRecent\(\),loadLiveMatch\(\)\]\)[\s\S]*applyRoute\(\)/);
assert.match(entry, /await applyRoute\(\);\s*void loadLiveMatch\(\);/);
assert.match(card, /data-lazy-scoreboard/);
assert.doesNotMatch(card, /scoreboard\(match\)/);
assert.match(recent, /placeholder\.outerHTML = scoreboard\(match\)/);
assert.match(playerCard, /data-lazy-scoreboard/);
assert.match(playerSearch, /renderScoreboardRows\(data\.match, userId\)/);
assert.doesNotMatch(playerSearch, /server-stats/);
assert.doesNotMatch(playerSearch, /Promise\.all\(\[\s*apiGet\(`\/api\/community\/players[\s\S]*admin\/replays/);
assert.match(playerSearch, /void hydrateReplayDownloads\(target, internalMatches, userId, guildId\)/);
assert.match(playerSearch, /data-personal-match-feed><\/div>/);
assert.match(css, /content-visibility:auto/);

console.log("community loading performance checks passed");
