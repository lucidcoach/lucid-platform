import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const app = readFileSync(new URL("../docs/community/js/app-report6.js", import.meta.url), "utf8");
const player = readFileSync(new URL("../docs/community/js/pages/playerSearch.js", import.meta.url), "utf8");

assert.match(app, /playerView:\{championFilter,scrollY:window\.scrollY\}/);
assert.match(app, /filter\.dispatchEvent\(new Event\("input"\)\)/);
assert.match(app, /window\.scrollTo\(0, Number\(saved\.scrollY \|\| 0\)\)/);
assert.match(app, /routeState:event\.state/);
assert.match(player, /data-rank-switch="riot"/);
assert.match(player, /profile-rank-switcher-body/);
assert.match(player, /data-rank-switch-title/);
assert.match(player, /panel\.hidden=panel\.dataset\.rankPanel/);
assert.match(player, /button\.dataset\.rankSwitch=showRiot\?"internal":"riot"/);

console.log("player navigation state checks passed");
