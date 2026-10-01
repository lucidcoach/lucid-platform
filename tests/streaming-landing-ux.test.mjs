import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = (path) => readFileSync(new URL(path, import.meta.url), "utf8");
const page = read("../docs/streaming/index.html");
const script = read("../docs/streaming/streaming.js");
const css = read("../docs/streaming/streaming.css");
const app = read("../docs/app.js");

for (const id of ["mineEyebrow", "mineTitle", "mineDescription", "mineLogin", "accountSection", "workspaceList"]) {
  assert.match(page, new RegExp(`id="${id}"`));
}
assert.match(page, /방송 연결[\s\S]+참가자 선택[\s\S]+팀 편성 · 기록/);
assert.match(script, /user \? "내 방송을 관리하세요"/);
assert.doesNotMatch(script.match(/function accountName[^\n]+/)[0], /preferredDisplayName|riotAccounts/);
assert.doesNotMatch(page, /!참가|참가 대기열|채팅 명령어/);
assert.match(script, /workspace-status\$\{item\.channelId \? " connected"/);
assert.match(script, /연결된 방송이 없습니다/);
assert.match(css, /\.mine-hero\{[^}]+grid-template-columns/);
assert.match(css, /@media\(max-width:600px\)\{\.mine-hero/);
for (const id of ["profileMenu", "profileMenuName", "profileDiscordState", "profileBroadcastState", "profileAccount", "profileBroadcast", "profileLogout"]) {
  assert.match(page, new RegExp(`id="${id}"`));
}
assert.match(script, /치지직 · \$\{connected\[0\]\.channelName/);
assert.match(script, /logoutAuthSessions\(\)/);
assert.match(css, /\.profile-menu-popover\{/);
assert.match(app, /URLSearchParams\(location\.search\)\.get\("view"\) === "account"/);

console.log("streaming landing UX checks passed");
