import { apiGet } from "../api.js?v=20260907live1";
import { championIcon } from "../assets.js?v=20260907live1";
import { $, escapeHtml, tierClass } from "../utils.js?v=20260907live1";

const esc=(v)=>escapeHtml(String(v??""));
const num=(v,d=0)=>Number.isFinite(Number(v))?Number(v).toFixed(d):"-";
const playerName=(p)=>p?.name||p?.displayName||p?.riotId||"알 수 없음";

function mostList(player={}){
  const rows=player.mostChampions||player.mosts||player.champions||[];
  if(!Array.isArray(rows)||!rows.length)return `<span class="live-most-empty">내전 모스트 기록 없음</span>`;
  return `<div class="live-mosts">${rows.slice(0,3).map(row=>{const name=typeof row==="string"?row:(row.champion||row.name||"");const games=typeof row==="object"?Number(row.games||row.count||0):0;const icon=championIcon(name);return `<span title="${esc(name)}${games?` · ${games}게임`:""}">${icon?`<img src="${esc(icon)}" alt="">`:""}<b>${esc(name)}</b>${games?`<em>${games}</em>`:""}</span>`;}).join("")}</div>`;
}

function teamPlayer(player={},side="blue"){
  const role=player.role||player.position||"-";
  const rank=player.serverRank||player.roleRank||null;
  const stat=player.keyStat||player.highlight||"";
  return `<article class="live-player ${side}">
    <div class="live-player-role">${esc(role)}</div>
    <div class="live-player-main"><button type="button" data-player-profile data-user-id="${esc(player.userId||"")}" data-guild-id="${esc(player.guildId||"")}"><strong>${esc(playerName(player))}</strong></button><span class="${tierClass(player.tier)}">${esc(player.tier||"미배치")} ${player.mmr!=null?`· ${Math.round(Number(player.mmr)||0)}점`:""}</span></div>
    <div class="live-player-form">${player.recentWinRate!=null?`최근 승률 <strong>${num(player.recentWinRate,0)}%</strong>`:`최근 기록 ${Number(player.recentGames||0)}경기`}${rank?`<small>${esc(role)} ${Number(rank)}위</small>`:""}</div>
    <div class="live-player-most">${mostList(player)}${stat?`<small>${esc(stat)}</small>`:""}</div>
  </article>`;
}

function matchupCard(item={}){
  return `<article class="live-matchup-card"><span>${esc(item.label||item.role||"핵심 매치")}</span><strong>${esc(item.title||item.summary||"주목할 매치업")}</strong><p>${esc(item.detail||item.description||"")}</p></article>`;
}

function renderLive(data={}){
  const match=data.match||data.liveMatch||data;
  const blue=match.blueTeam||match.blue||[];
  const red=match.redTeam||match.red||[];
  const matchups=match.matchups||match.keyMatchups||[];
  const section=$("liveMatchSection"),root=$("liveMatchRoot");
  if(!section||!root)return;
  if(!match||(!blue.length&&!red.length)){section.hidden=true;root.innerHTML="";return;}
  section.hidden=false;
  root.innerHTML=`<div class="live-shell">
    <header class="live-head"><div><span class="live-dot"></span><div><small>LIVE SCRIM</small><h2>현재 진행 중인 내전</h2><p>${esc(match.guildName||match.serverName||"현재 서버")} · ${esc(match.startedText||match.startedAtText||"라인업 확정")}</p></div></div><div class="live-balance"><span>팀 밸런스</span><strong>${match.balanceText?esc(match.balanceText):(match.blueAverageMmr!=null&&match.redAverageMmr!=null?`${Math.round(match.blueAverageMmr)} : ${Math.round(match.redAverageMmr)}`:"라인업 분석 중")}</strong></div></header>
    <div class="live-scoreboard"><section><div class="live-team-title blue"><strong>BLUE</strong><span>평균 ${esc(match.blueAverageTier||match.blueTier||"-")} ${match.blueAverageMmr!=null?`· ${Math.round(match.blueAverageMmr)}점`:""}</span></div>${blue.map(p=>teamPlayer({...p,guildId:p.guildId||match.guildId},"blue")).join("")}</section><div class="live-vs">VS</div><section><div class="live-team-title red"><strong>RED</strong><span>평균 ${esc(match.redAverageTier||match.redTier||"-")} ${match.redAverageMmr!=null?`· ${Math.round(match.redAverageMmr)}점`:""}</span></div>${red.map(p=>teamPlayer({...p,guildId:p.guildId||match.guildId},"red")).join("")}</section></div>
    <div class="live-preview"><div class="live-preview-title"><span>MATCH PREVIEW</span><strong>경기 전 핵심 정보</strong><small>실시간 챔피언 픽 없이, 기존 내전 기록으로 비교합니다.</small></div><div class="live-matchups">${matchups.length?matchups.slice(0,3).map(matchupCard).join(""):`<article class="live-matchup-card muted"><span>PREVIEW</span><strong>라인업 데이터 연결 완료</strong><p>서버별 통계가 쌓이면 포지션 순위, 최근 폼, 핵심 매치업이 자동으로 표시됩니다.</p></article>`}</div></div>
  </div>`;
}

export async function loadLiveMatch(){
  const section=$("liveMatchSection");
  if(!section)return;
  try{const data=await apiGet(`/api/community/live-match`);renderLive(data);}catch(error){
    // 백엔드가 아직 live-match API를 제공하지 않으면 홈 화면에서 조용히 숨김.
    section.hidden=true;
  }
}
