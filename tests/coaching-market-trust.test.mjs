import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = (path) => readFileSync(new URL(path, import.meta.url), "utf8");
const market = read("../docs/js/pages/market.js");
const cards = read("../docs/js/components/coachCard.js");
const mobileCss = read("../docs/css/ui-overhaul.css");

assert.doesNotMatch(market, /getOriginalPrice|amount \* 1\.7/);
assert.doesNotMatch(cards, /getOriginalPrice|amount \* 1\.7/);
assert.match(market, /category\.id !== "academy"/);
assert.match(market, /count \? `★ .*후기.*` : "후기 없음"/);
assert.match(market, /state\.siteSettings\?\.maintenance !== false/);
assert.match(market, /data-open-auth="guest">\$\{escapeHtml\(state\.siteSettings\.maintenanceCta\)\}/);
assert.match(market, /<div id="lessonBookingMount"><\/div>/);
assert.match(market, /시간 확인은 로그인 없이 가능/);
assert.match(market, /mountBookingForm\("lessonBookingMount", coach\)/);
assert.match(mobileCss, /\.filter-block,.filter-row,.market-head,.featured-card[^{]+\{min-width:0;max-width:100%\}/);

console.log("coaching market trust checks passed");
