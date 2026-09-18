import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const html = readFileSync(new URL("../docs/community/index.html", import.meta.url), "utf8");
const scrims = readFileSync(new URL("../docs/community/js/scrims.js", import.meta.url), "utf8");
assert.match(scrims, /weekly-ranking-avatar/);
assert.match(scrims, /data\.player\?\.equippedTitle/);
assert.doesNotMatch(html, /MATCH HISTORY/);
assert.match(html, /data-match-category="all">전체[\s\S]*data-match-category="scrim">내전[\s\S]*data-match-category="tournament">토너먼트[\s\S]*data-match-category="event">이벤트/);
assert.doesNotMatch(html, /data-match-category="(?:league|aram)"/);

console.log("server history filter checks passed");
