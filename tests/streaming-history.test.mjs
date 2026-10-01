import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { VIEW_ROUTES, viewFromSearch, viewUrlFor } from "../docs/streaming/history-state.js";

const source = readFileSync(new URL("../docs/streaming/streaming.js", import.meta.url), "utf8");
const base = "https://lucidgame.kr/streaming/";

assert.equal(VIEW_ROUTES.quick, "team");
assert.equal(viewFromSearch("?view=team"), "quick");
assert.equal(viewFromSearch("?view=quick"), "quick");
assert.equal(viewFromSearch("?view=auction"), "auction");
assert.equal(viewFromSearch("?view=history"), "records");
assert.equal(viewFromSearch("?view=records"), "records");
assert.equal(viewFromSearch("?channel=streamer-a"), "workspace");
assert.deepEqual(
  ["mine","quick","auction","records"].map((view) => viewUrlFor(base, view)),
  ["/streaming/","/streaming/?view=team","/streaming/?view=auction","/streaming/?view=history"],
);
assert.equal(viewUrlFor(`${base}?view=history`, "auction", "streamer-a"), "/streaming/?view=auction&channel=streamer-a");
assert.match(source, /history\.pushState\(\{streamingView:name\}/);
assert.match(source, /history\.pushState\(\{streamingView:"workspace"\}/);
assert.match(source, /addEventListener\("popstate",\(\)=>applyLocation\(\)\)/);
assert.match(source, /await applyLocation\(\)/);
assert.doesNotMatch(source, /history\.replaceState/);

console.log("streaming browser history checks passed");
