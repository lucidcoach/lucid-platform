
import { getCurrentUser, isCommunityAdmin } from "../auth.js?v=20260907oauth1";
import { API_BASE_URL } from "../config.js?v=20260904d";
import { renderMileage } from "./mileage.js?v=20260906ops2";

const esc=(value)=>String(value??"").replace(/[&<>"']/g,ch=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[ch]));
let activeSection="dashboard";
let adminGuilds=[];
let selectedGuild="";
let guildsLoaded=false;
let guildAdminAccess=false;
let missingArchived=false;
const apiUrl=path=>`${API_BASE_URL.replace(/\/$/,"")}${path}`;
async function adminRequest(path,{method="GET",body}={}){const response=await fetch(apiUrl(path),{method,credentials:"include",headers:body?{"Content-Type":"application/json"}:{},body:body?JSON.stringify(body):undefined});const data=await response.json().catch(()=>({}));if(!response.ok||!data.ok)throw new Error(data.error||"요청에 실패했습니다.");return data;}

const sections = [
  ["members","회원 관리","가입 회원·권한·Discord 연결 상태 확인","U"],
  ["server","서버 설정","서버별 내전·채널·권한 설정","⚙"],
  ["mileage","포인트 관리","지급 규칙·상점·주문·감사로그","M"],
  ["events","이벤트","진행 이벤트·랭킹·보상","★"],
  ["missing","상세스탯 누락","누락된 경기 확인·목록 정리","⌕"],
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
      ${sections.filter(([id])=>isCommunityAdmin()||!["data","support"].includes(id)).map(([id,title,desc,icon])=>`
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
          <div class="admin-form-section"><h3>내전 설정</h3><form id="matchFrequencyForm" class="mileage-form"><label class="wide">내전 빈도<select name="value"><option>적음</option><option>보통</option><option>많음</option></select></label><button class="wide" type="submit">변경 요청</button></form><div class="admin-setting-row"><div><strong>큐 운영</strong><small>예약시간과 자동 팀 구성은 실시간 큐 상태가 필요하므로 Discord 큐 패널에서 관리합니다.</small></div></div></div>
        </div>
        <div data-server-panel="channels" hidden><div class="admin-form-section"><h3>채널 설정</h3><form id="serverChannelForm" class="mileage-form"><label>기능<select name="key"><option value="announcement">공지사항</option><option value="patchnote">패치노트</option><option value="match_output">내전 출력</option><option value="report">신고 접수</option><option value="league_output">리그전 출력</option></select></label><label>Discord 채널 ID<input name="channelId" required inputmode="numeric" pattern="[0-9]+"></label><button class="wide" type="submit">변경 요청</button></form><div class="admin-draft-note">참가·기록·도움말처럼 패널 메시지를 다시 만들어야 하는 채널은 현재 Discord /채널설정을 사용해주세요.</div></div></div>
        <div data-server-panel="permissions" hidden><div class="admin-form-section"><h3>내전 관리자 역할</h3><form id="adminRoleForm" class="mileage-form"><label class="wide">Discord 역할 ID<input name="roleId" required inputmode="numeric" pattern="[0-9]+"></label><button class="wide" type="submit">변경 요청</button></form><div class="admin-setting-row"><div><strong>홈페이지 관리 권한</strong><small>Discord 관리자·서버 관리 권한·내전 관리자 역할을 봇이 주기적으로 확인합니다.</small></div></div></div></div>
        <p id="serverActionStatus" class="mileage-status"></p>
      </section>
    </div>
  `);
}

const actionLabels={set_match_frequency:"내전 빈도",set_channel:"채널 설정",set_admin_role:"관리자 역할"};
const statusLabels={pending:"대기",processing:"적용 중",completed:"완료",failed:"실패"};
async function loadServerSettings(){
  if(!selectedGuild)return;
  try{
    const data=await adminRequest(`/api/community/admin/guilds/${encodeURIComponent(selectedGuild)}/settings`),settings=data.settings||{};
    const frequency=document.querySelector('#matchFrequencyForm [name="value"]');if(frequency)frequency.value=settings.matchFrequency||"보통";
    const role=document.querySelector('#adminRoleForm [name="roleId"]');if(role)role.value=settings.adminRoleId||"";
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
  const pages={dashboard,members:memberPanel,server:serverPanel,mileage:mileagePanel,events:eventsPanel,missing:missingPanel,logs:logsPanel,data:dataPanel,support:supportPanel};
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
  if(activeSection==="server")loadServerSettings();
  if(activeSection==="missing"){
    loadMissingDetails();
    root.querySelector("#missingRefresh")?.addEventListener("click",loadMissingDetails);
    root.querySelectorAll("[data-missing-archived]").forEach(button=>button.addEventListener("click",()=>{missingArchived=button.dataset.missingArchived==="1";renderSection();}));
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
