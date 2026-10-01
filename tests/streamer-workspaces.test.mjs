import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = (path) => readFileSync(new URL(path, import.meta.url), "utf8");
const publicPage = read("../docs/s/index.html");
const script = read("../docs/s/streamer.js");
const manageCss = read("../docs/s/manage.css");
const streaming = read("../docs/streaming/index.html");
const streamingScript = read("../docs/streaming/streaming.js");
const publicHome = read("../docs/index.html");

assert.match(streaming, /id="adminNav"[^>]*>스트리머 서버 관리<\/button>\s*<button id="contentNav"[^>]*>콘텐츠 관리<\/button>/);
assert.match(streamingScript, /\.\.\/s\/\?slug=\$\{encodeURIComponent\(workspace\.slug\)\}&view=manage/);
assert.match(streaming, /id="registeredPlayersPanel"[\s\S]*등록 참가자[\s\S]*id="registeredPlayerRows"/);
assert.match(streamingScript, /state\.workspace\.canManage \? \(await request\(`\/api\/streaming\/workspaces\/\$\{encodeURIComponent\(slug\)\}\/players`\)\)\.players : \[\]/);
assert.match(streamingScript, /총 \$\{players\.length\}명 · 현재 참가 \$\{state\.queue\.length\}명/);
assert.match(streamingScript, /contentNav"\)\.hidden = !userIsAdmin\(user\)/);
assert.match(script, /if\(!userIsAdmin\(user\)\).*관리자 전용 메뉴입니다/);
assert.match(script, /hidden=!userIsAdmin\(user\)/);
assert.match(manageCss, /\.manage-content\{[^}]*align-content:start/);
assert.match(manageCss, /\.manage-tabs button\.active\{/);
assert.match(script, /data-manage-type="versus">방대방/);
assert.match(script, /data-manage-type="solo_rank_challenge">솔랭내기/);
assert.doesNotMatch(script, /settingsForm|페이지 설정/);

for (const label of ["홈", "전적", "방대방", "솔랭내기", "관리"]) assert.match(publicPage, new RegExp(`>${label}<`));
assert.match(script, /public\/workspaces\/\$\{encodeURIComponent\(slug\)\}/);
assert.match(script, /data\.records\|\|\[\]/);
assert.match(script, /workspaces\/\$\{encodeURIComponent\(slug\)\}\/contents/);
assert.match(script, /data-winner="A"/);
assert.match(script, /data-save-ranking/);
assert.match(script, /overlayId/);
assert.match(streaming, /id="streamerApply"[^>]*>스트리머 전용 서버 신청/);
assert.match(streaming, /id="recordSiteApply"[^>]*>스트리머 전적사이트 신청/);
assert.match(streamingScript, /\.\.\/s\/\?slug=\$\{encodeURIComponent\(item\.slug\)\}&view=records/);
assert.match(streaming, /class="streamer-server-intro"[\s\S]*방대방[\s\S]*솔랭내기[\s\S]*내전·경기 기록[\s\S]*방송용 Overlay/);
assert.doesNotMatch(publicHome, /streamerApply|스트리머 전용 서버 신청|스트리머 전용 Lucid/);
assert.match(streaming, /새 Workspace 생성/);
assert.doesNotMatch(script + streaming, /결제|입금|PG|구독/);

console.log("streamer workspace page checks passed");
