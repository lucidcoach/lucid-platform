import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = (path) => readFileSync(new URL(path, import.meta.url), "utf8");
const html = read("../docs/index.html");
const page = read("../docs/js/pages/coachSelf.js");
const service = read("../docs/js/coachService.js");
const css = read("../docs/css/ui-overhaul.css");

assert.match(html, /id="coachCalendarPanel"/);
assert.match(html, /외부 강의[\s\S]+개인 일정[\s\S]+휴무 \/ 예약 불가/);
assert.match(page, /fetchCoachCalendar[\s\S]+createCoachCalendarEvent[\s\S]+updateCoachCalendarEvent/);
assert.match(page, /data-calendar-date[\s\S]+openCalendarEventDialog/);
assert.match(page, /data-calendar-coach=""[\s\S]+전체/);
assert.match(page, /runCoachReservationAction[\s\S]+"complete"[\s\S]+"reject"/);
assert.match(service, /\/api\/coach\/calendar/);
assert.match(css, /\.calendar-grid[^{]*\{[^}]*grid-template-columns/);
assert.match(css, /body\[data-theme="dark"\]|var\(--panel\)/);

console.log("coach calendar checks passed");
