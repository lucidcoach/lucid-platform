import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = (path) => readFileSync(new URL(path, import.meta.url), "utf8");
const tokens = read("../docs/community/css/tokens.css");
const layout = read("../docs/community/css/layout.css");
const profile = read("../docs/community/css/profile.css");
const matches = read("../docs/community/css/matches.css");
const playerSearch = read("../docs/community/js/pages/playerSearch.js");

assert.match(tokens, /--content:\s*1120px/);
assert.match(layout, /\.community-main[^}]+var\(--content\)/);
assert.match(profile, /#recentSearches\{grid-template-columns:repeat\(3,minmax\(0,1fr\)\)\}/);
assert.match(profile, /profile-dashboard-grid\{grid-template-columns:minmax\(380px,1\.2fr\) minmax\(350px,1\.1fr\) minmax\(315px,\.95fr\)/);
assert.match(profile, /profile-summary-panel>\.profile-rank-switcher\{margin:0;padding:0;border:0;background:transparent\}/);
assert.match(profile, /role-tier-main\{grid-template-columns:minmax\(112px,1fr\) 110px 50px!important;gap:5px!important\}/);
assert.match(profile, /summoner-profile-icon\.title-icon\{width:56px!important;height:56px!important\}/);
assert.match(profile, /profile-dashboard-grid>\.associate-stats-panel\{padding:16px\}/);
assert.match(profile, /@media\(max-width:1150px\)[\s\S]+grid-template-columns:minmax\(360px,1\.05fr\) minmax\(350px,1fr\)/);
assert.match(profile, /associate-row[^}]+min-height:42px/);
assert.match(matches, /#recentView,[\s\S]+max-width:100%!important/);
assert.doesNotMatch(playerSearch, /<div class="profile-champion-panel">/);

console.log("community density checks passed");
