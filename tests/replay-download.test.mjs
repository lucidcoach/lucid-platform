import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const search = readFileSync(new URL("../docs/community/js/pages/playerSearch.js", import.meta.url), "utf8");
const card = readFileSync(new URL("../docs/community/js/components/playerMatchCard.js", import.meta.url), "utf8");
assert.match(search, /isCommunityAdmin\(\) \? apiGet\("\/api\/community\/admin\/replays\?limit=500"/);
assert.match(search, /credentials:"include"/);
assert.match(search, /ROFL 다운로드에 실패했습니다/);
assert.match(card, /match\.replay\?\.id/);
assert.match(card, /data-replay-download/);

console.log("admin replay download checks passed");
