import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const source = readFileSync(new URL("../docs/community/js/pages/communityAdmin.js", import.meta.url), "utf8");

for (const text of ["챔피언 숙련", "챔피언:", "기본 칭호:", "특수 칭호:", "최초 획득:", "서버 최초", "복합 서버 최초"]) {
  assert.match(source, new RegExp(text));
}
for (const field of ["row.champion", "row.defaultTitle", "row.overrideTitle", "row.claimed", "row.claimantName"]) {
  assert.match(source, new RegExp(field.replace(".", "\\.")));
}

console.log("champion mastery admin catalog checks passed");
