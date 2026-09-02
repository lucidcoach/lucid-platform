import { loadGameAssets } from "./assets.js";
import { $ } from "./utils.js";
import { switchView } from "./view.js";
import { loadRecent } from "./pages/recentMatches.js";
import { searchPlayers } from "./pages/playerSearch.js";

function bindEvents() {
  $("playerSearchForm").addEventListener("submit",(event)=>{ event.preventDefault(); const query=$("playerSearchInput").value.trim(); if(query) searchPlayers(query); });
  $("clearSearchBtn").addEventListener("click",()=>{ $("playerSearchInput").value=""; switchView("recent"); });
  $("refreshMatchesBtn").addEventListener("click",()=>loadRecent());
  $("loadMoreBtn").addEventListener("click",()=>loadRecent({append:true}));
  document.querySelectorAll(".nav-tab[data-view='recent']").forEach((button)=>button.addEventListener("click",()=>switchView("recent")));
}

bindEvents();
await loadGameAssets();
await loadRecent();
