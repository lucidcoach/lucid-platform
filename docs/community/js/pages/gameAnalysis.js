import { apiGet } from "../api.js?v=20260905ad";
import { championIcon } from "../assets.js?v=20260905ab";
import { $, escapeHtml } from "../utils.js?v=20260905ab";
import { switchView } from "../view.js?v=20260904r";

const ROLE_OPTIONS = ["탑", "정글", "미드", "원딜", "서폿"];
const METRICS = [
  ["csm", "CS/min", 1],
  ["gpm", "Gold/min", 0],
  ["dpm", "DPM", 0],
  ["kda", "KDA", 2],
  ["kp", "KP", 1],
];

const tierOrder = ["I","B","S","G","P","E","D","M","GM","C"];
function tierBand(tier="") {
  const t = String(tier || "").toUpperCase().replace(/\s/g, "");
  if (t.startsWith("GM")) return "GM";
  const m = t.match(/^(C|M|D|E|P|G|S|B|I)/);
  return m ? m[1] : "";
}
function tierSort(a,b){ return tierOrder.indexOf(tierBand(a)) - tierOrder.indexOf(tierBand(b)); }
function avg(rows,key){
  const vals = rows.map(r=>Number(r?.[key])).filter(Number.isFinite);
  return vals.length ? vals.reduce((a,b)=>a+b,0)/vals.length : null;
}
function fmt(v,d=1){ return Number.isFinite(Number(v)) ? Number(v).toFixed(d) : "-"; }
function pctDiff(value, base){
  const a=Number(value), b=Number(base);
  if(!Number.isFinite(a)||!Number.isFinite(b)||b===0) return null;
  return (a-b)/Math.abs(b)*100;
}
function metricValue(row,key){
  if(key === "kp") return Number(row?.kp || 0);
  return Number(row?.[key] || 0);
}
function normalizeChampion(value=""){ return String(value).trim().toLowerCase().replace(/[\s.'’_-]/g,""); }
function sameChampion(a,b){ return normalizeChampion(a) === normalizeChampion(b); }

async function loadAllMatches(max=500){
  const rows=[]; let offset=0;
  while(rows.length < max){
    const data = await apiGet(`/api/community/matches?limit=50&offset=${offset}&category=all`);
    const batch = data.matches || [];
    rows.push(...batch);
    offset += batch.length;
    if(!batch.length || offset >= Number(data.total||0)) break;
  }
  return rows.slice(0,max);
}

function findFocus(match,userId){ return (match?.players||[]).find(p=>String(p.userId)===String(userId)); }
function byChampionRole(matches,champion,role){
  const rows=[];
  for(const match of matches){
    for(const p of (match.players||[])){
      if(sameChampion(p.champion,champion) && String(p.role)===String(role)) rows.push({...p, time:match.time, matchId:match.matchId});
    }
  }
  return rows;
}
function uniquePlayerMatches(rows){
  const seen=new Set();
  return rows.filter(r=>{ const k=`${r.matchId}:${r.userId}`; if(seen.has(k)) return false; seen.add(k); return true; });
}
function benchmarkGroups(rows){
  const map=new Map();
  for(const row of rows){
    const tier=String(row.tier||"미배치");
    if(!tier || tier==="미배치") continue;
    if(!map.has(tier)) map.set(tier,[]);
    map.get(tier).push(row);
  }
  return [...map.entries()].sort((a,b)=>tierSort(a[0],b[0]));
}
function confidence(n){ if(n>=300)return["A","높음"]; if(n>=150)return["B","충분"]; if(n>=75)return["C","보통"]; return["LOW","표본 적음"]; }

function metricCard(key,label,digits,focus,current,upper){
  const cv=current ? avg(current,key):null, uv=upper ? avg(upper,key):null;
  const d=pctDiff(metricValue(focus,key),cv);
  const cls=d==null?"":d>=0?"positive":"negative";
  return `<div class="analysis-metric-card">
    <span>${label}</span><strong>${fmt(metricValue(focus,key),digits)}</strong>
    <small class="${cls}">${d==null?"비교 표본 없음":`${d>=0?"+":""}${d.toFixed(1)}% · 현재 티어 평균 대비`}</small>
    <div><em>동티어 ${fmt(cv,digits)}</em><em>상위 ${fmt(uv,digits)}</em></div>
  </div>`;
}

function tierTable(groups,focusTier){
  if(!groups.length) return `<div class="analysis-empty-inline">같은 챔피언·포지션 표본이 아직 없습니다.</div>`;
  return `<div class="analysis-tier-table">
    <div class="analysis-tier-head"><span>티어</span><span>표본</span>${METRICS.map(m=>`<span>${m[1]}</span>`).join("")}</div>
    ${groups.map(([tier,rows])=>`<div class="analysis-tier-row ${tier===focusTier?"is-current":""}"><strong>${escapeHtml(tier)}</strong><span>${rows.length}</span>${METRICS.map(([k,,d])=>`<span>${fmt(avg(rows,k),d)}</span>`).join("")}</div>`).join("")}
  </div>`;
}

function growthBlock(rows){
  const ordered=[...rows].sort((a,b)=>String(a.time).localeCompare(String(b.time)));
  if(ordered.length<4) return `<div class="analysis-empty-inline">같은 챔피언·포지션 기록이 ${ordered.length}경기라 성장 추세는 4경기부터 표시합니다.</div>`;
  const size=Math.min(5,Math.floor(ordered.length/2));
  const early=ordered.slice(0,size), recent=ordered.slice(-size);
  return `<div class="growth-grid">${METRICS.map(([k,label,d])=>{
    const a=avg(early,k), b=avg(recent,k), diff=pctDiff(b,a), cls=diff==null?"":diff>=0?"positive":"negative";
    return `<div class="growth-card"><span>${label}</span><strong>${fmt(a,d)} <b>→</b> ${fmt(b,d)}</strong><em class="${cls}">${diff==null?"-":`${diff>=0?"▲":"▼"} ${Math.abs(diff).toFixed(1)}%`}</em></div>`;
  }).join("")}</div><p class="analysis-footnote">초기 ${size}경기 평균과 최근 ${size}경기 평균 비교 · Lucid 내전 상세기록 기준</p>`;
}

function insightRows(focus,current){
  if(!focus || !current?.length) return "";
  const scored=METRICS.map(([k,label])=>({label,diff:pctDiff(metricValue(focus,k),avg(current,k))})).filter(x=>Number.isFinite(x.diff));
  scored.sort((a,b)=>b.diff-a.diff);
  const best=scored.slice(0,2), weak=[...scored].sort((a,b)=>a.diff-b.diff).slice(0,2);
  return `<div class="analysis-insight-grid"><section><h3>강점</h3>${best.map(x=>`<p><strong>${x.label}</strong><span class="positive">동티어 평균보다 ${Math.abs(x.diff).toFixed(1)}% ${x.diff>=0?"높음":"낮음"}</span></p>`).join("")||"<p>표본 부족</p>"}</section><section><h3>보완</h3>${weak.map(x=>`<p><strong>${x.label}</strong><span class="${x.diff<0?"negative":"positive"}">${x.diff<0?"동티어 평균보다":"동티어 평균보다"} ${Math.abs(x.diff).toFixed(1)}% ${x.diff<0?"낮음":"높음"}</span></p>`).join("")||"<p>표본 부족</p>"}</section></div>`;
}

async function renderAnalysis({userId="",guildId="",matchId="",champion="",role=""}={}){
  switchView("analysis");
  const target=$("analysisResults");
  const button=$("analysisRunBtn");
  if(button){button.disabled=true;button.textContent="분석 중";}
  target.innerHTML=`<div class="analysis-loading">같은 챔피언·포지션 표본을 모으는 중...</div>`;
  try{
    const matches=await loadAllMatches();
    let selectedMatch=matchId?matches.find(m=>String(m.matchId)===String(matchId)):null;
    let focus=selectedMatch&&userId?findFocus(selectedMatch,userId):null;
    if(focus){ champion=focus.champion; role=focus.role; }
    champion=String(champion||$("analysisChampion")?.value||"").trim();
    role=String(role||$("analysisRole")?.value||"정글");
    if(!champion) throw new Error("챔피언을 입력해주세요.");
    if($("analysisChampion")) $("analysisChampion").value=champion;
    if($("analysisRole")) $("analysisRole").value=role;

    const samples=uniquePlayerMatches(byChampionRole(matches,champion,role));
    const groups=benchmarkGroups(samples);
    let ownRows=userId?samples.filter(r=>String(r.userId)===String(userId)):[];
    if(!focus && ownRows.length) focus=[...ownRows].sort((a,b)=>String(b.time).localeCompare(String(a.time)))[0];
    if(!focus){
      focus={champion,role,tier:"",csm:avg(samples,"csm")||0,gpm:avg(samples,"gpm")||0,dpm:avg(samples,"dpm")||0,kda:avg(samples,"kda")||0,kp:avg(samples,"kp")||0};
    }
    const currentTier=focus.tier||"";
    const current=groups.find(([t])=>t===currentTier)?.[1]||[];
    const currentBand=tierBand(currentTier), nextBand=tierOrder[tierOrder.indexOf(currentBand)+1];
    const upper=groups.filter(([t])=>tierBand(t)===nextBand).flatMap(([,r])=>r);
    const [confCode,confLabel]=confidence(samples.length);
    const icon=championIcon(champion);

    target.innerHTML=`
      <section class="analysis-context-card">
        <div class="analysis-context-title">${icon?`<img src="${escapeHtml(icon)}" alt="">`:""}<div><small>${userId?"선택한 내전 경기 기준":"Lucid 내전 표본 기준"}</small><h2>${escapeHtml(champion)} · ${escapeHtml(role)}</h2><p>${currentTier?`당시 티어 <strong>${escapeHtml(currentTier)}</strong> · `:""}동일 챔피언/포지션 ${samples.length}경기 비교</p></div></div>
        <div class="analysis-confidence-badge ${confCode.toLowerCase()}"><strong>${confCode}</strong><span>${confLabel}</span></div>
      </section>
      <div class="analysis-subtabs"><button class="active" type="button" data-analysis-anchor="game">이번 경기</button><button type="button" data-analysis-anchor="tiers">티어 비교</button><button type="button" data-analysis-anchor="growth">내 성장</button></div>
      <section id="analysisGame" class="analysis-section"><div class="analysis-section-head"><div><small>THIS MATCH</small><h2>이번 경기 vs 티어 평균</h2></div></div><div class="analysis-metric-grid">${METRICS.map(m=>metricCard(...m,focus,current,upper)).join("")}</div>${insightRows(focus,current)}</section>
      <section id="analysisTiers" class="analysis-section"><div class="analysis-section-head"><div><small>BENCHMARK</small><h2>${escapeHtml(champion)} ${escapeHtml(role)} 티어별 평균</h2></div><span>Lucid 내전 데이터 · ${samples.length}표본</span></div>${tierTable(groups,currentTier)}</section>
      <section id="analysisGrowth" class="analysis-section"><div class="analysis-section-head"><div><small>GROWTH</small><h2>내 ${escapeHtml(champion)} 성장 변화</h2></div><span>${ownRows.length}경기</span></div>${userId?growthBlock(ownRows):`<div class="analysis-empty-inline">개인전적의 경기에서 분석을 열면 내 성장 변화가 연결됩니다.</div>`}</section>
      <section class="analysis-api-note"><strong>일반 유저 Riot 벤치마크</strong><span>현재 화면은 Lucid 내전 API 데이터로 먼저 동작합니다. 별도 Riot benchmark DB의 <code>region + patch + tier + position + champion</code> 셀을 이 비교표에 그대로 합칠 수 있게 구조를 분리했습니다.</span></section>`;

    target.querySelectorAll("[data-analysis-anchor]").forEach(btn=>btn.addEventListener("click",()=>{
      target.querySelectorAll("[data-analysis-anchor]").forEach(x=>x.classList.toggle("active",x===btn));
      const id={game:"analysisGame",tiers:"analysisTiers",growth:"analysisGrowth"}[btn.dataset.analysisAnchor];
      document.getElementById(id)?.scrollIntoView({behavior:"smooth",block:"start"});
    }));
  }catch(error){ target.innerHTML=`<div class="analysis-empty-inline"><strong>분석하지 못했습니다.</strong><span>${escapeHtml(error.message)}</span></div>`; }
  finally{ if(button){button.disabled=false;button.textContent="분석";} }
}

export function openAnalysisFromMatch(detail={}){
  const url=new URL(window.location.href); url.search="";
  url.searchParams.set("view","analysis");
  for(const key of ["userId","guildId","matchId","champion","role"]){ if(detail[key]) url.searchParams.set(key,detail[key]); }
  history.pushState({view:"analysis"},"",`${url.pathname}${url.search}`);
  return renderAnalysis(detail);
}

export function applyAnalysisRoute(params){
  const detail={userId:params.get("userId")||"",guildId:params.get("guildId")||"",matchId:params.get("matchId")||"",champion:params.get("champion")||"",role:params.get("role")||""};
  if(detail.matchId || detail.champion) return renderAnalysis(detail);
  switchView("analysis");
  return Promise.resolve();
}

export function bindAnalysisPage(){
  const btn=$("analysisRunBtn");
  btn?.addEventListener("click",()=>renderAnalysis({champion:$("analysisChampion")?.value||"",role:$("analysisRole")?.value||"정글"}));
  $("analysisChampion")?.addEventListener("keydown",e=>{if(e.key==="Enter"){e.preventDefault();btn?.click();}});
}
