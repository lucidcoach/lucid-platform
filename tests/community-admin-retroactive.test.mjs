import assert from "node:assert/strict";
import fs from "node:fs";

const source = fs.readFileSync(new URL("../docs/community/js/pages/communityAdmin.js", import.meta.url), "utf8");

assert.match(source, /전적 소급 복구/);
assert.match(source, /retroactive-rofl\/upload\?guildId=/);
assert.match(source, /retroactive-rofl\/apply/);
assert.match(source, /confirmNewMatch:completeMissing/);
assert.match(source, /기존 승패\/MMR은 유지/);
assert.match(source, /participantMapped/);

console.log("community admin retroactive ROFL checks passed");
