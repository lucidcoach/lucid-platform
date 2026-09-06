
import { getCurrentUser, isCommunityAdmin } from "../auth.js?v=20260905admin2";
import { API_BASE_URL } from "../config.js?v=20260904d";
import { renderMileage } from "./mileage.js?v=20260906ops2";

const esc=(value)=>String(value??"").replace(/[&<>"']/g,ch=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[ch]));
let activeSection="dashboard";
let adminGuilds=[];
let selectedGuild="";
let guildsLoaded=false;
let guildAdminAccess=false;
const apiUrl=path=>`${API_BASE_URL.replace(/\/$/,"")}${path}`;
async function adminRequest(path,{method="GET",body}={}){const response=await fetch(apiUrl(path),{method,credentials:"include",headers:body?{"Content-Type":"application/json"}:{},body:body?JSON.stringify(body):undefined});const data=await response.json().catch(()=>({}));if(!response.ok||!data.ok)throw new Error(data.error||"요청에 실패했습니다.");return data;}

const sections = [
  ["server","서버 설정","서버별 내전·채널·권한 설정","⚙"],
  ["mileage","마일리지 관리","지급 규칙·상점·주문·감사로그","M"],
  ["events","이벤트","진행 이벤트·랭킹·보상","★"],
  ["missing","상세스탯 누락","누락된 경기 확인·목록 정리","⌕"],
  ["logs","운영 로그","채팅·관리자 작업·신고·마일리지 로그","≡"],
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

function mileagePanel(){
  return shell(`
    ${panelTitle("마일리지 관리","실제 지급 설정·상점·주문·환불·감사로그를 한 화면에서 관리합니다.")}
    <div id="adminMileageRoot"></div>
  `);
}

function shopPanel(){
  return shell(`
    ${panelTitle("상점 관리","마일리지로 구매할 상품과 주문을 관리합니다.")}
    <div class="shop-admin-grid">
      <section class="admin-work-panel shop-products-panel">
        <div class="admin-toolbar">
          <div class="admin-subtabs">
            <button class="active" data-shop-tab="products" data-tab-message="상품 목록입니다.">상품</button>
            <button data-shop-tab="orders" data-tab-message="구매 처리와 환불은 실제 마일리지 관리 화면에서 처리합니다.">주문</button>
            <button data-shop-tab="settings" data-tab-message="상점 사용 여부와 상품 설정은 실제 마일리지 관리 화면에서 처리합니다.">상점 설정</button>
          </div>
          <button class="admin-primary" id="shopCreateBtn">+ 상품 등록</button>
        </div>

        <div class="shop-summary-row">
          <article><span>판매중 상품</span><strong>3</strong></article>
          <article><span>오늘 주문</span><strong>7</strong></article>
          <article><span>처리 대기</span><strong>2</strong></article>
          <article><span>오늘 사용 마일리지</span><strong>4,300 P</strong></article>
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
        <div class="shop-balance-card"><span>내 마일리지</span><strong>1,420 P</strong></div>
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
      <div class="admin-toolbar"><p class="admin-tab-feedback">상세스탯이 10명 미만 저장된 경기를 표시합니다.</p><button id="missingRefresh" class="admin-primary">새로고침</button></div>
      <div id="missingDetailsList" class="admin-table"><div class="admin-empty-admin"><strong>불러오는 중...</strong></div></div>
      <div class="admin-draft-note">삭제는 경기/MMR을 지우지 않고 누락 관리 목록에서 보관 처리합니다. 원본 경기기록을 직접 지우면 봇 메모리와 충돌할 수 있어 안전하게 분리했습니다.</div>
    </section>
  `);
}

function logsPanel(){
  return shell(`
    ${panelTitle("운영 로그","채팅로그를 포함해 관리자 작업과 주요 변경 이력을 모읍니다.")}
    <section class="admin-work-panel">
      <div class="admin-subtabs"><button class="active" data-log-kind="chat">채팅</button><button data-log-kind="mileage">마일리지 감사</button><button data-log-kind="reports">신고</button></div>
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
        ${["유저 데이터","경기 기록","전적","마일리지","서버 설정","운영 로그"].map((x,i)=>`<label><input type="checkbox" ${i<5?"checked":""}><span>${x}</span></label>`).join("")}
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
  try{const data=await adminRequest(`/api/community/admin/guilds/${encodeURIComponent(selectedGuild)}/missing-details`),rows=data.matches||[];target.innerHTML=rows.length?`<div class="admin-table-head admin-log-cols"><span>경기</span><span>누락 인원</span><span>저장 상태</span><span>관리</span></div>${rows.map(row=>`<div class="admin-table-row admin-log-cols"><span><strong>${esc(row.time||row.matchId)}</strong><small>${esc(row.matchId)}</small></span><span>${esc((row.missingPlayers||[]).join(", ")||"확인 필요")}</span><span>${row.savedCount}/10명</span><button class="admin-select-button" data-archive-missing="${esc(row.matchId)}">삭제(보관)</button></div>`).join("")}`:`<div class="admin-empty-admin"><strong>누락된 상세스탯 경기가 없습니다.</strong></div>`;target.querySelectorAll("[data-archive-missing]").forEach(button=>button.addEventListener("click",async()=>{if(!confirm("이 경기를 누락 관리 목록에서 삭제하고 보관 처리할까요?\n기본 경기/MMR 기록은 유지됩니다."))return;await adminRequest(`/api/community/admin/guilds/${encodeURIComponent(selectedGuild)}/missing-details/${encodeURIComponent(button.dataset.archiveMissing)}`,{method:"DELETE",body:{reason:"관리자 누락 목록 정리"}});loadMissingDetails();}));}catch(error){target.innerHTML=`<div class="admin-empty-admin"><strong>불러오지 못했습니다.</strong><span>${esc(error.message)}</span></div>`;}
}

async function loadOperationLogs(kind="chat"){
  const target=document.getElementById("operationLogList");if(!target||!selectedGuild)return;target.innerHTML=`<div class="admin-empty-admin"><strong>불러오는 중...</strong></div>`;
  try{const data=await adminRequest(`/api/community/admin/guilds/${encodeURIComponent(selectedGuild)}/logs/${kind}`),rows=data.logs||[];target.innerHTML=rows.length?rows.map(row=>kind==="chat"?`<div class="admin-table-row admin-log-cols"><span>${esc(row.authorName)}<small>${esc(row.userId)}</small></span><span>${esc(row.content||"(첨부파일)")}</span><span>#${esc(row.channelName)}</span><span>${esc(row.createdAt)}</span></div>`:kind==="reports"?`<div class="admin-table-row admin-log-cols"><span>${esc(row.id)}<small>${esc(row.status)}</small></span><span><strong>${esc(row.target)}</strong><small>${esc(row.reason)}</small></span><span>${esc(row.createdAt)}</span><span>${row.status==="open"?`<button class="admin-select-button" data-report-action="${esc(row.id)}" data-status="processed">처리완료</button> <button class="admin-select-button" data-report-action="${esc(row.id)}" data-status="dismissed">잘못된 신고</button>`:"보관됨"}</span></div>`:`<div class="admin-table-row admin-log-cols"><span>${esc(row.userId)}<small>${esc(row.type)}</small></span><span>${esc(row.reason)}</span><span>${Number(row.amount)>0?"+":""}${Number(row.amount).toLocaleString()}P</span><span>${esc(row.createdAt)}<small>${esc(row.administratorId||"")}</small></span></div>`).join(""):`<div class="admin-empty-admin"><strong>표시할 로그가 없습니다.</strong></div>`;target.querySelectorAll("[data-report-action]").forEach(button=>button.addEventListener("click",async()=>{const reason=prompt(button.dataset.status==="dismissed"?"잘못된 신고로 보관하는 이유":"처리 내용을 남겨주세요","");if(reason===null)return;await adminRequest(`/api/community/admin/guilds/${encodeURIComponent(selectedGuild)}/reports/${encodeURIComponent(button.dataset.reportAction)}`,{method:"DELETE",body:{status:button.dataset.status,reason}});loadOperationLogs("reports");}));}catch(error){target.innerHTML=`<div class="admin-empty-admin"><strong>불러오지 못했습니다.</strong><span>${esc(error.message)}</span></div>`;}
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
  const pages={dashboard,server:serverPanel,mileage:mileagePanel,events:eventsPanel,missing:missingPanel,logs:logsPanel,data:dataPanel,support:supportPanel};
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

  if(activeSection==="mileage")renderMileage({rootId:"adminMileageRoot",initialGuild:selectedGuild,managersOnly:true,showAdmin:true});
  if(activeSection==="server")loadServerSettings();
  if(activeSection==="missing"){
    loadMissingDetails();
    root.querySelector("#missingRefresh")?.addEventListener("click",loadMissingDetails);
  }
  if(activeSection==="logs"){
    loadOperationLogs("chat");
    root.querySelectorAll("[data-log-kind]").forEach(button=>button.addEventListener("click",()=>{
      root.querySelectorAll("[data-log-kind]").forEach(item=>item.classList.toggle("active",item===button));
      loadOperationLogs(button.dataset.logKind);
    }));
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
export function hasCommunityAdminAccess(){return Boolean(getCurrentUser()&&guildAdminAccess);}

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
