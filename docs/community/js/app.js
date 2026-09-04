import { loadGameAssets } from "./assets.js?v=20260904r";
import { $ } from "./utils.js?v=20260904r";
import { switchView } from "./view.js?v=20260904r";
import { loadRecent } from "./pages/recentMatches.js?v=20260904w";
import { state } from "./state.js?v=20260904r";
import { openPlayer, searchPlayers } from "./pages/playerSearch.js?v=20260904w";


const RECENT_SEARCH_KEY = "lucid-community-recent-searches-v2";
const FAVORITE_SEARCH_KEY = "lucid-community-favorite-searches-v1";
const RECENT_SEARCH_LIMIT = 8;
const FAVORITE_SEARCH_LIMIT = 12;

function safeRows(key, limit) {
  try {
    const rows = JSON.parse(localStorage.getItem(key) || "[]");
    return Array.isArray(rows) ? rows.filter((row) => row?.name && row?.userId && row?.guildId).slice(0,limit) : [];
  } catch (_) { return []; }
}
function readRecentSearches() { return safeRows(RECENT_SEARCH_KEY, RECENT_SEARCH_LIMIT); }
function readFavoriteSearches() { return safeRows(FAVORITE_SEARCH_KEY, FAVORITE_SEARCH_LIMIT); }
function esc(value) { return String(value ?? "").replace(/[&<>"']/g, (ch) => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[ch])); }
function samePlayer(row, userId, guildId) { return String(row.userId) === String(userId) && String(row.guildId) === String(guildId); }

function searchMemoryRow(row, {favorite=false} = {}) {
  const isFavorite = readFavoriteSearches().some((item) => samePlayer(item,row.userId,row.guildId));
  return `<div class="search-memory-row">
    <button class="search-memory-open" type="button" data-memory-user="${esc(row.userId)}" data-memory-guild="${esc(row.guildId)}" title="${esc(row.name)} 전적 보기"><span>${esc(row.name)}</span></button>
    <button class="search-memory-star${isFavorite ? " active" : ""}" type="button" data-memory-star data-memory-user="${esc(row.userId)}" data-memory-guild="${esc(row.guildId)}" data-memory-name="${esc(row.name)}" aria-label="즐겨찾기">${isFavorite ? "★" : "☆"}</button>
    ${favorite ? `<button class="search-memory-remove" type="button" data-favorite-remove data-memory-user="${esc(row.userId)}" data-memory-guild="${esc(row.guildId)}" aria-label="즐겨찾기 삭제">×</button>` : `<button class="search-memory-remove" type="button" data-recent-remove data-memory-user="${esc(row.userId)}" data-memory-guild="${esc(row.guildId)}" aria-label="최근 검색 삭제">×</button>`}
  </div>`;
}

function bindSearchMemory(target) {
  target?.querySelectorAll("[data-memory-user].search-memory-open").forEach((button) => button.addEventListener("click", () => openPlayer(button.dataset.memoryUser, button.dataset.memoryGuild, { historyMode:"push" })));
  target?.querySelectorAll("[data-memory-star]").forEach((button) => button.addEventListener("click", () => toggleFavorite({name:button.dataset.memoryName,userId:button.dataset.memoryUser,guildId:button.dataset.memoryGuild})));
}

function renderSearchMemory() {
  const recentTarget = $("recentSearches");
  const favoriteTarget = $("favoriteSearches");
  const recent = readRecentSearches();
  const favorites = readFavoriteSearches();
  if (recentTarget) {
    recentTarget.innerHTML = recent.length ? recent.map((row)=>searchMemoryRow(row)).join("") : `<div class="search-memory-empty">검색 기록이 없습니다.</div>`;
    recentTarget.querySelectorAll("[data-recent-remove]").forEach((button)=>button.addEventListener("click",()=>{
      localStorage.setItem(RECENT_SEARCH_KEY, JSON.stringify(readRecentSearches().filter((row)=>!samePlayer(row,button.dataset.memoryUser,button.dataset.memoryGuild))));
      renderSearchMemory();
    }));
    bindSearchMemory(recentTarget);
  }
  if (favoriteTarget) {
    favoriteTarget.innerHTML = favorites.length ? favorites.map((row)=>searchMemoryRow(row,{favorite:true})).join("") : `<div class="search-memory-empty">즐겨찾기 없음</div>`;
    favoriteTarget.querySelectorAll("[data-favorite-remove]").forEach((button)=>button.addEventListener("click",()=>{
      localStorage.setItem(FAVORITE_SEARCH_KEY, JSON.stringify(readFavoriteSearches().filter((row)=>!samePlayer(row,button.dataset.memoryUser,button.dataset.memoryGuild))));
      renderSearchMemory();
    }));
    bindSearchMemory(favoriteTarget);
  }
}

function rememberRecentSearch(detail = {}) {
  const name = String(detail.name || "").trim(), userId = String(detail.userId || "").trim(), guildId = String(detail.guildId || "").trim();
  if (!name || !userId || !guildId) return;
  const next = [{name,userId,guildId}, ...readRecentSearches().filter((row)=>!samePlayer(row,userId,guildId))].slice(0,RECENT_SEARCH_LIMIT);
  localStorage.setItem(RECENT_SEARCH_KEY, JSON.stringify(next));
  renderSearchMemory();
}

function toggleFavorite(detail = {}) {
  const name = String(detail.name || "").trim(), userId = String(detail.userId || "").trim(), guildId = String(detail.guildId || "").trim();
  if (!name || !userId || !guildId) return;
  const rows = readFavoriteSearches();
  const exists = rows.some((row)=>samePlayer(row,userId,guildId));
  const next = exists ? rows.filter((row)=>!samePlayer(row,userId,guildId)) : [{name,userId,guildId}, ...rows].slice(0,FAVORITE_SEARCH_LIMIT);
  localStorage.setItem(FAVORITE_SEARCH_KEY, JSON.stringify(next));
  renderSearchMemory();
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
  window.addEventListener("lucid:favorite-toggle", (event) => toggleFavorite(event.detail));
}

bindEvents();
renderSearchMemory();
await loadGameAssets();
await loadRecent();
applyRoute();
