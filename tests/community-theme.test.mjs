import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const html=readFileSync(new URL("../docs/community/index.html",import.meta.url),"utf8");
const app=readFileSync(new URL("../docs/community/js/app-report6.js",import.meta.url),"utf8");
const tokens=readFileSync(new URL("../docs/community/css/tokens.css",import.meta.url),"utf8");

assert.match(html,/id="communityThemeBtn"/);
assert.match(html,/localStorage\.getItem\("coach-theme"\)/);
assert.match(app,/localStorage\.setItem\(THEME_KEY,next\)/);
assert.match(tokens,/html\[data-theme="light"\]/);

console.log("community theme checks passed");
