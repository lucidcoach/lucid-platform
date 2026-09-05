import { apiGet } from "../api.js?v=20260905ae";
import { championIcon } from "../assets.js?v=20260905ae";
import { $, escapeHtml } from "../utils.js?v=20260905ae";
import { switchView } from "../view.js?v=20260904r";
import { canAnalyzePlayer, getAnalysisIdentity, canAnalyzeAllPlayers, getRiotAccounts } from "../auth.js?v=20260905ag";

const METRICS = [["csm","CS/분",1],["gpm","분당 골드",0],["dpm","DPM",0],["kda","KDA",2],["kp","킬관여",1]];
const RADAR_METRICS = [["csm","성장"],["gpm","골드"],["dpm","딜량"],["kda","KDA"],["kp","킬관여"],["aiScore","AI"]];
const TIER_ORDER=["I","B","S","G","P","E","D","M","GM","C"];
const TIER_NAME={I:"아이언",B:"브론즈",S:"실버",G:"골드",P:"플래티넘",E:"에메랄드",D:"다이아몬드",M:"마스터",GM:"그랜드마스터",C:"챌린저"};
let analysisState={tab:"overview",role:"정글",champion:""};
let dashboardCache={key:"",loadedAt:0,matches:null,profile:null,solo:null,identity:null,fullLoaded:false};
let dashboardWarmupPromise=null;
const DASHBOARD_CACHE_TTL=5*60*1000;

function tierBand(tier=""){const raw=String(tier||"");const t=raw.toUpperCase().replace(/[\s_-]+/g,"");if(t.startsWith("GRANDMASTER")||t.startsWith("GM")||raw.includes("그랜드마스터"))return"GM";if(t.startsWith("CHALLENGER")||raw.includes("챌린저"))return"C";if(t.startsWith("MASTER")||t==="M"||raw.includes("마스터"))return"M";const m=t.match(/^(D|E|P|G|S|B|I)/);return m?m[1]:"";}
function tierName(tier){const b=tierBand(tier);return TIER_NAME[b]||String(tier||"미배치");}
function avg(rows,key){const vals=rows.map(r=>Number(r?.[key])).filter(Number.isFinite);return vals.length?vals.reduce((a,b)=>a+b,0)/vals.length:null;}
function fmt(v,d=1){return Number.isFinite(Number(v))?Number(v).toFixed(d):"-";}
function pctDiff(value,base){const a=Number(value),b=Number(base);return Number.isFinite(a)&&Number.isFinite(b)&&b!==0?(a-b)/Math.abs(b)*100:null;}
function metricValue(row,key){return Number(row?.[key]||0);}
function normalizeChampion(v=""){return String(v).trim().toLowerCase().replace(/[\s.'’_-]/g,"");}
function sameChampion(a,b){return normalizeChampion(a)===normalizeChampion(b);}
function confidence(n){if(n>=300)return["A","높음"];if(n>=150)return["B","충분"];if(n>=75)return["C","보통"];return["LOW","표본 적음"];}
function winRate(rows){const played=rows.filter(r=>["win","loss"].includes(String(r.result)));return played.length?played.filter(r=>r.result==="win").length/played.length*100:0;}
function esc(v){return escapeHtml(String(v??""));}

async function loadAllMatches(max=500){
  const pageSize=50;
  const first=await apiGet(`/api/community/matches?limit=${pageSize}&offset=0&category=all`);
  const firstRows=first.matches||[];
  const total=Math.min(Number(first.total||firstRows.length),max);
  if(firstRows.length>=total||total<=pageSize)return firstRows.slice(0,max);

  const offsets=[];
  for(let offset=pageSize;offset<total;offset+=pageSize)offsets.push(offset);

  const rows=[...firstRows];
  const concurrency=4;
  for(let i=0;i<offsets.length;i+=concurrency){
    const chunk=offsets.slice(i,i+concurrency);
    const pages=await Promise.all(chunk.map(offset=>
      apiGet(`/api/community/matches?limit=${pageSize}&offset=${offset}&category=all`).catch(()=>({matches:[]}))
    ));
    pages.forEach(page=>rows.push(...(page.matches||[])));
  }
  return rows.slice(0,max);
}

async function loadInitialMatches(){return loadAllMatches(100);}

async function loadProfile(identity){if(!identity?.userId||!identity?.guildId)return null;try{return await apiGet(`/api/community/players/${encodeURIComponent(identity.userId)}?guildId=${encodeURIComponent(identity.guildId)}&limit=30`);}catch(_){return null;}}
async function loadSoloSummary(){const riotId=(getRiotAccounts()||[])[0];if(!riotId)return{available:false,reason:"riot_id_missing"};try{return await apiGet(`/api/community/riot/solo-summary?riotId=${encodeURIComponent(riotId)}`);}catch(_){return{available:false,reason:"api_not_ready",riotId};}}
function flattenMatches(matches){const out=[];for(const match of matches)for(const p of(match.players||[]))out.push({...p,time:match.time,matchId:match.matchId,guildId:match.guildId});return out;}
function findFocus(match,userId){return(match?.players||[]).find(p=>String(p.userId)===String(userId));}
function byChampionRole(matches,champion,role){return flattenMatches(matches).filter(p=>sameChampion(p.champion,champion)&&String(p.role)===String(role));}
function uniquePlayerMatches(rows){const seen=new Set();return rows.filter(r=>{const k=`${r.matchId}:${r.userId}`;if(seen.has(k))return false;seen.add(k);return true;});}
function benchmarkGroups(rows){const map=new Map();for(const row of rows){const band=tierBand(row.tier);if(!band)continue;if(!map.has(band))map.set(band,[]);map.get(band).push(row);}return[...map.entries()].sort((a,b)=>TIER_ORDER.indexOf(a[0])-TIER_ORDER.indexOf(b[0]));}
function groupFor(groups,band){return groups.find(([t])=>t===band)?.[1]||[];}
function ownRows(matches,identity){if(!identity)return[];return flattenMatches(matches).filter(r=>String(r.userId)===String(identity.userId));}

function metricCard(key,label,digits,focus,current,upper,currentBand,upperBand){const cv=avg(current,key),uv=avg(upper,key),diff=pctDiff(metricValue(focus,key),cv);const cls=diff==null?"":diff>=0?"positive":"negative";return `<div class="analysis-metric-card"><span>${label}</span><strong>${fmt(metricValue(focus,key),digits)}</strong><small class="${cls}">${diff==null?"동티어 표본 없음":`${diff>=0?"+":""}${diff.toFixed(1)}% · ${tierName(currentBand)} 평균 대비`}</small><div><em>${tierName(currentBand)} ${fmt(cv,digits)}</em><em>${upperBand?`${tierName(upperBand)} ${fmt(uv,digits)}`:"상위 티어 -"}</em></div></div>`;}
function tierTable(groups,currentBand){if(!groups.length)return`<div class="analysis-empty-inline">같은 챔피언·포지션 표본이 아직 없습니다.</div>`;return`<div class="analysis-tier-table"><div class="analysis-tier-head"><span>티어</span><span>표본</span>${METRICS.map(m=>`<span>${m[1]}</span>`).join("")}</div>${groups.map(([band,rows])=>`<div class="analysis-tier-row ${band===currentBand?"is-current":""}"><strong>${tierName(band)}</strong><span>${rows.length}</span>${METRICS.map(([k,,d])=>`<span>${fmt(avg(rows,k),d)}</span>`).join("")}</div>`).join("")}</div>`;}
function insightRows(focus,current,currentBand){if(!focus||!current?.length)return"";const scored=METRICS.map(([k,label])=>({label,diff:pctDiff(metricValue(focus,k),avg(current,k))})).filter(x=>Number.isFinite(x.diff));const best=[...scored].sort((a,b)=>b.diff-a.diff).slice(0,2),weak=[...scored].sort((a,b)=>a.diff-b.diff).slice(0,2);return`<div class="analysis-insight-grid"><section><h3>강점</h3>${best.map(x=>`<p><strong>${x.label}</strong><span class="positive">평균보다 ${Math.abs(x.diff).toFixed(1)}% ${x.diff>=0?"높음":"낮음"}</span></p>`).join("")||"<p>표본 부족</p>"}</section><section><h3>보완 후보</h3>${weak.map(x=>`<p><strong>${x.label}</strong><span class="${x.diff<0?"negative":"positive"}">평균보다 ${Math.abs(x.diff).toFixed(1)}% ${x.diff<0?"낮음":"높음"}</span></p>`).join("")||"<p>표본 부족</p>"}</section></div>`;}
function growthBlock(rows){const ordered=[...rows].sort((a,b)=>String(a.time).localeCompare(String(b.time)));if(ordered.length<4)return`<div class="analysis-empty-inline">기록이 ${ordered.length}경기라 성장 추세는 4경기부터 표시합니다.</div>`;const size=Math.min(5,Math.floor(ordered.length/2)),early=ordered.slice(0,size),recent=ordered.slice(-size);return`<div class="growth-grid">${METRICS.map(([k,label,d])=>{const a=avg(early,k),b=avg(recent,k),diff=pctDiff(b,a),cls=diff==null?"":diff>=0?"positive":"negative";return`<div class="growth-card"><span>${label}</span><strong>${fmt(a,d)} <b>→</b> ${fmt(b,d)}</strong><em class="${cls}">${diff==null?"-":`${diff>=0?"▲":"▼"} ${Math.abs(diff).toFixed(1)}%`}</em></div>`;}).join("")}</div><p class="analysis-footnote">초기 ${size}경기 평균과 최근 ${size}경기 평균 비교 · Lucid 내전 기록 기준</p>`;}

function radarPoints(values,cx=92,cy=86,r=62){return values.map((v,i)=>{const a=-Math.PI/2+i*Math.PI/3,rr=r*Math.max(.08,Math.min(.95,v));return`${(cx+Math.cos(a)*rr).toFixed(1)},${(cy+Math.sin(a)*rr).toFixed(1)}`;}).join(" ");}
function compactRadar(focus,current){const own=RADAR_METRICS.map(([k])=>{const b=avg(current,k),v=metricValue(focus,k);return b&&v?Math.max(.15,Math.min(.95,.5*(v/b))):.5;});const benchmark=RADAR_METRICS.map(()=>.5);const axes=RADAR_METRICS.map(([,label],i)=>{const a=-Math.PI/2+i*Math.PI/3,x=92+Math.cos(a)*78,y=86+Math.sin(a)*78;return`<text x="${x.toFixed(1)}" y="${y.toFixed(1)}" text-anchor="middle">${label}</text>`;}).join("");const grid=[.25,.5,.75].map(scale=>`<polygon points="${radarPoints(RADAR_METRICS.map(()=>scale))}" class="radar-grid"/>`).join("");return`<svg class="compact-radar" viewBox="0 0 184 172">${grid}<polygon points="${radarPoints(benchmark)}" class="radar-benchmark"/><polygon points="${radarPoints(own)}" class="radar-own"/>${axes}</svg>`;}
function compactMessages(focus,current,currentBand){if(!current.length)return[`${tierName(currentBand)} 동일 챔피언·포지션 표본이 아직 부족합니다.`];const scored=METRICS.map(([k,label])=>({label,d:pctDiff(metricValue(focus,k),avg(current,k))})).filter(x=>Number.isFinite(x.d));if(!scored.length)return["비교 가능한 상세 지표가 부족합니다."];const best=[...scored].sort((a,b)=>b.d-a.d)[0],weak=[...scored].sort((a,b)=>a.d-b.d)[0];return[`${best.label}은 평균보다 ${Math.abs(best.d).toFixed(0)}% ${best.d>=0?"높습니다":"낮습니다"}.`,weak&&weak.label!==best.label?`${weak.label}은 평균보다 ${Math.abs(weak.d).toFixed(0)}% ${weak.d<0?"낮아 개선 후보입니다":"높습니다"}.`:"",`${tierName(currentBand)} ${focus.champion} ${focus.role} 평균과 비교했습니다.`].filter(Boolean);}

function statBox(label,value,sub=""){return`<div class="ga-stat"><span>${esc(label)}</span><strong>${esc(value)}</strong>${sub?`<small>${esc(sub)}</small>`:""}</div>`;}
function roleBars(rows){const roles=["탑","정글","미드","원딜","서폿"],total=Math.max(1,rows.length);return roles.map(role=>{const n=rows.filter(r=>r.role===role).length,p=Math.round(n/total*100);return`<div class="ga-role-row"><span>${role}</span><div><i style="width:${p}%"></i></div><b>${p}%</b></div>`;}).join("");}
function topChampions(rows){const map=new Map();for(const r of rows){if(!r.champion)continue;const x=map.get(r.champion)||{champion:r.champion,games:0,wins:0};x.games++;if(r.result==="win")x.wins++;map.set(r.champion,x);}return[...map.values()].sort((a,b)=>b.games-a.games).slice(0,4);}
function profileHead(profile,identity,solo){const p=profile?.player||{};const riotId=getRiotAccounts()?.[0]||identity?.name||"Riot ID 미등록";return`<section class="ga-profile-head"><div class="ga-profile-id"><div class="ga-avatar">${p.profileIconUrl?`<img src="${esc(p.profileIconUrl)}" alt="">`:"L"}</div><div><small>ANALYSIS PLAYER</small><h2>${esc(riotId)}</h2><span>${identity?.name&&identity.name!==riotId?`Lucid 등록명 · ${esc(identity.name)}`:"Lucid 커뮤니티 분석"}</span></div></div><div class="ga-rank-pair"><div><span>Riot 솔로랭크</span><strong>${solo?.available!==false?esc(solo?.tier||"연동 중"):"API 연동 대기"}</strong><small>${solo?.lp!=null?`${esc(solo.lp)} LP`:"솔로랭크 API endpoint 필요"}</small></div><div><span>Lucid 내전 티어</span><strong>${esc(p.tier||"미배치")}</strong><small>${p.games||0}경기 · 승률 ${fmt(p.winRate,1)}%</small></div></div></section>`;}
function tabs(){const items=[["overview","종합"],["champion","챔피언 분석"],["role","포지션 분석"],["compare","비교 분석"],["growth","성장 분석"]];return`<div class="ga-tabs">${items.map(([id,label])=>`<button class="${analysisState.tab===id?"active":""}" data-ga-tab="${id}" type="button">${label}</button>`).join("")}</div>`;}

function overviewPanel(rows,profile,solo){const p=profile?.player||{},recent=rows.slice(0,20),champs=topChampions(rows);return`<div class="ga-overview-grid"><section class="ga-panel ga-span-2"><div class="ga-panel-head"><div><small>PERFORMANCE</small><h3>솔로랭크 + 내전 한눈에 보기</h3></div><span class="ga-source-pill">두 데이터 소스</span></div><div class="ga-dual-source"><div class="ga-source-card riot"><span>Riot 솔로랭크 API</span><strong>${solo?.available!==false?esc(solo?.tier||"데이터 대기"):"백엔드 연동 필요"}</strong><p>${solo?.available!==false?"솔로랭크 최근 전적과 티어 데이터":"현재 커뮤니티 API에는 솔로랭크 endpoint가 없어 UI만 연결 준비됨"}</p></div><div class="ga-source-card lucid"><span>Lucid 내전 기록</span><strong>${rows.length}경기</strong><p>ROFL 상세기록 기반 포지션·챔피언·성장 분석</p></div></div><div class="ga-stat-grid">${statBox("최근 20경기 승률",`${fmt(winRate(recent),1)}%`)}${statBox("내전 평균 KDA",fmt(avg(recent,"kda"),2))}${statBox("내전 CS/분",fmt(avg(recent,"csm"),1))}${statBox("내전 DPM",fmt(avg(recent,"dpm"),0))}${statBox("AI Score",fmt(avg(recent,"aiScore"),1))}</div></section><section class="ga-panel"><div class="ga-panel-head"><div><small>ROLE</small><h3>주 포지션</h3></div></div><div class="ga-role-bars">${roleBars(rows)}</div></section><section class="ga-panel"><div class="ga-panel-head"><div><small>CHAMPIONS</small><h3>자주 플레이한 챔피언</h3></div></div><div class="ga-champion-list">${champs.map(c=>`<button type="button" data-ga-champion="${esc(c.champion)}"><img src="${esc(championIcon(c.champion)||"")}" alt=""><span><strong>${esc(c.champion)}</strong><small>${c.games}경기 · ${Math.round(c.wins/c.games*100)}%</small></span></button>`).join("")||"<p>내전 기록이 없습니다.</p>"}</div></section><section class="ga-panel ga-span-2"><div class="ga-panel-head"><div><small>INSIGHT</small><h3>분석 방향</h3></div></div><div class="ga-insight-list"><p><b>1</b> 챔피언 분석에서 같은 챔피언·포지션의 티어 평균을 비교합니다.</p><p><b>2</b> 포지션 분석에서 내전 플레이 성향을 역할별로 확인합니다.</p><p><b>3</b> 솔로랭크 API가 연결되면 동일 지표를 솔랭과 내전으로 나란히 비교합니다.</p></div></section></div>`;}

function championPanel(matches,rows){const champs=topChampions(rows);const champion=analysisState.champion||champs[0]?.champion||"";const role=analysisState.role||rows.find(r=>sameChampion(r.champion,champion))?.role||"정글";const samples=uniquePlayerMatches(byChampionRole(matches,champion,role));const own=samples.filter(r=>rows.some(o=>o.matchId===r.matchId&&String(o.userId)===String(r.userId)));const focus=[...own].sort((a,b)=>String(b.time).localeCompare(String(a.time)))[0]||samples[0];const groups=benchmarkGroups(samples);const band=tierBand(focus?.tier),current=groupFor(groups,band),next=TIER_ORDER[TIER_ORDER.indexOf(band)+1]||"",upper=groupFor(groups,next);return`<section class="ga-panel"><div class="ga-filter-row"><label>챔피언<select id="gaChampionSelect">${champs.map(c=>`<option ${c.champion===champion?"selected":""}>${esc(c.champion)}</option>`).join("")}</select></label><label>포지션<select id="gaRoleSelect">${["탑","정글","미드","원딜","서폿"].map(r=>`<option ${r===role?"selected":""}>${r}</option>`).join("")}</select></label><div class="ga-filter-note">내 내전 + 동일 챔피언/포지션 표본</div></div>${champion&&focus?`<div class="ga-champion-head"><img src="${esc(championIcon(champion)||"")}" alt=""><div><small>CHAMPION DEEP DIVE</small><h3>${esc(champion)} · ${esc(role)}</h3><p>내 ${own.length}경기 · 전체 표본 ${samples.length}경기</p></div></div><div class="analysis-metric-grid">${METRICS.map(m=>metricCard(...m,focus,current,upper,band,next)).join("")}</div>${insightRows(focus,current,band)}<div class="ga-section-gap">${tierTable(groups,band)}</div>`:`<div class="analysis-empty-inline">분석할 내전 챔피언 기록이 없습니다.</div>`}</section>`;}
function rolePanel(rows){const role=analysisState.role||"정글",mine=rows.filter(r=>r.role===role),allBand=tierBand(mine[0]?.tier),comparison=rows.filter(r=>tierBand(r.tier)===allBand);const cards=[["판수",mine.length,0],["승률",`${fmt(winRate(mine),1)}%`,0],["KDA",fmt(avg(mine,"kda"),2),0],["CS/분",fmt(avg(mine,"csm"),1),0],["DPM",fmt(avg(mine,"dpm"),0),0],["킬관여",`${fmt(avg(mine,"kp"),1)}%`,0]];return`<section class="ga-panel"><div class="ga-role-tabs">${["탑","정글","미드","원딜","서폿"].map(r=>`<button class="${r===role?"active":""}" data-ga-role="${r}">${r}</button>`).join("")}</div><div class="ga-stat-grid role">${cards.map(([l,v])=>statBox(l,v)).join("")}</div><div class="ga-compare-bars"><div class="ga-panel-head"><div><small>ROLE PROFILE</small><h3>${role} 플레이 스타일</h3></div><span>내 기록 vs 내 티어 전체 기록</span></div>${METRICS.map(([k,label])=>{const a=avg(mine,k)||0,b=avg(comparison,k)||0,max=Math.max(a,b,1);return`<div class="ga-compare-row"><span>${label}</span><div class="ga-bar-pair"><i style="width:${Math.min(100,a/max*100)}%"></i><b style="width:${Math.min(100,b/max*100)}%"></b></div><em>${fmt(a,k==="kda"?2:1)} / ${fmt(b,k==="kda"?2:1)}</em></div>`;}).join("")}</div></section>`;}
function comparePanel(rows){const band=tierBand(rows[0]?.tier),same=rows.filter(r=>tierBand(r.tier)===band),next=TIER_ORDER[TIER_ORDER.indexOf(band)+1]||"",upper=rows.filter(r=>tierBand(r.tier)===next);const grade=METRICS.map(([k])=>pctDiff(avg(rows,k),avg(same,k))).filter(Number.isFinite);const score=grade.length?grade.reduce((a,b)=>a+b,0)/grade.length:0;const letter=score>=15?"A":score>=5?"A-":score>=-5?"B+":score>=-15?"B":"C+";return`<div class="ga-compare-layout"><section class="ga-panel ga-grade"><small>BENCHMARK</small><strong>${letter}</strong><h3>${tierName(band)} 평균 대비</h3><p>현재 저장된 내전 상세기록을 기준으로 계산한 상대 평가입니다.</p></section><section class="ga-panel"><div class="ga-panel-head"><div><small>DETAIL</small><h3>내 기록 / 같은 티어 / 한 티어 위</h3></div></div><div class="analysis-tier-table"><div class="analysis-tier-head"><span>지표</span><span>나</span><span>${tierName(band)}</span><span>${tierName(next)}</span><span>동티어 차이</span><span></span><span></span></div>${METRICS.map(([k,label,d])=>{const me=avg(rows,k),sameAvg=avg(same,k),up=avg(upper,k),diff=pctDiff(me,sameAvg);return`<div class="analysis-tier-row"><strong>${label}</strong><span>${fmt(me,d)}</span><span>${fmt(sameAvg,d)}</span><span>${fmt(up,d)}</span><span class="${diff>=0?"positive":"negative"}">${diff==null?"-":`${diff>=0?"+":""}${diff.toFixed(1)}%`}</span><span></span><span></span></div>`;}).join("")}</div></section></div>`;}
function growthPanel(rows){const recent=[...rows].sort((a,b)=>String(a.time).localeCompare(String(b.time))).slice(-30);return`<section class="ga-panel"><div class="ga-panel-head"><div><small>GROWTH</small><h3>최근 경기 성장 변화</h3></div><div class="ga-range"><button>10경기</button><button class="active">20경기</button><button>30경기</button></div></div>${growthBlock(recent)}<div class="ga-growth-note"><strong>데이터 소스</strong><span class="active">Lucid 내전</span><span>솔로랭크 API 연결 후 함께 표시</span></div></section>`;}

function dashboardIdentityKey(identity){
  const riotId=(getRiotAccounts()||[])[0]||"";
  return `${identity?.guildId||""}:${identity?.userId||""}:${riotId}`;
}
function invalidateDashboardCache(){dashboardCache={key:"",loadedAt:0,matches:null,profile:null,solo:null,identity:null,fullLoaded:false};dashboardWarmupPromise=null;}
function dashboardCacheValid(identity){return dashboardCache.matches&&dashboardCache.key===dashboardIdentityKey(identity)&&(Date.now()-dashboardCache.loadedAt)<DASHBOARD_CACHE_TTL;}
function renderDashboardFromData(target,matches,profile,solo,identity){
  const rows=ownRows(matches,identity);
  const body=analysisState.tab==="champion"?championPanel(matches,rows):analysisState.tab==="role"?rolePanel(rows):analysisState.tab==="compare"?comparePanel(rows):analysisState.tab==="growth"?growthPanel(rows):overviewPanel(rows,profile,solo);
  target.innerHTML=`${profileHead(profile,identity,solo)}${tabs()}<div class="ga-tab-body">${body}</div>`;
  bindDashboardEvents(target);
}
async function warmFullDashboard(identity){
  const key=dashboardIdentityKey(identity);
  if(dashboardWarmupPromise)return dashboardWarmupPromise;
  dashboardWarmupPromise=(async()=>{
    try{
      const matches=await loadAllMatches(500);
      if(dashboardCache.key!==key)return;
      dashboardCache={...dashboardCache,matches,loadedAt:Date.now(),fullLoaded:true};
      const target=$("analysisResults");
      if(target&&document.getElementById("analysisView")?.classList.contains("active")){
        renderDashboardFromData(target,dashboardCache.matches,dashboardCache.profile,dashboardCache.solo,identity);
      }
    }finally{
      dashboardWarmupPromise=null;
    }
  })();
  return dashboardWarmupPromise;
}

async function renderDashboard({forceReload=false}={}){
  switchView("analysis");
  const target=$("analysisResults");
  if(!target)return;
  const identity=getAnalysisIdentity();
  if(!identity&&!canAnalyzeAllPlayers()){target.innerHTML=`<div class="analysis-empty-inline"><strong>분석할 Riot ID가 필요합니다.</strong><span>로그인 후 내 정보에 Riot ID를 등록하면 솔로랭크와 내전 분석을 연결할 수 있습니다.</span></div>`;return;}

  if(!forceReload&&dashboardCacheValid(identity)){
    renderDashboardFromData(target,dashboardCache.matches,dashboardCache.profile,dashboardCache.solo,identity);
    if(!dashboardCache.fullLoaded)warmFullDashboard(identity);
    return;
  }

  target.innerHTML=`<div class="analysis-loading">게임 분석을 준비하는 중...</div>`;
  try{
    // 첫 화면은 최근 100경기 + 내 프로필만 기다려서 빠르게 표시한다.
    // 솔로랭크와 전체 500경기 표본은 뒤에서 조용히 채운다.
    const[matches,profile]=await Promise.all([loadInitialMatches(),loadProfile(identity)]);
    dashboardCache={
      key:dashboardIdentityKey(identity),
      loadedAt:Date.now(),
      matches,
      profile,
      solo:{available:false,reason:"loading"},
      identity,
      fullLoaded:false
    };
    renderDashboardFromData(target,matches,profile,dashboardCache.solo,identity);

    loadSoloSummary().then(solo=>{
      if(dashboardCache.key!==dashboardIdentityKey(identity))return;
      dashboardCache={...dashboardCache,solo,loadedAt:Date.now()};
      if(document.getElementById("analysisView")?.classList.contains("active")){
        renderDashboardFromData(target,dashboardCache.matches,dashboardCache.profile,solo,identity);
      }
    }).catch(()=>{});

    warmFullDashboard(identity);
  }catch(error){
    target.innerHTML=`<div class="analysis-empty-inline"><strong>분석 데이터를 불러오지 못했습니다.</strong><span>${esc(error.message)}</span></div>`;
  }
}
function rerenderDashboardFromCache(){
  const target=$("analysisResults");
  const identity=getAnalysisIdentity();
  if(target&&dashboardCacheValid(identity)){renderDashboardFromData(target,dashboardCache.matches,dashboardCache.profile,dashboardCache.solo,identity);return true;}
  renderDashboard();
  return false;
}
function bindDashboardEvents(target){
  target.querySelectorAll("[data-ga-tab]").forEach(btn=>btn.addEventListener("click",()=>{analysisState.tab=btn.dataset.gaTab;rerenderDashboardFromCache();}));
  target.querySelectorAll("[data-ga-role]").forEach(btn=>btn.addEventListener("click",()=>{analysisState.role=btn.dataset.gaRole;rerenderDashboardFromCache();}));
  target.querySelectorAll("[data-ga-champion]").forEach(btn=>btn.addEventListener("click",()=>{analysisState.champion=btn.dataset.gaChampion;analysisState.tab="champion";rerenderDashboardFromCache();}));
  target.querySelector("#gaChampionSelect")?.addEventListener("change",e=>{analysisState.champion=e.target.value;rerenderDashboardFromCache();});
  target.querySelector("#gaRoleSelect")?.addEventListener("change",e=>{analysisState.role=e.target.value;rerenderDashboardFromCache();});
}

export async function renderCompactMatchAnalysis(detail={},target){if(!target)return;const{userId="",guildId="",matchId=""}=detail;if(!canAnalyzePlayer(userId,guildId)){target.innerHTML=`<div class="compact-analysis-empty"><strong>분석 권한이 필요합니다.</strong><span>${canAnalyzeAllPlayers()?"":"로그인 후 내 정보에 등록한 Riot ID의 경기만 분석할 수 있습니다."}</span></div>`;return;}target.innerHTML=`<div class="compact-analysis-loading">분석 중...</div>`;try{const matches=await loadAllMatches();const match=matches.find(m=>String(m.matchId)===String(matchId));const focus=match?findFocus(match,userId):null;if(!focus)throw new Error("경기 데이터를 찾지 못했습니다.");const samples=uniquePlayerMatches(byChampionRole(matches,focus.champion,focus.role));const groups=benchmarkGroups(samples),band=tierBand(focus.tier),current=groupFor(groups,band);target.innerHTML=`<div class="compact-analysis-card"><div class="compact-analysis-title"><div><small>간단 분석</small><strong>${esc(focus.champion)} · ${esc(focus.role)}</strong><span>이번 경기 ${esc(focus.tier||"-")} → ${tierName(band)} 평균</span></div><div class="compact-analysis-legend"><i></i>내 수치 <b></b>티어 평균</div></div>${compactRadar(focus,current)}<div class="compact-analysis-messages">${compactMessages(focus,current,band).map(x=>`<p>${esc(x)}</p>`).join("")}</div><button class="compact-analysis-full" type="button" data-open-full-analysis data-user-id="${esc(userId)}" data-guild-id="${esc(guildId)}" data-match-id="${esc(matchId)}" data-champion="${esc(focus.champion||"")}" data-role="${esc(focus.role||"")}">상세 분석 보기</button></div>`;}catch(e){target.innerHTML=`<div class="compact-analysis-empty"><strong>분석하지 못했습니다.</strong><span>${esc(e.message)}</span></div>`;}}

async function renderMatchAnalysis({userId="",guildId="",matchId="",champion="",role=""}={}){switchView("analysis");const target=$("analysisResults");if(userId&&!canAnalyzePlayer(userId,guildId)){target.innerHTML=`<div class="analysis-empty-inline"><strong>분석 권한이 필요합니다.</strong><span>일반 계정은 등록한 Riot ID의 내전 기록만 분석할 수 있습니다.</span></div>`;return;}target.innerHTML=`<div class="analysis-loading">선택한 경기를 분석하는 중...</div>`;try{const matches=await loadAllMatches();const selected=matches.find(m=>String(m.matchId)===String(matchId));let focus=selected&&userId?findFocus(selected,userId):null;if(focus){champion=focus.champion;role=focus.role;}if(!champion)throw new Error("챔피언 정보를 찾지 못했습니다.");const samples=uniquePlayerMatches(byChampionRole(matches,champion,role));const groups=benchmarkGroups(samples),own=userId?samples.filter(r=>String(r.userId)===String(userId)):[];if(!focus)focus=own[0]||samples[0];const band=tierBand(focus?.tier),current=groupFor(groups,band),next=TIER_ORDER[TIER_ORDER.indexOf(band)+1]||"",upper=groupFor(groups,next),[cc,cl]=confidence(samples.length);target.innerHTML=`<section class="analysis-context-card"><div class="analysis-context-title"><img src="${esc(championIcon(champion)||"")}" alt=""><div><small>선택한 내전 경기</small><h2>${esc(champion)} · ${esc(role)}</h2><p>${tierName(band)} 평균과 상세 비교</p></div></div><div class="analysis-confidence-badge"><strong>${cc}</strong><span>${cl}</span></div></section><div class="analysis-subtabs"><button class="active" type="button" data-back-dashboard>게임 분석 메인</button><button type="button" data-analysis-anchor="game">이번 경기</button><button type="button" data-analysis-anchor="tiers">티어 비교</button><button type="button" data-analysis-anchor="growth">내 성장</button></div><section id="analysisGame" class="analysis-section"><div class="analysis-section-head"><div><small>THIS MATCH</small><h2>이번 경기 vs ${tierName(band)} 평균</h2></div></div><div class="analysis-metric-grid">${METRICS.map(m=>metricCard(...m,focus,current,upper,band,next)).join("")}</div>${insightRows(focus,current,band)}</section><section id="analysisTiers" class="analysis-section"><div class="analysis-section-head"><div><small>BENCHMARK</small><h2>${esc(champion)} ${esc(role)} 티어별 평균</h2></div></div>${tierTable(groups,band)}</section><section id="analysisGrowth" class="analysis-section"><div class="analysis-section-head"><div><small>GROWTH</small><h2>내 ${esc(champion)} 성장 변화</h2></div></div>${growthBlock(own)}</section>`;target.querySelector("[data-back-dashboard]")?.addEventListener("click",()=>renderDashboard());target.querySelectorAll("[data-analysis-anchor]").forEach(btn=>btn.addEventListener("click",()=>document.getElementById({game:"analysisGame",tiers:"analysisTiers",growth:"analysisGrowth"}[btn.dataset.analysisAnchor])?.scrollIntoView({behavior:"smooth"})));}catch(error){target.innerHTML=`<div class="analysis-empty-inline"><strong>분석하지 못했습니다.</strong><span>${esc(error.message)}</span></div>`;}}

export function openAnalysisFromMatch(detail={}){const url=new URL(window.location.href);url.search="";url.searchParams.set("view","analysis");for(const key of["userId","guildId","matchId","champion","role"])if(detail[key])url.searchParams.set(key,detail[key]);history.pushState({view:"analysis"},"",`${url.pathname}${url.search}`);return renderMatchAnalysis(detail);}
export function applyAnalysisRoute(params){const detail={userId:params.get("userId")||"",guildId:params.get("guildId")||"",matchId:params.get("matchId")||"",champion:params.get("champion")||"",role:params.get("role")||""};if(detail.matchId)return renderMatchAnalysis(detail);return renderDashboard();}
export function bindAnalysisPage(){const btn=$("analysisRunBtn");btn?.addEventListener("click",()=>{analysisState.champion=$("analysisChampion")?.value||"";analysisState.role=$("analysisRole")?.value||"정글";analysisState.tab="champion";renderDashboard();});window.addEventListener("lucid:auth-changed",()=>{invalidateDashboardCache();if(document.getElementById("analysisView")?.classList.contains("active"))renderDashboard({forceReload:true});});}
