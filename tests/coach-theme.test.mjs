import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const html = readFileSync(new URL("../docs/index.html", import.meta.url), "utf8");
const themeCss = readFileSync(new URL("../docs/css/ui-overhaul.css", import.meta.url), "utf8");
const themeInit = html.indexOf('localStorage.getItem("coach-theme")');
const stylesheet = html.indexOf('<link rel="stylesheet"');
const bodyTheme = html.indexOf("document.body.dataset.theme=document.documentElement.dataset.theme");
const content = html.indexOf('<div class="app-shell">');

assert.ok(themeInit >= 0 && themeInit < stylesheet);
assert.ok(bodyTheme >= 0 && bodyTheme < content);
assert.match(themeCss, /body\[data-theme="dark"\]/);
assert.match(themeCss, /market-compact-head/);
assert.match(themeCss, /coaching uses the same flat, high-contrast visual system as Community/);

console.log("coach initial theme checks passed");
