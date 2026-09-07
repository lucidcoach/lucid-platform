import { apiGet } from "../api.js?v=20260907permissions1";
import { championIcon } from "../assets.js?v=20260907analysis1";
import { $, escapeHtml, relativeTime } from "../utils.js?v=20260907analysis1";
import { switchView } from "../view.js?v=20260907analysis1";
import { canAnalyzePlayer, getAnalysisIdentity, canAnalyzeAllPlayers, isCommunityAdmin, isCommunityCoach, getCurrentUser } from "../auth.js?v=20260907oauth1";

const ROLES = ["전체", "탑", "정글", "미드", "원딜", "서폿"];
const ROLE_METRICS = {
  "전체": [["kda","KDA"],["dpm","DPM"],["kp","킬관여"],["csm","CS/분"],["gpm","골드/분"],["winRate","승률"]],
  "탑": [["lanePhaseScore","라인전"],["gpm","골드획득"],["dpm","데미지"],["teamfightScore","한타 기여도"],["macroScore","운영"],["influenceScore","영향력"]],
  "정글": [["jungleGrowthScore","성장"],["gankScore","갱킹"],["skirmishScore","교전"],["objectiveScore","오브젝트"],["jungleDamageScore","데미지"],["jungleMacroScore","운영"]],
  "미드": [["dpm","DPM"],["kda","KDA"],["csm","CS/분"],["gpm","골드/분"],["kp","킬관여"],["winRate","승률"]],
  "원딜": [["dpm","DPM"],["csm","CS/분"],["gpm","골드/분"],["kda","KDA"],["kp","킬관여"],["winRate","승률"]],
  "서폿": [["kp","킬관여"],["visionPerMin","시야/분"],["ccPerMin","CC/분"],["allyCarePerMin","힐·실드/분"],["kda","KDA"],["winRate","승률"]],
};

let dashboard = { role:"전체", tab:"scrim", section:"matches", identity:null, profile:null, metrics:new Map() };
const esc = (value) => escapeHtml(String(value ?? ""));
const number = (value, digits=1) => Number.isFinite(Number(value)) ? Number(value).toFixed(digits) : "-";
const SCORE_KEYS = new Set(["lanePhaseScore","teamfightScore","macroScore","influenceScore","jungleGrowthScore","gankScore","skirmishScore","objectiveScore","jungleDamageScore","jungleMacroScore"]);
const metricText = (key, value) => {
  if (value == null) return "-";
  if (SCORE_KEYS.has(key)) return `${number(value, 1)}점`;
  if (["gpm","dpm"].includes(key)) return number(value, 0);
  return `${number(value, key === "kda" ? 2 : 1)}${["kp","winRate"].includes(key) ? "%" : ""}`;
};

function firstFinite(row, keys) {
  for (const key of keys) {
    const raw = row?.[key];
    if (raw == null || raw === "") continue;
    const value = Number(raw);
    if (Number.isFinite(value)) return value;
  }
  return null;
}

function topMetricValue(player, opponent, key) {
  if (!player) return null;
  if (key === "lanePhaseScore") return firstFinite(player,["lanePhaseScore","topLaneScore","laneScore"]);
  if (key === "teamfightScore") return firstFinite(player,["teamfightScore","teamfightContributionScore","fightScore"]);
  if (key === "macroScore") return firstFinite(player,["macroScore","operationScore","sideLaneScore"]);
  if (key === "influenceScore") {
    const explicit=firstFinite(player,["influenceScore","topInfluenceScore"]);
    if (explicit != null) return explicit;
    const mine=firstFinite(player,["kp"]), other=firstFinite(opponent,["kp"]);
    if (mine == null || other == null) return null;
    return Math.max(0,Math.min(100,50+(mine-other)));
  }
  return firstFinite(player,[key]);
}

function comparisonValue(player, opponent, key) {
  if (player?.role === "탑") return topMetricValue(player, opponent, key);
  return firstFinite(player,[key]);
}

function hasAnalysisAccess(userId="", guildId="") {
  return isCommunityAdmin() || isCommunityCoach() || canAnalyzeAllPlayers(guildId) || canAnalyzePlayer(userId, guildId);
}

function analysisAccessMessage() {
  const user=getCurrentUser();
  if(!user)return "로그인 후 Discord 연동이 필요합니다.";
  if(!user.discordConnected&&!user.discord_connected)return "Discord 연동 후 본인이 등록한 계정만 분석할 수 있습니다.";
  if(!Array.isArray(user.analysisPlayers)||!user.analysisPlayers.length)return "Discord에서 /소환사등록을 먼저 해주세요.";
  return "본인이 등록한 계정만 볼 수 있습니다. 다른 회원 분석은 관리자 권한이 필요합니다.";
}

function radarPoints(values, radius=112, cx=150, cy=140) {
  return values.map((value,index) => {
    const angle = -Math.PI / 2 + index * Math.PI / 3;
    const size = radius * Math.max(.06, Math.min(1, value));
    return `${(cx + Math.cos(angle) * size).toFixed(1)},${(cy + Math.sin(angle) * size).toFixed(1)}`;
  }).join(" ");
}

function radar(labels, own=null, compare=null, legend="서버 내 순위") {
  const grid = [.25,.5,.75,1].map(scale => `<polygon points="${radarPoints(labels.map(() => scale))}" class="server-radar-grid"/>`).join("");
  const axes = labels.map((label,index) => {
    const angle = -Math.PI / 2 + index * Math.PI / 3;
    const x = 150 + Math.cos(angle) * 137, y = 140 + Math.sin(angle) * 137;
    return `<text x="${x.toFixed(1)}" y="${y.toFixed(1)}" text-anchor="middle">${esc(label)}</text>`;
  }).join("");
  return `<div class="server-radar-wrap"><div class="server-radar-legend">${own?`<span><i></i>나</span>`:""}${compare ? `<span><b></b>${esc(legend)}</span>` : `<span>${own?esc(legend):"데이터 부족"}</span>`}</div><svg class="server-radar" viewBox="0 0 300 280" role="img" aria-label="육각형 경기 지표 그래프">${grid}${compare ? `<polygon points="${radarPoints(compare)}" class="server-radar-compare"/>` : ""}${own?`<polygon points="${radarPoints(own)}" class="server-radar-own"/>`:""}${axes}</svg>${!own&&!compare?`<strong class="server-radar-empty">비교 가능한 경기 데이터가 부족합니다.</strong>`:""}</div>`;
}

function metricRankScore(metric={}) {
  const rank=Number(metric.rank), total=Number(metric.total);
  return rank > 0 && total > 0 ? Math.max(.06, (total-rank+1)/total) : null;
}

function roleButtons() {
  return `<div class="server-role-tabs" role="tablist" aria-label="분석 포지션">${ROLES.map(role => `<button type="button" class="${dashboard.role===role?"active":""}" data-server-role="${role}">${role}</button>`).join("")}</div>`;
}

function serverMetricPanel(metrics={}) {
  const order = dashboard.role === "탑" ? ROLE_METRICS["탑"] : (metrics.metricOrder || ROLE_METRICS[dashboard.role]);
  const values = order.map(item => metricRankScore(metrics.metrics?.[item.key || item[0]]));
  return `<section class="server-analysis-card radar-card">
    <div class="server-card-head"><div><small>SERVER RANKING</small><h2>${esc(dashboard.role)} 라인 서버 지표</h2></div><span>${Number(metrics.sampleGames||0)}경기 기준</span></div>
    ${roleButtons()}${radar(order.map(item=>item.label||item[1]),values.every(Number.isFinite)?values:null)}
    <div class="server-rank-list">${order.map(item=>{const key=item.key||item[0],label=item.label||item[1],row=metrics.metrics?.[key]||{};return `<div><span>${esc(label)}</span><strong>${metricText(key,row.value)}</strong><small>${row.rank?`${row.rank}위 / ${row.total}명 · 상위 ${row.topPercent}%`:`비교 기록 없음`}</small></div>`;}).join("")}</div>
  </section>`;
}

function focusPlayer(match, userId) {
  return (match.players || []).find(row => String(row.userId) === String(userId));
}

function scrimMatchCard(match, userId) {
  const player=focusPlayer(match,userId); if(!player)return"";
  const won=player.result==="win", delta=Math.round(Number(player.mmrDelta||0)), icon=championIcon(player.champion);
  return `<article class="analysis-history-card ${won?"win":"loss"}">
    <div class="analysis-history-result"><strong>${won?"승리":"패배"}${delta?` (${delta>0?"+":""}${delta})`:""}</strong><span>${esc(relativeTime(match.time))}</span><small>${esc(match.mode||"내전")}</small></div>
    <div class="analysis-history-champion">${icon?`<img src="${esc(icon)}" alt="">`:""}<span>${Number(player.level||0)||""}</span></div>
    <div class="analysis-history-kda"><strong>${Number(player.kills||0)} / ${Number(player.deaths||0)} / ${Number(player.assists||0)}</strong><span>${player.deaths===0?"Perfect":`${number(player.kda,2)} KDA`}</span></div>
    <button type="button" data-open-full-analysis data-user-id="${esc(userId)}" data-guild-id="${esc(match.guildId)}" data-match-id="${esc(match.matchId)}">분석</button>
  </article>`;
}

function sourcePanel(profile={}) {
  const matches=profile.matches||[], userId=profile.player?.userId||dashboard.identity?.userId||"";
  return `<section class="server-analysis-card source-card">
    <div class="analysis-source-tabs"><button type="button" class="${dashboard.tab==="scrim"?"active":""}" data-analysis-source="scrim">내전 게임 분석</button><button type="button" class="${dashboard.tab==="solo"?"active":""}" data-analysis-source="solo">솔로랭크 분석</button></div>
    ${dashboard.tab==="solo" ? `<div class="solo-pending"><strong>솔로랭크 분석은 준비 중입니다.</strong><span>Riot API 연결 후 전적과 분석을 제공합니다.</span></div>` : `<div class="analysis-history-list">${matches.map(match=>scrimMatchCard(match,userId)).join("")||`<div class="solo-pending"><strong>분석할 내전 기록이 없습니다.</strong></div>`}</div>`}
  </section>`;
}

function bindDashboard(target) {
  target.querySelectorAll("[data-server-role]").forEach(button => button.addEventListener("click", async () => {
    dashboard.role=button.dataset.serverRole; await renderDashboardBody(target);
  }));
  target.querySelectorAll("[data-analysis-source]").forEach(button => button.addEventListener("click", () => {
    dashboard.tab=button.dataset.analysisSource; renderDashboardBody(target);
  }));
}

async function loadServerMetrics(role) {
  if(dashboard.metrics.has(role))return dashboard.metrics.get(role);
  const identity=dashboard.identity;
  const data=await apiGet(`/api/community/players/${encodeURIComponent(identity.userId)}/server-metrics?guildId=${encodeURIComponent(identity.guildId)}&role=${encodeURIComponent(role)}`);
  dashboard.metrics.set(role,data.metrics); return data.metrics;
}

async function renderDashboardBody(target) {
  document.querySelectorAll("[data-analysis-section]").forEach(button=>button.classList.toggle("active",button.dataset.analysisSection===dashboard.section));
  if(dashboard.section==="matches"){
    target.innerHTML=`<div class="server-analysis-user"><span>${esc(dashboard.profile.player?.name||dashboard.identity?.name||"분석 대상")}</span><strong>경기 분석</strong></div><div class="server-analysis-layout">${sourcePanel(dashboard.profile)}</div>`;
    bindDashboard(target);
    return;
  }
  target.innerHTML=`<div class="server-analysis-loading">서버 통계를 불러오는 중...</div>`;
  try {
    const metrics=await loadServerMetrics(dashboard.role);
    target.innerHTML=`<div class="server-analysis-user"><span>${esc(dashboard.profile.player?.name||dashboard.identity?.name||"분석 대상")}</span><strong>서버 지표 <em>(서버 기준)</em></strong></div><div class="server-analysis-layout">${serverMetricPanel(metrics)}</div>`;
    bindDashboard(target);
  } catch(error) {
    target.innerHTML=`<div class="analysis-empty-inline"><strong>서버 통계를 불러오지 못했습니다.</strong><span>${esc(error.message)}</span></div>`;
  }
}

async function renderDashboard({forceReload=false,identity:requestedIdentity=null,section=dashboard.section}={}) {
  switchView("analysis"); const target=$("analysisResults"); if(!target)return;
  document.querySelectorAll("[data-analysis-section]").forEach(button=>button.classList.toggle("active",button.dataset.analysisSection===section));
  const identity=requestedIdentity?.userId&&requestedIdentity?.guildId?requestedIdentity:getAnalysisIdentity();
  if(!identity&&!canAnalyzeAllPlayers(identity?.guildId||"")){target.innerHTML=`<div class="analysis-empty-inline"><strong>분석할 Riot ID가 필요합니다.</strong><span>${analysisAccessMessage()}</span></div>`;return;}
  if(!identity){target.innerHTML=`<div class="analysis-empty-inline"><strong>분석할 유저를 선택해주세요.</strong><span>개인전적에서 유저를 선택한 뒤 분석할 수 있습니다.</span></div>`;return;}
  if(forceReload||dashboard.identity?.userId!==identity.userId||dashboard.identity?.guildId!==identity.guildId){
    target.innerHTML=`<div class="server-analysis-loading">내전 기록을 불러오는 중...</div>`;
    try { dashboard={role:"전체",tab:"scrim",section,identity,profile:await apiGet(`/api/community/analysis/players/${encodeURIComponent(identity.userId)}?guildId=${encodeURIComponent(identity.guildId)}&limit=30`),metrics:new Map()}; }
    catch(error){target.innerHTML=`<div class="analysis-empty-inline"><strong>분석 데이터를 불러오지 못했습니다.</strong><span>${esc(error.message)}</span></div>`;return;}
  }
  await renderDashboardBody(target);
}

function opponentFor(match, focus) {
  return (match.players||[]).find(row => row.team!==focus.team && row.role===focus.role);
}

function backToDashboard(identity={},originView="") {
  if(originView==="player"){history.back();return;}
  const url=new URL(window.location.href); url.search=""; url.searchParams.set("view","analysis");
  if(identity.userId)url.searchParams.set("userId",identity.userId);
  if(identity.guildId)url.searchParams.set("guildId",identity.guildId);
  history.pushState({view:"analysis"},"",`${url.pathname}${url.search}`); return renderDashboard({identity});
}

function opponentComparison(match,focus,opponent) {
  const metrics=ROLE_METRICS[focus.role]||ROLE_METRICS["전체"];
  const pairs=metrics.map(([key,label])=>{const mine=comparisonValue(focus,opponent,key),other=comparisonValue(opponent,focus,key);return {key,label,mine,other,diff:Number.isFinite(mine)&&Number.isFinite(other)?(SCORE_KEYS.has(key)||["kp","winRate"].includes(key)?mine-other:(other!==0?(mine-other)/Math.abs(other)*100:null)):null};});
  const usable=pairs.filter(row=>Number.isFinite(row.diff));
  const best=usable.filter(row=>row.diff>0).sort((a,b)=>b.diff-a.diff)[0], weak=usable.filter(row=>row.diff<0).sort((a,b)=>a.diff-b.diff)[0];
  const complete=pairs.every(row=>Number.isFinite(row.mine)&&Number.isFinite(row.other)&&(row.mine||row.other));
  const own=complete?pairs.map(row=>SCORE_KEYS.has(row.key)?Math.max(.06,Math.min(1,row.mine/100)):Math.max(.08,Math.min(.92,row.mine/((row.mine+row.other)||1)))):null;
  const enemy=complete?pairs.map(row=>SCORE_KEYS.has(row.key)?Math.max(.06,Math.min(1,row.other/100)):Math.max(.08,Math.min(.92,row.other/((row.mine+row.other)||1)))):null;
  return `<div class="opponent-report">
    <button class="report-back" type="button" data-back-dashboard>← 분석 메인</button>
    <section class="opponent-hero"><div><small>LANE MATCHUP</small><h1>${esc(focus.name)} vs ${esc(opponent?.name||"상대 라이너")}</h1><p>${esc(focus.role)} · ${esc(focus.champion)} vs ${esc(opponent?.champion||"-")}</p></div><div><span>${focus.result==="win"?"승리":"패배"}</span><strong>${Number(focus.kills||0)} / ${Number(focus.deaths||0)} / ${Number(focus.assists||0)}</strong></div></section>
    <div class="opponent-layout"><section class="server-analysis-card">${radar(metrics.map(row=>row[1]),own,enemy,opponent?.name||"상대")}</section><section class="server-analysis-card opponent-summary"><h2>상대 라이너 비교</h2>${best?`<article class="good"><span>잘한 부분</span><strong>${esc(best.label)} ${compactDeltaText(best)}</strong><p>${esc(opponent.name)}보다 높았습니다.</p></article>`:""}${weak?`<article class="weak"><span>밀린 부분</span><strong>${esc(weak.label)} ${compactDeltaText(weak)}</strong><p>${esc(opponent.name)}보다 낮았습니다.</p></article>`:""}</section></div>
    <section class="opponent-metric-grid">${pairs.map(row=>`<article><span>${esc(row.label)}</span><div><strong>${metricText(row.key,row.mine)}</strong><i>VS</i><b>${metricText(row.key,row.other)}</b></div><small class="${row.diff>=0?"positive":"negative"}">${compactDeltaText(row)}</small></article>`).join("")}</section>
  </div>`;
}

async function renderMatchAnalysis({userId="",guildId="",matchId="",originView=""}={}) {
  switchView("analysis"); const target=$("analysisResults");
  if(!hasAnalysisAccess(userId,guildId)){target.innerHTML=`<div class="analysis-empty-inline"><strong>분석 권한이 필요합니다.</strong><span>${analysisAccessMessage()}</span></div>`;return;}
  target.innerHTML=`<div class="server-analysis-loading">상대 라이너와 비교하는 중...</div>`;
  try {const [,data]=await Promise.all([apiGet(`/api/community/analysis/players/${encodeURIComponent(userId)}?guildId=${encodeURIComponent(guildId)}&limit=1`),apiGet(`/api/community/matches/${encodeURIComponent(matchId)}?guildId=${encodeURIComponent(guildId)}`)]),match=data.match,focus=focusPlayer(match,userId),opponent=focus&&opponentFor(match,focus);if(!focus||!opponent)throw new Error("같은 라인의 상대 기록을 찾지 못했습니다.");target.innerHTML=opponentComparison(match,focus,opponent);target.querySelector("[data-back-dashboard]")?.addEventListener("click",()=>backToDashboard({userId,guildId},originView));}
  catch(error){target.innerHTML=`<div class="analysis-empty-inline"><strong>경기를 분석하지 못했습니다.</strong><span>${esc(error.message)}</span></div>`;}
}

function comparisonRows(focus,opponent) {
  const metrics=ROLE_METRICS[focus.role]||ROLE_METRICS.전체;
  return metrics.map(([key,label])=>{
    const mine=comparisonValue(focus,opponent,key), other=comparisonValue(opponent,focus,key);
    let delta=null, score=null;
    if(Number.isFinite(mine)&&Number.isFinite(other)){
      if(SCORE_KEYS.has(key)||["kp","winRate"].includes(key)){
        delta=mine-other; score=delta;
      }else if(other!==0){
        delta=(mine-other)/Math.abs(other)*100; score=delta;
      }
    }
    return {key,label,mine,other,delta,score};
  });
}

function compactDeltaText(row){
  if(!Number.isFinite(row?.delta)) return "비교 데이터 없음";
  const sign=row.delta>0?"+":"";
  if(SCORE_KEYS.has(row.key)||["kp","winRate"].includes(row.key)) return `${sign}${row.delta.toFixed(1)}점`;
  return `${sign}${row.delta.toFixed(1)}%`;
}

function compactSummary(rows, opponentName){
  const usable=rows.filter(row=>Number.isFinite(row.score));
  const positives=[...usable].filter(row=>row.score>0).sort((a,b)=>b.score-a.score).slice(0,2);
  const negatives=[...usable].filter(row=>row.score<0).sort((a,b)=>a.score-b.score).slice(0,2);
  const balanced=usable.filter(row=>Math.abs(row.score)<=2).slice(0,2);
  const line=(title,items,cls)=>items.length?`<div class="compact-matchup-line ${cls}"><span>${title}</span><strong>${items.map(row=>`${esc(row.label)} ${compactDeltaText(row)}`).join(" · ")}</strong></div>`:"";
  return `<div class="compact-matchup-summary">
    ${line("우세",positives,"good")}
    ${line("열세",negatives,"weak")}
    ${!positives.length&&!negatives.length&&balanced.length?line("비슷",balanced,"even"):""}
    ${!usable.length?`<div class="compact-matchup-line even"><span>비교</span><strong>육각형 지표 데이터가 아직 부족합니다.</strong></div>`:""}
    <p>${esc(opponentName)}와 같은 라인 기준으로 이번 경기 차이를 요약했습니다.</p>
  </div>`;
}

export async function renderCompactMatchAnalysis(detail={},target) {
  if(!target)return;
  if(!hasAnalysisAccess(detail.userId,detail.guildId)){
    target.innerHTML=`<div class="compact-analysis-empty"><strong>분석 권한이 필요합니다.</strong><span>본인 경기 또는 관리 권한이 있는 서버의 회원만 분석할 수 있습니다.</span></div>`;
    return;
  }
  target.innerHTML=`<div class="compact-analysis-loading">상대 라이너와 비교하는 중...</div>`;
  try {
    const data=await apiGet(`/api/community/matches/${encodeURIComponent(detail.matchId)}?guildId=${encodeURIComponent(detail.guildId)}`);
    const focus=focusPlayer(data.match,detail.userId), opponent=focus&&opponentFor(data.match,focus);
    if(!focus||!opponent)throw new Error("같은 라인의 상대 기록을 찾지 못했습니다.");
    const rows=comparisonRows(focus,opponent), metrics=ROLE_METRICS[focus.role]||ROLE_METRICS.전체;
    const complete=rows.every(row=>Number.isFinite(row.mine)&&Number.isFinite(row.other)&&(row.mine||row.other));
    const own=complete?rows.map(row=>SCORE_KEYS.has(row.key)?Math.max(.06,Math.min(1,row.mine/100)):Math.max(.08,Math.min(.92,row.mine/((row.mine+row.other)||1)))):null;
    const enemy=complete?rows.map(row=>SCORE_KEYS.has(row.key)?Math.max(.06,Math.min(1,row.other/100)):Math.max(.08,Math.min(.92,row.other/((row.mine+row.other)||1)))):null;
    target.innerHTML=`<div class="compact-analysis-card compact-matchup-card">
      <div class="compact-matchup-head"><div><small>간단 분석</small><strong>${esc(focus.name)} <i>vs</i> ${esc(opponent.name)}</strong><span>${esc(focus.role)} · ${esc(focus.champion)} vs ${esc(opponent.champion||"-")}</span></div></div>
      ${radar(metrics.map(row=>row[1]),own,enemy,opponent.name)}
      ${compactSummary(rows,opponent.name)}
      <button class="compact-analysis-full" type="button" data-open-full-analysis data-user-id="${esc(detail.userId)}" data-guild-id="${esc(detail.guildId)}" data-match-id="${esc(detail.matchId)}">자세히 보기</button>
    </div>`;
  }catch(error){
    target.innerHTML=`<div class="compact-analysis-empty"><strong>분석하지 못했습니다.</strong><span>${esc(error.message)}</span></div>`;
  }
}

export function openAnalysisFromMatch(detail={}) {const url=new URL(window.location.href);url.search="";url.searchParams.set("view","analysis");for(const key of ["userId","guildId","matchId","riotId","originView"])if(detail[key])url.searchParams.set(key,detail[key]);history.pushState({view:"analysis"},"",`${url.pathname}${url.search}`);return renderMatchAnalysis(detail);}
export function applyAnalysisRoute(params) {const detail={userId:params.get("userId")||"",guildId:params.get("guildId")||"",matchId:params.get("matchId")||"",riotId:params.get("riotId")||"",originView:params.get("originView")||""};if(detail.riotId)detail.name=detail.riotId;const section=params.get("section")==="server"?"server":"matches";dashboard.section=section;return detail.matchId?renderMatchAnalysis(detail):renderDashboard({identity:detail.userId&&detail.guildId?detail:null,section});}
export function bindAnalysisPage() {
  document.querySelectorAll("[data-analysis-section]").forEach(button=>button.addEventListener("click",()=>{const url=new URL(window.location.href),identity=dashboard.identity;url.search="";url.searchParams.set("view","analysis");if(button.dataset.analysisSection==="server")url.searchParams.set("section","server");if(identity?.userId)url.searchParams.set("userId",identity.userId);if(identity?.guildId)url.searchParams.set("guildId",identity.guildId);history.pushState({view:"analysis"},"",`${url.pathname}${url.search}`);dashboard.section=button.dataset.analysisSection;renderDashboard({identity,section:dashboard.section});}));
  window.addEventListener("lucid:auth-changed",()=>{dashboard.identity=null;if(document.getElementById("analysisView")?.classList.contains("active"))applyAnalysisRoute(new URLSearchParams(window.location.search));});
}
