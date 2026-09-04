import { apiGet } from "../api.js?v=20260904p";
import { PLAYER_MATCH_LIMIT } from "../config.js?v=20260904p";
import { championIcon } from "../assets.js?v=20260904p";
import { $, escapeHtml, kdaClass, normalizeRoleKey, tierClass, winRateClass } from "../utils.js?v=20260904p";
import { renderLoading, switchView } from "../view.js?v=20260904p";
import { playerMatchCard } from "../components/playerMatchCard.js?v=20260904p";
import { bindExpanders } from "../components/scoreboard.js?v=20260904p";


function refreshStorageKey(userId, guildId) {
  return `lucid-community-player-refresh:${String(guildId || "")}:${String(userId || "")}`;
}

function readRefreshTime(userId, guildId) {
  const value = Number(localStorage.getItem(refreshStorageKey(userId, guildId)) || 0);
  return Number.isFinite(value) && value > 0 ? value : 0;
}

function writeRefreshTime(userId, guildId) {
  const value = Date.now();
  localStorage.setItem(refreshStorageKey(userId, guildId), String(value));
  return value;
}

function refreshRelativeTime(timestamp) {
  if (!timestamp) return "갱신 기록 없음";
  const diff = Math.max(0, Date.now() - timestamp);
  const min = Math.floor(diff / 60000);
  if (min < 1) return "방금 전";
  if (min < 60) return `${min}분 전`;
  const hour = Math.floor(min / 60);
  if (hour < 24) return `${hour}시간 전`;
  return `${Math.floor(hour / 24)}일 전`;
}

function updateUrl(params, mode = "push") {
  if (mode === "none") return;
  const url = new URL(window.location.href);
  url.search = "";
  for (const [key, value] of Object.entries(params || {})) {
    if (value != null && String(value)) url.searchParams.set(key, String(value));
  }
  history[mode === "replace" ? "replaceState" : "pushState"]({}, "", `${url.pathname}${url.search}`);
}

function candidate(row) {
  const alias = row.matchedName && row.matchedName !== row.name
    ? `<small class="matched-alias">${escapeHtml(row.matchedName)}로 검색됨</small>`
    : "";
  return `<button class="search-candidate" type="button" data-user-id="${escapeHtml(row.userId)}" data-guild-id="${escapeHtml(row.guildId)}"><span><strong>${escapeHtml(row.name)}</strong>${alias}<span>${escapeHtml(row.tier)} · ${Number(row.games || 0)}경기</span></span><span>전적 보기 ›</span></button>`;
}

const TIER_ICON = {
  C: "challenger.png",
  GM: "grandmaster.png",
  M: "master.png",
  D: "diamond.png",
  E: "emerald.png",
  P: "platinum.png",
  G: "gold.png",
  S: "silver.png",
  B: "bronze.png",
  I: "iron.png",
};

function tierIcon(tier = "") {
  const key = String(tier || "").match(/^(GM|[CMDEP G S B I])/i)?.[1]?.replaceAll(" ", "").toUpperCase()
    || String(tier || "").match(/^(GM|[CMDEPGSBI])/i)?.[1]?.toUpperCase()
    || "I";
  return `assets/tiers/${TIER_ICON[key] || TIER_ICON.I}`;
}

function isFavoriteLocal(userId, guildId) {
  try {
    const rows = JSON.parse(localStorage.getItem("lucid-community-favorite-searches-v1") || "[]");
    return Array.isArray(rows) && rows.some((row) => String(row?.userId) === String(userId) && String(row?.guildId) === String(guildId));
  } catch (_) { return false; }
}

function profileIconUrl(player = {}) {
  const direct = String(player?.profileIconUrl || "").trim();
  if (direct) return direct;
  const iconId = Number(player?.profileIconId || 0);
  return iconId > 0
    ? `https://raw.communitydragon.org/latest/plugins/rcp-be-lol-game-data/global/default/v1/profile-icons/${iconId}.jpg`
    : "";
}

function roleDelta(row = {}) {
  const delta = Number(row?.recent10Delta || 0);
  if (!Number.isFinite(delta) || Math.round(delta) === 0) return "";
  const up = delta > 0;
  return `<span class="role-tier-delta ${up ? "up" : "down"}">${up ? "▲" : "▼"}${Math.abs(Math.round(delta))}점</span>`;
}

function tierLeaguePoints(tier = "", rawScore = 0) {
  const score = Math.max(0, Math.round(Number(rawScore || 0)));
  const compact = String(tier || "").trim().toUpperCase().replace(/[\s_-]+/g, "");
  if (!score) return 0;
  if (compact.startsWith("CHALLENGER") || compact === "C") return Math.max(0, score - 3600);
  if (compact.startsWith("GRANDMASTER") || compact === "GM") return Math.max(0, score - 3200);
  if (compact.startsWith("MASTER") || compact === "M") return Math.max(0, score - 2800);
  const division = Number((compact.match(/([1-4])$/) || [])[1] || 4);
  const majorBase = compact.startsWith("DIAMOND") || compact.startsWith("D") ? 2400
    : compact.startsWith("EMERALD") || compact.startsWith("E") ? 2000
    : compact.startsWith("PLATINUM") || compact.startsWith("P") ? 1600
    : compact.startsWith("GOLD") || compact.startsWith("G") ? 1200
    : compact.startsWith("SILVER") || compact.startsWith("S") ? 800
    : compact.startsWith("BRONZE") || compact.startsWith("B") ? 400
    : 0;
  const divisionBase = majorBase + (4 - Math.max(1, Math.min(4, division))) * 100;
  return Math.max(0, score - divisionBase);
}

function roleTierBoard(rows = []) {
  const roles = ["탑", "정글", "미드", "원딜", "서폿"];
  const list = Array.isArray(rows)
    ? rows
    : Object.entries(rows || {}).map(([role, value]) => ({ role, ...(value && typeof value === "object" ? value : { tier:value }) }));
  const byRole = new Map(list.map((row) => [normalizeRoleKey(row?.role || row?.position || row?.lane), row]));
  return `<section class="role-tier-board role-tier-compact" aria-label="라인별 내전 티어">
    <div class="profile-section-title"><strong>라인별 내전 티어</strong></div>
    <div class="role-tier-list">${roles.map((role) => {
      const row = byRole.get(role) || { role, tier: "미배치", wins: 0, losses: 0 };
      const tier = String(row?.tier || row?.tierName || row?.rank || "").trim();
      const compactTier = tier.toUpperCase().replace(/[\s_-]+/g, "");
      const hasTier = Boolean(tier) && !["-","미배치","언랭","UNRANKED","UNPLACED","NONE","NULL"].includes(compactTier);
      if (!hasTier) {
        return `<div class="role-tier-line unplaced">
          <span class="role-tier-role">${escapeHtml(role)}</span>
          <span class="role-tier-unplaced">미배치</span>
        </div>`;
      }
      const lp = tierLeaguePoints(tier, row.mmr || row.score || 0);
      return `<div class="role-tier-line ${tierClass(tier)}">
        <span class="role-tier-role">${escapeHtml(role)}</span>
        <span class="role-tier-main">
          <span class="role-tier-rank"><img src="${escapeHtml(tierIcon(tier))}" alt="" loading="lazy"><strong class="tier-text ${tierClass(tier)}">${escapeHtml(tier)}</strong><span class="role-tier-mmr">${lp.toLocaleString()}점</span></span>
          <span class="role-tier-record"><em>${Number(row.wins || row.win || 0)}승</em><b>${Number(row.losses || row.loss || 0)}패</b><i>${Number(row.winRate || 0).toFixed(1)}%</i></span>
          ${roleDelta(row)}
        </span>
      </div>`;
    }).join("")}</div>
  </section>`;
}

function championRow(row) {
  const icon = championIcon(row.champion);
  return `<div class="champion-stat-row">
    <div class="champion-stat-name">${icon ? `<img src="${escapeHtml(icon)}" alt="" loading="lazy">` : ""}<strong>${escapeHtml(row.champion)}</strong></div>
    <span>${Number(row.games || 0)}게임</span>
    <span class="${winRateClass(row.winRate)}">${Number(row.winRate || 0).toFixed(1)}%</span>
    <span class="${kdaClass(row.kda)}">${Number(row.kda || 0).toFixed(2)}</span>
  </div>`;
}

function championStatsPanel(groups = {}) {
  const tabs = ["전체", "탑", "정글", "미드", "원딜", "서폿"];
  return `<section class="champion-stats-panel">
    <div class="profile-section-title"><strong>챔피언 통계</strong></div>
    <div class="champion-role-tabs" role="tablist">${tabs.map((role, i) => `<button type="button" class="champion-role-tab${i === 0 ? " active" : ""}" data-champion-role="${escapeHtml(role)}">${escapeHtml(role)}</button>`).join("")}</div>
    <div class="champion-stat-head"><span>챔피언</span><span>게임</span><span>승률</span><span>KDA</span></div>
    <div class="champion-stat-list" data-champion-list></div>
    <button class="champion-more-button" type="button" data-champion-more hidden>더 보기</button>
  </section>`;
}

function bindChampionStats(target, groups = {}) {
  const list = target.querySelector("[data-champion-list]");
  const more = target.querySelector("[data-champion-more]");
  const tabs = [...target.querySelectorAll("[data-champion-role]")];
  if (!list || !more) return;
  let role = "전체";
  let expanded = false;

  const render = () => {
    const rows = Array.isArray(groups?.[role]) ? groups[role] : [];
    const visible = expanded ? rows : rows.slice(0, 6);
    list.innerHTML = visible.length
      ? visible.map(championRow).join("")
      : `<div class="champion-stat-empty">해당 라인의 저장된 상세 기록이 없습니다.</div>`;
    more.hidden = rows.length <= 6;
    more.textContent = expanded ? "접기" : `더 보기 (${rows.length})`;
  };

  tabs.forEach((button) => button.addEventListener("click", () => {
    tabs.forEach((item) => item.classList.toggle("active", item === button));
    role = button.dataset.championRole || "전체";
    expanded = false;
    render();
  }));
  more.addEventListener("click", () => {
    expanded = !expanded;
    render();
  });
  render();
}

export async function openPlayer(userId,guildId,{historyMode="push"}={}) {
  updateUrl({ player: userId, guild: guildId }, historyMode);
  switchView("search");
  const target=$("searchResults");
  renderLoading(target,4);
  try {
    const data=await apiGet(`/api/community/players/${encodeURIComponent(userId)}?guildId=${encodeURIComponent(guildId)}&limit=${PLAYER_MATCH_LIMIT}`);
    const p=data.player;
    if ($("playerSearchInput")) $("playerSearchInput").value = p.name || "";
    const aliases=(p.aliases || []).filter(Boolean);

    window.dispatchEvent(new CustomEvent("lucid:player-opened", { detail: { name:p.name || "", userId:String(userId), guildId:String(guildId) } }));
    const lastRefresh = readRefreshTime(userId, guildId) || writeRefreshTime(userId, guildId);

    target.innerHTML=`<section class="profile-dashboard-grid">
      <div class="profile-summary-panel">
        <div class="profile-title-row"><div class="profile-name profile-name-with-icon"><span class="summoner-profile-icon placeholder" aria-label="소환사 아이콘 자리"></span><div class="profile-name-copy"><div class="profile-name-main"><span class="tier-badge ${tierClass(p.tier)}">${escapeHtml(p.tier || "-")}</span><h1 title="${escapeHtml(p.name)}">${escapeHtml(p.name)}</h1><button class="profile-favorite-button${isFavoriteLocal(userId,guildId) ? " active" : ""}" type="button" data-profile-favorite aria-label="즐겨찾기" title="즐겨찾기">${isFavoriteLocal(userId,guildId) ? "★" : "☆"}</button></div><span class="summoner-level-text placeholder">Lv --</span></div></div><div class="profile-refresh-wrap"><button class="profile-refresh-button" type="button" data-profile-refresh>전적 갱신</button><span class="profile-refresh-time" data-profile-refresh-time>최근 갱신: ${escapeHtml(refreshRelativeTime(lastRefresh))}</span></div></div>
        <div class="profile-overview profile-overview-compact">
          <div class="profile-record"><span>전적</span><strong>${Number(p.games || 0)}전 <em>${Number(p.wins || 0)}승</em> <b>${Number(p.losses || 0)}패</b></strong><small>승률 <b class="${winRateClass(p.winRate)}">${Number(p.winRate || 0).toFixed(1)}%</b></small></div>
          <div class="profile-record"><span>평균 KDA</span><strong class="${kdaClass(p.averageKda)}">${Number(p.averageKda || 0).toFixed(2)}</strong></div>
        </div>
        ${roleTierBoard(p.roleTiers || [])}
      </div>
      <div class="profile-champion-panel">
        ${championStatsPanel(p.championStats || {})}
      </div>
    </section>
    <div class="match-feed personal-feed">${(data.matches || []).map((m)=>playerMatchCard(m,userId)).join("") || `<div class="empty-state"><strong>상세 스탯이 있는 경기 기록이 없습니다.</strong></div>`}</div>`;

    bindChampionStats(target, p.championStats || {});
    bindExpanders(target);
    target.querySelector("[data-profile-favorite]")?.addEventListener("click", (event) => {
      window.dispatchEvent(new CustomEvent("lucid:favorite-toggle", { detail: { name:p.name || "", userId:String(userId), guildId:String(guildId) } }));
      const nowFavorite = !event.currentTarget.classList.contains("active");
      event.currentTarget.classList.toggle("active", nowFavorite);
      event.currentTarget.textContent = nowFavorite ? "★" : "☆";
    });
    const refreshButton = target.querySelector("[data-profile-refresh]");
    refreshButton?.addEventListener("click", async () => {
      if (refreshButton.disabled) return;
      refreshButton.disabled = true;
      refreshButton.textContent = "갱신 중...";
      try {
        const stamp = writeRefreshTime(userId, guildId);
        await openPlayer(userId, guildId, { historyMode:"none" });
        const timeNode = document.querySelector("[data-profile-refresh-time]");
        if (timeNode) timeNode.textContent = `최근 갱신: ${refreshRelativeTime(stamp)}`;
      } catch (_) {
        refreshButton.disabled = false;
        refreshButton.textContent = "전적 갱신";
      }
    });
  } catch(error) {
    target.innerHTML=`<div class="empty-state"><strong>개인 전적을 불러오지 못했습니다.</strong><span>${escapeHtml(error.message)}</span></div>`;
  }
}

export async function searchPlayers(query,{historyMode="push"}={}) {
  updateUrl({ q: query }, historyMode);
  switchView("search");
  const target=$("searchResults");
  renderLoading(target,2);
  try {
    const data=await apiGet(`/api/community/search?q=${encodeURIComponent(query)}&limit=12`);
    const players=data.players || [];
    if(players.length===1){
      await openPlayer(players[0].userId,players[0].guildId,{historyMode:"replace"});
      return;
    }
    target.innerHTML=`<h1 class="search-title">검색 결과</h1><div class="search-results-block">${players.map(candidate).join("") || `<div class="empty-state"><strong>검색 결과가 없습니다.</strong><span>등록된 본계정 또는 부계정 Riot ID를 확인해주세요.</span></div>`}</div>`;
    target.querySelectorAll(".search-candidate").forEach((b)=>b.addEventListener("click",()=>openPlayer(b.dataset.userId,b.dataset.guildId,{historyMode:"push"})));
  } catch(error) {
    const notConfigured = error.code === "community_guild_not_configured";
    target.innerHTML = notConfigured
      ? `<div class="empty-state"><strong>커뮤니티 전적 연결을 기다리고 있습니다.</strong><span>공개 서버 연결 후 닉네임 검색을 사용할 수 있습니다.</span></div>`
      : `<div class="empty-state"><strong>검색하지 못했습니다.</strong><span>${escapeHtml(error.message)}</span></div>`;
  }
}
