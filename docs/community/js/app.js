import { loadGameAssets } from "./assets.js?v=20260904r";
import { $ } from "./utils.js?v=20260904r";
import { switchView } from "./view.js?v=20260904r";
import { loadRecent } from "./pages/recentMatches.js?v=20260904x";
import { state } from "./state.js?v=20260904r";
import { openPlayer, searchPlayers } from "./pages/playerSearch.js?v=20260905ak";
import { applyAnalysisRoute, bindAnalysisPage, openAnalysisFromMatch, renderCompactMatchAnalysis } from "./pages/gameAnalysis.js?v=20260905ag";
import { bindRankingPage, loadRankings } from "./pages/ranking.js?v=20260905ai";
import { renderCommunityAdmin, syncAdminAccess } from "./pages/communityAdmin.js?v=20260905admin1";
import { initCommunityAuth, canAnalyzePlayer, getCurrentUser, getAnalysisIdentity, getRiotAccounts, saveRiotAccounts, isCommunityAdmin, isCommunityCoach, canAnalyzeAllPlayers } from "./auth.js?v=20260905ag";


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
  const view = params.get("view");
  const player = params.get("player");
  const guild = params.get("guild");
  const query = params.get("q");

  if (view === "account") {
    openCommunityAccount({push:false});
    return;
  }
  if (view === "analysis") {
    applyAnalysisRoute(params);
    return;
  }
  if (view === "ranking") {
    switchView("ranking");
    loadRankings();
    return;
  }
  if (view === "admin") {
    if (!isCommunityAdmin()) { goRecent({push:false}); return; }
    switchView("admin");
    renderCommunityAdmin();
    return;
  }
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

function renderCommunityAccount() {
  const target = $("communityAccountContent");
  if (!target) return;
  const user = getCurrentUser();
  if (!user) {
    target.innerHTML = `<div class="community-account-card"><h2>로그인이 필요합니다.</h2><p class="riot-account-help">오른쪽 위 로그인 또는 Discord로 연결을 이용해주세요.</p></div>`;
    return;
  }
  const accounts = getRiotAccounts();
  const slots = Array.from({length:5}, (_,i) => accounts[i] || "");
  const discordName = user.discordDisplayName || user.discord_display_name || "";
  target.innerHTML = `<div class="community-account-shell">
    <section class="community-account-card">
      <h2>내 계정</h2>
      <div class="community-account-summary">
        <div class="row"><small>닉네임</small><strong>${esc(user.displayName || "-")}</strong></div>
        <div class="row"><small>이메일</small><strong>${esc(user.email || "-")}</strong></div>
        <div class="row"><small>Discord</small><strong class="${discordName ? "connected" : ""}">${esc(discordName || "연결 안 됨")}</strong></div>
        <div class="row"><small>권한</small><strong>${isCommunityAdmin() ? "관리자 · 모든 유저 분석 가능" : isCommunityCoach() ? "코치 · 모든 유저 분석 가능" : "일반 · 등록 계정 분석 가능"}</strong></div>
      </div>
    </section>
    <section class="community-account-card">
      <h2>내 Riot ID</h2>
      <form id="riotAccountForm" class="riot-account-form">
        ${slots.map((value,i)=>`<label class="riot-account-row"><span>${i===0 ? "본계정" : `부계정 ${i}`}</span><input name="riotAccount${i}" value="${esc(value)}" placeholder="닉네임#태그" autocomplete="off" maxlength="49"></label>`).join("")}
        <p class="riot-account-help">본계정 1개 + 부계정 4개까지 등록할 수 있습니다. 등록된 Riot ID와 일치하는 내전 기록은 게임 분석에서 모두 열립니다.</p>
        <div class="riot-account-actions"><button class="riot-account-save" type="submit">저장</button><span id="riotAccountStatus" class="riot-account-status"></span></div>
      </form>
    </section>
  </div>`;
  $("riotAccountForm")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    const status = $("riotAccountStatus");
    const button = form.querySelector("button[type=submit]");
    const values = Array.from({length:5}, (_,i) => form.elements[`riotAccount${i}`]?.value || "");
    try {
      button.disabled = true;
      if(status){ status.textContent="저장 중..."; status.className="riot-account-status"; }
      await saveRiotAccounts(values);
      if(status){ status.textContent="저장되었습니다."; status.className="riot-account-status ok"; }
    } catch(error) {
      if(status){ status.textContent=error.message || "저장에 실패했습니다."; status.className="riot-account-status error"; }
    } finally { button.disabled = false; }
  });
}

function openCommunityAccount({push=true}={}) {
  if(push){ const url=new URL(window.location.href); url.search=""; url.searchParams.set("view","account"); history.pushState({view:"account"},"",`${url.pathname}${url.search}`); }
  switchView("account");
  renderCommunityAccount();
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
      } else if (button.dataset.view === "ranking") {
        const url = new URL(window.location.href);
        url.search = "";
        url.searchParams.set("view", "ranking");
        history.pushState({ view: "ranking" }, "", `${url.pathname}${url.search}`);
        switchView("ranking");
        loadRankings();
      } else if (button.dataset.view === "admin") {
        if (!isCommunityAdmin()) return;
        const url = new URL(window.location.href);
        url.search = "";
        url.searchParams.set("view", "admin");
        history.pushState({ view: "admin" }, "", `${url.pathname}${url.search}`);
        switchView("admin");
        renderCommunityAdmin();
      } else {
        switchView(button.dataset.view);
      }
    });
  });
  document.addEventListener("click", (event) => {
    const fullAnalysisTrigger = event.target.closest("[data-open-full-analysis]");
    if (fullAnalysisTrigger) {
      event.preventDefault(); event.stopPropagation();
      openAnalysisFromMatch({
        userId: fullAnalysisTrigger.dataset.userId, guildId: fullAnalysisTrigger.dataset.guildId,
        matchId: fullAnalysisTrigger.dataset.matchId, champion: fullAnalysisTrigger.dataset.champion, role: fullAnalysisTrigger.dataset.role,
      });
      return;
    }
    const analysisTrigger = event.target.closest("[data-game-analysis]");
    if (analysisTrigger) {
      event.preventDefault(); event.stopPropagation();
      const detail={
        userId: analysisTrigger.dataset.userId, guildId: analysisTrigger.dataset.guildId,
        matchId: analysisTrigger.dataset.matchId, champion: analysisTrigger.dataset.champion, role: analysisTrigger.dataset.role,
      };
      if (!canAnalyzePlayer(detail.userId, detail.guildId)) {
        const message = getCurrentUser()
          ? "내 정보에 등록한 Riot ID의 경기만 분석할 수 있습니다. 코치 권한 이상은 모든 유저를 분석할 수 있습니다."
          : "게임 분석은 로그인 후 사용할 수 있습니다. 오른쪽 위에서 로그인하거나 Discord로 연결해주세요.";
        window.alert(message);
        return;
      }
      const card=analysisTrigger.closest(".personal-match");
      card?.classList.add("expanded");
      const expander=card?.querySelector(".personal-expand"); if(expander) expander.textContent="⌃";
      const target=card?.querySelector("[data-compact-analysis]");
      renderCompactMatchAnalysis(detail,target);
      return;
    }
    const trigger = event.target.closest("[data-player-profile]");
    if (!trigger) return;
    event.preventDefault();
    event.stopPropagation();
    const userId = trigger.dataset.userId;
    const guildId = trigger.dataset.guildId;
    if (!userId || !guildId) return;
    openPlayer(userId, guildId, { historyMode: "push" });
  });
  window.addEventListener("lucid:open-account", () => openCommunityAccount());
  window.addEventListener("lucid:auth-changed", () => { syncAdminAccess(); if(document.getElementById("accountView")?.classList.contains("active")) renderCommunityAccount(); if(document.getElementById("adminView")?.classList.contains("active")) renderCommunityAdmin(); });
  window.addEventListener("lucid:admin-denied", () => goRecent({push:false}));
  window.addEventListener("lucid:logged-out", () => goRecent());
  window.addEventListener("popstate", () => applyRoute({ fromPop: true }));
  window.addEventListener("lucid:player-opened", (event) => rememberRecentSearch(event.detail));
  window.addEventListener("lucid:favorite-toggle", (event) => toggleFavorite(event.detail));
}

bindEvents();
bindAnalysisPage();
bindRankingPage();
renderSearchMemory();
await initCommunityAuth();
syncAdminAccess();
await loadGameAssets();
await loadRecent();
applyRoute();
