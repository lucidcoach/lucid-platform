import { apiGet } from "../api.js";
import { PLAYER_MATCH_LIMIT } from "../config.js";
import { $, escapeHtml } from "../utils.js";
import { renderLoading, switchView } from "../view.js";
import { playerMatchCard } from "../components/playerMatchCard.js";
import { bindExpanders } from "../components/scoreboard.js";

function candidate(row) {
  return `<button class="search-candidate" type="button" data-user-id="${escapeHtml(row.userId)}" data-guild-id="${escapeHtml(row.guildId)}"><span><strong>${escapeHtml(row.name)}</strong><span>${escapeHtml(row.tier)} · ${Number(row.games || 0)}경기</span></span><span>전적 보기 ›</span></button>`;
}

export async function openPlayer(userId,guildId) {
  switchView("search"); const target=$("searchResults"); renderLoading(target,4);
  try {
    const data=await apiGet(`/api/community/players/${encodeURIComponent(userId)}?guildId=${encodeURIComponent(guildId)}&limit=${PLAYER_MATCH_LIMIT}`);
    const p=data.player;
    target.innerHTML=`<section class="profile-head"><div><div class="profile-name"><span class="tier-badge">${escapeHtml(p.tier || "-")}</span><h1>${escapeHtml(p.name)}</h1></div><div class="profile-stats"><div class="profile-stat"><span>최근 기록</span><strong>${Number(p.games || 0)}경기</strong></div><div class="profile-stat"><span>승률</span><strong>${Number(p.winRate || 0).toFixed(1)}%</strong></div><div class="profile-stat"><span>평균 AI Score</span><strong>${p.averageAiScore == null ? "-" : Number(p.averageAiScore).toFixed(1)}</strong></div><div class="profile-stat"><span>최다 챔피언</span><strong>${escapeHtml(p.favoriteChampion || "-")}</strong></div></div></div></section><div class="match-feed">${(data.matches || []).map((m)=>playerMatchCard(m,userId)).join("") || `<div class="empty-state"><strong>상세 스탯이 있는 경기 기록이 없습니다.</strong></div>`}</div>`;
    bindExpanders(target);
  } catch(error) { target.innerHTML=`<div class="empty-state"><strong>개인 전적을 불러오지 못했습니다.</strong><span>${escapeHtml(error.message)}</span></div>`; }
}

export async function searchPlayers(query) {
  switchView("search"); const target=$("searchResults"); renderLoading(target,2);
  try {
    const data=await apiGet(`/api/community/search?q=${encodeURIComponent(query)}&limit=12`); const players=data.players || [];
    if(players.length===1){ await openPlayer(players[0].userId,players[0].guildId); return; }
    target.innerHTML=`<h1 class="search-title">검색 결과</h1><div class="search-results-block">${players.map(candidate).join("") || `<div class="empty-state"><strong>검색 결과가 없습니다.</strong><span>Lucid Bot에 등록된 닉네임인지 확인해주세요.</span></div>`}</div>`;
    target.querySelectorAll(".search-candidate").forEach((b)=>b.addEventListener("click",()=>openPlayer(b.dataset.userId,b.dataset.guildId)));
  } catch(error) { target.innerHTML=`<div class="empty-state"><strong>검색하지 못했습니다.</strong><span>${escapeHtml(error.message)}</span></div>`; }
}
