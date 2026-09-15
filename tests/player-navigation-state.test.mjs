import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const app = readFileSync(new URL("../docs/community/js/app-report6.js", import.meta.url), "utf8");
const player = readFileSync(new URL("../docs/community/js/pages/playerSearch.js", import.meta.url), "utf8");
const profile = readFileSync(new URL("../docs/community/css/profile.css", import.meta.url), "utf8");

assert.match(app, /playerView:\{championFilter,personalQueue,scrollY:window\.scrollY\}/);
assert.match(app, /filter\.dispatchEvent\(new Event\("input"\)\)/);
assert.match(app, /saved\.personalQueue \|\| "internal"/);
assert.match(app, /window\.scrollTo\(0, Number\(saved\.scrollY \|\| 0\)\)/);
assert.match(app, /routeState:event\.state/);
assert.match(player, /data-rank-switch="riot"/);
assert.match(player, /profile-rank-switcher-body/);
assert.match(player, /data-rank-switch-title/);
assert.match(player, /panel\.hidden=panel\.dataset\.rankPanel/);
assert.match(player, /button\.dataset\.rankSwitch=showRiot\?"internal":"riot"/);
assert.match(player, /\[\["internal","내전"\],\["solo","솔랭"\],\["flex","자랭"\],\["normal","일반"\],\["aram","칼바람"\],\["all","전체"\]\]/);
assert.match(player, /let category = "internal"/);
assert.match(player, /const pageSize = 10/);
assert.match(player, /visible\.slice\(\(page - 1\) \* pageSize, page \* pageSize\)/);
assert.match(player, /class="personal-history-pagination"/);
assert.match(player, /scrollIntoView\(\{ behavior:"smooth", block:"start" \}\)/);
assert.match(profile, /\.personal-feed\{align-content:start;gap:10px;min-height:930px\}/);
assert.match(profile, /input::\-webkit-search-decoration\{display:none\}/);

console.log("player navigation state checks passed");
