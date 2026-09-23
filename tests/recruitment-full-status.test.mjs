import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";

const source = readFileSync(new URL("../docs/community/js/pages/recruitment.js", import.meta.url), "utf8")
  .replace(/^import .*;\r?\n/gm, "")
  .replace("export async function loadRecruitments()", "async function loadRecruitments()");
const { card, schedule } = vm.runInNewContext(`${source}\n({ card: queueCard, schedule: scheduleText })`, { escapeHtml: String });
const full = card({ title: "칼바람", queueKey: "aram", participantCount: 10, capacity: 10, joinUrl: "https://discord.com" });
assert.match(full, /마감/);
assert.doesNotMatch(full, /모집 중|참가하기/);
assert.match(card({ participantCount: 9, capacity: 10, joinUrl: "https://discord.com" }), /모집 중|참가하기/);
const scheduled = card({ title: "2️⃣0️⃣시 내전 🕹️", scheduledAt: "2026-09-24 00:00:00", bestOf: 1 });
assert.match(scheduled, /내전 🕹️/);
assert.doesNotMatch(scheduled, /2️⃣0️⃣시|단판 2경기/);
assert.match(scheduled, /단판/);
assert.match(schedule({ scheduledAt: "2026-09-24 00:00:00" }), /00:00 KST$/);
