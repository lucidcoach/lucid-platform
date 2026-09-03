import { loadGameAssets } from "./assets.js?v=20260904f";
import { $ } from "./utils.js?v=20260904f";
import { switchView } from "./view.js?v=20260904f";
import { loadRecent } from "./pages/recentMatches.js?v=20260904f";
import { state } from "./state.js?v=20260904f";
import { openPlayer, searchPlayers } from "./pages/playerSearch.js?v=20260904f";


const RECENT_SEARCH_KEY = "lucid-community-recent-searches-v1";
const RECENT_SEARCH_LIMIT = 5;

function readRecentSearches() {
  try {
    const rows = JSON.parse(localStorage.getItem(RECENT_SEARCH_KEY) || "[]");
    return Array.isArray(rows) ? rows.filter((row) => row?.name && row?.userId && row?.guildId).slice(0,RECENT_SEARCH_LIMIT) : [];
  } catch (_) {
    return [];
  }
}

function renderRecentSearches() {
  const target = $("recentSearches");
  if (!target) return;
  const rows = readRecentSearches();
  target.innerHTML = rows.map((row) => {
    const userId = String(row.userId).replaceAll('"','&quot;');
    const guildId = String(row.guildId).replaceAll('"','&quot;');
    const name = String(row.name).replace(/[&<>]/g, "");
    return `<span class="recent-search-chip" data-recent-entry>
      <button class="recent-search-open" type="button" data-recent-user="${userId}" data-recent-guild="${guildId}" title="${String(row.name).replaceAll('"','&quot;')} 전적 보기">${name}</button>
      <button class="recent-search-remove" type="button" data-recent-remove="${userId}" data-recent-remove-guild="${guildId}" aria-label="${name} 최근 검색 삭제" title="최근 검색 삭제">×</button>
    </span>`;
  }).join("");
  target.hidden = rows.length === 0;
  target.querySelectorAll("[data-recent-user]").forEach((button) => button.addEventListener("click", () => {
    openPlayer(button.dataset.recentUser, button.dataset.recentGuild, { historyMode:"push" });
  }));
  target.querySelectorAll("[data-recent-remove]").forEach((button) => button.addEventListener("click", (event) => {
    event.preventDefault();
    event.stopPropagation();
    const userId = String(button.dataset.recentRemove || "");
    const guildId = String(button.dataset.recentRemoveGuild || "");
    const next = readRecentSearches().filter((row) => !(String(row.userId) === userId && String(row.guildId) === guildId));
    localStorage.setItem(RECENT_SEARCH_KEY, JSON.stringify(next));
    renderRecentSearches();
  }));
}

function rememberRecentSearch(detail = {}) {
  const name = String(detail.name || "").trim();
  const userId = String(detail.userId || "").trim();
  const guildId = String(detail.guildId || "").trim();
  if (!name || !userId || !guildId) return;
  const next = [{name,userId,guildId}, ...readRecentSearches().filter((row) => !(String(row.userId) === userId && String(row.guildId) === guildId))].slice(0,RECENT_SEARCH_LIMIT);
  localStorage.setItem(RECENT_SEARCH_KEY, JSON.stringify(next));
  renderRecentSearches();
}

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
  window.addEventListener("lucid:player-opened", (event) => rememberRecentSearch(event.detail));
}

bindEvents();
renderRecentSearches();
await loadGameAssets();
await loadRecent();
applyRoute();
