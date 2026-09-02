import { loadGameAssets } from "./assets.js";
import { $ } from "./utils.js";
import { switchView } from "./view.js";
import { loadRecent } from "./pages/recentMatches.js";
import { state } from "./state.js";
import { openPlayer, searchPlayers } from "./pages/playerSearch.js";

function communityBaseUrl() {
  return `${window.location.pathname}`;
}

function recentUrl() {
  return communityBaseUrl();
}

function applyRoute({ fromPop = false } = {}) {
  const params = new URLSearchParams(window.location.search);
  const player = params.get("player");
  const guild = params.get("guild");
  const query = params.get("q");

  if (player && guild) {
    openPlayer(player, guild, { historyMode: "none" });
    return;
  }
  if (query) {
    const input = $("playerSearchInput");
    if (input) input.value = query;
    searchPlayers(query, { historyMode: "none" });
    return;
  }
  switchView("recent");
  if (!fromPop) loadRecent();
}

function goRecent({ push = true } = {}) {
  if (push) history.pushState({ view: "recent" }, "", recentUrl());
  $("playerSearchInput").value = "";
  switchView("recent");
}

function bindEvents() {
  $("playerSearchForm").addEventListener("submit",(event)=>{
    event.preventDefault();
    const query=$("playerSearchInput").value.trim();
    if(query) searchPlayers(query, { historyMode: "push" });
  });
  $("communityHomeBtn").addEventListener("click",()=>goRecent());
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
    button.addEventListener("click", () => {
      if (button.dataset.view === "recent") {
        goRecent();
      } else {
        switchView(button.dataset.view);
      }
    });
  });
  document.addEventListener("click", (event) => {
    const trigger = event.target.closest("[data-player-profile]");
    if (!trigger) return;
    event.preventDefault();
    event.stopPropagation();
    const userId = trigger.dataset.userId;
    const guildId = trigger.dataset.guildId;
    if (!userId || !guildId) return;
    openPlayer(userId, guildId, { historyMode: "push" });
  });
  window.addEventListener("popstate", () => applyRoute({ fromPop: true }));
}

bindEvents();
await loadGameAssets();
await loadRecent();
applyRoute();
