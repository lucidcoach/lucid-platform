import assert from "node:assert/strict";
import fs from "node:fs";

const source=fs.readFileSync(new URL("../docs/community/js/pages/communityAdmin.js",import.meta.url),"utf8");
for(const text of ["riotAccountAuditSearch","unlink_riot_account","data-account-unlink","accountAuditPage","accountAuditQuery"]){
  assert.match(source,new RegExp(text));
}
