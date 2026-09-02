import { apiGet } from "../api.js";
import { PLAYER_MATCH_LIMIT } from "../config.js";
import { championIcon } from "../assets.js";
import { $, escapeHtml } from "../utils.js";
import { renderLoading, switchView } from "../view.js";
import { playerMatchCard } from "../components/playerMatchCard.js";
import { bindExpanders } from "../components/scoreboard.js";

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

function roleTierBoard(rows = []) {
  const roles = ["탑", "정글", "미드", "원딜", "서폿"];
  const byRole = new Map(rows.map((row) => [row.role, row]));
  return `<section class="role-tier-board role-tier-compact" aria-label="라인별 내전 티어">
    <div class="profile-section-title"><strong>라인별 내전 티어</strong></div>
    <div class="role-tier-list">${roles.map((role) => {
      const row = byRole.get(role) || { role, tier: "미배치", placed: false, wins: 0, losses: 0 };
      if (!row.placed || row.tier === "미배치") {
        return `<div class="role-tier-line unplaced">
          <span class="role-tier-role">${escapeHtml(role)}</span>
          <span class="role-tier-unplaced">미배치</span>
        </div>`;
      }
      return `<div class="role-tier-line">
        <span class="role-tier-role">${escapeHtml(role)}</span>
        <img src="${escapeHtml(tierIcon(row.tier))}" alt="" loading="lazy">
        <strong>${escapeHtml(row.tier)}</strong>
        <span class="role-tier-record"><em>${Number(row.wins || 0)}승</em> <b>${Number(row.losses || 0)}패</b></span>
      </div>`;
    }).join("")}</div>
  </section>`;
}

function championRow(row) {
  const icon = championIcon(row.champion);
  return `<div class="champion-stat-row">
    <div class="champion-stat-name">${icon ? `<img src="${escapeHtml(icon)}" alt="" loading="lazy">` : ""}<strong>${escapeHtml(row.champion)}</strong></div>
    <span>${Number(row.games || 0)}게임</span>
    <span class="${Number(row.winRate || 0) >= 50 ? "positive" : ""}">${Number(row.winRate || 0).toFixed(1)}%</span>
    <span>${Number(row.kda || 0).toFixed(2)}</span>
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

    target.innerHTML=`<section class="profile-dashboard-grid">
      <div class="profile-summary-panel">
        <div class="profile-name"><span class="tier-badge">${escapeHtml(p.tier || "-")}</span><h1>${escapeHtml(p.name)}</h1></div>
        ${aliases.length > 1 ? `<div class="profile-aliases">등록 계정 ${aliases.map((name)=>`<span>${escapeHtml(name)}</span>`).join("")}</div>` : ""}
        <div class="profile-overview profile-overview-compact">
          <div class="profile-record"><span>전적</span><strong>${Number(p.games || 0)}전 <em>${Number(p.wins || 0)}승</em> <b>${Number(p.losses || 0)}패</b></strong><small>승률 ${Number(p.winRate || 0).toFixed(1)}%</small></div>
          <div class="profile-record"><span>평균 KDA</span><strong>${Number(p.averageKda || 0).toFixed(2)}</strong></div>
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
