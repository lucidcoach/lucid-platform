import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const app = readFileSync(new URL("../docs/community/js/app-report6.js", import.meta.url), "utf8");

assert.match(app, /playerView:\{championFilter,scrollY:window\.scrollY\}/);
assert.match(app, /filter\.dispatchEvent\(new Event\("input"\)\)/);
assert.match(app, /window\.scrollTo\(0, Number\(saved\.scrollY \|\| 0\)\)/);
assert.match(app, /routeState:event\.state/);

console.log("player navigation state checks passed");
