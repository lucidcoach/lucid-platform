import { apiGet } from "../api.js?v=20260905ar";
import { championIcon } from "../assets.js?v=20260905ar";
import { $, escapeHtml } from "../utils.js?v=20260905ar";
import { switchView } from "../view.js?v=20260905ar";
import { canAnalyzePlayer, getAnalysisIdentity, canAnalyzeAllPlayers, getRiotAccounts } from "../auth.js?v=20260905ar";

const METRICS = [
  ["csm", "CS/분", 1],
  ["gpm", "분당 골드", 0],
  ["dpm", "DPM", 0],
  ["kda", "KDA", 2],
  ["kp", "킬관여", 1],
];
const TIER_ORDER = ["I","B","S","G","P","E","D","M","GM","C"];
const TIER_NAME = {I:"아이언",B:"브론즈",S:"실버",G:"골드",P:"플래티넘",E:"에메랄드",D:"다이아몬드",M:"마스터",GM:"그랜드마스터",C:"챌린저"};
const ROLES=["탑","정글","미드","원딜","서폿"];

const analysisState={tab:"overview",champion:"",role:"정글"};
let dashboardCache={key:"",loadedAt:0,profile:null,solo:null,identity:null};
const benchmarkCache=new Map();
const CACHE_TTL=5*60*1000;

function esc(v){return escapeHtml(String(v??""));}
function fmt(v,d=1){return Number.isFinite(Number(v))?Number(v).toFixed(d):"-";}
function tierBand(tier=""){
  const raw=String(tier||""); const t=raw.toUpperCase().replace(/[\s_-]+/g,"");
  if(t.startsWith("GRANDMASTER")||t.startsWith("GM")||raw.includes("그랜드마스터"))return"GM";
  if(t.startsWith("CHALLENGER")||raw.includes("챌린저"))return"C";
  if(t.startsWith("MASTER")||t==="M"||raw.includes("마스터"))return"M";
  const m=t.match(/^(D|E|P|G|S|B|I)/);return m?m[1]:"";
}
function tierName(tier){const b=tierBand(tier);return TIER_NAME[b]||String(tier||"미배치");}
function pctDiff(value,base){const a=Number(value),b=Number(base);return Number.isFinite(a)&&Number.isFinite(b)&&b!==0?(a-b)/Math.abs(b)*100:null;}
function avg(rows,key){const vals=rows.map(r=>Number(r?.[key])).filter(Number.isFinite);return vals.length?vals.reduce((a,b)=>a+b,0)/vals.length:null;}
function winRate(rows){const played=rows.filter(r=>["win","loss"].includes(String(r.result)));return played.length?played.filter(r=>r.result==="win").length/played.length*100:0;}
function findFocus(match,userId){return(match?.players||[]).find(p=>String(p.userId)===String(userId));}
function ownRows(profile,identity){return (profile?.matches||[]).map(m=>{const p=findFocus(m,identity?.userId);return p?{...p,time:m.time,matchId:m.matchId,guildId:m.guildId}:null;}).filter(Boolean);}
function dashboardIdentityKey(identity){return identity?`${identity.guildId}:${identity.userId}`:"admin";}
function dashboardCacheValid(identity){return dashboardCache.profile&&dashboardCache.key===dashboardIdentityKey(identity)&&(Date.now()-dashboardCache.loadedAt)<CACHE_TTL;}
function invalidateDashboardCache(){dashboardCache={key:"",loadedAt:0,profile:null,solo:null,identity:null};benchmarkCache.clear();}

async function loadProfile(identity){
  if(!identity?.userId||!identity?.guildId)return null;
  try{return await apiGet(`/api/community/players/${encodeURIComponent(identity.userId)}?guildId=${encodeURIComponent(identity.guildId)}&limit=30`);}catch(_){return null;}
}
async function loadSoloSummary(){
  const riotId=(getRiotAccounts()||[])[0];
  if(!riotId)return{available:false,reason:"riot_id_missing"};
  try{return await apiGet(`/api/community/riot/solo-summary?riotId=${encodeURIComponent(riotId)}`);}catch(_){return{available:false,reason:"api_not_ready",riotId};}
}
async function getBenchmark({champion="",role="",guildId=""}={}){
  const key=`${guildId}|${champion}|${role}`;
  const cached=benchmarkCache.get(key);
  if(cached&&(Date.now()-cached.at)<CACHE_TTL)return cached.data;
  const q=new URLSearchParams();
  if(champion)q.set("champion",champion);
  if(role)q.set("role",role);
  if(guildId)q.set("guildId",guildId);
  const data=await apiGet(`/api/community/analysis/benchmark?${q.toString()}`);
  benchmarkCache.set(key,{at:Date.now(),data});
  return data;
}
function benchmarkTier(data,band){return(data?.tiers||[]).find(x=>x.tier===band)||null;}
function metricFromTier(row,key){return Number(row?.metrics?.[key]);}

function statBox(label,value,sub=""){return`<div class="ga-stat"><span>${esc(label)}</span><strong>${esc(value)}</strong>${sub?`<small>${esc(sub)}</small>`:""}</div>`;}
function profileHead(profile,identity,solo){
  const p=profile?.player||{};const riotId=getRiotAccounts()?.[0]||identity?.name||"Riot ID 미등록";
  return`<section class="ga-profile-head"><div class="ga-profile-id"><div class="ga-avatar">${p.profileIconUrl?`<img src="${esc(p.profileIconUrl)}" alt="">`:"L"}</div><div><small>ANALYSIS PLAYER</small><h2>${esc(riotId)}</h2><span>${identity?.name&&identity.name!==riotId?`Lucid 등록명 · ${esc(identity.name)}`:"Lucid 커뮤니티 분석"}</span></div></div><div class="ga-rank-pair"><div><span>Riot 솔로랭크</span><strong>${solo?.available!==false?esc(solo?.tier||"연동 중"):"API 연동 대기"}</strong><small>${solo?.lp!=null?`${esc(solo.lp)} LP`:"솔로랭크 API endpoint 필요"}</small></div><div><span>Lucid 내전 티어</span><strong>${esc(p.tier||"미배치")}</strong><small>${p.games||0}경기 · 승률 ${fmt(p.winRate,1)}%</small></div></div></section>`;
}
function tabs(){const items=[["overview","종합"],["champion","챔피언 분석"],["role","포지션 분석"],["compare","비교 분석"],["growth","성장 분석"]];return`<div class="ga-tabs">${items.map(([id,label])=>`<button class="${analysisState.tab===id?"active":""}" data-ga-tab="${id}" type="button">${label}</button>`).join("")}</div>`;}
function topChampions(profile){return(profile?.player?.championStats?.["전체"]||[]).slice(0,5);}
function roleBars(rows){const total=Math.max(1,rows.length);return ROLES.map(role=>{const n=rows.filter(r=>r.role===role).length,p=Math.round(n/total*100);return`<div class="ga-role-row"><span>${role}</span><div><i style="width:${p}%"></i></div><b>${p}%</b></div>`;}).join("");}
function overviewPanel(profile,rows,solo){
  const p=profile?.player||{},recent=rows.slice(0,20),champs=topChampions(profile);
  return`<div class="ga-overview-grid"><section class="ga-panel ga-span-2"><div class="ga-panel-head"><div><small>PERFORMANCE</small><h3>솔로랭크 + 내전 한눈에 보기</h3></div><span class="ga-source-chip">내전 상세기록 기준</span></div><div class="ga-stat-grid">${statBox("최근 내전 승률",`${fmt(winRate(recent),1)}%`,`${recent.length}경기`)}${statBox("전체 내전 승률",`${fmt(p.winRate,1)}%`,`${p.games||0}경기`)}${statBox("평균 KDA",fmt(p.averageKda,2))}${statBox("평균 CS",fmt(p.averageCs,1))}${statBox("AI Score",p.averageAiScore==null?"-":fmt(p.averageAiScore,1))}</div></section><section class="ga-panel"><div class="ga-panel-head"><div><small>ROLE</small><h3>주 포지션</h3></div></div>${roleBars(rows)}</section><section class="ga-panel"><div class="ga-panel-head"><div><small>CHAMPIONS</small><h3>자주 플레이한 챔피언</h3></div></div><div class="ga-champion-list">${champs.map(c=>`<button data-ga-champion="${esc(c.champion)}"><img src="${esc(championIcon(c.champion)||"")}" alt=""><span><strong>${esc(c.champion)}</strong><small>${c.games}경기 · ${fmt(c.winRate,0)}%</small></span></button>`).join("")||"<p>내전 기록이 없습니다.</p>"}</div></section><section class="ga-panel ga-span-2"><div class="ga-panel-head"><div><small>DATA FLOW</small><h3>비교 데이터는 필요한 순간에만 집계합니다.</h3></div></div><div class="ga-insight-list"><p><b>1</b> 브라우저가 내전 500경기를 내려받지 않습니다.</p><p><b>2</b> 챔피언·포지션을 선택하면 백엔드가 해당 조건의 평균만 반환합니다.</p><p><b>3</b> 솔로랭크 API가 연결되면 같은 Riot ID 기준으로 나란히 비교합니다.</p></div></section></div>`;
}
function growthBlock(rows){
  const ordered=[...rows].sort((a,b)=>String(a.time).localeCompare(String(b.time)));
  if(ordered.length<4)return`<div class="analysis-empty-inline">기록이 ${ordered.length}경기라 성장 추세는 4경기부터 표시합니다.</div>`;
  const size=Math.min(5,Math.floor(ordered.length/2)),early=ordered.slice(0,size),recent=ordered.slice(-size);
  return`<div class="growth-grid">${METRICS.map(([k,label,d])=>{const a=avg(early,k),b=avg(recent,k),diff=pctDiff(b,a),cls=diff==null?"":diff>=0?"positive":"negative";return`<div class="growth-card"><span>${label}</span><strong>${fmt(a,d)} <b>→</b> ${fmt(b,d)}</strong><em class="${cls}">${diff==null?"-":`${diff>=0?"▲":"▼"} ${Math.abs(diff).toFixed(1)}%`}</em></div>`;}).join("")}</div><p class="analysis-footnote">초기 ${size}경기 평균과 최근 ${size}경기 평균 비교 · 내 개인 기록만 사용</p>`;
}
function tierTable(data,currentBand){
  const tiers=data?.tiers||[];
  if(!tiers.length)return`<div class="analysis-empty-inline">해당 조건의 비교 표본이 아직 없습니다.</div>`;
  return`<div class="analysis-tier-table"><div class="analysis-tier-head"><span>티어</span><span>표본</span>${METRICS.map(m=>`<span>${m[1]}</span>`).join("")}</div>${tiers.map(row=>`<div class="analysis-tier-row ${row.tier===currentBand?"is-current":""}"><strong>${tierName(row.tier)}</strong><span>${row.sampleCount}</span>${METRICS.map(([k,,d])=>`<span>${fmt(metricFromTier(row,k),d)}</span>`).join("")}</div>`).join("")}</div>`;
}
function metricCards(focus,data){
  const band=tierBand(focus?.tier),current=benchmarkTier(data,band),idx=TIER_ORDER.indexOf(band),nextBand=idx>=0?TIER_ORDER[idx+1]:"",upper=benchmarkTier(data,nextBand);
  return METRICS.map(([k,label,d])=>{const v=Number(focus?.[k]),base=metricFromTier(current,k),diff=pctDiff(v,base),cls=diff==null?"":diff>=0?"positive":"negative";return`<div class="analysis-metric-card"><span>${label}</span><strong>${fmt(v,d)}</strong><small class="${cls}">${diff==null?"동티어 표본 없음":`${diff>=0?"+":""}${diff.toFixed(1)}% · ${tierName(band)} 평균 대비`}</small><div><em>${tierName(band)} ${fmt(base,d)}</em><em>${nextBand?`${tierName(nextBand)} ${fmt(metricFromTier(upper,k),d)}`:"상위 티어 -"}</em></div></div>`;}).join("");
}
function benchmarkInsights(focus,data){
  const band=tierBand(focus?.tier),current=benchmarkTier(data,band);
  if(!current)return"";
  const scored=METRICS.map(([k,label])=>({label,diff:pctDiff(Number(focus?.[k]),metricFromTier(current,k))})).filter(x=>Number.isFinite(x.diff));
  const best=[...scored].sort((a,b)=>b.diff-a.diff).slice(0,2),weak=[...scored].sort((a,b)=>a.diff-b.diff).slice(0,2);
  return`<div class="analysis-insight-grid"><section><h3>강점</h3>${best.map(x=>`<p><strong>${x.label}</strong><span class="positive">평균보다 ${Math.abs(x.diff).toFixed(1)}% ${x.diff>=0?"높음":"낮음"}</span></p>`).join("")||"<p>표본 부족</p>"}</section><section><h3>보완 후보</h3>${weak.map(x=>`<p><strong>${x.label}</strong><span class="${x.diff<0?"negative":"positive"}">평균보다 ${Math.abs(x.diff).toFixed(1)}% ${x.diff<0?"낮음":"높음"}</span></p>`).join("")||"<p>표본 부족</p>"}</section></div>`;
}

async function championPanel(profile,rows,identity){
  const champs=topChampions(profile),champion=analysisState.champion||champs[0]?.champion||"";
  const mine=rows.filter(r=>r.champion===champion);const role=analysisState.role||mine[0]?.role||"정글";
  const own=mine.filter(r=>r.role===role),focus=own[0];
  if(!champion||!focus)return`<section class="ga-panel"><div class="analysis-empty-inline">분석할 내전 챔피언 기록이 없습니다.</div></section>`;
  const data=await getBenchmark({champion,role,guildId:identity?.guildId||""});
  const band=tierBand(focus.tier);
  return`<section class="ga-panel"><div class="ga-filter-row"><label>챔피언<select id="gaChampionSelect">${champs.map(c=>`<option ${c.champion===champion?"selected":""}>${esc(c.champion)}</option>`).join("")}</select></label><label>포지션<select id="gaRoleSelect">${ROLES.map(r=>`<option ${r===role?"selected":""}>${r}</option>`).join("")}</select></label><div class="ga-filter-note">백엔드 집계 · 원본 경기 다운로드 없음</div></div><div class="ga-champion-head"><img src="${esc(championIcon(champion)||"")}" alt=""><div><small>CHAMPION DEEP DIVE</small><h3>${esc(champion)} · ${esc(role)}</h3><p>내 ${own.length}경기 · 전체 비교 표본 ${data.sampleCount||0}건</p></div></div><div class="analysis-metric-grid">${metricCards(focus,data)}</div>${benchmarkInsights(focus,data)}<div class="ga-section-gap">${tierTable(data,band)}</div></section>`;
}
async function rolePanel(rows,identity){
  const role=analysisState.role||"정글",mine=rows.filter(r=>r.role===role),focus=mine[0];
  const data=await getBenchmark({role,guildId:identity?.guildId||""});
  const band=tierBand(focus?.tier),same=benchmarkTier(data,band);
  const cards=[["판수",mine.length],["승률",`${fmt(winRate(mine),1)}%`],["KDA",fmt(avg(mine,"kda"),2)],["CS/분",fmt(avg(mine,"csm"),1)],["DPM",fmt(avg(mine,"dpm"),0)],["킬관여",`${fmt(avg(mine,"kp"),1)}%`]];
  return`<section class="ga-panel"><div class="ga-role-tabs">${ROLES.map(r=>`<button class="${r===role?"active":""}" data-ga-role="${r}">${r}</button>`).join("")}</div><div class="ga-stat-grid role">${cards.map(([l,v])=>statBox(l,v)).join("")}</div><div class="ga-compare-bars"><div class="ga-panel-head"><div><small>ROLE PROFILE</small><h3>${role} 플레이 스타일</h3></div><span>내 기록 vs ${tierName(band)} ${role} 평균</span></div>${METRICS.map(([k,label,d])=>{const a=avg(mine,k)||0,b=metricFromTier(same,k)||0,max=Math.max(a,b,1);return`<div class="ga-compare-row"><span>${label}</span><div class="ga-bar-pair"><i style="width:${Math.min(100,a/max*100)}%"></i><b style="width:${Math.min(100,b/max*100)}%"></b></div><em>${fmt(a,d)} / ${fmt(b,d)}</em></div>`;}).join("")}</div></section>`;
}
async function comparePanel(rows,identity){
  const role=analysisState.role||rows[0]?.role||"정글"; const mine=rows.filter(r=>r.role===role); const focus=mine[0]||rows[0];
  const data=await getBenchmark({role,guildId:identity?.guildId||""});
  const band=tierBand(focus?.tier),same=benchmarkTier(data,band),idx=TIER_ORDER.indexOf(band),next=idx>=0?TIER_ORDER[idx+1]:"",upper=benchmarkTier(data,next);
  const diffs=METRICS.map(([k])=>pctDiff(avg(mine,k),metricFromTier(same,k))).filter(Number.isFinite),score=diffs.length?diffs.reduce((a,b)=>a+b,0)/diffs.length:0;
  const letter=score>=15?"A":score>=5?"A-":score>=-5?"B+":score>=-15?"B":"C+";
  return`<div class="ga-compare-layout"><section class="ga-panel ga-grade"><small>BENCHMARK</small><strong>${letter}</strong><h3>${tierName(band)} ${role} 평균 대비</h3><p>백엔드 집계값과 내 개인 기록을 비교한 상대 평가입니다.</p></section><section class="ga-panel"><div class="ga-panel-head"><div><small>DETAIL</small><h3>내 기록 / 같은 티어 / 한 티어 위</h3></div></div><div class="analysis-tier-table"><div class="analysis-tier-head"><span>지표</span><span>나</span><span>${tierName(band)}</span><span>${tierName(next)}</span><span>동티어 차이</span><span></span><span></span></div>${METRICS.map(([k,label,d])=>{const me=avg(mine,k),sameAvg=metricFromTier(same,k),up=metricFromTier(upper,k),diff=pctDiff(me,sameAvg);return`<div class="analysis-tier-row"><strong>${label}</strong><span>${fmt(me,d)}</span><span>${fmt(sameAvg,d)}</span><span>${fmt(up,d)}</span><span class="${diff>=0?"positive":"negative"}">${diff==null?"-":`${diff>=0?"+":""}${diff.toFixed(1)}%`}</span><span></span><span></span></div>`;}).join("")}</div></section></div>`;
}
function growthPanel(rows){return`<section class="ga-panel"><div class="ga-panel-head"><div><small>GROWTH</small><h3>최근 경기 성장 변화</h3></div><div class="ga-range"><button>10경기</button><button class="active">20경기</button><button>30경기</button></div></div>${growthBlock(rows.slice(0,30))}<div class="ga-growth-note"><strong>데이터 소스</strong><span class="active">Lucid 내전</span><span>솔로랭크 API 연결 후 함께 표시</span></div></section>`;}

async function renderActivePanel(target,profile,solo,identity){
  const rows=ownRows(profile,identity); const panel=target.querySelector("#gaPanelHost"); if(!panel)return;
  if(analysisState.tab==="overview"){panel.innerHTML=overviewPanel(profile,rows,solo);bindDashboardEvents(target,profile,solo,identity);return;}
  if(analysisState.tab==="growth"){panel.innerHTML=growthPanel(rows);bindDashboardEvents(target,profile,solo,identity);return;}
  panel.innerHTML=`<div class="analysis-loading">비교 통계를 불러오는 중...</div>`;
  try{
    if(analysisState.tab==="champion")panel.innerHTML=await championPanel(profile,rows,identity);
    else if(analysisState.tab==="role")panel.innerHTML=await rolePanel(rows,identity);
    else if(analysisState.tab==="compare")panel.innerHTML=await comparePanel(rows,identity);
  }catch(e){panel.innerHTML=`<div class="analysis-empty-inline"><strong>비교 통계를 불러오지 못했습니다.</strong><span>${esc(e.message)}</span></div>`;}
  bindDashboardEvents(target,profile,solo,identity);
}
function renderDashboardShell(target,profile,solo,identity){target.innerHTML=`${profileHead(profile,identity,solo)}${tabs()}<div id="gaPanelHost"></div>`;return renderActivePanel(target,profile,solo,identity);}
async function renderDashboard({forceReload=false}={}){
  switchView("analysis"); const target=$("analysisResults");if(!target)return; const identity=getAnalysisIdentity();
  if(!identity){target.innerHTML=`<div class="analysis-empty-inline"><strong>분석할 Riot ID가 필요합니다.</strong><span>${canAnalyzeAllPlayers()?"관리자는 개인 전적에서 분석할 유저를 선택하거나, 내 정보에 Riot ID를 등록해주세요.":"로그인 후 내 정보에 등록한 Riot ID로 분석할 수 있습니다."}</span></div>`;return;}
  if(!forceReload&&dashboardCacheValid(identity)){await renderDashboardShell(target,dashboardCache.profile,dashboardCache.solo,identity);return;}
  target.innerHTML=`<div class="analysis-loading">게임 분석을 준비하는 중...</div>`;
  try{
    const [profile,solo]=await Promise.all([loadProfile(identity),loadSoloSummary()]);
    dashboardCache={key:dashboardIdentityKey(identity),loadedAt:Date.now(),profile,solo,identity};
    await renderDashboardShell(target,profile,solo,identity);
  }catch(e){target.innerHTML=`<div class="analysis-empty-inline"><strong>분석 데이터를 불러오지 못했습니다.</strong><span>${esc(e.message)}</span></div>`;}
}
function bindDashboardEvents(target,profile,solo,identity){
  target.querySelectorAll("[data-ga-tab]").forEach(btn=>btn.addEventListener("click",async()=>{analysisState.tab=btn.dataset.gaTab;target.querySelectorAll("[data-ga-tab]").forEach(x=>x.classList.toggle("active",x===btn));await renderActivePanel(target,profile,solo,identity);}));
  target.querySelectorAll("[data-ga-champion]").forEach(btn=>btn.addEventListener("click",async()=>{analysisState.champion=btn.dataset.gaChampion;analysisState.tab="champion";await renderDashboardShell(target,profile,solo,identity);}));
  target.querySelectorAll("[data-ga-role]").forEach(btn=>btn.addEventListener("click",async()=>{analysisState.role=btn.dataset.gaRole;await renderActivePanel(target,profile,solo,identity);}));
  target.querySelector("#gaChampionSelect")?.addEventListener("change",async e=>{analysisState.champion=e.target.value;await renderActivePanel(target,profile,solo,identity);});
  target.querySelector("#gaRoleSelect")?.addEventListener("change",async e=>{analysisState.role=e.target.value;await renderActivePanel(target,profile,solo,identity);});
}

export async function renderCompactMatchAnalysis(detail={},target){
  if(!target)return; const{userId="",guildId="",matchId=""}=detail;
  if(!canAnalyzePlayer(userId,guildId)){target.innerHTML=`<div class="compact-analysis-empty"><strong>분석 권한이 필요합니다.</strong><span>${canAnalyzeAllPlayers()?"":"로그인 후 내 정보에 등록한 Riot ID의 경기만 분석할 수 있습니다."}</span></div>`;return;}
  target.innerHTML=`<div class="compact-analysis-loading">분석 중...</div>`;
  try{
    const detailData=await apiGet(`/api/community/matches/${encodeURIComponent(matchId)}?guildId=${encodeURIComponent(guildId)}`),match=detailData?.match,focus=match?findFocus(match,userId):null;
    if(!focus)throw new Error("경기 데이터를 찾지 못했습니다.");
    const data=await getBenchmark({champion:focus.champion,role:focus.role,guildId}); const band=tierBand(focus.tier),same=benchmarkTier(data,band);
    const messages=METRICS.map(([k,label])=>({label,d:pctDiff(Number(focus[k]),metricFromTier(same,k))})).filter(x=>Number.isFinite(x.d));
    const best=[...messages].sort((a,b)=>b.d-a.d)[0],weak=[...messages].sort((a,b)=>a.d-b.d)[0];
    target.innerHTML=`<div class="compact-analysis-card"><div class="compact-analysis-title"><div><small>간단 분석</small><strong>${esc(focus.champion)} · ${esc(focus.role)}</strong><span>이번 경기 → ${tierName(band)} 평균</span></div></div><div class="compact-analysis-messages">${best?`<p>${best.label}은 평균보다 ${Math.abs(best.d).toFixed(0)}% ${best.d>=0?"높습니다":"낮습니다"}.</p>`:""}${weak&&weak!==best?`<p>${weak.label}은 평균보다 ${Math.abs(weak.d).toFixed(0)}% ${weak.d<0?"낮아 개선 후보입니다":"높습니다"}.</p>`:""}<p>비교 표본 ${data.sampleCount||0}건 · 원본 경기 다운로드 없음</p></div><button class="compact-analysis-full" type="button" data-open-full-analysis data-user-id="${esc(userId)}" data-guild-id="${esc(guildId)}" data-match-id="${esc(matchId)}" data-champion="${esc(focus.champion||"")}" data-role="${esc(focus.role||"")}">상세 분석 보기</button></div>`;
  }catch(e){target.innerHTML=`<div class="compact-analysis-empty"><strong>분석하지 못했습니다.</strong><span>${esc(e.message)}</span></div>`;}
}

async function renderMatchAnalysis({userId="",guildId="",matchId=""}={}){
  switchView("analysis");const target=$("analysisResults");
  if(userId&&!canAnalyzePlayer(userId,guildId)){target.innerHTML=`<div class="analysis-empty-inline"><strong>분석 권한이 필요합니다.</strong><span>일반 계정은 등록한 Riot ID의 내전 기록만 분석할 수 있습니다.</span></div>`;return;}
  target.innerHTML=`<div class="analysis-loading">선택한 경기를 분석하는 중...</div>`;
  try{
    const [detailData,profile]=await Promise.all([apiGet(`/api/community/matches/${encodeURIComponent(matchId)}?guildId=${encodeURIComponent(guildId)}`),apiGet(`/api/community/players/${encodeURIComponent(userId)}?guildId=${encodeURIComponent(guildId)}&limit=30`)]);
    const match=detailData?.match,focus=match?findFocus(match,userId):null;if(!focus)throw new Error("경기 데이터를 찾지 못했습니다.");
    const data=await getBenchmark({champion:focus.champion,role:focus.role,guildId});const band=tierBand(focus.tier);const rows=ownRows(profile,{userId,guildId}).filter(r=>r.champion===focus.champion&&r.role===focus.role);
    target.innerHTML=`<section class="analysis-context-card"><div class="analysis-context-title"><img src="${esc(championIcon(focus.champion)||"")}" alt=""><div><small>선택한 내전 경기</small><h2>${esc(focus.champion)} · ${esc(focus.role)}</h2><p>${tierName(band)} 평균과 상세 비교 · 표본 ${data.sampleCount||0}</p></div></div></section><div class="analysis-subtabs"><button class="active" type="button" data-back-dashboard>게임 분석 메인</button><button type="button" data-analysis-anchor="game">이번 경기</button><button type="button" data-analysis-anchor="tiers">티어 비교</button><button type="button" data-analysis-anchor="growth">내 성장</button></div><section id="analysisGame" class="analysis-section"><div class="analysis-section-head"><div><small>THIS MATCH</small><h2>이번 경기 vs ${tierName(band)} 평균</h2></div></div><div class="analysis-metric-grid">${metricCards(focus,data)}</div>${benchmarkInsights(focus,data)}</section><section id="analysisTiers" class="analysis-section"><div class="analysis-section-head"><div><small>BENCHMARK</small><h2>${esc(focus.champion)} ${esc(focus.role)} 티어별 평균</h2></div><span>백엔드 집계값</span></div>${tierTable(data,band)}</section><section id="analysisGrowth" class="analysis-section"><div class="analysis-section-head"><div><small>GROWTH</small><h2>내 ${esc(focus.champion)} 성장 변화</h2></div></div>${growthBlock(rows)}</section>`;
    target.querySelector("[data-back-dashboard]")?.addEventListener("click",()=>renderDashboard());
    target.querySelectorAll("[data-analysis-anchor]").forEach(btn=>btn.addEventListener("click",()=>document.getElementById({game:"analysisGame",tiers:"analysisTiers",growth:"analysisGrowth"}[btn.dataset.analysisAnchor])?.scrollIntoView({behavior:"smooth"})));
  }catch(e){target.innerHTML=`<div class="analysis-empty-inline"><strong>분석하지 못했습니다.</strong><span>${esc(e.message)}</span></div>`;}
}

export function openAnalysisFromMatch(detail={}){const url=new URL(window.location.href);url.search="";url.searchParams.set("view","analysis");for(const key of["userId","guildId","matchId","champion","role"])if(detail[key])url.searchParams.set(key,detail[key]);history.pushState({view:"analysis"},"",`${url.pathname}${url.search}`);return renderMatchAnalysis(detail);}
export function applyAnalysisRoute(params){const detail={userId:params.get("userId")||"",guildId:params.get("guildId")||"",matchId:params.get("matchId")||""};if(detail.matchId)return renderMatchAnalysis(detail);return renderDashboard();}
export function bindAnalysisPage(){
  $("analysisRunBtn")?.addEventListener("click",()=>{analysisState.champion=$("analysisChampion")?.value||"";analysisState.role=$("analysisRole")?.value||"정글";analysisState.tab="champion";renderDashboard();});
  window.addEventListener("lucid:auth-changed",()=>{invalidateDashboardCache();if(document.getElementById("analysisView")?.classList.contains("active"))renderDashboard({forceReload:true});});
}
