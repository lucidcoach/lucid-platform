import { loadGameAssets } from "./assets.js";
import { $ } from "./utils.js";
import { switchView } from "./view.js";
import { loadRecent } from "./pages/recentMatches.js";
import { state } from "./state.js";
import { openPlayer, searchPlayers } from "./pages/playerSearch.js";

function bindEvents() {
  $("playerSearchForm").addEventListener("submit",(event)=>{ event.preventDefault(); const query=$("playerSearchInput").value.trim(); if(query) searchPlayers(query); });
  $("clearSearchBtn").addEventListener("click",()=>{ $("playerSearchInput").value=""; switchView("recent"); });
  $("refreshMatchesBtn").addEventListener("click",()=>loadRecent());
  $("loadMoreBtn").addEventListener("click",()=>loadRecent({append:true}));
  document.querySelectorAll("[data-match-category]").forEach((button) => {
    button.addEventListener("click", () => {
      state.recentCategory = button.dataset.matchCategory || "all";
      document.querySelectorAll("[data-match-category]").forEach((item) => item.classList.toggle("active", item === button));
      loadRecent();
    });
  });
  document.querySelectorAll(".nav-tab[data-view]").forEach((button) => {
    button.addEventListener("click", () => switchView(button.dataset.view));
  });
  document.addEventListener("click", (event) => {
    const trigger = event.target.closest("[data-player-profile]");
    if (!trigger) return;
    event.preventDefault();
    event.stopPropagation();
    const userId = trigger.dataset.userId;
    const guildId = trigger.dataset.guildId;
    if (!userId || !guildId) return;
    const input = $("playerSearchInput");
    if (input) input.value = trigger.textContent.trim();
    openPlayer(userId, guildId);
  });
}

bindEvents();
await loadGameAssets();
await loadRecent();
