import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";

const read = path => readFileSync(new URL(path, import.meta.url), "utf8");
const lecture = read("../docs/index.html");
const community = read("../docs/community/index.html");
const view = read("../docs/community/js/view.js");

for (const file of [
  "../docs/favicon.ico",
  "../docs/assets/favicon-16x16-v20260914.png",
  "../docs/assets/favicon-32x32-v20260914.png",
  "../docs/assets/apple-touch-icon-v20260914.png",
  "../docs/assets/lucid-logo-20260914.png",
]) assert.equal(existsSync(new URL(file, import.meta.url)), true, `${file} is missing`);

assert.match(lecture, /<title>Lucid 강의 \| 롤 코칭<\/title>/);
assert.match(lecture, /property="og:site_name" content="Lucid"/);
assert.match(community, /favicon-32x32-v20260914\.png/);
assert.match(community, /property="og:site_name" content="Lucid"/);
assert.match(view, /Lucid 전적검색 \| 롤 내전 · 전적 분석/);
assert.match(view, /Lucid 게임 분석 \| 내전 리포트/);
assert.match(view, /Lucid 랭킹 \| 내전 · 포지션 랭킹/);
assert.match(view, /Lucid 포인트 상점/);
assert.match(view, /document\.title = title/);

console.log("browser branding checks passed");
