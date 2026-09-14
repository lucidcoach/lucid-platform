import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const admin = readFileSync(new URL("../docs/community/js/pages/communityAdmin.js", import.meta.url), "utf8");
const profile = readFileSync(new URL("../docs/community/js/pages/playerSearch.js", import.meta.url), "utf8");
const adminCss = readFileSync(new URL("../docs/community/css/admin.css", import.meta.url), "utf8");

for (const text of ["이미지 편집", "기본 이미지로 복원", "선택 취소", "customIconUrl", "championNames", "iconSource"]) {
  assert.match(admin, new RegExp(text));
}
assert.match(admin, /method:"DELETE"/);
for (const text of ["TITLE_ICON_MAX_BYTES", "validateTitleIcon", "URL.createObjectURL", "URL.revokeObjectURL", "변경 미리보기", "이미지 크기는 256×256이어야 합니다.", "이미지는 512KB 이하여야 합니다.", "지원하지 않는 이미지 형식입니다.", "커스텀 이미지 사용 중", "기본 이미지 사용 중", "현재 칭호 전용 이미지를 제거하고 기본 이미지로 복원할까요?"]) {
  assert.match(admin, new RegExp(text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")));
}
assert.match(admin, /data-title-icon-save disabled/);
assert.match(admin, /disabled=!preview\.valid/);
assert.match(admin, /titleIconFileInfo\(file,preview\.width,preview\.height\)/);
assert.match(admin, /preview\.errors\.map/);
assert.match(admin, /const url=URL\.createObjectURL\(file\);titlePreviewUrl=url;const markup=[\s\S]+showTitleIconPreview\(row,markup,"변경 미리보기"[\s\S]+await validateTitleIcon\(file,url\)/);
assert.match(adminCss, /#titleIconStatus\.is-error\{color:var\(--danger\)\}/);
assert.match(admin, /titleSubcategory/);
assert.match(admin, /primaryCategory/);
assert.match(profile, /equippedTitleBadge\(p\.equippedTitle\)/);
assert.match(profile, /칭호 없음/);
assert.match(profile, /title\.iconSource === "champion"/);
assert.match(profile, /titleProfileIcon\(p\.equippedTitle, scrimIcon\)/);
assert.doesNotMatch(profile, /roleBadges\(/);
assert.doesNotMatch(profile, /profile-role-badges/);
assert.match(profile, /title\.iconSource === "custom"/);
assert.match(profile, /String\(title\.displayTitle\)\.startsWith\(title\.iconEmoji\)/);

console.log("title icon admin and profile checks passed");
