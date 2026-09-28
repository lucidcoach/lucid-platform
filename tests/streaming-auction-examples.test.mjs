import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = (path) => readFileSync(new URL(path, import.meta.url), "utf8");
const script = read("../docs/streaming/streaming.js");
const css = read("../docs/streaming/streaming.css");
const examples = script.slice(script.indexOf("const exampleChampions"), script.indexOf("async function loadRecordExamples"));

assert.match(script, /linked\.length\?linked:ownedWorkspaces\.filter[^;]+\.slice\(0,1\)/);
assert.match(script, /data-preview-team/);
assert.match(script, /preview=team/);
assert.match(examples, /`소환사 \$\{index\+1\}`/);
assert.match(examples, /ddragon\.leagueoflegends\.com/);
assert.doesNotMatch(examples, /privatePlayerName|focus\.name|item\.name/);
assert.match(css, /\.record-team>div>img/);
assert.match(css, /\.record-kda img/);

console.log("streaming auction preview and anonymous example checks passed");
