import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = (path) => readFileSync(new URL(path, import.meta.url), "utf8");
const page = read("../docs/streaming/index.html");
const script = read("../docs/streaming/streaming.js");
const css = read("../docs/streaming/streaming.css");

for (const id of ["mineEyebrow", "mineTitle", "mineDescription", "mineLogin", "accountSection", "workspaceList"]) {
  assert.match(page, new RegExp(`id="${id}"`));
}
assert.match(page, /방송 연결[\s\S]+참가자 모집[\s\S]+팀 편성 · 기록/);
assert.match(script, /user \? `\$\{user\.displayName \|\| "스트리머"\}님의 방송을 관리하세요`/);
assert.match(script, /workspace-status\$\{item\.channelId \? " connected"/);
assert.match(script, /연결된 방송이 없습니다/);
assert.match(css, /\.mine-hero\{[^}]+grid-template-columns/);
assert.match(css, /@media\(max-width:600px\)\{\.mine-hero/);

console.log("streaming landing UX checks passed");
