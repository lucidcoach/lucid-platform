import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createMarketPage } from "../docs/js/pages/market.js";

const read = (path) => readFileSync(new URL(path, import.meta.url), "utf8");
const page = read("../docs/index.html");
const market = read("../docs/js/pages/market.js");
const styles = read("../docs/css/components.css");

assert.match(page, /bookingAvailabilityDate[\s\S]+bookingAvailabilityTimes[\s\S]+bookingAvailabilitySlot[^>]+type="hidden"/);
assert.match(market, /addLocalDays\(fromDate, 13\)/);
assert.match(market, /startsAtMs > Date\.now\(\)/);
assert.match(market, /availabilityDateKey[\s\S]+data-availability-slot/);
assert.match(market, /현재 예약 가능한 시간이 없습니다/);
assert.doesNotMatch(market, /timeInput\.readOnly = false/);
assert.match(styles, /\.availability-time-list[^}]+grid-template-columns/);

const { normalizeAvailabilitySlot } = createMarketPage({ render() {}, openAuthModal() {}, startTossPayment() {}, loadCoachesFromApi() {} });
assert.equal(normalizeAvailabilitySlot({ id: "past", startsAt: new Date(Date.now() - 60_000).toISOString(), status: "open" }).available, false);
assert.equal(normalizeAvailabilitySlot({ id: "future", startsAt: new Date(Date.now() + 60_000).toISOString(), status: "open" }).available, true);

console.log("booking availability UX checks passed");
