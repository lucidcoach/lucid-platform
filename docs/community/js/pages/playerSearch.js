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
  const alias = row.matchedName && row.matchedName !== row.name ? `<small class="matched-alias">${escapeHtml(row.matchedName)}로 검색됨</small>` : "";
  return `<button class="search-candidate" type="button" data-user-id="${escapeHtml(row.userId)}" data-guild-id="${escapeHtml(row.guildId)}"><span><strong>${escapeHtml(row.name)}</strong>${alias}<span>${escapeHtml(row.tier)} · ${Number(row.games || 0)}경기</span></span><span>전적 보기 ›</span></button>`;
}

function championSummary(rows = []) {
  if (!rows.length) return "";
  return `<div class="profile-champions">${rows.map((row) => {
    const icon = championIcon(row.champion);
    return `<div class="profile-champion">${icon ? `<img src="${escapeHtml(icon)}" alt="" loading="lazy">` : ""}<div><strong>${escapeHtml(row.champion)}</strong><span>${Number(row.games || 0)}게임 · ${Number(row.winRate || 0).toFixed(0)}% · KDA ${Number(row.kda || 0).toFixed(2)}</span></div></div>`;
  }).join("")}</div>`;
}

export async function openPlayer(userId,guildId,{historyMode="push"}={}) {
  updateUrl({ player: userId, guild: guildId }, historyMode);
  switchView("search"); const target=$("searchResults"); renderLoading(target,4);
  try {
    const data=await apiGet(`/api/community/players/${encodeURIComponent(userId)}?guildId=${encodeURIComponent(guildId)}&limit=${PLAYER_MATCH_LIMIT}`);
    const p=data.player;
    if ($("playerSearchInput")) $("playerSearchInput").value = p.name || "";
    const aliases=(p.aliases || []).filter(Boolean);
    target.innerHTML=`<section class="profile-head profile-head-compact">
      <div class="profile-identity">
        <div class="profile-name"><span class="tier-badge">${escapeHtml(p.tier || "-")}</span><h1>${escapeHtml(p.name)}</h1></div>
        ${aliases.length > 1 ? `<div class="profile-aliases">등록 계정 ${aliases.map((name)=>`<span>${escapeHtml(name)}</span>`).join("")}</div>` : ""}
      </div>
      <div class="profile-overview">
        <div class="profile-record"><span>전적</span><strong>${Number(p.games || 0)}전 <em>${Number(p.wins || 0)}승</em> <b>${Number(p.losses || 0)}패</b></strong><small>승률 ${Number(p.winRate || 0).toFixed(1)}%</small></div>
        <div class="profile-record"><span>평균 KDA</span><strong>${Number(p.averageKda || 0).toFixed(2)}</strong><small>평균 피해량 ${Number(p.averageDamage || 0).toLocaleString()}</small></div>
        <div class="profile-record"><span>평균 AI Score</span><strong>${p.averageAiScore == null ? "-" : Number(p.averageAiScore).toFixed(1)}</strong><small>최근 상세기록 기준</small></div>
        ${championSummary(p.topChampions || [])}
      </div>
    </section>
    <div class="match-feed personal-feed">${(data.matches || []).map((m)=>playerMatchCard(m,userId)).join("") || `<div class="empty-state"><strong>상세 스탯이 있는 경기 기록이 없습니다.</strong></div>`}</div>`;
    bindExpanders(target);
  } catch(error) { target.innerHTML=`<div class="empty-state"><strong>개인 전적을 불러오지 못했습니다.</strong><span>${escapeHtml(error.message)}</span></div>`; }
}

export async function searchPlayers(query,{historyMode="push"}={}) {
  updateUrl({ q: query }, historyMode);
  switchView("search"); const target=$("searchResults"); renderLoading(target,2);
  try {
    const data=await apiGet(`/api/community/search?q=${encodeURIComponent(query)}&limit=12`); const players=data.players || [];
    if(players.length===1){ await openPlayer(players[0].userId,players[0].guildId,{historyMode:"replace"}); return; }
    target.innerHTML=`<h1 class="search-title">검색 결과</h1><div class="search-results-block">${players.map(candidate).join("") || `<div class="empty-state"><strong>검색 결과가 없습니다.</strong><span>등록된 본계정 또는 부계정 Riot ID를 확인해주세요.</span></div>`}</div>`;
    target.querySelectorAll(".search-candidate").forEach((b)=>b.addEventListener("click",()=>openPlayer(b.dataset.userId,b.dataset.guildId,{historyMode:"push"})));
  } catch(error) {
    const notConfigured = error.code === "community_guild_not_configured";
    target.innerHTML = notConfigured
      ? `<div class="empty-state"><strong>커뮤니티 전적 연결을 기다리고 있습니다.</strong><span>공개 서버 연결 후 닉네임 검색을 사용할 수 있습니다.</span></div>`
      : `<div class="empty-state"><strong>검색하지 못했습니다.</strong><span>${escapeHtml(error.message)}</span></div>`;
  }
}
