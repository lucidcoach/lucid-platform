import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { runInNewContext } from "node:vm";

const source = readFileSync(new URL("../docs/community/js/pages/playerSearch.js", import.meta.url), "utf8");
const chooseRole = source.slice(source.indexOf("function mostPlayedRole("), source.indexOf("function bindLpTrend("));
const mostPlayedRole = runInNewContext(`${chooseRole}; mostPlayedRole`, { normalizeRoleKey: (role) => role || "" });
const roles = [{ role:"탑", games:12 }, { role:"미드", games:4 }, { role:"정글", games:8 }];
assert.equal(mostPlayedRole(roles), "탑");
assert.equal(mostPlayedRole([{ role:"탑", games:0 }, { role:"미드", games:0 }], [{ players:[{ userId:"1", role:"탑" }] }], "1"), "탑");
assert.equal(mostPlayedRole([]), "미드");
assert.match(source, /selectProfileRole\(defaultRole\)/);
const details = source.slice(source.indexOf("function roleDetails("), source.indexOf("function officialRanksPanel("));
const roleDetails = runInNewContext(`${details}; roleDetails`, {
  normalizeRoleKey: (role) => role,
  tierLeaguePoints: (_tier, value) => value,
});
const matches = [
  { players:[{ userId:"1", role:"미드", result:"win", kda:4, cs:180, aiScore:92, award:"MVP", afterMmr:120, mmrDelta:20 }] },
  { players:[{ userId:"1", role:"탑", result:"loss", kda:2, cs:100, aiScore:40, award:"ACE", afterMmr:80, mmrDelta:-8 }] },
];
const mid = roleDetails(matches, "1", "미드", { placed:true, tier:"M", mmr:120, recent10Games:1, recent10Delta:20 });
const top = roleDetails(matches, "1", "탑", { placed:true, tier:"G", mmr:80 });
assert.match(mid, /1경기 1승 0패/);
assert.match(mid, /MVP 1회/);
assert.doesNotMatch(mid, /ACE 1회/);
assert.match(top, /1경기 0승 1패/);
assert.match(top, /ACE 1회/);
assert.doesNotMatch(top, /MVP 1회/);
