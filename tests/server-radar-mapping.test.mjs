import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const report = readFileSync(new URL("../docs/community/js/pages/gameAnalysisReport6.js", import.meta.url), "utf8");

for (const mapping of [
  '["lanePhaseScore","라인전"]', '["gpm","골드획득"]', '["dpm","데미지"]',
  '["teamfightScore","한타 기여도"]', '["macroScore","운영"]', '["influenceScore","영향력"]',
  '["jungleGrowthScore","성장"]', '["gankScore","갱킹"]', '["skirmishScore","교전"]',
  '["objectiveScore","오브젝트"]', '["jungleDamageScore","데미지"]', '["jungleMacroScore","운영"]',
]) assert.ok(report.includes(mapping), mapping);

assert.match(report, /values\.every\(Number\.isFinite\)\?values:null/);
assert.match(report, /비교 기록 없음/);

console.log("server radar mapping checks passed");
