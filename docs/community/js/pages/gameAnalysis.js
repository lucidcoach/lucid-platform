import { apiGet } from "../api.js?v=20260905ae";
import { championIcon } from "../assets.js?v=20260905ae";
import { $, escapeHtml } from "../utils.js?v=20260905ae";
import { switchView } from "../view.js?v=20260904r";
import { canAnalyzePlayer, getAnalysisIdentity, canAnalyzeAllPlayers } from "../auth.js?v=20260905ag";

const METRICS = [
  ["csm", "CS/분", 1],
  ["gpm", "분당 골드", 0],
  ["dpm", "DPM", 0],
  ["kda", "KDA", 2],
  ["kp", "킬관여", 1],
];
const RADAR_METRICS = [
  ["csm", "성장"], ["gpm", "골드"], ["dpm", "딜량"],
  ["kda", "KDA"], ["kp", "킬관여"], ["aiScore", "AI"]
];
const TIER_ORDER = ["I","B","S","G","P","E","D","M","GM","C"];
const TIER_NAME = {I:"아이언",B:"브론즈",S:"실버",G:"골드",P:"플래티넘",E:"에메랄드",D:"다이아몬드",M:"마스터",GM:"그랜드마스터",C:"챌린저"};

function tierBand(tier=""){
  const t=String(tier||"").toUpperCase().replace(/[\s_-]+/g,"");
  if(t.startsWith("GRANDMASTER")||t.startsWith("GM")||String(tier).includes("그랜드마스터")) return "GM";
  if(t.startsWith("CHALLENGER")||t.startsWith("C")||String(tier).includes("챌린저")) return "C";
  if(t.startsWith("MASTER")||t==="M"||String(tier).includes("마스터")) return "M";
  const m=t.match(/^(D|E|P|G|S|B|I)/); return m?m[1]:"";
}
function tierName(tier){ const b=tierBand(tier); return TIER_NAME[b]||String(tier||"미배치"); }
function avg(rows,key){ const vals=rows.map(r=>Number(r?.[key])).filter(Number.isFinite); return vals.length?vals.reduce((a,b)=>a+b,0)/vals.length:null; }
function fmt(v,d=1){ return Number.isFinite(Number(v))?Number(v).toFixed(d):"-"; }
function pctDiff(value,base){ const a=Number(value),b=Number(base); return Number.isFinite(a)&&Number.isFinite(b)&&b!==0?(a-b)/Math.abs(b)*100:null; }
function metricValue(row,key){ return Number(row?.[key]||0); }
function normalizeChampion(v=""){ return String(v).trim().toLowerCase().replace(/[\s.'’_-]/g,""); }
function sameChampion(a,b){ return normalizeChampion(a)===normalizeChampion(b); }
function confidence(n){ if(n>=300)return["A","높음"]; if(n>=150)return["B","충분"]; if(n>=75)return["C","보통"]; return["LOW","표본 적음"]; }

async function loadAllMatches(max=500){
  const rows=[]; let offset=0;
  while(rows.length<max){
    const data=await apiGet(`/api/community/matches?limit=50&offset=${offset}&category=all`);
    const batch=data.matches||[]; rows.push(...batch); offset+=batch.length;
    if(!batch.length||offset>=Number(data.total||0)) break;
  }
  return rows.slice(0,max);
}
function findFocus(match,userId){ return (match?.players||[]).find(p=>String(p.userId)===String(userId)); }
function byChampionRole(matches,champion,role){
  const rows=[];
  for(const match of matches) for(const p of (match.players||[])) if(sameChampion(p.champion,champion)&&String(p.role)===String(role)) rows.push({...p,time:match.time,matchId:match.matchId});
  return rows;
}
function uniquePlayerMatches(rows){ const seen=new Set(); return rows.filter(r=>{const k=`${r.matchId}:${r.userId}`;if(seen.has(k))return false;seen.add(k);return true;}); }
function benchmarkGroups(rows){
  const map=new Map();
  for(const row of rows){ const band=tierBand(row.tier); if(!band) continue; if(!map.has(band)) map.set(band,[]); map.get(band).push(row); }
  return [...map.entries()].sort((a,b)=>TIER_ORDER.indexOf(a[0])-TIER_ORDER.indexOf(b[0]));
}
function groupFor(groups,band){ return groups.find(([t])=>t===band)?.[1]||[]; }

function metricCard(key,label,digits,focus,current,upper,currentBand,upperBand){
  const cv=avg(current,key),uv=avg(upper,key),diff=pctDiff(metricValue(focus,key),cv); const cls=diff==null?"":diff>=0?"positive":"negative";
  return `<div class="analysis-metric-card"><span>${label}</span><strong>${fmt(metricValue(focus,key),digits)}</strong><small class="${cls}">${diff==null?"동티어 표본 없음":`${diff>=0?"+":""}${diff.toFixed(1)}% · ${tierName(currentBand)} 평균 대비`}</small><div><em>${tierName(currentBand)} ${fmt(cv,digits)}</em><em>${upperBand?`${tierName(upperBand)} ${fmt(uv,digits)}`:"상위 티어 -"}</em></div></div>`;
}
function tierTable(groups,currentBand){
  if(!groups.length) return `<div class="analysis-empty-inline">같은 챔피언·포지션 표본이 아직 없습니다.</div>`;
  return `<div class="analysis-tier-table"><div class="analysis-tier-head"><span>티어</span><span>표본</span>${METRICS.map(m=>`<span>${m[1]}</span>`).join("")}</div>${groups.map(([band,rows])=>`<div class="analysis-tier-row ${band===currentBand?"is-current":""}"><strong>${tierName(band)}</strong><span>${rows.length}</span>${METRICS.map(([k,,d])=>`<span>${fmt(avg(rows,k),d)}</span>`).join("")}</div>`).join("")}</div>`;
}
function growthBlock(rows){
  const ordered=[...rows].sort((a,b)=>String(a.time).localeCompare(String(b.time)));
  if(ordered.length<4) return `<div class="analysis-empty-inline">같은 챔피언·포지션 기록이 ${ordered.length}경기라 성장 추세는 4경기부터 표시합니다.</div>`;
  const size=Math.min(5,Math.floor(ordered.length/2)),early=ordered.slice(0,size),recent=ordered.slice(-size);
  return `<div class="growth-grid">${METRICS.map(([k,label,d])=>{const a=avg(early,k),b=avg(recent,k),diff=pctDiff(b,a),cls=diff==null?"":diff>=0?"positive":"negative";return `<div class="growth-card"><span>${label}</span><strong>${fmt(a,d)} <b>→</b> ${fmt(b,d)}</strong><em class="${cls}">${diff==null?"-":`${diff>=0?"▲":"▼"} ${Math.abs(diff).toFixed(1)}%`}</em></div>`;}).join("")}</div><p class="analysis-footnote">초기 ${size}경기 평균과 최근 ${size}경기 평균 비교 · Lucid 내전 상세기록 기준</p>`;
}
function insightRows(focus,current,currentBand){
  if(!focus||!current?.length) return "";
  const scored=METRICS.map(([k,label])=>({label,diff:pctDiff(metricValue(focus,k),avg(current,k))})).filter(x=>Number.isFinite(x.diff));
  const best=[...scored].sort((a,b)=>b.diff-a.diff).slice(0,2), weak=[...scored].sort((a,b)=>a.diff-b.diff).slice(0,2);
  return `<div class="analysis-insight-grid"><section><h3>이번 경기 강점</h3>${best.map(x=>`<p><strong>${x.label}</strong><span class="positive">${tierName(currentBand)} 평균보다 ${Math.abs(x.diff).toFixed(1)}% 높음</span></p>`).join("")||"<p>표본 부족</p>"}</section><section><h3>우선 보완</h3>${weak.map(x=>`<p><strong>${x.label}</strong><span class="${x.diff<0?"negative":"positive"}">${tierName(currentBand)} 평균보다 ${Math.abs(x.diff).toFixed(1)}% ${x.diff<0?"낮음":"높음"}</span></p>`).join("")||"<p>표본 부족</p>"}</section></div>`;
}

function radarPoints(values,cx=92,cy=86,r=62){
  return values.map((v,i)=>{const a=-Math.PI/2+i*Math.PI/3,rr=r*Math.max(.08,Math.min(.95,v));return `${(cx+Math.cos(a)*rr).toFixed(1)},${(cy+Math.sin(a)*rr).toFixed(1)}`;}).join(" ");
}
function compactRadar(focus,current){
  const own=RADAR_METRICS.map(([k])=>{const b=avg(current,k),v=metricValue(focus,k);return b&&v?Math.max(.15,Math.min(.95,.5*(v/b))):.5;});
  const benchmark=RADAR_METRICS.map(()=>.5);
  const axes=RADAR_METRICS.map(([,label],i)=>{const a=-Math.PI/2+i*Math.PI/3,x=92+Math.cos(a)*78,y=86+Math.sin(a)*78;return `<text x="${x.toFixed(1)}" y="${y.toFixed(1)}" text-anchor="middle">${label}</text>`;}).join("");
  const grid=[.25,.5,.75].map(scale=>`<polygon points="${radarPoints(RADAR_METRICS.map(()=>scale))}" class="radar-grid"/>`).join("");
  return `<svg class="compact-radar" viewBox="0 0 184 172" role="img" aria-label="이번 경기와 티어 평균 육각형 비교">${grid}<polygon points="${radarPoints(benchmark)}" class="radar-benchmark"/><polygon points="${radarPoints(own)}" class="radar-own"/>${axes}</svg>`;
}
function compactMessages(focus,current,currentBand){
  if(!current.length) return [`${tierName(currentBand)} 동일 챔피언·포지션 표본이 아직 부족합니다.`];
  const scored=METRICS.map(([k,label])=>({label,d:pctDiff(metricValue(focus,k),avg(current,k))})).filter(x=>Number.isFinite(x.d));
  if(!scored.length) return ["비교 가능한 상세 지표가 부족합니다."];
  const best=[...scored].sort((a,b)=>b.d-a.d)[0],weak=[...scored].sort((a,b)=>a.d-b.d)[0];
  const out=[];
  if(best) out.push(`${best.label}은 ${tierName(currentBand)} 평균보다 ${Math.abs(best.d).toFixed(0)}% ${best.d>=0?"높습니다":"낮습니다"}.`);
  if(weak&&weak.label!==best?.label) out.push(`${weak.label}은 ${tierName(currentBand)} 평균보다 ${Math.abs(weak.d).toFixed(0)}% ${weak.d<0?"낮아 우선 개선 후보입니다":"높습니다"}.`);
  out.push(`이번 경기는 ${tierName(currentBand)} ${focus.champion} ${focus.role} 평균과 비교했습니다.`);
  return out;
}

export async function renderCompactMatchAnalysis(detail={},target){
  if(!target) return;
  const {userId="",guildId="",matchId=""}=detail;
  if(!canAnalyzePlayer(userId,guildId)){
    target.innerHTML=`<div class="compact-analysis-empty"><strong>분석 권한이 필요합니다.</strong><span>${canAnalyzeAllPlayers()?"":"로그인 후 내 정보에 등록한 Riot ID의 경기만 분석할 수 있습니다. 코치 권한 이상은 모든 유저를 분석할 수 있습니다."}</span></div>`; return;
  }
  target.innerHTML=`<div class="compact-analysis-loading">분석 중...</div>`;
  try{
    const matches=await loadAllMatches(); const match=matches.find(m=>String(m.matchId)===String(matchId)); const focus=match?findFocus(match,userId):null;
    if(!focus) throw new Error("경기 데이터를 찾지 못했습니다.");
    const samples=uniquePlayerMatches(byChampionRole(matches,focus.champion,focus.role)); const groups=benchmarkGroups(samples); const band=tierBand(focus.tier); const current=groupFor(groups,band);
    target.innerHTML=`<div class="compact-analysis-card"><div class="compact-analysis-title"><div><small>간단 분석</small><strong>${escapeHtml(focus.champion)} · ${escapeHtml(focus.role)}</strong><span>이번 경기 ${escapeHtml(focus.tier||"-")} → ${tierName(band)} 평균</span></div><div class="compact-analysis-legend"><i></i>내 수치 <b></b>티어 평균</div></div>${compactRadar(focus,current)}<div class="compact-analysis-messages">${compactMessages(focus,current,band).map(x=>`<p>${escapeHtml(x)}</p>`).join("")}</div><button class="compact-analysis-full" type="button" data-open-full-analysis data-user-id="${escapeHtml(userId)}" data-guild-id="${escapeHtml(guildId)}" data-match-id="${escapeHtml(matchId)}" data-champion="${escapeHtml(focus.champion||"")}" data-role="${escapeHtml(focus.role||"")}">상세 분석 보기</button></div>`;
  }catch(e){ target.innerHTML=`<div class="compact-analysis-empty"><strong>분석하지 못했습니다.</strong><span>${escapeHtml(e.message)}</span></div>`; }
}

async function renderAnalysis({userId="",guildId="",matchId="",champion="",role=""}={}){
  switchView("analysis"); const target=$("analysisResults"),button=$("analysisRunBtn");
  if(userId && !canAnalyzePlayer(userId,guildId)){ target.innerHTML=`<div class="analysis-empty-inline"><strong>분석 권한이 필요합니다.</strong><span>일반 계정은 내 정보에 등록한 Riot ID의 내전 기록만 분석할 수 있습니다. 코치 권한 이상은 모든 유저를 분석할 수 있습니다.</span></div>`; return; }
  if(button){button.disabled=true;button.textContent="분석 중";} target.innerHTML=`<div class="analysis-loading">같은 챔피언·포지션 표본을 모으는 중...</div>`;
  try{
    const matches=await loadAllMatches(); const selectedMatch=matchId?matches.find(m=>String(m.matchId)===String(matchId)):null; let focus=selectedMatch&&userId?findFocus(selectedMatch,userId):null;
    if(focus){champion=focus.champion;role=focus.role;} champion=String(champion||$("analysisChampion")?.value||"").trim(); role=String(role||$("analysisRole")?.value||"정글"); if(!champion) throw new Error("챔피언을 입력해주세요.");
    if($("analysisChampion")) $("analysisChampion").value=champion; if($("analysisRole")) $("analysisRole").value=role;
    const samples=uniquePlayerMatches(byChampionRole(matches,champion,role)); const groups=benchmarkGroups(samples); const ownRows=userId?samples.filter(r=>String(r.userId)===String(userId)):[];
    if(!focus&&ownRows.length) focus=[...ownRows].sort((a,b)=>String(b.time).localeCompare(String(a.time)))[0];
    if(!focus) focus={champion,role,tier:"",csm:avg(samples,"csm")||0,gpm:avg(samples,"gpm")||0,dpm:avg(samples,"dpm")||0,kda:avg(samples,"kda")||0,kp:avg(samples,"kp")||0};
    const currentBand=tierBand(focus.tier), current=groupFor(groups,currentBand), nextBand=TIER_ORDER[TIER_ORDER.indexOf(currentBand)+1]||"", upper=groupFor(groups,nextBand); const [confCode,confLabel]=confidence(samples.length); const icon=championIcon(champion);
    target.innerHTML=`<section class="analysis-context-card"><div class="analysis-context-title">${icon?`<img src="${escapeHtml(icon)}" alt="">`:""}<div><small>${matchId?"선택한 내전 경기":"내 기록 기준"}</small><h2>${escapeHtml(champion)} · ${escapeHtml(role)}</h2><p>${focus.tier?`이번 경기 <strong>${escapeHtml(focus.tier)}</strong> · `:""}<strong>${tierName(currentBand)}</strong> 구간 평균과 비교${nextBand?` · 다음 기준 <strong>${tierName(nextBand)}</strong>`:""}</p><span class="analysis-context-detail">${tierName(currentBand)}는 ${current.length}경기 · 전체 동일 챔피언/포지션 ${samples.length}경기 표본</span></div></div><div class="analysis-confidence-badge ${confCode.toLowerCase()}"><strong>${confCode}</strong><span>${confLabel}</span></div></section><div class="analysis-subtabs"><button class="active" type="button" data-analysis-anchor="game">이번 경기</button><button type="button" data-analysis-anchor="tiers">티어 비교</button><button type="button" data-analysis-anchor="growth">내 성장</button></div><section id="analysisGame" class="analysis-section"><div class="analysis-section-head"><div><small>THIS MATCH</small><h2>${escapeHtml(champion)} ${escapeHtml(role)} · 이번 경기 vs ${tierName(currentBand)} 평균</h2></div></div><div class="analysis-metric-grid">${METRICS.map(m=>metricCard(...m,focus,current,upper,currentBand,nextBand)).join("")}</div>${insightRows(focus,current,currentBand)}</section><section id="analysisTiers" class="analysis-section"><div class="analysis-section-head"><div><small>BENCHMARK</small><h2>${escapeHtml(champion)} ${escapeHtml(role)} 티어 구간별 평균</h2></div><span>G4~G1=골드 · P4~P1=플래티넘처럼 한 구간으로 묶음</span></div>${tierTable(groups,currentBand)}</section><section id="analysisGrowth" class="analysis-section"><div class="analysis-section-head"><div><small>GROWTH</small><h2>내 ${escapeHtml(champion)} 성장 변화</h2></div><span>${ownRows.length}경기</span></div>${userId?growthBlock(ownRows):`<div class="analysis-empty-inline">내 정보에 Riot ID를 등록하면 해당 계정의 성장 변화가 연결됩니다.</div>`}</section>`;
    target.querySelectorAll("[data-analysis-anchor]").forEach(btn=>btn.addEventListener("click",()=>{target.querySelectorAll("[data-analysis-anchor]").forEach(x=>x.classList.toggle("active",x===btn));const id={game:"analysisGame",tiers:"analysisTiers",growth:"analysisGrowth"}[btn.dataset.analysisAnchor];document.getElementById(id)?.scrollIntoView({behavior:"smooth",block:"start"});}));
  }catch(error){target.innerHTML=`<div class="analysis-empty-inline"><strong>분석하지 못했습니다.</strong><span>${escapeHtml(error.message)}</span></div>`;}finally{if(button){button.disabled=false;button.textContent="분석";}}
}

export function openAnalysisFromMatch(detail={}){ const url=new URL(window.location.href);url.search="";url.searchParams.set("view","analysis");for(const key of ["userId","guildId","matchId","champion","role"])if(detail[key])url.searchParams.set(key,detail[key]);history.pushState({view:"analysis"},"",`${url.pathname}${url.search}`);return renderAnalysis(detail); }
export function applyAnalysisRoute(params){ const detail={userId:params.get("userId")||"",guildId:params.get("guildId")||"",matchId:params.get("matchId")||"",champion:params.get("champion")||"",role:params.get("role")||""};if(detail.matchId||detail.champion)return renderAnalysis(detail);switchView("analysis");return Promise.resolve(); }
export function bindAnalysisPage(){ const btn=$("analysisRunBtn");btn?.addEventListener("click",()=>{const own=getAnalysisIdentity();renderAnalysis({userId:own?.userId||"",guildId:own?.guildId||"",champion:$("analysisChampion")?.value||"",role:$("analysisRole")?.value||"정글"});});$("analysisChampion")?.addEventListener("keydown",e=>{if(e.key==="Enter"){e.preventDefault();btn?.click();}}); }
