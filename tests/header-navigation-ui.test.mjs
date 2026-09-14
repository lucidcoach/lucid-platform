import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = (path) => readFileSync(new URL(path, import.meta.url), "utf8");
const page = read("../docs/community/index.html");
const entry = read("../docs/community/js/app-report6.js");
const auth = read("../docs/community/js/auth.js");
const profile = read("../docs/community/js/pages/playerSearch.js");
const tokens = read("../docs/community/css/tokens.css");

const searchView = page.indexOf('id="searchView"');
const memory = page.indexOf('class="search-memory-panel"');
const searchResults = page.indexOf('id="searchResults"');
assert.ok(searchView < memory && memory < searchResults, "recent searches must belong to searchView");
assert.equal(page.match(/class="search-memory-panel"/g)?.length, 1);
assert.match(entry, /RECENT_SEARCH_LIMIT = 5/);
assert.match(page, /communityProfileMenu/);
assert.match(page, /nav-hierarchy-divider/);
assert.doesNotMatch(page, /id="communityLogoutBtn"/);
assert.match(auth, /preferredDisplayName \|\| riotAccounts\[0\]/);
for (const token of ["--surface-hover", "--surface-active", "--primary-hover", "--primary-active", "--nav-hover", "--focus-ring"]) assert.match(tokens, new RegExp(token));
assert.match(profile, /searchParams\.set\("champions", "1"\)/);
assert.match(profile, /rows\.slice\(0, 6\)/);
assert.doesNotMatch(profile, /`더 보기 \(\$\{rows\.length\}\)`/);
assert.doesNotMatch(profile, /최근 \$\{Number\(data\.sampleGames/);

console.log("header navigation and champion detail checks passed");
