
import { getCurrentUser, getResolvedAnalysisPlayers, isCommunityAdmin } from "../auth.js?v=20260905admin2";

const esc=(value)=>String(value??"").replace(/[&<>"']/g,ch=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[ch]));
let activeSection="dashboard";

const sections = [
  ["server","서버 설정","서버별 내전·채널·권한 설정","⚙"],
  ["mileage","마일리지","지급 규칙·거래내역·수동 조정","M"],
  ["shop","상점","상품·주문·상점 운영","▣"],
  ["events","이벤트","진행 이벤트·랭킹·보상","★"],
  ["users","유저 탐색","코치/분석 권한용 유저 분석","⌕"],
  ["logs","운영 로그","채팅·관리자 작업·신고·마일리지 로그","≡"],
  ["data","데이터 관리","서버 데이터 내보내기","⇩"],
  ["support","문의 관리","커뮤니티/봇 문의 처리","?"],
];

function uniqueGuilds(){
  const rows=getResolvedAnalysisPlayers?.()||[];
  const seen=new Set();
  return rows.filter(row=>{
    const key=String(row.guildId||"");
    if(!key||seen.has(key))return false;
    seen.add(key); return true;
  }).map(row=>({id:String(row.guildId),name:row.guildName||row.serverName||`서버 ${row.guildId}`}));
}

function shell(content){
  const user=getCurrentUser();
  const guilds=uniqueGuilds();
  const guildOptions=guilds.length
    ? guilds.map(g=>`<option value="${esc(g.id)}">${esc(g.name)}</option>`).join("")
    : `<option value="">현재 커뮤니티 서버</option>`;
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
      ${sections.map(([id,title,desc,icon])=>`
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
  return shell(`
    ${panelTitle("서버 설정","기존 Discord 설정을 서버 단위로 정리하는 영역입니다.")}
    <div class="admin-layout">
      <nav class="admin-side-tabs">
        <button class="active">기본 설정</button><button>내전 설정</button><button>채널 설정</button><button>권한</button>
      </nav>
      <section class="admin-work-panel">
        <div class="admin-form-section"><h3>내전 운영</h3>
          <div class="admin-setting-row"><div><strong>내전 빈도</strong><small>MMR 변동 규칙에 사용할 서버 운영 빈도</small></div><select><option>보통</option><option>낮음</option><option>높음</option></select></div>
          <div class="admin-setting-row"><div><strong>큐 진행 시간</strong><small>큐가 열린 뒤 자동 진행에 사용하는 시간</small></div><div class="admin-inline-input"><input value="10"><span>분</span></div></div>
        </div>
        <div class="admin-form-section"><h3>채널 설정</h3>
          <div class="admin-setting-row"><div><strong>일반 채널</strong></div><button class="admin-select-button"># 일반</button></div>
          <div class="admin-setting-row"><div><strong>내전 채널</strong></div><button class="admin-select-button"># 내전</button></div>
          <div class="admin-setting-row"><div><strong>도움말 채널</strong><small>/가이드설정 → /채널설정 도움말 통합 예정</small></div><button class="admin-select-button"># 도움말</button></div>
        </div>
        <div class="admin-draft-note">UI 설계 단계 · 저장 동작은 기존 서버 설정 API 연결 시 활성화</div>
      </section>
    </div>
  `);
}

function mileagePanel(){
  return shell(`
    ${panelTitle("마일리지","서버별 포인트 경제를 설정하고 추적합니다.")}
    <div class="admin-stat-grid">
      <article><span>총 유통량</span><strong>— P</strong><small>DB 연동 후 표시</small></article>
      <article><span>최근 7일 지급</span><strong>+ — P</strong><small>적립 총액</small></article>
      <article><span>최근 7일 사용</span><strong>- — P</strong><small>상점 소비</small></article>
      <article><span>활동 유저</span><strong>— 명</strong><small>최근 7일</small></article>
    </div>
    <section class="admin-work-panel">
      <div class="admin-subtabs"><button class="active">지급 설정</button><button>거래내역</button><button>수동 조정</button><button>경제 현황</button></div>
      ${[
        ["내전 정상 완료","경기 정상 종료 시 지급","20 P",true],
        ["승리 보너스","승리팀에 추가 지급","5 P",true],
        ["음성채널 활동","30분당 지급 · 일일 상한 설정","5 P / 30분",true],
        ["주간 활동 퀘스트","주간 조건 완료 시 지급","설정",true],
        ["이벤트 / 리그 참가","실제 참가 확정 시 지급","설정",true],
        ["친구 초대","초대 유저 실제 활동 조건 달성 시 지급","설정",false],
        ["운영진 기여 보상","관리자가 사유와 함께 수동 지급","수동",true],
      ].map(([name,desc,value,on])=>`
        <div class="admin-setting-row">
          <div><strong>${name}</strong><small>${desc}</small></div>
          <div class="admin-setting-actions"><span>${value}</span><i class="admin-toggle ${on?"on":""}"></i></div>
        </div>`).join("")}
      <div class="admin-economy-hint"><strong>운영 가이드</strong><span>일/주간 획득 상한과 예상 주간 획득량을 함께 표시하는 구조를 권장합니다.</span></div>
    </section>
  `);
}

function shopPanel(){
  return shell(`
    ${panelTitle("상점 관리","마일리지로 구매할 상품과 주문을 관리합니다.")}
    <div class="shop-admin-grid">
      <section class="admin-work-panel shop-products-panel">
        <div class="admin-toolbar">
          <div class="admin-subtabs">
            <button class="active" data-shop-tab="products">상품</button>
            <button data-shop-tab="orders">주문</button>
            <button data-shop-tab="settings">상점 설정</button>
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
      <div class="admin-toolbar"><div class="admin-subtabs"><button class="active">진행중</button><button>종료</button></div><button class="admin-primary">+ 이벤트</button></div>
      <article class="admin-event-card"><div><small>진행중</small><h3>9월 내전왕</h3><p>2026.09.01 ~ 09.30 · 참가자/점수/순위를 한 화면에서 관리</p></div><div class="admin-event-actions"><button>상세</button><button>수정</button><button>종료</button></div></article>
    </section>
  `);
}

function usersPanel(){
  return shell(`
    ${panelTitle("유저 탐색","코치/분석 권한자가 조건별 유저를 찾는 관리 도구입니다.")}
    <section class="admin-work-panel">
      <div class="admin-filter-grid"><label>티어<select><option>전체</option><option>골드</option><option>플래티넘</option></select></label><label>포지션<select><option>전체</option><option>정글</option><option>미드</option></select></label><label>챔피언<input placeholder="챔피언 검색"></label><label>최소 판수<input value="10"></label><button class="admin-primary">검색</button></div>
      <div class="admin-empty-admin"><strong>분석 조건을 선택하세요.</strong><span>저평가 후보, 성장 유저, 지표 우수/취약 유저를 이 영역에 표시합니다.</span></div>
    </section>
  `);
}

function logsPanel(){
  return shell(`
    ${panelTitle("운영 로그","채팅로그를 포함해 관리자 작업과 주요 변경 이력을 모읍니다.")}
    <section class="admin-work-panel">
      <div class="admin-subtabs"><button class="active">채팅</button><button>관리자 작업</button><button>마일리지</button><button>신고</button></div>
      <div class="admin-table">
        <div class="admin-table-head admin-log-cols"><span>유저/관리자</span><span>내용</span><span>위치</span><span>시간</span></div>
        <div class="admin-empty-admin"><strong>운영 로그 API 연결 대기</strong><span>/채팅로그 기능은 이 화면으로 이관할 예정입니다.</span></div>
      </div>
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
      <div class="admin-subtabs"><button class="active">전체</button><button>미처리</button><button>처리중</button><button>완료</button></div>
      <div class="admin-empty-admin"><strong>아직 등록된 문의가 없습니다.</strong><span>커뮤니티/봇 문의가 접수되면 이곳에서 처리 상태를 관리합니다.</span></div>
    </section>
  `);
}

function renderSection(){
  const root=document.getElementById("communityAdminRoot");
  if(!root)return;
  if(!isCommunityAdmin()){
    root.innerHTML=`<div class="admin-denied"><strong>관리자 권한이 필요합니다.</strong><span>커뮤니티 관리자에게만 보이는 페이지입니다.</span></div>`;
    return;
  }
  const pages={dashboard,server:serverPanel,mileage:mileagePanel,shop:shopPanel,events:eventsPanel,users:usersPanel,logs:logsPanel,data:dataPanel,support:supportPanel};
  root.innerHTML=(pages[activeSection]||dashboard)();
  root.querySelectorAll("[data-admin-section]").forEach(btn=>btn.addEventListener("click",()=>{
    activeSection=btn.dataset.adminSection||"dashboard";
    renderSection();
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

}

export function syncAdminAccess(){
  const nav=document.getElementById("communityAdminNav");
  if(nav)nav.hidden=!isCommunityAdmin();
  if(!isCommunityAdmin() && document.getElementById("adminView")?.classList.contains("active")){
    window.history.replaceState({view:"recent"},"",window.location.pathname);
    window.dispatchEvent(new CustomEvent("lucid:admin-denied"));
  }
}

export function renderCommunityAdmin(){
  activeSection=activeSection||"dashboard";
  renderSection();
}
