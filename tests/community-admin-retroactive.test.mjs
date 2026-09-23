import assert from "node:assert/strict";
import fs from "node:fs";

const source = fs.readFileSync(new URL("../docs/community/js/pages/communityAdmin.js", import.meta.url), "utf8");

assert.match(source, /전적 소급 복구/);
assert.match(source, /\["retro","리플레이 소급"/);
assert.match(source, /retro:retroPanel/);
assert.match(source, /activeSection==="retro"/);
assert.match(source, /retroactive-rofl\/upload\?guildId=/);
assert.match(source, /retroactive-rofl\/apply/);
assert.match(source, /confirmNewMatch:completeMissing/);
assert.match(source, /기존 승패\/MMR은 유지/);
assert.match(source, /participantMapped/);
assert.match(source, /data-retro-reinspect/);
assert.match(source, /retroactive-rofl\/reinspect/);
assert.match(source, /data-retro-mode="new"/);
assert.match(source, /data-retro-mode="replace"/);
assert.match(fs.readFileSync(new URL("../docs/community/js/app-report6.js", import.meta.url), "utf8"), /communityAdmin\.js\?v=20260923ops2/);

console.log("community admin retroactive ROFL checks passed");
