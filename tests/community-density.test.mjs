import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = (path) => readFileSync(new URL(path, import.meta.url), "utf8");
const tokens = read("../docs/community/css/tokens.css");
const layout = read("../docs/community/css/layout.css");
const profile = read("../docs/community/css/profile.css");
const matches = read("../docs/community/css/matches.css");
const playerSearch = read("../docs/community/js/pages/playerSearch.js");
const utils = read("../docs/community/js/utils.js");

assert.match(tokens, /--content:\s*1120px/);
assert.match(layout, /\.community-main[^}]+var\(--content\)/);
assert.match(profile, /#recentSearches\{grid-template-columns:repeat\(3,minmax\(0,1fr\)\)\}/);
assert.match(profile, /profile-dashboard-grid\{grid-template-columns:minmax\(380px,1\.2fr\) minmax\(350px,1\.1fr\) minmax\(315px,\.95fr\)/);
assert.match(profile, /profile-summary-panel>\.profile-rank-switcher\{margin:16px 0 0;padding:0;border:0;background:transparent\}/);
assert.match(profile, /role-tier-main\{grid-template-columns:104px 103px 46px!important;justify-content:start;gap:3px!important\}/);
assert.match(profile, /summoner-profile-stack \.summoner-profile-icon\{width:60px!important;height:60px!important\}/);
assert.match(profile, /profile-name-with-icon\{display:grid!important;grid-template-columns:62px minmax\(0,1fr\) auto!important/);
assert.match(profile, /profile-rank-switcher>\.profile-section-title\{margin-bottom:10px\}/);
assert.match(playerSearch, /profile-title-action-row">\$\{equippedTitleBadge\(p\.equippedTitle\)}<\/div><div class="profile-name-main/);
assert.match(playerSearch, /<\/div><div class="profile-refresh-wrap profile-refresh-above-name">/);
assert.match(playerSearch, /role-tier-result/);
assert.doesNotMatch(playerSearch, /profile-overview profile-overview-compact/);
assert.match(playerSearch, /data-profile-live hidden>● LIVE/);
assert.match(playerSearch, /currentGameForPlayer\(userId, guildId\)/);
assert.match(playerSearch, /profile-equipped-title is-empty"><i aria-hidden="true">◇<\/i><b>칭호 없음<\/b>/);
assert.match(profile, /profile-dashboard-grid>\.associate-stats-panel\{padding:16px\}/);
assert.match(profile, /@media\(max-width:1150px\)[\s\S]+grid-template-columns:minmax\(360px,1\.05fr\) minmax\(350px,1fr\)/);
assert.match(profile, /associate-row[^}]+min-height:42px/);
assert.match(matches, /#recentView,[\s\S]+max-width:100%!important/);
assert.doesNotMatch(playerSearch, /<div class="profile-champion-panel">/);
assert.match(utils, /return `BO\$\{bestOf\}\\n매치 \$\{seriesGame\}`/);
assert.match(matches, /\.match-mode,\.result-meta>div\{white-space:pre-line\}/);

console.log("community density checks passed");
