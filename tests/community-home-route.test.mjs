import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = (path) => readFileSync(new URL(path, import.meta.url), "utf8");
const page = read("../docs/community/index.html");
const entry = read("../docs/community/js/app-report6.js");
const matchCard = read("../docs/community/js/components/matchCard.js");
const scrims = read("../docs/community/scrims/index.html");

assert.match(page, /id="homeView" class="content-view active/);
assert.match(page, /<base id="communityBase" href="\.\/">/);
assert.match(page, /communityBase[\s\S]*new URL\("\.\/",location\.href\)\.href/);
assert.match(page, /id="homePlayerSearchForm"[\s\S]*대한민국 서버[\s\S]*id="homeRecentSearches"/);
assert.match(page, /현재 진행 중인 내전[\s\S]*공개된 모집이 없습니다/);
assert.match(entry, /new URL\("scrims\/", COMMUNITY_ROOT_URL\)/);
assert.match(entry, /switchView\("home"\)/);
assert.match(scrims, /searchParams\.set\("view", "recent"\)/);
assert.match(matchCard, /assets\/tiers/);
assert.match(matchCard, /won \? `<span class="team-result-label">승리<\/span>` : ""/);
assert.doesNotMatch(matchCard, /team-result-label">\$\{won \? "승리" : "패배"/);

console.log("community home and scrim route checks passed");
