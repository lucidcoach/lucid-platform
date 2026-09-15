import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = (path) => readFileSync(new URL(path, import.meta.url), "utf8");
const page = read("../docs/community/index.html");
const entry = read("../docs/community/js/app-report6.js");
const matchCard = read("../docs/community/js/components/matchCard.js");
const scrims = read("../docs/community/scrims/index.html");
const homeCss = read("../docs/community/css/community-home.css");
const recruitment = read("../docs/community/js/pages/recruitment.js");

assert.match(page, /id="homeView" class="content-view active/);
assert.match(page, /<base id="communityBase" href="\.\/">/);
assert.match(page, /communityBase[\s\S]*endsWith\("\/scrims"\)\?"\.\.\/":"\.\/"/);
assert.match(page, /id="homePlayerSearchForm"[\s\S]*대한민국 서버[\s\S]*id="homeRecentSearches"/);
assert.match(page, /소환사를 검색해보세요/);
assert.match(page, /현재 진행 중인 내전[\s\S]*현재 모집 중인 내전이 없습니다/);
assert.doesNotMatch(page, /LUCID COMMUNITY|LIVE MATCH|RECRUITMENT|SERVER SCRIMS/);
assert.match(page, /aria-label="최근 검색"/);
assert.match(homeCss, /recent-label-compact\{display:none\}/);
assert.doesNotMatch(homeCss, /home-search-recent\{display:none/);
assert.match(homeCss, /home-live-member \.current-form\{display:none/);
assert.match(recruitment, /apiGet\("\/api\/community\/recruitments"\)/);
assert.match(homeCss, /\.recruitment-preview-button\{[\s\S]*var\(--primary-subtle\)/);
assert.match(entry, /loadRecruitments/);
assert.match(entry, /new URL\("scrims\/", COMMUNITY_ROOT_URL\)/);
assert.match(entry, /switchView\("home"\)/);
assert.match(entry, /window\.location\.replace\(recentUrl\(\)\)/);
assert.doesNotMatch(scrims, /fetch\("\.\.\/index\.html"\)|document\.write/);
assert.match(scrims, /js\/scrims\.js\?v=20260915reference4/);
assert.match(scrims, /id="weeklyRanking"/);
assert.match(matchCard, /assets\/tiers/);
assert.match(matchCard, /<small>\$\{team === "blue" \? "BLUE TEAM" : "RED TEAM"\}<\/small>\$\{won \? `<span class="team-result-label">승리<\/span>` : ""\}/);
assert.doesNotMatch(matchCard, /team-result-label">\$\{won \? "승리" : "패배"/);

console.log("community home and scrim route checks passed");
