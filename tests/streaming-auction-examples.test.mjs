import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = (path) => readFileSync(new URL(path, import.meta.url), "utf8");
const script = read("../docs/streaming/streaming.js");
const css = read("../docs/streaming/streaming.css");
const examples = script.slice(script.indexOf("const exampleChampions"), script.indexOf("async function loadRecordExamples"));

assert.match(script, /linked\.length\?linked:ownedWorkspaces\.filter[^;]+\.slice\(0,1\)/);
assert.match(script, /data-preview-team/);
assert.match(script, /preview=team/);
assert.match(script, /!\(auctionState\?\.canManage&&auctionPanel==="setup"\)\)loadAuction/);
assert.match(script, /LIVE AUCTION/);
assert.match(script, /team\.points>=nextBid/);
assert.match(script, /data-expected-amount/);
assert.match(script, /peakTier/);
assert.match(script, /TEAM CAPTAINS/);
assert.match(script, /item\.name\|\|item\.riotId/);
assert.match(script, /auction-waiting-name/);
assert.doesNotMatch(script, /낙찰 확정/);
assert.doesNotMatch(script, /name="bidSeconds"/);
assert.match(script, /자동 낙찰까지/);
assert.match(script, /<b>대기 /);
assert.match(script, /<b>유찰 /);
assert.match(script, /\.\.\/assets\/logo\.png/);
assert.doesNotMatch(script, /\.\.\/logo\.png/);
assert.match(script, /aria-label="남은 입찰 시간"/);
assert.match(css, /\.auction-team\.is-leading/);
assert.match(css, /\.auction-stage\.is-urgent/);
assert.match(css, /body:has\(#auctionView\.active \.auction-stage\)>main/);
assert.match(examples, /`소환사 \$\{index\+1\}`/);
assert.match(examples, /ddragon\.leagueoflegends\.com/);
assert.doesNotMatch(examples, /privatePlayerName|focus\.name|item\.name/);
assert.match(css, /\.record-team>div>img/);
assert.match(css, /\.record-kda img/);

console.log("streaming auction preview and anonymous example checks passed");
