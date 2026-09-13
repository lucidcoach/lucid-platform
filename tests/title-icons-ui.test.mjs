import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const admin = readFileSync(new URL("../docs/community/js/pages/communityAdmin.js", import.meta.url), "utf8");
const profile = readFileSync(new URL("../docs/community/js/pages/playerSearch.js", import.meta.url), "utf8");

for (const text of ["이미지 편집", "이미지 제거", "customIconUrl", "championNames", "iconSource"]) {
  assert.match(admin, new RegExp(text));
}
assert.match(admin, /method:"DELETE"/);
for (const text of ["TITLE_ICON_MAX_BYTES", "validateTitleIcon", "URL.createObjectURL", "URL.revokeObjectURL", "변경 미리보기", "이미지는 256×256이어야 합니다.", "이미지는 512KB 이하여야 합니다.", "지원하지 않는 이미지 형식입니다."]) {
  assert.match(admin, new RegExp(text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")));
}
assert.match(admin, /titleSubcategory/);
assert.match(admin, /primaryCategory/);
assert.match(profile, /equippedTitleBadge\(p\.equippedTitle\)/);
assert.match(profile, /title\.iconSource === "champion"/);
assert.match(profile, /titleProfileIcon\(p\.equippedTitle, scrimIcon\)/);
assert.match(profile, /roleBadges\(p\.roleBadges \|\| \[\], p\.equippedTitle\)/);
assert.match(profile, /String\(role\.label \|\| ""\)\.trim\(\) !== titleName/);
assert.match(profile, /title\.iconSource === "custom"/);
assert.match(profile, /String\(title\.displayTitle\)\.startsWith\(title\.iconEmoji\)/);

console.log("title icon admin and profile checks passed");
