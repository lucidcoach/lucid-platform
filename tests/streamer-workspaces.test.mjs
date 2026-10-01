import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = (path) => readFileSync(new URL(path, import.meta.url), "utf8");
const publicPage = read("../docs/s/index.html");
const script = read("../docs/s/streamer.js");
const streaming = read("../docs/streaming/index.html");

for (const label of ["홈", "콘텐츠", "내전", "랭킹", "관리"]) assert.match(publicPage, new RegExp(`>${label}<`));
assert.match(script, /public\/workspaces\/\$\{encodeURIComponent\(slug\)\}/);
assert.match(script, /workspaces\/\$\{encodeURIComponent\(slug\)\}\/contents/);
assert.match(script, /data-winner="A"/);
assert.match(script, /data-save-ranking/);
assert.match(script, /overlayId/);
assert.match(streaming, /id="streamerApply"[^>]*>스트리머 전용 서버 신청/);
assert.match(streaming, /새 Workspace 생성/);
assert.doesNotMatch(script + streaming, /결제|입금|PG|구독/);

console.log("streamer workspace page checks passed");
