
import { getCurrentUser, isCommunityAdmin } from "../auth.js?v=20260907oauth1";
import { API_BASE_URL } from "../config.js?v=20260904d";
import { renderMileage } from "./mileage.js?v=20260911shop1";

const esc=(value)=>String(value??"").replace(/[&<>"']/g,ch=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[ch]));
let activeSection="dashboard";
let adminGuilds=[];
let selectedGuild="";
let guildsLoaded=false;
let guildAdminAccess=false;
let missingArchived=false;
let roflFiles=[];
let retroRoflFiles=[];
let roflRefreshTimer=0;
const apiUrl=path=>`${API_BASE_URL.replace(/\/$/,"")}${path}`;
async function adminRequest(path,{method="GET",body}={}){const multipart=body instanceof FormData;let response;try{response=await fetch(apiUrl(path),{method,credentials:"include",signal:AbortSignal.timeout(15000),headers:body&&!multipart?{"Content-Type":"application/json"}:{},body:body?(multipart?body:JSON.stringify(body)):undefined});}catch(error){if(error?.name==="TimeoutError")throw new Error("서버 응답 시간이 초과되었습니다. 잠시 후 다시 시도해주세요.");throw new Error("네트워크 또는 CORS 오류로 API 서버에 연결하지 못했습니다.");}const data=await response.json().catch(()=>({}));if(response.status===401)throw new Error("인증이 만료되었습니다. 다시 로그인해주세요.");if(response.status===403)throw new Error("관리자 권한이 없습니다.");if(response.status>=500)throw new Error(`서버 오류 (${response.status})가 발생했습니다. 잠시 후 다시 시도해주세요.`);if(response.status===404)throw new Error("요청한 데이터를 찾을 수 없습니다.");if(!response.ok||!data.ok)throw new Error(data.message||data.error||"요청에 실패했습니다.");return data;}

const sections = [
  ["members","회원 관리","가입 회원·권한·Discord 연결 상태 확인","U"],
  ["server","서버 설정","서버별 내전·채널·권한 설정","⚙"],
  ["titles","칭호 / 업적","서버 기준 칭호와 달성 조건 확인","🏷"],
  ["mileage","포인트 관리","지급 규칙·상점·주문·감사로그","M"],
  ["riot","Riot 공식전적 동기화","등록 계정·수집 상태·공동 플레이","R"],
  ["events","이벤트","진행 이벤트·랭킹·보상","★"],
  ["missing","상세스탯 누락","누락된 경기 확인·목록 정리","⌕"],
  ["retro","리플레이 소급","지난 경기 ROFL 검증·복구","↶"],
  ["rofl","ROFL 패치 분석","새 패치 진단·보존·Codex ZIP","R"],
  ["logs","운영 로그","채팅·관리자 작업·신고·포인트 로그","≡"],
  ["data","데이터 관리","서버 데이터 내보내기","⇩"],
  ["support","문의 관리","커뮤니티/봇 문의 처리","?"],
];

function uniqueGuilds(){
  const rows=[...adminGuilds];
  const seen=new Set();
  return rows.filter(row=>{
    const key=String(row.guildId||row.id||"");
    if(!key||seen.has(key))return false;
    seen.add(key); return true;
  }).map(row=>({id:String(row.guildId||row.id),name:row.guildName||row.serverName||row.name||`서버 ${row.guildId||row.id}`}));
}

async function loadAdminGuilds(){
  try{
    const response=await fetch(`${API_BASE_URL.replace(/\/$/,"")}/api/mileage/guilds`,{credentials:"include"});
    const data=await response.json().catch(()=>({}));
    if(response.ok&&data.ok)adminGuilds=(data.guilds||[]).filter(g=>g.canManage);
  }catch(_){adminGuilds=[];}
  guildAdminAccess=adminGuilds.length>0;
  const guilds=uniqueGuilds();
  if(!guilds.some(g=>g.id===selectedGuild))selectedGuild=guilds[0]?.id||"";
}

function shell(content){
  const user=getCurrentUser();
  const guilds=uniqueGuilds();
  const guildOptions=guilds.length
    ? guilds.map(g=>`<option value="${esc(g.id)}" ${g.id===selectedGuild?"selected":""}>${esc(g.name)}</option>`).join("")
    : `<option value="">관리 가능한 서버 없음</option>`;
  return `
    <div class="admin-page">
      <header class="admin-page-head">
        <div>
          <p class="section-kicker">COMMUNITY ADMIN</p>
          <h1>커뮤니티 관리</h1>
          <p>Discord 운영 기능을 홈페이지에서 한곳에 관리합니다.</p>
        </div>
        <div class="admin-server-picker">
          <span>관리 서버</span>
          <select id="adminGuildSelect">${guildOptions}</select>
          <small>${esc(user?.displayName||user?.email||"관리자")} · 관리자 권한</small>
        </div>
      </header>
      ${content}
    </div>`;
}

function dashboard(){
  return shell(`
    <section class="admin-server-summary">
      <div><span class="admin-dot"></span><div><strong>LucidGame 연결 서버</strong><small>서버별 설정과 운영 데이터를 관리합니다.</small></div></div>
      <span class="admin-status-pill">관리자 권한 확인됨</span>
    </section>
    <div class="admin-card-grid">
      ${sections.filter(([id])=>isCommunityAdmin()||!["retro","rofl","data","support"].includes(id)).map(([id,title,desc,icon])=>`
        <button class="admin-menu-card" type="button" data-admin-section="${id}">
          <span class="admin-menu-icon">${icon}</span>
          <span><strong>${title}</strong><small>${desc}</small></span>
          <b>›</b>
        </button>`).join("")}
    </div>
  `);
}

function panelTitle(title, subtitle){
  return `<div class="admin-panel-title"><button type="button" class="admin-back" data-admin-section="dashboard">← 관리 홈</button><div><h2>${title}</h2><p>${subtitle}</p></div></div>`;
}

function serverPanel(){
  const guild=uniqueGuilds().find(g=>g.id===selectedGuild);
  return shell(`
    ${panelTitle("서버 설정",guild?`${esc(guild.name)}의 Discord 운영 설정 안내입니다.`:"관리할 서버를 먼저 선택해주세요.")}
    <div class="admin-layout">
      <nav class="admin-side-tabs">
        <button class="active" data-server-tab="basic">기본 설정</button><button data-server-tab="match">내전 설정</button><button data-server-tab="channels">채널 설정</button><button data-server-tab="permissions">권한</button>
      </nav>
      <section class="admin-work-panel">
        <div data-server-panel="basic">
          <div class="admin-form-section"><h3>선택 서버</h3><div class="admin-setting-row"><div><strong>${esc(guild?.name||"선택된 서버 없음")}</strong><small>${guild?`Discord 서버 ID ${esc(guild.id)}`:"LucidGame이 동기화한 관리자 서버가 없습니다."}</small></div></div></div>
          <div class="admin-form-section"><h3>최근 적용 요청</h3><div id="serverActionList" class="mileage-list"><div class="admin-empty-admin"><strong>불러오는 중...</strong></div></div></div>
          <div class="admin-draft-note">변경 요청은 DB 작업 큐에 저장되고 LucidGame이 검증한 뒤 메모리와 DB에 함께 적용합니다.</div>
        </div>
        <div data-server-panel="match" hidden>
          <div class="admin-form-section"><h3>내전 설정</h3><form id="matchFrequencyForm" class="mileage-form"><label class="wide">내전 빈도<select name="value"><option>적음</option><option>보통</option><option>많음</option></select></label><button class="wide" type="submit">변경 요청</button></form></div>
          <div class="admin-form-section"><h3>일반 큐</h3><form id="generalQueueCreateForm" class="mileage-form"><label>경기 방식<select name="bestOf"><option value="1">단판</option><option value="3">BO3</option><option value="5">BO5</option></select></label><button type="submit">+ 일반 큐 생성</button></form><div id="generalQueueList" class="admin-queue-list"><div class="admin-empty-admin"><strong>불러오는 중...</strong></div></div></div>
        </div>
        <div data-server-panel="channels" hidden><div class="admin-form-section"><h3>채널 설정</h3><form id="serverChannelForm" class="mileage-form"><label>기능<select name="key"><option value="announcement">공지사항</option><option value="patchnote">패치노트</option><option value="match_output">내전 출력</option><option value="report">신고 접수</option><option value="league_output">리그전 출력</option></select></label><label>Discord 채널 ID<input name="channelId" required inputmode="numeric" pattern="[0-9]+"></label><button class="wide" type="submit">변경 요청</button></form><div class="admin-draft-note">참가·기록·도움말처럼 패널 메시지를 다시 만들어야 하는 채널은 현재 Discord /채널설정을 사용해주세요.</div></div></div>
        <div data-server-panel="permissions" hidden><div class="admin-form-section"><h3>내전 관리자 역할</h3><form id="adminRoleForm" class="mileage-form"><label class="wide">Discord 역할 ID<input name="roleId" required inputmode="numeric" pattern="[0-9]+"></label><button class="wide" type="submit">변경 요청</button></form><div class="admin-setting-row"><div><strong>홈페이지 관리 권한</strong><small>Discord 관리자·서버 관리 권한·내전 관리자 역할을 봇이 주기적으로 확인합니다.</small></div></div></div></div>
        <p id="serverActionStatus" class="mileage-status"></p>
      </section>
    </div>
  `);
}

const actionLabels={set_match_frequency:"내전 빈도",set_channel:"채널 설정",set_admin_role:"관리자 역할",create_general_queue:"일반 큐 생성",set_general_queue_best_of:"경기 방식",delete_general_queue:"일반 큐 삭제"};
const statusLabels={pending:"대기",processing:"적용 중",completed:"완료",failed:"실패"};
async function loadServerSettings(){
  if(!selectedGuild)return;
  try{
    const data=await adminRequest(`/api/community/admin/guilds/${encodeURIComponent(selectedGuild)}/settings`),settings=data.settings||{};
    const frequency=document.querySelector('#matchFrequencyForm [name="value"]');if(frequency)frequency.value=settings.matchFrequency||"보통";
    const role=document.querySelector('#adminRoleForm [name="roleId"]');if(role)role.value=settings.adminRoleId||"";
    const queues=document.getElementById("generalQueueList"),rows=settings.queues||[];
    if(queues)queues.innerHTML=rows.length?rows.map(row=>`<div class="admin-queue-row"><span><strong>일반 큐 ${Number(row.displayNumber)}</strong><small>${Number(row.participants||0)}/10명 · ${row.status==="in_progress"?"경기 진행 중":"대기 중"}${row.messageId?` · 패널 ${esc(row.messageId)}`:""}</small></span><select data-queue-mode="${esc(row.queueId)}" ${row.legacy||row.status==="in_progress"?"disabled":""}><option value="1" ${Number(row.bestOf)===1?"selected":""}>단판</option><option value="3" ${Number(row.bestOf)===3?"selected":""}>BO3</option><option value="5" ${Number(row.bestOf)===5?"selected":""}>BO5</option></select><button data-queue-delete="${esc(row.queueId)}" ${row.legacy||row.status==="in_progress"||Number(row.participants)>0?"disabled":""}>삭제</button></div>`).join(""):`<div class="admin-empty-admin"><strong>생성된 일반 큐가 없습니다.</strong></div>`;
    queues?.querySelectorAll("[data-queue-mode]").forEach(select=>select.addEventListener("change",()=>enqueueServerAction("set_general_queue_best_of",{queueId:select.dataset.queueMode,bestOf:Number(select.value)})));
    queues?.querySelectorAll("[data-queue-delete]").forEach(button=>button.addEventListener("click",()=>{if(confirm("대기자가 없는 이 큐를 삭제할까요?"))enqueueServerAction("delete_general_queue",{queueId:button.dataset.queueDelete});}));
    const list=document.getElementById("serverActionList"),actions=data.actions||[];
    if(list)list.innerHTML=actions.length?actions.map(row=>`<div class="mileage-row"><span><strong>${esc(actionLabels[row.action]||row.action)}</strong><br><small>${esc(row.updatedAt||row.createdAt)}</small></span><b>${esc(statusLabels[row.status]||row.status)}${row.error?` · ${esc(row.error)}`:""}</b></div>`).join(""):`<div class="admin-empty-admin"><strong>아직 변경 요청이 없습니다.</strong></div>`;
  }catch(error){const status=document.getElementById("serverActionStatus");if(status)status.textContent=error.message;}
}

async function enqueueServerAction(action,payload){
  const status=document.getElementById("serverActionStatus");if(status)status.textContent="봇 적용 대기열에 등록 중...";
  try{await adminRequest(`/api/community/admin/guilds/${encodeURIComponent(selectedGuild)}/actions`,{method:"POST",body:{action,payload,requestKey:crypto.randomUUID()}});if(status)status.textContent="요청을 등록했습니다. 봇이 최대 10초 안에 적용합니다.";setTimeout(loadServerSettings,1500);}catch(error){if(status)status.textContent=error.message;}
}


function memberRiotId(user={}){
  const accounts = Array.isArray(user.riotAccounts) ? user.riotAccounts : (Array.isArray(user.riot_accounts) ? user.riot_accounts : []);
  return String(user.riotId||user.riot_id||accounts[0]||"").trim();
}
function friendlyMemberName(user={}){
  const preferred=String(user.preferredDisplayName||user.preferred_display_name||"").trim();
  if(preferred)return preferred;
  const riotId=memberRiotId(user);
  if(riotId)return riotId;
  const discord=String(user.discordDisplayName||user.discord_display_name||"").trim();
  if(discord)return discord;
  const raw=String(user.displayName||user.display_name||user.nickname||"").trim();
  if(raw && !/^oauth\s*user$/i.test(raw))return raw;
  const email=String(user.email||"").trim();
  if(email)return email.split("@")[0]||"회원";
  return "회원";
}
function memberRoleFlags(user={}){
  const roles=new Set([...(Array.isArray(user.roles)?user.roles:[]),user.role].filter(Boolean).map(v=>String(v).toLowerCase()));
  return {
    coach:roles.has("coach")||Boolean(user.isCoach||user.is_coach),
    admin:roles.has("admin")||roles.has("administrator")||Boolean(user.isAdmin||user.is_admin),
  };
}
function memberRoleLabel(user={}){
  const flags=memberRoleFlags(user),labels=[];
  if(flags.admin)labels.push("관리자");
  if(flags.coach)labels.push("코치");
  return labels.length?labels.join(" · "):"일반 회원";
}
function memberServerAdminGuilds(user={}){
  const raw=user.serverAdminGuildIds||user.server_admin_guild_ids||user.managedGuildIds||user.managed_guild_ids||user.guildAdminIds||user.guild_admin_ids||[];
  return new Set((Array.isArray(raw)?raw:[]).map(String));
}
function memberPanel(){
  return shell(`
    ${panelTitle("회원 관리","가입 회원과 권한을 관리합니다.")}
    <section class="admin-member-summary" id="memberSummary">
      <article><span>전체 회원</span><strong id="memberTotal">-</strong><small>가입 계정</small></article>
      <article><span>Discord 연결</span><strong id="memberDiscord">-</strong><small>연동 완료</small></article>
      <article><span>코치</span><strong id="memberCoaches">-</strong><small>코치 권한</small></article>
      <article><span>관리자</span><strong id="memberAdmins">-</strong><small>전체 관리자</small></article>
    </section>
    <section class="admin-work-panel">
      <div class="admin-toolbar admin-member-toolbar"><div><strong>가입 회원</strong></div><button id="memberRefresh" class="admin-primary" type="button">새로고침</button></div>
      <div class="admin-member-search"><input id="memberSearch" type="search" placeholder="Riot ID, 이메일, Discord, 권한 검색"></div>
      <div class="admin-member-table">
        <div class="admin-member-head"><span>회원</span><span>이메일</span><span>권한</span><span>Discord</span><span>설정</span></div>
        <div id="memberList"><div class="admin-empty-admin"><strong>회원 목록을 불러오는 중...</strong></div></div>
      </div>
      <p id="memberActionStatus" class="mileage-status"></p>
    </section>
  `);
}
let memberRows=[];
function renderMemberRows(){
  const target=document.getElementById("memberList");if(!target)return;
  const q=String(document.getElementById("memberSearch")?.value||"").trim().toLowerCase();
  const rows=memberRows.filter(user=>!q||[friendlyMemberName(user),memberRiotId(user),user.email,user.discordDisplayName,user.discord_display_name,memberRoleLabel(user)].filter(Boolean).join(" ").toLowerCase().includes(q));
  target.innerHTML=rows.length?rows.map(user=>{
    const discord=Boolean(user.discordConnected||user.discord_connected||user.discordDisplayName||user.discord_display_name);
    const name=friendlyMemberName(user),riotId=memberRiotId(user),flags=memberRoleFlags(user),guildAdmins=memberServerAdminGuilds(user);
    const userId=String(user.id||user.userId||user.user_id||"");
    const isServerAdmin=selectedGuild?guildAdmins.has(String(selectedGuild)):false;
    return `<div class="admin-member-row" data-member-id="${esc(userId)}">
      <span><strong>${esc(name)}</strong>${riotId?`<small>Riot ID</small>`:""}</span>
      <span>${esc(user.email||"-")}</span>
      <span><b class="admin-member-role">${esc(memberRoleLabel(user))}</b>${selectedGuild&&isServerAdmin?`<small>${esc(uniqueGuilds().find(g=>g.id===selectedGuild)?.name||"선택 서버")} 관리자</small>`:""}</span>
      <span><i class="admin-member-discord ${discord?"connected":""}">${discord?"연결됨":"미연결"}</i>${discord?`<small>${esc(user.discordDisplayName||user.discord_display_name||"")}</small>`:""}</span>
      <span class="admin-member-actions">
        <label><input type="checkbox" data-member-coach ${flags.coach?"checked":""}> 코치</label>
        <label><input type="checkbox" data-member-admin ${flags.admin?"checked":""}> 관리자</label>
        <label class="server-admin-check" title="Discord 서버 관리자 권한에서 자동 동기화됩니다"><input type="checkbox" data-member-server-admin ${isServerAdmin?"checked":""} disabled> 서버 관리자</label>
        <button type="button" data-member-save>저장</button>
      </span>
    </div>`;
  }).join(""):`<div class="admin-empty-admin"><strong>${q?"검색 결과가 없습니다.":"가입 회원이 없습니다."}</strong></div>`;
  target.querySelectorAll("[data-member-save]").forEach(btn=>btn.addEventListener("click",()=>saveMemberPermissions(btn.closest("[data-member-id]"))));
}
async function saveMemberPermissions(row){
  if(!row)return;
  const userId=String(row.dataset.memberId||"");if(!userId)return;
  const coach=Boolean(row.querySelector("[data-member-coach]")?.checked);
  const admin=Boolean(row.querySelector("[data-member-admin]")?.checked);
  const status=document.getElementById("memberActionStatus");if(status)status.textContent="권한 저장 중...";
  try{
    const roles=[...(coach?["coach"]:[]),...(admin?["admin"]:[])];
    const role=coach?"coach":(admin?"admin":"student");
    const global=await adminRequest(`/api/users/${encodeURIComponent(userId)}`,{method:"PATCH",body:{role,roles,isCoach:coach,isAdmin:admin}});
    if(global?.user)memberRows=memberRows.map(item=>String(item.id||item.userId||item.user_id)===userId?{...item,...global.user}:item);
    if(status)status.textContent="권한을 저장했습니다.";
    renderMemberRows();
  }catch(error){if(status)status.textContent=error.message||"권한 저장에 실패했습니다.";}
}
async function loadMembers(){
  const target=document.getElementById("memberList");if(target)target.innerHTML=`<div class="admin-empty-admin"><strong>회원 목록을 불러오는 중...</strong></div>`;
  try{
    const data=await adminRequest("/api/users");memberRows=data.users||[];
    const discord=memberRows.filter(user=>user.discordConnected||user.discord_connected||user.discordDisplayName||user.discord_display_name).length;
    const coaches=memberRows.filter(user=>memberRoleFlags(user).coach).length;
    const admins=memberRows.filter(user=>memberRoleFlags(user).admin).length;
    const set=(id,value)=>{const el=document.getElementById(id);if(el)el.textContent=Number(value).toLocaleString();};
    set("memberTotal",memberRows.length);set("memberDiscord",discord);set("memberCoaches",coaches);set("memberAdmins",admins);
    renderMemberRows();
  }catch(error){if(target)target.innerHTML=`<div class="admin-empty-admin"><strong>회원 목록을 불러오지 못했습니다.</strong><span>${esc(error.message)}</span></div>`;}
}

function mileagePanel(){
  return shell(`
    ${panelTitle("포인트 관리","실제 지급 설정·상점·주문·환불·감사로그를 한 화면에서 관리합니다.")}
    <div id="adminMileageRoot"></div>
  `);
}

function shopPanel(){
  return shell(`
    ${panelTitle("상점 관리","포인트로 구매할 상품과 주문을 관리합니다.")}
    <div class="shop-admin-grid">
      <section class="admin-work-panel shop-products-panel">
        <div class="admin-toolbar">
          <div class="admin-subtabs">
            <button class="active" data-shop-tab="products" data-tab-message="상품 목록입니다.">상품</button>
            <button data-shop-tab="orders" data-tab-message="구매 처리와 환불은 실제 포인트 관리 화면에서 처리합니다.">주문</button>
            <button data-shop-tab="settings" data-tab-message="상점 사용 여부와 상품 설정은 실제 포인트 관리 화면에서 처리합니다.">상점 설정</button>
          </div>
          <button class="admin-primary" id="shopCreateBtn">+ 상품 등록</button>
        </div>

        <div class="shop-summary-row">
          <article><span>판매중 상품</span><strong>3</strong></article>
          <article><span>오늘 주문</span><strong>7</strong></article>
          <article><span>처리 대기</span><strong>2</strong></article>
          <article><span>오늘 사용 포인트</span><strong>4,300 P</strong></article>
        </div>

        <div class="shop-product-list">
          <article class="shop-product-card">
            <div class="shop-product-thumb">A</div>
            <div class="shop-product-main">
              <div class="shop-product-title-row"><strong>경기분석권</strong><span class="shop-status live">판매중</span></div>
              <p>게임 분석 상세 기능 1회 이용권</p>
              <div class="shop-product-meta"><span>500 P</span><span>재고 무제한</span><span>유저당 5회</span><span>자동 지급</span></div>
            </div>
            <div class="shop-product-actions"><button data-shop-action="edit">수정</button><button>판매중지</button></div>
          </article>

          <article class="shop-product-card">
            <div class="shop-product-thumb">C</div>
            <div class="shop-product-main">
              <div class="shop-product-title-row"><strong>코칭 5,000원 할인권</strong><span class="shop-status live">판매중</span></div>
              <p>Lucid 코칭 상품 결제 시 사용 가능한 할인권</p>
              <div class="shop-product-meta"><span>1,500 P</span><span>재고 30</span><span>유저당 1회</span><span>운영진 처리</span></div>
            </div>
            <div class="shop-product-actions"><button data-shop-action="edit">수정</button><button>판매중지</button></div>
          </article>

          <article class="shop-product-card muted">
            <div class="shop-product-thumb">R</div>
            <div class="shop-product-main">
              <div class="shop-product-title-row"><strong>특별 Discord 역할</strong><span class="shop-status paused">판매중지</span></div>
              <p>구매 후 지정 Discord 역할을 자동 지급</p>
              <div class="shop-product-meta"><span>800 P</span><span>재고 10</span><span>유저당 1회</span><span>Discord 역할</span></div>
            </div>
            <div class="shop-product-actions"><button data-shop-action="edit">수정</button><button>판매재개</button></div>
          </article>
        </div>
      </section>

      <aside class="shop-preview-panel">
        <div class="shop-preview-head"><span>사용자 상점 미리보기</span><small>파라다이스 서버</small></div>
        <div class="shop-balance-card"><span>내 포인트</span><strong>1,420 P</strong></div>
        <div class="shop-preview-item">
          <div class="shop-preview-thumb">A</div>
          <div><strong>경기분석권</strong><small>게임 분석 상세 기능 1회</small></div>
          <button>500 P</button>
        </div>
        <div class="shop-preview-item">
          <div class="shop-preview-thumb">C</div>
          <div><strong>코칭 할인권</strong><small>5,000원 할인</small></div>
          <button>1,500 P</button>
        </div>
        <div class="shop-preview-note">실제 사용자 상점은 커뮤니티 상단의 ‘상점’ 메뉴로 연결하는 구조를 권장합니다.</div>
      </aside>
    </div>

    <div class="shop-editor-backdrop" id="shopEditorBackdrop" hidden>
      <section class="shop-editor-dialog">
        <div class="shop-editor-head">
          <div><small>SHOP ITEM</small><h3 id="shopEditorTitle">상품 등록</h3></div>
          <button id="shopEditorClose" type="button">×</button>
        </div>
        <div class="shop-editor-form">
          <label class="wide"><span>상품명</span><input id="shopName" placeholder="예: 경기분석권"></label>
          <label><span>가격</span><div class="shop-input-suffix"><input id="shopPrice" type="number" value="500"><b>P</b></div></label>
          <label><span>상품 유형</span><select id="shopType"><option>경기분석권</option><option>코칭권/할인권</option><option>Discord 역할</option><option>운영진 수동 처리</option><option>쿠폰/코드</option></select></label>
          <label class="wide"><span>설명</span><textarea id="shopDescription" rows="3" placeholder="상품 설명"></textarea></label>
          <label><span>재고</span><input id="shopStock" placeholder="비워두면 무제한"></label>
          <label><span>유저당 구매 제한</span><input id="shopLimit" type="number" value="1"></label>
          <label><span>판매 시작</span><input id="shopStart" type="datetime-local"></label>
          <label><span>판매 종료</span><input id="shopEnd" type="datetime-local"></label>
          <label class="wide"><span>상품 이미지</span><div class="shop-image-drop">이미지 업로드 영역</div></label>
        </div>
        <div class="shop-editor-footer">
          <button class="admin-select-button" id="shopEditorCancel">취소</button>
          <button class="admin-primary" id="shopEditorSave">상품 저장</button>
        </div>
      </section>
    </div>
  `);
}

function eventsPanel(){
  return shell(`
    ${panelTitle("이벤트 관리","Discord /이벤트랭킹을 홈페이지 이벤트 관리로 이관하는 영역입니다.")}
    <section class="admin-work-panel">
      <div class="admin-empty-admin"><strong>이벤트 API는 아직 연결되지 않았습니다.</strong><span>현재 봇에는 홈페이지가 안전하게 수정할 별도 이벤트 저장소가 없어 Discord 운영 데이터와 실시간 연동할 수 없습니다.</span></div>
    </section>
  `);
}

function missingPanel(){
  return shell(`
    ${panelTitle("상세스탯 누락","기본 경기기록은 유지하면서 누락된 상세스탯 경기를 확인하고 관리 목록에서 제외합니다.")}
    <section class="admin-work-panel">
      <div class="admin-toolbar"><div class="admin-subtabs"><button class="${missingArchived?"":"active"}" data-missing-archived="0">누락 경기</button><button class="${missingArchived?"active":""}" data-missing-archived="1">보관함</button></div><button id="missingRefresh" class="admin-primary">새로고침</button></div>
      <p class="admin-tab-feedback">${missingArchived?"보관한 누락 경기입니다. 원본 경기/MMR은 유지되며 언제든 목록으로 복원할 수 있습니다.":"상세스탯이 10명 미만 저장된 경기의 양 팀·라인·닉네임을 표시합니다."}</p>
      <div id="missingDetailsList" class="admin-table"><div class="admin-empty-admin"><strong>불러오는 중...</strong></div></div>
      <div class="admin-draft-note">삭제는 경기/MMR을 지우지 않고 누락 관리 목록에서 보관 처리합니다. 원본 경기기록을 직접 지우면 봇 메모리와 충돌할 수 있어 안전하게 분리했습니다.</div>
    </section>
  `);
}

function logsPanel(){
  return shell(`
    ${panelTitle("운영 로그","채팅로그를 포함해 관리자 작업과 주요 변경 이력을 모읍니다.")}
    <section class="admin-work-panel">
      <div class="admin-subtabs"><button class="active" data-log-kind="chat">채팅</button><button data-log-kind="mileage">포인트 감사</button><button data-log-kind="reports">신고</button><button data-log-kind="moderation">경고·메모</button></div>
      <form id="chatLogFilters" class="admin-filter-grid"><label>채널<input name="channel" list="chatChannelOptions" placeholder="채널명 또는 ID"><datalist id="chatChannelOptions"></datalist></label><label>유저<input name="user" placeholder="닉네임 또는 Discord ID"></label><label>내용<input name="content" placeholder="메시지 내용"></label><button class="admin-primary" type="submit">검색</button><button class="admin-select-button" type="reset">초기화</button></form>
      <p class="admin-tab-feedback">선택한 서버의 최근 채팅 로그입니다.</p>
      <div id="operationLogList" class="admin-table"><div class="admin-empty-admin"><strong>불러오는 중...</strong></div></div>
    </section>
  `);
}

function dataPanel(){
  return shell(`
    ${panelTitle("데이터 관리","/서버데이터내보내기를 홈페이지 다운로드 방식으로 옮깁니다.")}
    <section class="admin-work-panel">
      <div class="admin-export-grid">
        ${["유저 데이터","경기 기록","전적","포인트","서버 설정","운영 로그"].map((x,i)=>`<label><input type="checkbox" ${i<5?"checked":""}><span>${x}</span></label>`).join("")}
      </div>
      <div class="admin-export-action"><div><strong>서버 데이터 파일 생성</strong><small>선택한 데이터만 묶어서 내려받는 구조</small></div><button class="admin-primary" disabled>데이터 파일 생성</button></div>
      <div class="admin-draft-note">백엔드 export endpoint 연결 후 버튼 활성화</div>
    </section>
  `);
}

function supportPanel(){
  return shell(`
    ${panelTitle("문의 관리","/봇제작자문의를 홈페이지 문의 시스템으로 이관합니다.")}
    <section class="admin-work-panel">
      <div class="admin-subtabs"><button class="active" data-inquiry-status="">전체</button><button data-inquiry-status="open">미처리</button><button data-inquiry-status="processing">처리중</button><button data-inquiry-status="completed">완료</button></div>
      <p class="admin-tab-feedback">전체 문의입니다.</p>
      <div id="adminInquiryList"><div class="admin-empty-admin"><strong>불러오는 중...</strong></div></div>
    </section>
  `);
}

function roflStatusClass(status=""){const value=String(status).toUpperCase();return value.includes("READY")?"ready":["BLOCKED","VALIDATION_FAILED"].includes(value)?"blocked":["PARTIAL","RESEARCHING"].includes(value)?"partial":"unknown";}
function roflTime(value){if(!value)return "-";const date=new Date(Number(value)*1000);return Number.isNaN(date.getTime())?"-":date.toLocaleString("ko-KR");}
function roflBytes(value){const bytes=Number(value||0);if(bytes<1024)return `${bytes} B`;if(bytes<1048576)return `${(bytes/1024).toFixed(1)} KB`;return `${(bytes/1048576).toFixed(1)} MB`;}
function roflList(values=[],empty="없음"){return values.length?values.map(value=>`<span>${esc(value)}</span>`).join(""):`<span class="muted">${empty}</span>`;}
const ROFL_CAPABILITY_NAMES={kills:"킬 이벤트",deaths_assists:"데스/어시스트 이벤트",level_events:"레벨업",skill_build:"스킬 빌드",objectives:"오브젝트",towers:"타워",checkpoint_player_series:"체크포인트 / 플레이어 추이",fight_raw_events:"교전 분석 원본 이벤트",bans:"밴 정보",item_timeline:"아이템 타임라인",timeline_xp:"시간대별 경험치",player_gold:"개인 골드 타임라인",team_gold:"팀 골드 타임라인","final stats / participants":"최종 스탯 / 참가자","kill events":"킬 이벤트","objective events":"오브젝트 이벤트","tower events":"타워 이벤트","level events":"레벨업 이벤트","skill build":"스킬 빌드","checkpoint / player series":"체크포인트 / 플레이어 추이","timeline XP":"시간대별 경험치","team gold timeline":"팀 골드 타임라인"};
const ROFL_CHECK_CAPABILITY_IDS={"kill events":"kills","objective events":"objectives","tower events":"towers","level events":"level_events","skill build":"skill_build","checkpoint / player series":"checkpoint_player_series","timeline XP":"timeline_xp","team gold timeline":"team_gold"};
function roflState(value){return String(value||"UNPROVEN").trim().split(/[ (]/)[0].toUpperCase();}
function roflStateLabel(value){return ({PASS:"정상",READY:"정상",UNPROVEN:"검증 부족",WAIT:"검증 부족",PARTIAL:"검증 부족",UNSUPPORTED:"아직 지원 안 함",BLOCKED:"운영 반영 보류",FAIL:"검증 실패"})[roflState(value)]||"확인 필요";}
function roflCapabilityGroups(checks,semanticEvidence,semanticRegression,currentBuild,baselineBuild){
  const rows=new Map(),skip=new Set(["patch detected","file header decode","fixture gate","production gate"]);
  Object.entries(checks).forEach(([name,value])=>{if(!skip.has(name)){const id=ROFL_CHECK_CAPABILITY_IDS[name]||name;rows.set(id,{name:ROFL_CAPABILITY_NAMES[name]||name,status:roflState(value)});}});
  Object.entries(semanticEvidence).forEach(([name,evidence])=>{if(rows.has(name))return;const target=semanticRegression[name]?.target;const status=target||((currentBuild===baselineBuild&&evidence?.conclusion==="confirmed")?"PASS":"UNPROVEN");rows.set(name,{name:ROFL_CAPABILITY_NAMES[name]||name,status:roflState(status)});});
  const groups={normal:[],insufficient:[],unsupported:[]};
  rows.forEach(row=>(row.status==="PASS"?groups.normal:row.status==="UNSUPPORTED"?groups.unsupported:groups.insufficient).push(row));
  return groups;
}
function roflCapabilityGroup(title,rows,kind){
  return `<section class="rofl-capability-group ${kind}"><h4>${title} <b>${rows.length}</b></h4>${rows.length?rows.map(row=>{const reason=kind==="insufficient"?`<small>${["FAIL","BLOCKED"].includes(row.status)?"현재 샘플 검증에 실패했습니다. 상세 원인 확인 후 진단 ZIP을 전달하세요.":"교차검증 근거가 부족합니다. 같은 패치 ROFL을 추가하면 자동 재검증됩니다."}</small>`:"";return `<div><span>${esc(row.name)}</span><strong>${esc(roflStateLabel(row.status))} <small>(${esc(row.status)})</small></strong>${reason}</div>`;}).join(""):`<p>해당 항목이 없습니다.</p>`}</section>`;
}

function roflPanel(){
  return shell(`
    ${panelTitle("ROFL 패치 분석","새 패치 ROFL을 보존하고 자동 진단한 뒤 Codex 전달 ZIP까지 준비합니다.")}
    <section class="rofl-guide"><strong>자동 흐름</strong><span>ROFL 업로드 → 원본 보존 → ground truth 수집 → 연구·재검증 → workflow 갱신</span><small>사람 입력은 문제가 있을 때의 수정 승인과 검증 통과 뒤의 배포 승인뿐입니다. 평상시 Codex/LLM은 사용하지 않습니다.</small></section>
    <section class="admin-work-panel rofl-upload-panel">
      <div id="roflDropzone" class="rofl-dropzone" tabindex="0"><strong>새 패치 ROFL을 여기에 놓으세요</strong><span>.rofl 여러 개를 한 번에 선택할 수 있습니다.</span><button id="roflPick" class="admin-select-button" type="button">ROFL 추가</button><input id="roflInput" type="file" accept=".rofl" multiple hidden></div>
      <div id="roflSelected" class="rofl-selected"><span>선택된 파일이 없습니다.</span></div>
      <div class="rofl-upload-actions"><button id="roflAnalyze" class="admin-primary" type="button" disabled>분석 시작</button><button id="roflRefresh" class="admin-select-button" type="button">상태 새로고침</button><span id="roflUploadStatus"></span></div>
      <div id="roflUploadResults"></div>
    </section>
    <div id="roflDashboard"><div class="admin-empty-admin"><strong>패치 상태를 불러오는 중...</strong></div></div>
    <section class="admin-work-panel">
      <div class="rofl-card-head"><div><small>GROUND TRUTH</small><h3>Fixture 원본 검증 데이터</h3></div><span id="roflGroundTruthStatus">패치 선택 대기</span></div>
      <div id="roflGroundTruthList" class="rofl-file-results"><div class="admin-empty-admin"><strong>패치 fixture를 불러오는 중...</strong></div></div>
    </section>
    <section class="admin-work-panel">
      <div class="rofl-card-head"><div><small>REPLAY ARCHIVE</small><h3>저장된 경기 리플레이</h3></div><button id="replayArchiveRefresh" class="admin-select-button" type="button">새로고침</button></div>
      <div id="replayArchiveList" class="rofl-file-results"><div class="admin-empty-admin"><strong>불러오는 중...</strong></div></div>
    </section>
  `);
}

function riotSyncPanel(){return shell(`${panelTitle("Riot 공식전적 동기화","등록 계정의 Match-V5 수집 상태와 오류를 확인합니다.")}<section class="admin-work-panel"><div class="admin-toolbar"><div><strong>24시간 자동 동기화</strong><small>수동 요청 → 최근 내전 참가자 → 장기 미동기화 계정 순으로 공정하게 처리합니다.</small></div><button id="riotSyncRefresh" class="admin-primary" type="button">새로고침</button></div><div id="riotSyncSummary" class="admin-stat-grid"><div class="admin-empty-admin"><strong>불러오는 중...</strong></div></div><div class="admin-form-section"><h3>최근 배치 처리 계정</h3><div id="riotSyncRecentBatch" class="admin-table"></div></div><div class="admin-form-section"><h3>다음 처리 예정 계정</h3><div id="riotSyncNextBatch" class="admin-table"></div></div><div id="riotSyncAccounts" class="admin-table"></div></section>`);}

const syncPriorityLabel={manual:"수동 요청",recent7:"최근 7일",recent30:"최근 30일",aging:"장기 미동기화"};
function syncBatchHtml(rows,{recent=false}={}){return rows.length?rows.map(row=>`<div class="admin-table-row admin-log-cols"><span><strong>${esc(row.riotId)}</strong><small>계정 ${Number(row.accountSlot)+1}</small></span><span>${recent?"처리 완료":esc(syncPriorityLabel[row.priority]||row.priority||"기본")}</span><span>${row.lastSuccessAt?esc(new Date(row.lastSuccessAt).toLocaleString("ko-KR")):"성공 기록 없음"}</span><span>${recent?(row.syncedAt?esc(new Date(row.syncedAt).toLocaleString("ko-KR")):esc(row.status||"")):(row.nextSyncAt?esc(new Date(row.nextSyncAt).toLocaleString("ko-KR")):"-")}</span></div>`).join(""):`<div class="admin-empty-admin"><strong>${recent?"최근 배치 기록이 없습니다.":"처리 예정 계정이 없습니다."}</strong></div>`;}

async function loadRiotSyncStatus(){
  const summary=document.getElementById("riotSyncSummary"),accounts=document.getElementById("riotSyncAccounts"),recent=document.getElementById("riotSyncRecentBatch"),next=document.getElementById("riotSyncNextBatch");if(!selectedGuild||!summary||!accounts||!recent||!next)return;
  try{const data=await adminRequest(`/api/community/admin/guilds/${encodeURIComponent(selectedGuild)}/riot-sync`);summary.innerHTML=[["등록 계정",data.registeredAccounts],["24시간 성공",data.succeeded24h],["실패",data.failedAccounts],["대기",data.pendingAccounts],["공식 경기",data.matchesTotal],["오늘 신규",data.matchesToday],["공동 플레이",data.sharedPlayMatches],["마지막 실행",data.lastFullSyncAt?new Date(data.lastFullSyncAt).toLocaleString("ko-KR"):"미실행"]].map(([label,value])=>`<article><span>${label}</span><strong>${esc(value)}</strong></article>`).join("");recent.innerHTML=syncBatchHtml(data.recentBatch||[],{recent:true});next.innerHTML=syncBatchHtml(data.nextBatch||[]);const rows=data.accounts||[];accounts.innerHTML=rows.length?rows.map(row=>`<div class="admin-table-row admin-log-cols"><span><strong>${esc(row.riotId)}</strong><small>계정 ${Number(row.accountSlot)+1}</small></span><span>${esc(row.status)}</span><span>${row.lastSuccessAt?esc(new Date(row.lastSuccessAt).toLocaleString("ko-KR")):"성공 기록 없음"}<small>다음 ${row.nextSyncAt?esc(new Date(row.nextSyncAt).toLocaleString("ko-KR")):"-"}</small></span><span>${esc(row.lastError||"")}</span></div>`).join(""):`<div class="admin-empty-admin"><strong>등록된 Riot 계정이 없습니다.</strong></div>`;}catch(error){summary.innerHTML=`<div class="admin-empty-admin"><strong>동기화 상태를 불러오지 못했습니다.</strong><span>${esc(error.message)}</span></div>`;accounts.innerHTML="";recent.innerHTML="";next.innerHTML="";}
}

function retroPanel(){
  return shell(`
    ${panelTitle("리플레이 소급","지난 경기 ROFL을 검증하고 누락된 기록만 안전하게 복구합니다.")}
    <section class="admin-work-panel rofl-upload-panel">
      <div class="rofl-card-head"><div><small>RETROACTIVE RECOVERY</small><h3>전적 소급 복구</h3></div><span>기존 전적은 다시 반영하지 않음</span></div>
      <div id="retroRoflDropzone" class="rofl-dropzone" tabindex="0"><strong>복구할 ROFL을 여기에 놓으세요</strong><span>먼저 원본 보존·참가자 10명·기존 경기 상태만 검사합니다.</span><button id="retroRoflPick" class="admin-select-button" type="button">ROFL 추가</button><input id="retroRoflInput" type="file" accept=".rofl" multiple hidden></div>
      <div id="retroRoflSelected" class="rofl-selected"><span>선택된 파일이 없습니다.</span></div>
      <div class="rofl-upload-actions"><button id="retroRoflAnalyze" class="admin-primary" type="button" disabled>검증 시작</button><button id="retroRoflRefresh" class="admin-select-button" type="button">결과 새로고침</button><span id="retroRoflStatus"></span></div>
      <div id="retroRoflResults" class="retroactive-results"><div class="admin-empty-admin"><strong>검증한 ROFL이 없습니다.</strong></div></div>
    </section>
  `);
}

function renderRoflDashboard(data){
  const target=document.getElementById("roflDashboard");if(!target)return;
  target.dataset.loaded="1";
  const sectionStatus=data.sectionStatus||{},sectionFailed=name=>sectionStatus[name]==="ERROR";
  const current=data.current||{},patchFailed=sectionFailed("patch")||(sectionStatus.patch==="PARTIAL"&&!current.build),detail=data.detail||{},status=patchFailed?"UNKNOWN":String(current.status||"UNKNOWN"),suff=current.sufficiency||{};
  const research=data.researchV13||data.researchV12||data.researchV11||{};
  const workflow=data.workflow||{},workflowCounts=workflow.counts||{},validation=workflow.validation||{},validationGates=validation.gates||{};
  const semanticBaseline=(research.baseline||{}).semantic_baseline||{},semanticEvidence=semanticBaseline.capability_evidence||{};
  const knownGood=Object.values(semanticEvidence).filter(item=>item&&item.conclusion==="confirmed").length;
  const checks=detail.diagnostic_checks||{},diff=detail.patch_diff||{},retention=data.retention||{},deploy=data.deploy||{},result=deploy.last_result||{};
  const regression=deploy.last_regression||data.regression||{},report=current.diagnostic_report||{},errors=detail.errors||[],representatives=detail.representative_fixtures||[];
  const reportReady=Boolean(research.handoff_ready||report.zip_path),halt=Boolean(data.decoderFingerprint&&deploy.safety_halt_fingerprint===data.decoderFingerprint);
  const histories=data.history||[];
  const fixtureGate=String(checks["fixture gate"]||""),minimum=Number(fixtureGate.match(/minimum\s+(\d+)/i)?.[1]||suff.recommended||5),fixtureCount=Number(current.fixture_count||0),needed=patchFailed?0:Math.max(0,minimum-fixtureCount);
  const semanticRegression=((research.final||{}).semantic_regression||{}).capability_regression||{},groups=roflCapabilityGroups(checks,semanticEvidence,semanticRegression,current.build,semanticBaseline.build);
  const blocked=status==="BLOCKED",researching=research.status==="RESEARCHING",fixPending=workflow.status==="FIX_APPROVAL_PENDING",deployPending=workflow.status==="DEPLOY_APPROVAL_PENDING";
  const overall=({READY:"✅ 검증 완료",PARTIAL:"⚠️ 검증 진행 중",BLOCKED:"⛔ 운영 반영 보류"})[status]||"ℹ️ 상태 확인 필요";
  const impact=patchFailed?"확인 가능한 기존 자료는 유지되며 분석 결과에는 영향이 없습니다.":blocked?"새 패치 자동 반영은 보류되며 기존 분석 결과는 유지됩니다.":"기존 기본 분석은 계속 사용할 수 있습니다.";
  const problem=patchFailed?"패치 상태 조회 실패":blocked?(current.blocker_summary||current.reason||"필수 검증이 통과되지 않았습니다."):needed?"검증용 ROFL 샘플 부족":researching?"자동 재검증 진행 중":"확인된 운영 차단 문제 없음";
  const action=patchFailed?"잠시 후 상태 새로고침":fixPending?"연구 결과를 확인하고 수정 승인":deployPending?"검증 결과를 확인하고 배포 승인":needed?`같은 패치 ROFL ${needed}개 추가 업로드`:researching?"자동 분석 완료 대기":"별도 조치가 필요하지 않습니다.";
  const recommendations=fixPending?["연구 결과와 fixture 수 확인","수정 승인","동결된 Codex package 전달"]:deployPending?["Validation·Regression 확인","배포 승인"]:needed?[`같은 패치 ROFL ${needed}개 추가 업로드`]:researching?["자동 분석 완료 대기"]:["별도 조치 없음"];
  target.innerHTML=`
    ${data.partial?`<section class="rofl-guide"><strong>일부 상태 조회 실패</strong><span>${esc(Object.keys(data.sectionErrors||{}).join(", ")||"storage")} 영역은 실제 0이 아니라 상태 확인이 필요합니다.</span><small>읽을 수 있는 보존 자료는 그대로 표시합니다.</small></section>`:""}
    <section class="rofl-operator-summary rofl-${roflStatusClass(status)}">
      <div class="rofl-card-head"><div><small>현재 상태 요약</small><h2>${esc(current.build||(patchFailed?"상태 확인 필요":"아직 감지되지 않음"))}</h2></div><strong class="rofl-status-badge">${esc(overall)} · ${esc(status)}</strong></div>
      <dl><div><dt>전체 상태</dt><dd>${esc(overall)}</dd></div><div><dt>운영 영향</dt><dd>${esc(impact)}</dd></div><div><dt>현재 문제</dt><dd>${esc(problem)}</dd></div><div><dt>지금 할 일</dt><dd>${esc(action)}</dd></div></dl>
    </section>
    <section class="rofl-stat-grid">
      <article><span>분석 충분도</span><strong>${esc(patchFailed?"상태 조회 실패":suff.label||"미수집")}</strong><small>${patchFailed?"fixture 수 확인 필요":`샘플 ${Number(current.fixture_count||0)}개 · 권장 ${Number(suff.recommended||5)}개`}</small><small>대표 ${representatives.map(row=>`${row.name} (${roflBytes(row.size_bytes)})`).join(" · ")||(patchFailed?"조회 실패":"미선정")}</small></article>
      <article><span>현재 decoder</span><strong class="rofl-code">${esc(data.decoderFingerprint||"-")}</strong><small>마지막 상태 ${roflTime(current.updated_at)}</small></article>
      <article><span>이전 패치 회귀</span><strong>${esc(regression.status||"NOT_RUN")}</strong><small>${esc(regression.summary||"배포 gate에서 실행")}</small></article>
      <article><span>배포 후 안전 상태</span><strong>${halt?"SAFETY_HALT":esc((deploy.pending_completion||{}).outcome||"대기")}</strong><small>${esc(deploy.last_error||"감지된 오류 없음")}</small></article>
      <article><span>v1.3 연구기</span><strong>${esc(sectionFailed("research")?"UNKNOWN / 상태 확인 필요":research.status||"NOT_STARTED")}</strong><small>${sectionFailed("research")?"research state 조회 실패":`${Number(research.progress||0)}% · baseline ${Number(semanticBaseline.fixture_count||0)}개 · KNOWN_GOOD ${knownGood}개 · 운영 READY와 분리`}</small></article>
    </section>
    <section class="rofl-two-column">
      <article class="admin-work-panel rofl-capabilities"><div class="rofl-card-head"><div><small>CAPABILITY</small><h3>분석 기능 상태</h3></div><span>내부 상태를 운영자 문구와 함께 표시</span></div>${roflCapabilityGroup("정상",groups.normal,"normal")}${roflCapabilityGroup("검증 부족",groups.insufficient,"insufficient")}${roflCapabilityGroup("아직 지원 안 함",groups.unsupported,"unsupported")}</article>
      <article class="admin-work-panel"><div class="rofl-card-head"><div><small>RESEARCH HANDOFF</small><h3>자동 연구 결과</h3></div><span>${reportReady?"대표 fixture 최대 3개":"준비 중"}</span></div><div class="rofl-report-info"><strong>${esc(String(research.handoff_path||report.zip_path||"").split(/[\\/]/).pop()||"아직 생성되지 않음")}</strong><span>build ${esc(current.build||"-")} · 운영 READY 권한 없음</span><small>결정론적 sidecar 결과이며 Codex/LLM을 호출하지 않습니다.</small></div><button id="roflDownload" class="admin-select-button" type="button" ${reportReady?"":"disabled"}>연구 Handoff 다운로드</button></article>
    </section>
    <section class="admin-work-panel"><div class="rofl-card-head"><div><small>APPROVAL WORKFLOW</small><h3>${esc(workflow.result||workflow.status||"RESEARCHING")}</h3></div><span>${esc(workflow.timeline_status||"")} · sequence ${Number(workflow.pending_sequence||workflow.sequence||0)}</span></div><div class="rofl-retention"><span>valid fixture <b>${Number(workflowCounts.valid||workflow.valid_fixture_count||0)}/${Number(workflowCounts.total||fixtureCount)}</b></span><span>ground truth <b>${Number(workflowCounts.ground_truth||workflow.ground_truth_count||0)}/${Number(workflowCounts.validation||workflowCounts.valid||0)}</b></span><span>confidence <b>${esc(workflow.confidence||"LOW")}</b></span><span>Validation <b>${validationGates.fixtures_match?`${Number(validationGates.fixture_count||0)}/${Number(validationGates.fixture_count||0)} PASS`:"대기"}</b></span><span>Regression <b>${esc(validationGates.regression_1617?.passed?`${Number(validationGates.regression_1617.tested_fixture_count||0)}/${Number(validationGates.regression_1617.tested_fixture_count||0)} PASS`:"대기")}</b></span></div><div class="rofl-upload-actions"><button class="admin-primary" type="button" data-rofl-approve-fix="${esc(current.build||"")}" ${fixPending?"":"disabled"}>수정 승인</button><button class="admin-primary" type="button" data-rofl-approve-deploy="${esc(current.build||"")}" ${deployPending?"":"disabled"}>배포 승인</button>${workflow.manifest?`<button class="admin-select-button" type="button" data-rofl-artifact="instruction" data-rofl-artifact-build="${esc(current.build||"")}">지시문 보기</button><button class="admin-select-button" type="button" data-rofl-artifact="package" data-rofl-artifact-build="${esc(current.build||"")}">Handoff ZIP</button>${(workflow.manifest.validation_bundles||[]).map((_,index)=>`<button class="admin-select-button" type="button" data-rofl-artifact="validation-bundle" data-rofl-artifact-part="${index+1}" data-rofl-artifact-build="${esc(current.build||"")}">Validation bundle${index?` ${index+1}`:""}</button>`).join("")}`:""}</div><small class="rofl-safe-note">수정 승인 전에는 Codex package가 동결되지 않으며, 배포 승인은 모든 validation gate 통과 뒤에만 활성화됩니다.</small></section>
    <section class="rofl-two-column rofl-gates">
      <article class="admin-work-panel"><div class="rofl-card-head"><div><small>검증 샘플</small><h3>현재 ${fixtureCount}개 / 최소 ${minimum}개</h3></div><strong>${needed?`추가로 ${needed}개 필요`:"최소 기준 충족"}</strong></div><p>${needed?"같은 패치 ROFL을 추가하면 자동으로 다시 검증합니다.":"샘플 수 기준을 충족했습니다. 각 분석 항목 결과를 확인하세요."}</p></article>
      <article class="admin-work-panel"><div class="rofl-card-head"><div><small>운영 적용 가능 여부</small><h3>${esc(roflStateLabel(checks["production gate"]||status))} <small>(${esc(roflState(checks["production gate"]||status))})</small></h3></div></div><dl><div><dt>이유</dt><dd>${esc(problem)}</dd></div><div><dt>운영 영향</dt><dd>${esc(impact)}</dd></div><div><dt>조치</dt><dd>${esc(action)}</dd></div></dl></article>
    </section>
    <section class="admin-work-panel"><div class="rofl-card-head"><div><small>PATCH DIFF</small><h3>이전 정상 패치와 확인된 차이</h3></div><span>추정 변화는 표시하지 않음</span></div><div class="rofl-diff-grid"><div><strong>새로 지원 확인</strong>${roflList(diff.added_or_newly_supported||[])}</div><div><strong>미지원 또는 미확정</strong>${roflList(diff.removed_or_unproven||[])}</div><div><strong>계속 지원 확인</strong>${roflList(diff.unchanged_supported||[])}</div></div></section>
    <section class="rofl-two-column">
      <article class="admin-work-panel"><div class="rofl-card-head"><div><small>RETENTION</small><h3>원본 보존 현황</h3></div><span>최소 14일</span></div><div class="rofl-retention">${patchFailed?"<span>ROFL 보존 상태를 불러오지 못했습니다.</span>":`<span>원본 <b>${Number(retention.raw_total||0)}</b></span><span>구조화 완료 <b>${Number(retention.structured_total||0)}</b></span><span>decode 대기 <b>${Number(retention.decode_pending||0)}</b></span><span>48시간 내 만료 <b>${Number(retention.expires_within_48h||0)}</b></span><span>사용량 <b>${roflBytes(retention.bytes_total)}</b></span>`}</div></article>
      <article class="admin-work-panel"><div class="rofl-card-head"><div><small>POST-DEPLOY</small><h3>자동 재분석</h3></div><span>${halt?"안전 중단":result.eligible?"최근 실행":"대기"}</span></div><div class="rofl-retention"><span>대상 <b>${Number(result.eligible||deploy.pending_before_run||0)}</b></span><span>성공·교체 <b>${Number(result.succeeded||0)}</b></span><span>실패·기존값 보존 <b>${Number(result.failed||0)}</b></span><span>저장 서버 <b>${Number(result.guilds||0)}</b></span></div><small class="rofl-safe-note">실패한 경기의 기존 분석은 삭제하거나 덮어쓰지 않습니다.</small></article>
    </section>
    <section class="admin-work-panel rofl-recommendations"><div class="rofl-card-head"><div><small>NEXT ACTION</small><h3>추천 작업</h3></div><span>위에서부터 순서대로 진행</span></div><ol>${recommendations.map(item=>`<li>${esc(item)}</li>`).join("")}</ol></section>
    <section class="admin-work-panel"><div class="rofl-card-head"><div><small>HISTORY</small><h3>패치 히스토리</h3></div><span>build를 누르면 상세 전환</span></div><div class="rofl-history">${histories.map(row=>`<button type="button" data-rofl-build="${esc(row.build)}"><span><strong>${esc(row.build)}</strong><small>${roflTime(row.updated_at)} · 샘플 ${Number(row.fixture_count||0)}개</small></span><b class="rofl-mini-status rofl-${roflStatusClass(row.status)}">${esc(roflStateLabel(row.status))} (${esc(row.status)})</b><em>${esc(row.blocker_summary||"")}</em></button>`).join("")||(patchFailed?"<p>패치 히스토리를 불러오지 못했습니다.</p>":"<p>기록된 패치가 없습니다.</p>")}</div></section>
    <details class="admin-work-panel rofl-details"><summary>상세 오류 및 구조 로그 보기</summary><div><h4>상세 사유</h4><pre>${esc(current.reason||"저장된 상세 사유 없음")}</pre><h4>실패 로그</h4>${errors.length?errors.map(error=>`<pre>${esc(error.source||"error")}: ${esc(error.error||"")}${error.traceback?`\\n\\n${esc(error.traceback)}`:""}</pre>`).join(""):"<p>저장된 실패 로그가 없습니다.</p>"}<h4>snapshot layout</h4><pre>${esc(JSON.stringify(diff.snapshot_layout||{},null,2))}</pre></div></details>
  `;
  target.querySelectorAll("[data-rofl-build]").forEach(button=>button.addEventListener("click",()=>loadRoflDashboard(button.dataset.roflBuild)));
  target.querySelector("#roflDownload")?.addEventListener("click",()=>downloadRoflReport(current.build));
  target.querySelector("[data-rofl-approve-fix]")?.addEventListener("click",()=>approveRoflWorkflow(current.build,"approve-fix","현재 연구 결과와 fixture/ground-truth 해시를 수정 package로 동결할까요?"));
  target.querySelector("[data-rofl-approve-deploy]")?.addEventListener("click",()=>approveRoflWorkflow(current.build,"approve-deploy","검증 결과를 확인했습니다. 배포를 승인할까요?"));
  target.querySelectorAll("[data-rofl-artifact]").forEach(button=>button.addEventListener("click",()=>downloadRoflWorkflowArtifact(button.dataset.roflArtifactBuild,button.dataset.roflArtifact,button.dataset.roflArtifactPart||1)));
}

let titleRows=[],levelIconState=null;
function titlePanel(){return shell(`${panelTitle("칭호 / 업적","봇이 실제 사용하는 칭호 정의와 달성 조건입니다.")}<section class="admin-work-panel admin-level-icon-panel"><div><small>내전 레벨 아이콘</small><h3>프로필 공용 아이콘</h3><p>PNG/JPG/WebP 정사각형 256 × 256 · 512KB 이하</p></div><form id="levelIconForm"><span id="levelIconPreview" class="admin-level-icon-preview">🎮</span><input name="icon" type="file" accept="image/png,image/jpeg,image/webp" required><button class="admin-primary" type="submit">아이콘 변경</button></form><small id="levelIconStatus">이미지를 올리기 전에는 🎮 이모지를 사용합니다.</small></section><section class="admin-work-panel"><div class="admin-title-tools"><input id="titleSearch" type="search" placeholder="칭호 또는 조건 검색"><select id="titleCategory"><option value="">전체 분류</option></select><b id="titleCount">0개</b></div><div id="titleCatalog" class="admin-title-grid"><div class="admin-empty-admin"><strong>불러오는 중...</strong></div></div></section>`);}
function renderTitleCatalog(){const search=String(document.getElementById("titleSearch")?.value||"").toLowerCase(),category=document.getElementById("titleCategory")?.value||"",rows=titleRows.filter(row=>(!category||row.category===category)&&(!search||`${row.name} ${row.condition}`.toLowerCase().includes(search)));const count=document.getElementById("titleCount"),target=document.getElementById("titleCatalog");if(count)count.textContent=`${rows.length}개`;if(target)target.innerHTML=rows.map(row=>`<article><span>${esc(row.icon||"🏷️")}</span><div><small>${esc(row.category||"기타")}${row.seriesGroup?` · ${esc(row.seriesGroup)}`:""}</small><strong>${esc(row.name)}</strong><p>${esc(row.condition||"조건 정보 없음")}</p></div></article>`).join("")||`<div class="admin-empty-admin"><strong>조건에 맞는 칭호가 없습니다.</strong></div>`;}
function renderLevelIcon(){const target=document.getElementById("levelIconPreview"),status=document.getElementById("levelIconStatus");if(target)target.innerHTML=levelIconState?`<img src="${esc(apiUrl(`/api/community/guilds/${encodeURIComponent(selectedGuild)}/level-icon?v=${levelIconState.sha256.slice(0,12)}`))}" alt="현재 내전 레벨 아이콘">`:"🎮";if(status&&levelIconState)status.textContent=`현재 ${levelIconState.width} × ${levelIconState.height} · ${new Date(levelIconState.updatedAt).toLocaleString("ko-KR")} 변경`;}
async function loadTitleCatalog(){if(!selectedGuild)return;try{const data=await adminRequest(`/api/community/admin/guilds/${encodeURIComponent(selectedGuild)}/titles`);titleRows=data.titles||[];levelIconState=data.levelIcon||null;renderLevelIcon();const select=document.getElementById("titleCategory"),categories=[...new Set(titleRows.map(row=>row.category).filter(Boolean))].sort();if(select)select.innerHTML=`<option value="">전체 분류</option>${categories.map(value=>`<option>${esc(value)}</option>`).join("")}`;renderTitleCatalog();}catch(error){const target=document.getElementById("titleCatalog");if(target)target.innerHTML=`<div class="admin-empty-admin"><strong>${esc(error.message)}</strong></div>`;}}

async function loadRoflDashboard(build=""){
  const target=document.getElementById("roflDashboard");if(!target)return;
  try{const data=await adminRequest(`/api/community/admin/rofl-patch/dashboard${build?`?build=${encodeURIComponent(build)}`:""}`);renderRoflDashboard(data);const selectedBuild=data.current?.build||build;if(selectedBuild)await loadRoflGroundTruth(selectedBuild);else if(data.sectionStatus?.patch!=="ERROR")await loadRoflGroundTruth("");}
  catch(error){const previous=target.dataset.loaded==="1";if(previous){target.querySelector("[data-rofl-fetch-error]")?.remove();target.insertAdjacentHTML("afterbegin",`<section class="rofl-guide" data-rofl-fetch-error><strong>패치 상태를 불러오지 못했습니다.</strong><span>${esc(error.message)}</span><small>마지막으로 확인된 상태는 아래에 유지합니다.</small></section>`);}else target.innerHTML=`<div class="admin-empty-admin"><strong>패치 상태를 불러오지 못했습니다.</strong><span>${esc(error.message)}</span></div>`;}
}

function renderRoflGroundTruth(rows=[]){
  const target=document.getElementById("roflGroundTruthList");if(!target)return;
  target.dataset.loaded="1";
  target.innerHTML=rows.length?rows.map(row=>`<div><strong>${esc(row.match_id)}</strong><span>ROFL ${row.rofl_preserved?"보존":"없음"} · Match-V5 ${row.read_error?"상태 확인":row.match_ground_truth?"있음":"없음"} · Timeline ${row.read_error?"상태 확인":row.timeline_ground_truth?"있음":"없음"}</span><small>마지막 수집 ${esc(row.fetched_at?new Date(row.fetched_at).toLocaleString("ko-KR"):row.read_error?"manifest 조회 실패":"-")}</small><button class="admin-select-button" type="button" data-ground-truth-match="${esc(row.match_id)}" data-ground-truth-build="${esc(row.build)}" data-ground-truth-force="${row.match_ground_truth&&row.timeline_ground_truth?"1":"0"}" ${row.rofl_preserved?"":"disabled"}>${row.match_ground_truth&&row.timeline_ground_truth?"재수집":"수집"}</button></div>`).join(""):`<div class="admin-empty-admin"><strong>보존된 ROFL이 없습니다.</strong></div>`;
  target.querySelectorAll("[data-ground-truth-match]").forEach(button=>button.addEventListener("click",()=>collectRoflGroundTruth(button)));
}
async function loadRoflGroundTruth(build){
  const status=document.getElementById("roflGroundTruthStatus");if(!build){if(status)status.textContent="패치가 아직 감지되지 않았습니다.";return renderRoflGroundTruth([]);}
  try{const data=await adminRequest(`/api/community/admin/rofl-ground-truth?build=${encodeURIComponent(build)}`);if(data.partial||!Array.isArray(data.fixtures)){if(status)status.textContent=data.message||"Ground truth 상태 조회 실패";return;}renderRoflGroundTruth(data.fixtures);if(status){const errors=data.fixtures.filter(row=>row.read_error).length;status.textContent=`${data.fixtures.filter(row=>row.match_ground_truth&&row.timeline_ground_truth).length}/${data.fixtures.length} 수집됨${errors?` · ${errors}개 상태 확인 필요`:""}`;}}
  catch(error){if(status)status.textContent=error.message;const target=document.getElementById("roflGroundTruthList");if(target?.dataset.loaded!=="1")target.innerHTML=`<div class="admin-empty-admin"><strong>Ground truth 상태를 불러오지 못했습니다.</strong><span>${esc(error.message)}</span></div>`;}
}
async function collectRoflGroundTruth(button){
  const status=document.getElementById("roflGroundTruthStatus");button.disabled=true;if(status)status.textContent=`${button.dataset.groundTruthMatch} 수집 중...`;
  try{const data=await adminRequest("/api/community/admin/rofl-ground-truth/collect",{method:"POST",body:{build:button.dataset.groundTruthBuild,matchId:button.dataset.groundTruthMatch,force:button.dataset.groundTruthForce==="1"}});renderRoflGroundTruth(data.fixtures||[]);if(status)status.textContent=`${button.dataset.groundTruthMatch} ${data.collection?.result||"완료"}`;}
  catch(error){if(status)status.textContent=error.message;button.disabled=false;}
}

function setRoflFiles(files){roflFiles=[...files].filter(file=>String(file.name||"").toLowerCase().endsWith(".rofl"));const list=document.getElementById("roflSelected"),button=document.getElementById("roflAnalyze");if(list)list.innerHTML=roflFiles.length?roflFiles.map(file=>`<span><strong>${esc(file.name)}</strong><small>${roflBytes(file.size)}</small></span>`).join(""):"<span>선택된 .rofl 파일이 없습니다.</span>";if(button)button.disabled=!roflFiles.length;}
async function uploadRoflFiles(){
  if(!roflFiles.length)return;const status=document.getElementById("roflUploadStatus"),button=document.getElementById("roflAnalyze"),results=document.getElementById("roflUploadResults"),uploading=[...roflFiles];button.disabled=true;if(status)status.textContent=`${uploading.length}개 원본 보존·분석 중...`;
  const body=new FormData();uploading.forEach(file=>body.append("files",file,file.name));
  try{const response=await fetch(apiUrl("/api/community/admin/rofl-patch/upload"),{method:"POST",credentials:"include",body}),data=await response.json().catch(()=>({}));if(!response.ok||!data.ok)throw new Error(data.message||data.error||"업로드에 실패했습니다.");const mixed=(data.builds||[]).length>1;if(status)status.textContent=mixed?"서로 다른 build가 감지되어 build별로 분리했습니다.":"분석 요청이 완료됐습니다.";if(results)results.innerHTML=`<div class="rofl-file-results">${(data.files||[]).map(row=>`<div><strong>${esc(row.filename)}</strong><span>${esc(row.build||"-")}</span><b class="rofl-${roflStatusClass(row.status)}">${row.ok?esc(row.status||"보존됨"):"실패"}${row.duplicate?" · 중복":""}</b><small>${esc(row.decodeError||row.error||"원본 보존 및 decode 완료")}</small></div>`).join("")}</div>`;roflFiles=[];setRoflFiles([]);renderRoflDashboard(data.dashboard||{});}
  catch(error){if(status)status.textContent=error.message;}finally{button.disabled=!roflFiles.length;}
}

function setRetroRoflFiles(files){retroRoflFiles=[...files].filter(file=>String(file.name||"").toLowerCase().endsWith(".rofl"));const list=document.getElementById("retroRoflSelected"),button=document.getElementById("retroRoflAnalyze");if(list)list.innerHTML=retroRoflFiles.length?retroRoflFiles.map(file=>`<span><strong>${esc(file.name)}</strong><small>${roflBytes(file.size)}</small></span>`).join(""):"<span>선택된 .rofl 파일이 없습니다.</span>";if(button)button.disabled=!retroRoflFiles.length||!selectedGuild;}
function renderRetroRoflActions(actions=[]){
  const target=document.getElementById("retroRoflResults");if(!target)return;
  target.innerHTML=actions.length?actions.map(row=>{const result=row.result||{},payload=row.payload||{},checks=result.checks||{},done=row.status==="completed",inspect=row.action==="inspect_retroactive_rofl",canApply=done&&inspect&&result.canApply;return `<article class="retroactive-card"><header><div><strong>${esc(result.filename||payload.filename||"ROFL")}</strong><small>${esc(result.roflMatchId||result.matchId||"")} · SHA-256 ${esc(String(result.sha256||payload.sha256||"").slice(0,12))}</small></div><b class="rofl-mini-status rofl-${row.status==="failed"?"blocked":done?"ready":"partial"}">${esc(row.status)}</b></header>${done?`<div class="retroactive-summary"><span>분류 <b>${esc(result.classification||"-")} · ${esc(result.classificationLabel||"")}</b></span><span>기존 경기 <b>${result.existingMatch?"있음":"없음"}</b></span><span>참가자 매핑 <b>${Number(result.participantMapped||0)}/${Number(result.participantTotal||10)}</b></span><span>상세 저장 <b>${Number(result.detailSavedCount||result.savedCount||0)}/10</b></span><span>승패/MMR <b>${checks.baseResult?(checks.mmrApplied?"기존값 유지":"기록 있음"):"미반영"}</b></span><span>ROFL 연결 <b>${checks.roflLinked?"있음":"누락"}</b></span></div>${result.error?`<p class="retroactive-error">${esc(result.error)}</p>`:""}${(result.participants||[]).length?`<details><summary>참가자 매핑 보기</summary><div class="retroactive-mapping">${result.participants.map(player=>`<span><strong>${esc(player.riotId||"이름 없음")}</strong><small>${player.matched?`${esc(player.userId)}${player.alias?" · 부계정":""}`:esc(player.reason||"매칭 실패")}</small></span>`).join("")}</div></details>`:""}${row.action==="apply_retroactive_rofl"&&result.applied?`<p class="rofl-safe-note">복구 완료 · 기존 승패/MMR ${result.baseResult==="created"?"신규 반영":"유지"} · 중복 반영 없음</p>`:""}`:`<p>${row.status==="failed"?esc(row.error||"검증 실패"):"worker 검증 대기 중..."}</p>`}<footer>${canApply?`<button class="admin-primary" type="button" data-retro-apply="${esc(result.sha256)}" data-retro-file="${esc(result.filename)}" data-retro-class="${esc(result.classification)}">복구 실행</button>`:""}${done&&!result.canApply&&result.classification==="E"?"이미 정상 완료된 경기입니다.":""}</footer></article>`;}).join(""):`<div class="admin-empty-admin"><strong>검증한 ROFL이 없습니다.</strong></div>`;
  target.querySelectorAll("[data-retro-apply]").forEach(button=>button.addEventListener("click",()=>applyRetroRofl(button)));
}
async function loadRetroRoflActions(){const status=document.getElementById("retroRoflStatus");if(!selectedGuild)return;try{const data=await adminRequest(`/api/community/admin/retroactive-rofl/actions?guildId=${encodeURIComponent(selectedGuild)}`);renderRetroRoflActions(data.actions||[]);if(status)status.textContent="검증 결과를 갱신했습니다.";}catch(error){if(status)status.textContent=error.message;}}
async function uploadRetroRoflFiles(){if(!retroRoflFiles.length||!selectedGuild)return;const status=document.getElementById("retroRoflStatus"),button=document.getElementById("retroRoflAnalyze"),body=new FormData();retroRoflFiles.forEach(file=>body.append("files",file,file.name));button.disabled=true;if(status)status.textContent="원본 보존 후 worker 검증을 요청하는 중...";try{const response=await fetch(apiUrl(`/api/community/admin/retroactive-rofl/upload?guildId=${encodeURIComponent(selectedGuild)}`),{method:"POST",credentials:"include",signal:AbortSignal.timeout(60000),body}),data=await response.json().catch(()=>({}));if(!response.ok||!data.ok)throw new Error(data.message||data.error||"업로드에 실패했습니다.");retroRoflFiles=[];setRetroRoflFiles([]);renderRetroRoflActions(data.actions||[]);if(status)status.textContent=`${(data.actions||[]).length}개 검증을 요청했습니다.`;setTimeout(loadRetroRoflActions,1500);}catch(error){if(status)status.textContent=error.message;}finally{button.disabled=!retroRoflFiles.length;}}
async function applyRetroRofl(button){const completeMissing=button.dataset.retroClass==="A",message=completeMissing?"완전 누락 경기입니다. 신규 전적으로 복구하면 승패/MMR이 1회 반영됩니다. 계속할까요?":"기존 승패/MMR은 유지하고 누락된 ROFL 데이터만 복구할까요?";if(!confirm(message))return;button.disabled=true;const status=document.getElementById("retroRoflStatus");try{await adminRequest("/api/community/admin/retroactive-rofl/apply",{method:"POST",body:{guildId:selectedGuild,sha256:button.dataset.retroApply,filename:button.dataset.retroFile,confirmNewMatch:completeMissing,requestKey:crypto.randomUUID()}});if(status)status.textContent="복구 작업을 요청했습니다.";setTimeout(loadRetroRoflActions,1500);}catch(error){if(status)status.textContent=error.message;button.disabled=false;}}
async function downloadRoflReport(build){if(!build)return;const status=document.getElementById("roflUploadStatus");try{if(status)status.textContent="진단 ZIP 준비 중...";const response=await fetch(apiUrl(`/api/community/admin/rofl-patch/report/${encodeURIComponent(build)}`),{credentials:"include"});if(!response.ok)throw new Error("진단 ZIP이 아직 준비되지 않았습니다.");const blob=await response.blob(),url=URL.createObjectURL(blob),link=document.createElement("a");link.href=url;link.download=(response.headers.get("Content-Disposition")||"").match(/filename="?([^";]+)"?/)?.[1]||`rofl_patch_${build}_codex.zip`;link.click();URL.revokeObjectURL(url);if(status)status.textContent="진단 ZIP을 다운로드했습니다.";}catch(error){if(status)status.textContent=error.message;}}
async function approveRoflWorkflow(build,action,message){if(!build||!confirm(message))return;const status=document.getElementById("roflUploadStatus");try{if(status)status.textContent="승인 기록 중...";await adminRequest(`/api/community/admin/rofl-patch/workflow/${encodeURIComponent(build)}/${action}`,{method:"POST"});if(status)status.textContent="승인되었습니다.";await loadRoflDashboard(build);}catch(error){if(status)status.textContent=error.message;}}
async function downloadRoflWorkflowArtifact(build,kind,part=1){const response=await fetch(apiUrl(`/api/community/admin/rofl-patch/workflow/${encodeURIComponent(build)}/${kind}?part=${encodeURIComponent(part)}`),{credentials:"include"});if(!response.ok)return alert("동결된 산출물을 찾지 못했습니다.");const blob=await response.blob(),url=URL.createObjectURL(blob),link=document.createElement("a");link.href=url;link.download=(response.headers.get("Content-Disposition")||"").match(/filename="?([^";]+)"?/)?.[1]||`${kind}-${build}`;link.click();URL.revokeObjectURL(url);}

async function loadReplayArchive(){const target=document.getElementById("replayArchiveList");if(!target)return;try{const data=await adminRequest("/api/community/admin/replays?limit=100"),rows=data.replays||[];target.innerHTML=rows.length?rows.map(row=>`<div><strong>경기 ${esc(row.matchId)}</strong><span>${esc(row.matchTime||row.uploadedAt||"시간 미상")} · ${esc(row.patch||"패치 미상")}</span><button class="admin-select-button" type="button" data-replay-download="${esc(row.id)}">다운로드</button></div>`).join(""):`<div class="admin-empty-admin"><strong>다운로드할 원본 ROFL이 없습니다.</strong></div>`;target.querySelectorAll("[data-replay-download]").forEach(button=>button.addEventListener("click",()=>downloadReplay(button.dataset.replayDownload)));}catch(error){target.innerHTML=`<div class="admin-empty-admin"><strong>리플레이를 불러오지 못했습니다.</strong><span>${esc(error.message)}</span></div>`;}}
async function downloadReplay(replayId){const response=await fetch(apiUrl(`/api/community/admin/replays/${encodeURIComponent(replayId)}`),{credentials:"include"});if(!response.ok)return alert("저장된 원본 파일을 찾지 못했습니다.");const blob=await response.blob(),url=URL.createObjectURL(blob),link=document.createElement("a");link.href=url;link.download=(response.headers.get("Content-Disposition")||"").match(/filename="?([^";]+)"?/)?.[1]||"lucid-replay.rofl";link.click();URL.revokeObjectURL(url);}

async function loadMissingDetails(){
  const target=document.getElementById("missingDetailsList");if(!target||!selectedGuild)return;
  const playerLine=player=>`<div class="missing-player ${player.detailSaved?"saved":"missing"}"><span><strong>${esc(player.name||"알 수 없음")}</strong><small>${esc(player.userId)}</small></span><span>${esc(player.role||"라인 미상")}</span><b>${player.detailSaved?"상세 저장":"상세 누락"}</b></div>`;
  try{const data=await adminRequest(`/api/community/admin/guilds/${encodeURIComponent(selectedGuild)}/missing-details${missingArchived?"?archived=1":""}`),rows=data.matches||[];target.innerHTML=rows.length?rows.map(row=>{const match=row.match||{},players=match.players||[],blue=players.filter(p=>p.team==="blue"),red=players.filter(p=>p.team==="red");return `<article class="missing-match-card"><header><div><strong>${esc(row.time||row.matchId)} · ${esc(row.mode)}</strong><small>경기 ID ${esc(row.matchId)} · ${row.savedCount}/10명 상세 저장 · 승리 ${esc(match.winner||row.winner||"-")}</small></div><button class="admin-select-button" ${missingArchived?`data-restore-missing="${esc(row.matchId)}"`:`data-archive-missing="${esc(row.matchId)}"`}>${missingArchived?"목록으로 복원":"보관함으로 이동"}</button></header><div class="missing-team-grid"><section><h4>BLUE TEAM</h4>${blue.map(playerLine).join("")||"팀 정보 없음"}</section><section><h4>RED TEAM</h4>${red.map(playerLine).join("")||"팀 정보 없음"}</section></div></article>`;}).join(""):`<div class="admin-empty-admin"><strong>${missingArchived?"보관된 누락 경기가 없습니다.":"누락된 상세스탯 경기가 없습니다."}</strong></div>`;target.querySelectorAll("[data-archive-missing]").forEach(button=>button.addEventListener("click",async()=>{if(!confirm("이 경기를 보관함으로 옮길까요?\n원본 경기와 MMR 기록은 삭제되지 않습니다."))return;await adminRequest(`/api/community/admin/guilds/${encodeURIComponent(selectedGuild)}/missing-details/${encodeURIComponent(button.dataset.archiveMissing)}`,{method:"DELETE",body:{reason:"관리자 누락 목록 정리"}});loadMissingDetails();}));target.querySelectorAll("[data-restore-missing]").forEach(button=>button.addEventListener("click",async()=>{await adminRequest(`/api/community/admin/guilds/${encodeURIComponent(selectedGuild)}/missing-details/${encodeURIComponent(button.dataset.restoreMissing)}`,{method:"PATCH"});loadMissingDetails();}));}catch(error){target.innerHTML=`<div class="admin-empty-admin"><strong>불러오지 못했습니다.</strong><span>${esc(error.message)}</span></div>`;}
}

async function loadOperationLogs(kind="chat"){
  const target=document.getElementById("operationLogList");if(!target||!selectedGuild)return;target.innerHTML=`<div class="admin-empty-admin"><strong>불러오는 중...</strong></div>`;
  const filters=document.getElementById("chatLogFilters"),params=new URLSearchParams();
  if(filters)filters.hidden=kind!=="chat";
  if(kind==="chat"&&filters){const form=new FormData(filters);for(const key of ["channel","user","content"]){const value=String(form.get(key)||"").trim();if(value)params.set(key,value);}}
  try{const data=await adminRequest(`/api/community/admin/guilds/${encodeURIComponent(selectedGuild)}/logs/${kind}${params.size?`?${params}`:""}`),rows=data.logs||[];if(kind==="chat"){const options=document.getElementById("chatChannelOptions"),channels=[...new Map(rows.map(row=>[row.channelId,row.channelName])).entries()];if(options)options.innerHTML=channels.map(([id,name])=>`<option value="${esc(name||id)}">${esc(id)}</option>`).join("");}target.innerHTML=rows.length?rows.map(row=>kind==="chat"?`<div class="admin-table-row admin-log-cols"><span>${esc(row.authorName)}<small>${esc(row.userId)}</small></span><span>${esc(row.content||"(첨부파일)")}</span><span>#${esc(row.channelName)}<small>${esc(row.channelId)}</small></span><span>${esc(row.createdAt)}</span></div>`:kind==="reports"?`<div class="admin-table-row admin-log-cols"><span>${esc(row.id)}<small>${esc(row.status)}</small></span><span><strong>${esc(row.target)}</strong><small>${esc(row.reason)}</small></span><span>${esc(row.createdAt)}</span><span>${row.status==="open"?`<button class="admin-select-button" data-report-action="${esc(row.id)}" data-status="processed">처리완료</button> <button class="admin-select-button" data-report-action="${esc(row.id)}" data-status="dismissed">잘못된 신고</button>`:"보관됨"}</span></div>`:kind==="moderation"?`<div class="admin-table-row admin-log-cols"><span><strong>${esc(row.target)}</strong><small>${esc(row.targetKey)}</small></span><span>${esc(row.note)}<small>신고 ${esc(row.reportId)}</small></span><span>이번 +${Number(row.warningDelta||0)} · 누적 ${Number(row.warningTotal||0)}</span><span>${esc(row.createdAt)}<small>관리자 ${esc(row.administratorId)}</small></span></div>`:`<div class="admin-table-row admin-log-cols"><span>${esc(row.userId)}<small>${esc(row.type)}</small></span><span>${esc(row.reason)}</span><span>${Number(row.amount)>0?"+":""}${Number(row.amount).toLocaleString()}P</span><span>${esc(row.createdAt)}<small>${esc(row.administratorId||"")}</small></span></div>`).join(""):`<div class="admin-empty-admin"><strong>표시할 로그가 없습니다.</strong></div>`;target.querySelectorAll("[data-report-action]").forEach(button=>button.addEventListener("click",async()=>{const reason=prompt(button.dataset.status==="dismissed"?"잘못된 신고로 보관하는 이유":"처리 메모를 입력해주세요","");if(reason===null||(!reason.trim()&&button.dataset.status==="processed"))return;let warningDelta=0;if(button.dataset.status==="processed"){const raw=prompt("이 처리로 추가할 경고 스택 수를 입력해주세요. 경고 없음은 0입니다.","0");if(raw===null)return;warningDelta=Number(raw);if(!Number.isInteger(warningDelta)||warningDelta<0||warningDelta>100){alert("경고 스택은 0~100 사이 정수로 입력해주세요.");return;}}await adminRequest(`/api/community/admin/guilds/${encodeURIComponent(selectedGuild)}/reports/${encodeURIComponent(button.dataset.reportAction)}`,{method:"DELETE",body:{status:button.dataset.status,reason,warningDelta}});loadOperationLogs("reports");}));}catch(error){target.innerHTML=`<div class="admin-empty-admin"><strong>불러오지 못했습니다.</strong><span>${esc(error.message)}</span></div>`;}
}

async function loadInquiries(status=""){
  const target=document.getElementById("adminInquiryList");if(!target)return;
  try{const data=await adminRequest(`/api/community/admin/inquiries${status?`?status=${status}`:""}`),rows=data.inquiries||[];target.innerHTML=rows.length?rows.map(row=>`<article class="admin-event-card"><div><small>${esc(row.status)} · ${esc(row.createdAt)}</small><h3>${esc(row.subject)}</h3><p>${esc(row.message)}</p><p>${esc(row.contact)}</p></div><div class="admin-event-actions"><button data-inquiry-id="${esc(row.id)}" data-inquiry-next="processing">처리중</button><button data-inquiry-id="${esc(row.id)}" data-inquiry-next="completed">완료</button></div></article>`).join(""):`<div class="admin-empty-admin"><strong>등록된 문의가 없습니다.</strong></div>`;target.querySelectorAll("[data-inquiry-id]").forEach(button=>button.addEventListener("click",async()=>{const note=prompt("관리 메모(선택)","");if(note===null)return;await adminRequest(`/api/community/admin/inquiries/${encodeURIComponent(button.dataset.inquiryId)}`,{method:"PATCH",body:{status:button.dataset.inquiryNext,note}});loadInquiries(status);}));}catch(error){target.innerHTML=`<div class="admin-empty-admin"><strong>불러오지 못했습니다.</strong><span>${esc(error.message)}</span></div>`;}
}

function renderSection(){
  const root=document.getElementById("communityAdminRoot");
  if(!root)return;
  if(!hasCommunityAdminAccess()){
    root.innerHTML=`<div class="admin-denied"><strong>관리자 권한이 필요합니다.</strong><span>커뮤니티 관리자에게만 보이는 페이지입니다.</span></div>`;
    return;
  }
  clearInterval(roflRefreshTimer);roflRefreshTimer=0;
  if(["retro","rofl"].includes(activeSection)&&!isCommunityAdmin())activeSection="dashboard";
  const pages={dashboard,members:memberPanel,server:serverPanel,titles:titlePanel,mileage:mileagePanel,riot:riotSyncPanel,events:eventsPanel,missing:missingPanel,retro:retroPanel,rofl:roflPanel,logs:logsPanel,data:dataPanel,support:supportPanel};
  root.innerHTML=(pages[activeSection]||dashboard)();
  root.querySelectorAll("[data-admin-section]").forEach(btn=>btn.addEventListener("click",()=>{
    const next=btn.dataset.adminSection||"dashboard";
    activeSection=next;
    renderSection();
  }));
  root.querySelector("#adminGuildSelect")?.addEventListener("change",event=>{selectedGuild=event.currentTarget.value;renderSection();});
  root.querySelectorAll("[data-server-tab]").forEach(btn=>btn.addEventListener("click",()=>{
    root.querySelectorAll("[data-server-tab]").forEach(item=>item.classList.toggle("active",item===btn));
    root.querySelectorAll("[data-server-panel]").forEach(panel=>panel.hidden=panel.dataset.serverPanel!==btn.dataset.serverTab);
  }));
  root.querySelector("#matchFrequencyForm")?.addEventListener("submit",event=>{event.preventDefault();const form=new FormData(event.currentTarget);enqueueServerAction("set_match_frequency",{value:form.get("value")});});
  root.querySelector("#generalQueueCreateForm")?.addEventListener("submit",event=>{event.preventDefault();const form=new FormData(event.currentTarget);enqueueServerAction("create_general_queue",{bestOf:Number(form.get("bestOf"))});});
  root.querySelector("#serverChannelForm")?.addEventListener("submit",event=>{event.preventDefault();const form=new FormData(event.currentTarget);enqueueServerAction("set_channel",{key:form.get("key"),channelId:form.get("channelId")});});
  root.querySelector("#adminRoleForm")?.addEventListener("submit",event=>{event.preventDefault();const form=new FormData(event.currentTarget);enqueueServerAction("set_admin_role",{roleId:form.get("roleId")});});
  root.querySelectorAll(".admin-subtabs button").forEach(btn=>btn.addEventListener("click",()=>{
    btn.parentElement?.querySelectorAll("button").forEach(item=>item.classList.toggle("active",item===btn));
    const feedback=root.querySelector(".admin-tab-feedback");
    if(feedback&&btn.dataset.tabMessage)feedback.textContent=btn.dataset.tabMessage;
  }));
  const openShopEditor=(mode="create")=>{
    const backdrop=document.getElementById("shopEditorBackdrop");
    const title=document.getElementById("shopEditorTitle");
    if(title) title.textContent=mode==="edit"?"상품 수정":"상품 등록";
    if(backdrop) backdrop.hidden=false;
  };
  root.querySelector("#shopCreateBtn")?.addEventListener("click",()=>openShopEditor("create"));
  root.querySelectorAll('[data-shop-action="edit"]').forEach(btn=>btn.addEventListener("click",()=>openShopEditor("edit")));
  const closeShopEditor=()=>{const backdrop=document.getElementById("shopEditorBackdrop");if(backdrop)backdrop.hidden=true;};
  root.querySelector("#shopEditorClose")?.addEventListener("click",closeShopEditor);
  root.querySelector("#shopEditorCancel")?.addEventListener("click",closeShopEditor);
  root.querySelector("#shopEditorSave")?.addEventListener("click",()=>{
    closeShopEditor();
    alert("현재는 UI 초안입니다. 다음 단계에서 실제 상점 DB/API 저장 기능을 연결하면 됩니다.");
  });
  root.querySelector("#shopEditorBackdrop")?.addEventListener("click",e=>{if(e.target===e.currentTarget)closeShopEditor();});

  if(activeSection==="members"){loadMembers();root.querySelector("#memberRefresh")?.addEventListener("click",loadMembers);root.querySelector("#memberSearch")?.addEventListener("input",renderMemberRows);}
  if(activeSection==="mileage")renderMileage({rootId:"adminMileageRoot",initialGuild:selectedGuild,managersOnly:true,showAdmin:true});
  if(activeSection==="riot"){loadRiotSyncStatus();root.querySelector("#riotSyncRefresh")?.addEventListener("click",loadRiotSyncStatus);}
  if(activeSection==="server")loadServerSettings();
  if(activeSection==="titles"){loadTitleCatalog();root.querySelector("#titleSearch")?.addEventListener("input",renderTitleCatalog);root.querySelector("#titleCategory")?.addEventListener("change",renderTitleCatalog);root.querySelector("#levelIconForm")?.addEventListener("submit",async event=>{event.preventDefault();const status=root.querySelector("#levelIconStatus");try{if(status)status.textContent="업로드 중...";const data=await adminRequest(`/api/community/admin/guilds/${encodeURIComponent(selectedGuild)}/level-icon`,{method:"POST",body:new FormData(event.currentTarget)});levelIconState=data.levelIcon;renderLevelIcon();event.currentTarget.reset();}catch(error){if(status)status.textContent=error.message;}});}
  if(activeSection==="missing"){
    loadMissingDetails();
    root.querySelector("#missingRefresh")?.addEventListener("click",loadMissingDetails);
    root.querySelectorAll("[data-missing-archived]").forEach(button=>button.addEventListener("click",()=>{missingArchived=button.dataset.missingArchived==="1";renderSection();}));
  }
  if(activeSection==="rofl"){
    loadRoflDashboard();
    loadReplayArchive();
    const input=root.querySelector("#roflInput"),drop=root.querySelector("#roflDropzone");
    root.querySelector("#roflPick")?.addEventListener("click",()=>input?.click());
    input?.addEventListener("change",()=>setRoflFiles(input.files||[]));
    for(const eventName of ["dragenter","dragover"])drop?.addEventListener(eventName,event=>{event.preventDefault();drop.classList.add("dragging");});
    for(const eventName of ["dragleave","drop"])drop?.addEventListener(eventName,event=>{event.preventDefault();drop.classList.remove("dragging");if(eventName==="drop")setRoflFiles(event.dataTransfer?.files||[]);});
    root.querySelector("#roflAnalyze")?.addEventListener("click",uploadRoflFiles);
    root.querySelector("#roflRefresh")?.addEventListener("click",()=>loadRoflDashboard());
    root.querySelector("#replayArchiveRefresh")?.addEventListener("click",loadReplayArchive);
    roflRefreshTimer=setInterval(()=>{if(activeSection==="rofl"&&document.getElementById("adminView")?.classList.contains("active"))loadRoflDashboard();},15000);
  }
  if(activeSection==="retro"){
    loadRetroRoflActions();
    const retroInput=root.querySelector("#retroRoflInput"),retroDrop=root.querySelector("#retroRoflDropzone");
    root.querySelector("#retroRoflPick")?.addEventListener("click",()=>retroInput?.click());
    retroInput?.addEventListener("change",()=>setRetroRoflFiles(retroInput.files||[]));
    for(const eventName of ["dragenter","dragover"])retroDrop?.addEventListener(eventName,event=>{event.preventDefault();retroDrop.classList.add("dragging");});
    for(const eventName of ["dragleave","drop"])retroDrop?.addEventListener(eventName,event=>{event.preventDefault();retroDrop.classList.remove("dragging");if(eventName==="drop")setRetroRoflFiles(event.dataTransfer?.files||[]);});
    root.querySelector("#retroRoflAnalyze")?.addEventListener("click",uploadRetroRoflFiles);
    root.querySelector("#retroRoflRefresh")?.addEventListener("click",loadRetroRoflActions);
    roflRefreshTimer=setInterval(()=>{if(activeSection==="retro"&&document.getElementById("adminView")?.classList.contains("active"))loadRetroRoflActions();},15000);
  }
  if(activeSection==="logs"){
    loadOperationLogs("chat");
    root.querySelectorAll("[data-log-kind]").forEach(button=>button.addEventListener("click",()=>{
      root.querySelectorAll("[data-log-kind]").forEach(item=>item.classList.toggle("active",item===button));
      loadOperationLogs(button.dataset.logKind);
    }));
    root.querySelector("#chatLogFilters")?.addEventListener("submit",event=>{event.preventDefault();loadOperationLogs("chat");});
    root.querySelector("#chatLogFilters")?.addEventListener("reset",()=>setTimeout(()=>loadOperationLogs("chat"),0));
  }
  if(activeSection==="support"){
    loadInquiries("");
    root.querySelectorAll("[data-inquiry-status]").forEach(button=>button.addEventListener("click",()=>{
      root.querySelectorAll("[data-inquiry-status]").forEach(item=>item.classList.toggle("active",item===button));
      loadInquiries(button.dataset.inquiryStatus);
    }));
  }

}

// 서버 관리 화면은 사이트 역할명이 아니라 Discord에서 봇이 검증한 길드 관리자만 연다.
export function hasCommunityAdminAccess(){return Boolean(getCurrentUser()&&(isCommunityAdmin()||guildAdminAccess));}

export async function syncAdminAccess(){
  if(!getCurrentUser()){adminGuilds=[];guildAdminAccess=false;guildsLoaded=false;}
  else if(!guildsLoaded){guildsLoaded=true;await loadAdminGuilds();}
  const nav=document.getElementById("communityAdminNav");
  if(nav)nav.hidden=!hasCommunityAdminAccess();
  if(!hasCommunityAdminAccess() && document.getElementById("adminView")?.classList.contains("active")){
    window.history.replaceState({view:"recent"},"",window.location.pathname);
    window.dispatchEvent(new CustomEvent("lucid:admin-denied"));
  }
}

export function renderCommunityAdmin({home=false}={}){
  if(home)activeSection="dashboard";
  activeSection=activeSection||"dashboard";
  renderSection();
  if(!guildsLoaded){
    guildsLoaded=true;
    loadAdminGuilds().then(renderSection);
  }
}
