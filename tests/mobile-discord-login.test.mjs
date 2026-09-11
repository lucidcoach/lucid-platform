import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const page = readFileSync(new URL("../docs/community/index.html", import.meta.url), "utf8");
const auth = readFileSync(new URL("../docs/community/js/auth.js", import.meta.url), "utf8");
const authCss = readFileSync(new URL("../docs/community/css/auth.css", import.meta.url), "utf8");
const mileage = readFileSync(new URL("../docs/community/js/pages/mileage.js", import.meta.url), "utf8");

assert.ok(page.indexOf('data-community-oauth="discord"') < page.indexOf('name="email"'));
assert.match(page, /data-community-oauth="discord"[^>]*>.*Discord로 로그인/s);
assert.match(auth, /returnTo",window\.location\.href/);
assert.match(auth, /e\.key==="Escape".*closeModal/);
assert.match(authCss, /max-height:calc\(100dvh/);
assert.match(authCss, /overflow-y:auto/);
assert.match(authCss, /safe-area-inset-bottom/);
assert.match(authCss, /min-height:48px/);
assert.match(mileage, /data-mileage-discord-login>Discord로 로그인/);
assert.match(mileage, /communityLinkBtn/);

console.log("mobile Discord login checks passed");
