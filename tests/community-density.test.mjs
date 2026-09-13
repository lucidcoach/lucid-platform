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
assert.match(profile, /profile-dashboard-grid\{grid-template-columns:minmax\(370px,1\.18fr\) minmax\(350px,1\.1fr\) minmax\(325px,\.97fr\)/);
assert.match(profile, /profile-dashboard-grid>\.associate-stats-panel\{padding:16px\}/);
assert.match(profile, /@media\(max-width:1150px\)[\s\S]+grid-template-columns:minmax\(360px,1\.05fr\) minmax\(350px,1fr\)/);
assert.match(profile, /associate-row[^}]+min-height:42px/);
assert.match(matches, /#recentView,[\s\S]+max-width:100%!important/);
assert.doesNotMatch(playerSearch, /<div class="profile-champion-panel">/);

console.log("community density checks passed");
