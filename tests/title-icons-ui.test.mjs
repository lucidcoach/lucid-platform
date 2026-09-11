import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const admin = readFileSync(new URL("../docs/community/js/pages/communityAdmin.js", import.meta.url), "utf8");
const profile = readFileSync(new URL("../docs/community/js/pages/playerSearch.js", import.meta.url), "utf8");

for (const text of ["이미지 편집", "이미지 제거", "customIconUrl", "championNames", "iconSource"]) {
  assert.match(admin, new RegExp(text));
}
assert.match(admin, /method:"DELETE"/);
assert.match(profile, /equippedTitleBadge\(p\.equippedTitle\)/);
assert.match(profile, /title\.iconSource === "champion"/);
assert.match(profile, /titleProfileIcon\(p\.equippedTitle, scrimIcon\)/);
assert.match(profile, /roleBadges\(p\.roleBadges \|\| \[\]\)/);
assert.match(profile, /title\.iconSource === "custom"/);
assert.match(profile, /String\(title\.displayTitle\)\.startsWith\(title\.iconEmoji\)/);

console.log("title icon admin and profile checks passed");
