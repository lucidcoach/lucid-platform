import {
  ADMIN_TOKEN_KEY,
  API_BASE_URL,
  EMAIL_MAX_LENGTH,
  PASSWORD_MAX_LENGTH,
  PASSWORD_MIN_LENGTH,
  THEME_KEY,
} from "../config.js";
import { state, text } from "../catalog.js";
import {
  deleteCurrentUser as deleteCurrentUserApi,
  fetchCurrentUser,
  loginUser,
  logoutAuthSessions,
  signupUser,
  updateCurrentUser,
  userIsAdmin,
  userIsCoach,
  userRoles,
} from "../auth.js";
import { loginAdmin } from "../admin.js";
import { paymentStatus, submitGuestConsultation } from "../reservations.js";
import { byId as $, escapeHtml, formatDateTime, formatWon, parseReservationPrice } from "../utils.js";

export function createAuthAccountPage({
  render: renderApp,
  loadCoachProfile,
  handlePaymentReturn,
  renderScheduleSummaryMarkup,
}) {
function showOAuthResult() {
  const url = new URL(window.location.href);
  const error = url.searchParams.get("oauth_error");
  const success = url.searchParams.get("oauth") === "success";
  if (!error && !success) return;
  url.searchParams.delete("oauth");
  url.searchParams.delete("oauth_error");
  history.replaceState({}, "", `${url.pathname}${url.search}${url.hash}`);
  if (error) {
    openAuthModal("login");
    const messages = {
      account_link_required: "같은 이메일의 기존 계정이 있습니다. 기존 방식으로 로그인해 주세요.",
      discord_already_linked: "이 사이트 계정 또는 Discord 계정은 이미 연결되어 있습니다.",
      login_required: "기존 계정으로 다시 로그인한 뒤 Discord를 연결해 주세요.",
      oauth_cancelled: "소셜 로그인이 취소되었습니다.",
      invalid_oauth_state: "로그인 요청이 만료되었습니다. 다시 시도해 주세요.",
    };
    const status = $("authStatus");
    if (status) status.textContent = messages[error] || "소셜 로그인에 실패했습니다. 다시 시도해 주세요.";
  }
}

function hasCoachMenuAccess() {
  return Boolean(state.currentUser);
}

function getUserRoles(user = state.currentUser) {
  return userRoles(user);
}

function isAdminUser(user = state.currentUser) {
  return userIsAdmin(user);
}

function isCoachUser(user = state.currentUser) {
  return userIsCoach(user);
}

function getFallbackCoachKey(user = state.currentUser) {
  if (!user) return "";
  const knownKey = getKnownCoachKeyForUser(user);
  if (user.coachKey || knownKey) return user.coachKey || knownKey;
  return String(user.displayName || user.email || "")
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9가-힣]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

function getKnownCoachKeyForUser(user = state.currentUser) {
  const name = String(user?.displayName || "").toLowerCase();
  if (name.includes("샤이니스트") || name.includes("shineast")) return "shineast";
  if (name.includes("메피") || name.includes("mephi")) return "mephi";
  if (name.includes("정미르") || name.includes("미르") || name.includes("mireu")) return "mireu";
  if (name.includes("페르소나") || name.includes("persona")) return "persona";
  return "";
}

function hasCoachLikeAccount() {
  return isAdminUser() || isCoachUser() || Boolean(getKnownCoachKeyForUser());
}

function renderRoleMenu() {
  const menu = $("sideRoleMenu");
  if (!menu) return;
  if (!hasCoachMenuAccess() || isAdminUser()) {
    menu.hidden = true;
    menu.innerHTML = "";
    return;
  }
  const canManageLessons = hasCoachLikeAccount();
  menu.hidden = false;
  menu.innerHTML = `
    <span class="label">${canManageLessons ? "코치 메뉴" : "계정 메뉴"}</span>
    ${canManageLessons ? `<button class="role-menu-button ${state.activeView === "coachSelf" ? "active" : ""}" id="openCoachSelfMenuBtn" type="button">코치센터</button>` : ""}
    ${!isAdminUser() && !isCoachUser() ? `<button class="role-menu-button ${state.activeView === "coachApply" ? "active" : ""}" id="openCoachApplyMenuBtn" type="button">코치 등록 요청</button>` : ""}
  `;
  $("openCoachSelfMenuBtn")?.addEventListener("click", () => {
    if (!isAdminUser()) state.coachSelfKey = getFallbackCoachKey();
    state.activeView = "coachSelf";
    renderApp();
  });
  $("openCoachApplyMenuBtn")?.addEventListener("click", () => {
    state.activeView = "coachApply";
    renderApp();
  });
}

function renderUserActions() {
  const loginButton = $("loginOpenBtn");
  const guestButton = $("guestBuyOpenBtn");
  const discordButton = $("discordConnectBtn");
  const adminMenu = document.querySelector(".admin-menu");
  if (adminMenu) {
    adminMenu.hidden = !isAdminUser();
    if (adminMenu.hidden) adminMenu.removeAttribute("open");
  }
  if (!loginButton || !guestButton) return;
  if (state.currentUser) {
    const accountRole = isAdminUser() ? "관리자" : (isCoachUser() ? "코치" : "수강생");
    loginButton.textContent = `${accountRole} · ${state.currentUser.displayName || state.currentUser.email || "내 계정"}`;
    const studentNav = $("navStudent");
    if (studentNav) studentNav.textContent = isCoachUser() ? "코치 현황" : "내 수강";
    loginButton.title = "내 정보 열기";
    loginButton.setAttribute("aria-label", "내 정보 열기");
    loginButton.classList.add("active-user");
    guestButton.textContent = "로그아웃";
    if (discordButton) {
      discordButton.hidden = false;
      const connected = Boolean(state.currentUser.discordConnected || state.currentUser.discord_connected || state.currentUser.discordDisplayName || state.currentUser.discord_display_name);
      discordButton.textContent = connected ? `Discord · ${state.currentUser.discordDisplayName || state.currentUser.discord_display_name || "연결됨"}` : "Discord 연결";
      discordButton.title = connected ? "Discord 계정 연결됨 · 내 정보에서 확인" : "Discord 계정 연결";
      discordButton.setAttribute("aria-label", discordButton.title);
      discordButton.classList.toggle("active-user", connected);
    }
  } else {
    loginButton.textContent = "로그인";
    const studentNav = $("navStudent");
    if (studentNav) studentNav.textContent = "내 수강";
    loginButton.title = "로그인";
    loginButton.setAttribute("aria-label", "로그인");
    loginButton.classList.remove("active-user");
    guestButton.textContent = "비회원 강의 구매";
    if (discordButton) {
      discordButton.hidden = false;
      discordButton.textContent = "Discord로 계속하기";
      discordButton.title = "Discord로 계속하기";
      discordButton.setAttribute("aria-label", "Discord로 계속하기");
      discordButton.classList.remove("active-user");
    }
  }
}

function handleLoginButtonClick() {
  if (!state.currentUser) {
    openAuthModal("login");
    return;
  }
  state.activeView = "account";
  renderApp();
}

function handleDiscordButtonClick() {
  if (!state.currentUser) {
    openAuthModal("login");
    return;
  }
  const connected = Boolean(state.currentUser.discordConnected || state.currentUser.discord_connected || state.currentUser.discordDisplayName || state.currentUser.discord_display_name);
  if (connected) {
    state.activeView = "account";
    renderApp();
    return;
  }
  startDiscordOAuth();
}

function startDiscordOAuth() {
  if (!state.currentUser) {
    openAuthModal("login");
    return;
  }
  window.location.assign(`${API_BASE_URL.replace(/\/$/, "")}/api/auth/oauth/discord/start`);
}

function applyTheme(theme) {
  const nextTheme = theme === "dark" ? "dark" : "light";
  document.body.dataset.theme = nextTheme;
  localStorage.setItem(THEME_KEY, nextTheme);
  const button = $("themeToggleBtn");
  if (button) {
    button.textContent = nextTheme === "dark" ? "라이트모드" : "다크모드";
    button.setAttribute("aria-pressed", String(nextTheme === "dark"));
  }
}

function toggleTheme() {
  applyTheme(document.body.dataset.theme === "dark" ? "light" : "dark");
}

function closeAuthModal() {
  const modal = $("authModal");
  if (modal) modal.hidden = true;
}

function openAuthModal(mode = "login") {
  const modal = $("authModal");
  const body = $("authBody");
  if (!modal || !body) return;
  const nextMode = ["login", "signup", "guest"].includes(mode) ? mode : "login";
  document.querySelectorAll("[data-auth-mode]").forEach((button) => {
    button.classList.toggle("active", button.dataset.authMode === nextMode);
  });
  body.innerHTML = renderAuthMarkup(nextMode);
  bindAuthForm(nextMode);
  bindPasswordToggles(body);
  modal.hidden = false;
}

function bindPasswordToggles(root = document) {
  root.querySelectorAll("[data-toggle-password]").forEach((button) => {
    button.addEventListener("click", () => {
      const input = button.closest(".password-field")?.querySelector("input");
      if (!input) return;
      const shouldShow = input.type === "password";
      input.type = shouldShow ? "text" : "password";
      button.textContent = shouldShow ? "숨김" : "보기";
      button.setAttribute("aria-label", shouldShow ? "비밀번호 숨기기" : "비밀번호 보기");
      button.title = shouldShow ? "비밀번호 숨기기" : "비밀번호 보기";
    });
  });
}

function renderAuthMarkup(mode) {
  if (mode === "signup") {
    return `
      <form class="auth-content" id="authForm">
        <span class="eyebrow">회원가입</span>
        <h2 id="authTitle">수강생 계정 만들기</h2>
        <p>강의 구매 내역, 예약 시간, 후기 작성 권한을 계정에 저장합니다.</p>
        <label>닉네임<input name="displayName" required minlength="1" maxlength="12" pattern=".{1,12}" placeholder="1~12자 닉네임"><small class="field-hint">1~12자로 입력해주세요.</small></label>
        <label>이메일<input name="email" type="email" required maxlength="${EMAIL_MAX_LENGTH}" autocomplete="email" placeholder="example@email.com"></label>
        <label>비밀번호
          <span class="password-field">
            <input name="password" type="password" required minlength="${PASSWORD_MIN_LENGTH}" maxlength="${PASSWORD_MAX_LENGTH}" autocomplete="new-password" placeholder="8자 이상, 128자 이하">
            <button class="password-toggle" type="button" data-toggle-password aria-label="비밀번호 보기" title="비밀번호 보기">보기</button>
          </span>
        </label>
        <button class="primary" type="submit">회원가입</button>
        <span class="auth-status" id="authStatus" aria-live="polite"></span>
      </form>
    `;
  }
  if (mode === "guest") {
    const selected = state.coaches.find((coach) => coach.id === state.selectedCoachId);
    return `
      <form class="auth-content" id="guestConsultForm">
        <span class="eyebrow">비회원 강의 구매</span>
        <h2 id="authTitle">비회원으로 강의 구매</h2>
        <p>로그인 없이 Riot ID와 연락처를 남기면 운영진이 확인 후 구매 일정을 안내합니다.</p>
        ${selected ? `<div class="guest-selected"><span>선택 강의</span><strong>${escapeHtml(selected.name)}</strong><em>${escapeHtml(selected.price)}</em></div>` : ""}
        <label>Riot 닉네임#태그<input name="riotId" required placeholder="Riot 닉네임#태그"></label>
        <label>연락처<input name="contact" required placeholder="디스코드 또는 이메일"></label>
        <label>받고싶은 피드백 라인 및 포인트<textarea name="feedbackPoint" required rows="4" placeholder="예: 탑 라인, 가렌 1/5/10 게임 라인전이 잘 안풀려서 피드백 받고 싶습니다."></textarea></label>
        <label>강의 방식<textarea name="lessonStyle" required rows="3" placeholder="예: 주2회 한달 강의 희망합니다."></textarea></label>
        <button class="primary" type="submit">비회원 강의 구매</button>
        <span class="auth-status" id="guestConsultStatus" aria-live="polite"></span>
      </form>
    `;
  }
  return `
    <form class="auth-content" id="authForm">
      <span class="eyebrow">로그인</span>
      <h2 id="authTitle">내 강의 이어보기</h2>
      <p>예약 내역과 후기 작성 가능 강의를 계정으로 이어서 확인합니다.</p>
      <label>이메일<input name="email" type="email" required maxlength="${EMAIL_MAX_LENGTH}" autocomplete="email" placeholder="example@email.com"></label>
      <label>비밀번호
        <span class="password-field">
          <input name="password" type="password" required minlength="${PASSWORD_MIN_LENGTH}" maxlength="${PASSWORD_MAX_LENGTH}" autocomplete="current-password" placeholder="비밀번호">
          <button class="password-toggle" type="button" data-toggle-password aria-label="비밀번호 보기" title="비밀번호 보기">보기</button>
        </span>
      </label>
      <button class="primary" type="submit">로그인</button>
      <div class="auth-divider"><span>또는 소셜 계정으로</span></div>
      <div class="social-auth" aria-label="소셜 로그인">
        <button class="google" type="button" data-oauth-provider="google"><img src="assets/google-logo.jpg" alt=""><span>Google로 계속하기</span></button>
        <button class="naver" type="button" data-oauth-provider="naver"><img src="assets/naver.jpg" alt=""><span>네이버로 계속하기</span></button>
        <button class="discord" type="button" data-oauth-provider="discord"><img src="assets/discord-login.png" alt=""><span>Discord로 계속하기</span></button>
      </div>
      <span class="auth-status" id="authStatus" aria-live="polite"></span>
    </form>
  `;
}

function bindAuthForm(mode) {
  if (mode === "guest") {
    bindGuestConsultForm();
    return;
  }
  const form = $("authForm");
  if (!form) return;
  form.querySelectorAll("[data-oauth-provider]").forEach((button) => {
    button.addEventListener("click", () => {
      window.location.assign(`${API_BASE_URL.replace(/\/$/, "")}/api/auth/oauth/${button.dataset.oauthProvider}/start`);
    });
  });
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const button = form.querySelector("button[type='submit']");
    const status = $("authStatus");
    const originalText = button.textContent;
    button.disabled = true;
    button.textContent = mode === "signup" ? "가입 중" : "로그인 중";
    if (status) status.textContent = "";
    const data = new FormData(form);
    try {
      const user = mode === "signup"
        ? await signupUser({
            displayName: data.get("displayName"),
            email: data.get("email"),
            password: data.get("password"),
          })
        : await loginUser({
            email: data.get("email"),
            password: data.get("password"),
          });
      state.currentUser = user;
      if (state.currentUser?.coachKey) state.coachSelfKey = state.currentUser.coachKey;
      state.coachDashboardLoadState = "idle";
      state.coachDashboardLoadError = "";
      state.studentReservationLoadState = "idle";
      state.studentReservationLoadError = "";
      state.bookings = [];
      state.refundRequests = [];
      state.submittedReviewIds = [];
      closeAuthModal();
      if (state.currentUser?.needsNickname || state.currentUser?.nicknameSetupRequired) state.activeView = "student";
      renderApp();
      if (isCoachUser()) await loadCoachProfile();
      await handlePaymentReturn();
    } catch (error) {
      if (status) status.textContent = getAuthErrorMessage(error.message);
    } finally {
      button.disabled = false;
      button.textContent = originalText;
    }
  });
}

function bindGuestConsultForm() {
  const form = $("guestConsultForm");
  if (!form) return;
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const selected = state.coaches.find((coach) => coach.id === state.selectedCoachId);
    const button = form.querySelector("button[type='submit']");
    const status = $("guestConsultStatus");
    const originalText = button.textContent;
    const data = new FormData(form);
    button.disabled = true;
    button.textContent = "문의 접수 중";
    if (status) status.textContent = "";
    try {
      await submitGuestConsultation({
        selectedCoach: selected,
        riotId: data.get("riotId"),
        contact: data.get("contact"),
        feedbackPoint: data.get("feedbackPoint"),
        lessonStyle: data.get("lessonStyle"),
      });
      form.reset();
      closeAuthModal();
       alert("비회원 강의 구매 문의가 접수되었습니다. 운영진이 연락드릴게요.");
    } catch (error) {
      if (status) status.textContent = error.message || "문의를 접수하지 못했습니다.";
    } finally {
      button.disabled = false;
      button.textContent = originalText;
    }
  });
}


function accountBookingDate(row) {
  const candidates = [
    row?.scheduledAt, row?.scheduled_at, row?.startAt, row?.start_at,
    row?.reservationAt, row?.reservation_at, row?.time,
  ];
  for (const value of candidates) {
    if (!value) continue;
    const raw = String(value).trim();
    const normalized = raw
      .replace(/[.]/g, "-")
      .replace(/\s+/g, " ")
      .replace(/(\d{4}-\d{2}-\d{2})\s+(\d{1,2}:\d{2})/, "$1T$2");
    const date = new Date(normalized);
    if (!Number.isNaN(date.getTime())) return date;
  }
  return null;
}

function accountWeekBounds(now = new Date()) {
  const start = new Date(now);
  const day = start.getDay() || 7;
  start.setHours(0, 0, 0, 0);
  start.setDate(start.getDate() - day + 1);
  const end = new Date(start);
  end.setDate(end.getDate() + 7);
  return { start, end };
}

function accountUpcomingRows(rows) {
  const now = new Date();
  return rows
    .filter((row) => !["완료", "취소"].includes(String(row?.status || "")))
    .map((row) => ({ row, date: accountBookingDate(row) }))
    .sort((a, b) => {
      if (a.date && b.date) return a.date - b.date;
      if (a.date) return -1;
      if (b.date) return 1;
      return 0;
    })
    .filter((item) => !item.date || item.date >= now)
    .map((item) => item.row);
}

function renderAccountDashboardMarkup() {
  const rows = Array.isArray(state.bookings) ? state.bookings : [];
  if (isCoachUser()) {
    const loading = state.coachDashboardLoadState === "loading" || state.coachDashboardLoadState === "idle";
    const error = state.coachDashboardLoadState === "error";
    const completed = rows.filter((row) => String(row.status || "") === "완료");
    const active = rows.filter((row) => !["완료", "취소"].includes(String(row.status || "")));
    const { start, end } = accountWeekBounds();
    const thisWeek = active.filter((row) => {
      const date = accountBookingDate(row);
      return date && date >= start && date < end;
    });
    const completedRevenue = completed.reduce((sum, row) => {
      const paid = Number(row.payment?.amount || row.paymentAmount || row.payment_amount || 0);
      if (paid > 0) return sum + paid;
      return sum + Number(parseReservationPrice(row.coachPrice).amount || 0);
    }, 0);
    const uniqueStudents = new Set(
      completed.map((row) => String(row.student || row.studentName || row.contact || "").trim()).filter(Boolean)
    );
    const upcoming = accountUpcomingRows(active).slice(0, 3);
    const weeklyHours = (state.coachSchedule?.weekly || []).reduce(
      (sum, item) => sum + (item.enabled === false ? 0 : Math.max(0, Number(item.endMinute || 0) - Number(item.startMinute || 0)) / 60),
      0
    );

    return `
      <section class="account-role-dashboard">
        <div class="account-section-head">
          <div><span>코치 대시보드</span><strong>이번 주 운영 현황</strong></div>
          <div class="account-head-actions">
            <button class="secondary mini" type="button" id="accountCoachDashboardBtn">예약 현황</button>
            <button class="primary mini" type="button" id="accountCoachCenterBtn2">일정 · 강의 관리</button>
          </div>
        </div>
        ${error ? `<div class="account-data-error">예약 현황을 불러오지 못했습니다. 코치 현황에서 다시 확인해주세요.</div>` : `
          <div class="account-kpi-row">
            <article><span>이번 주 예약</span><strong>${loading ? "…" : `${thisWeek.length}건`}</strong></article>
            <article><span>완료 강의 매출</span><strong>${loading ? "…" : formatWon(completedRevenue)}</strong><small>정산 전 · 완료 예약 기준</small></article>
            <article><span>완료 수강생</span><strong>${loading ? "…" : `${uniqueStudents.size}명`}</strong></article>
            <article><span>주간 가능 시간</span><strong>${state.coachScheduleLoadState === "loaded" ? `${weeklyHours.toLocaleString("ko-KR")}시간` : "…"}</strong></article>
          </div>
          <div class="account-dashboard-grid">
            <article class="account-next-card account-upcoming-card">
              <span>다가오는 예약</span>
              ${upcoming.length ? `
                <div class="account-upcoming-list">
                  ${upcoming.map((row) => `
                    <div>
                      <strong>${escapeHtml(row.time || "시간 확인 중")}</strong>
                      <p>${escapeHtml(row.student || "수강생")} · ${escapeHtml(row.lesson || row.coachName || "강의")}</p>
                    </div>
                  `).join("")}
                </div>
              ` : `<strong>예정된 예약 없음</strong><p>새 예약이 들어오면 여기에 표시됩니다.</p>`}
            </article>
            <article class="account-schedule-card">
              <div><span>코칭 가능 시간</span><button class="text-button" type="button" id="accountScheduleEditBtn">시간표 수정</button></div>
              ${state.coachScheduleLoadState === "loaded"
                ? (renderScheduleSummaryMarkup ? renderScheduleSummaryMarkup() : "")
                : `<p>주간 시간표를 불러오는 중입니다.</p>`}
            </article>
          </div>
          <div class="account-schedule-editor ${state.accountScheduleExpanded ? "open" : ""}" id="accountScheduleEditorWrap" ${state.accountScheduleExpanded ? "" : "hidden"}>
            <div class="account-schedule-editor-head">
              <div><span>코칭 가능 시간 설정</span><strong>주간 시간표</strong></div>
              <button class="secondary mini" type="button" id="accountScheduleCloseBtn">접기</button>
            </div>
            <div id="accountCoachAvailabilityPanel"></div>
          </div>
        `}
      </section>
    `;
  }

  const loading = state.studentReservationLoadState === "loading" || state.studentReservationLoadState === "idle";
  const error = state.studentReservationLoadState === "error";
  const active = rows.filter((row) => !["완료", "취소"].includes(String(row.status || "")));
  const paid = rows.filter((row) => ["PAID", "PARTIALLY_REFUNDED"].includes(paymentStatus(row)));
  const payable = rows.filter((row) =>
    ["신규", "상담중", "결제대기", "코치확정대기", "예약확정"].includes(String(row.status || "")) &&
    !["PAID", "PARTIALLY_REFUNDED", "CANCELED", "REFUNDED"].includes(paymentStatus(row))
  );
  const reviewable = rows.filter((row) => String(row.status || "") === "완료" && paymentStatus(row) === "PAID" && !row.review);
  const next = accountUpcomingRows(active)[0];
  const paidAmount = paid.reduce((sum, row) => sum + Number(row.payment?.amount || 0), 0);

  return `
    <section class="account-role-dashboard">
      <div class="account-section-head">
        <div><span>수강 대시보드</span><strong>내 코칭 현황</strong></div>
        <button class="primary mini" type="button" id="accountStudentCenterBtn">내 수강 보기</button>
      </div>
      ${error ? `<div class="account-data-error">수강 내역을 불러오지 못했습니다. 내 수강에서 다시 확인해주세요.</div>` : `
        <div class="account-kpi-row">
          <article><span>진행 중 예약</span><strong>${loading ? "…" : `${active.length}건`}</strong></article>
          <article><span>결제 완료</span><strong>${loading ? "…" : formatWon(paidAmount)}</strong></article>
          <article><span>결제 대기</span><strong>${loading ? "…" : `${payable.length}건`}</strong></article>
          <article><span>후기 작성</span><strong>${loading ? "…" : `${reviewable.length}건`}</strong></article>
        </div>
        <article class="account-next-card student">
          <span>다음 코칭</span>
          ${next ? `
            <strong>${escapeHtml(next.time || "시간 확인 중")}</strong>
            <p>${escapeHtml(next.coachName || "코치")} · ${escapeHtml(next.lesson || "예약 강의")}</p>
            <small>${escapeHtml(next.status || "")}</small>
          ` : `<strong>예정된 코칭 없음</strong><p>예약이 확정되면 다음 일정이 여기에 표시됩니다.</p>`}
        </article>
      `}
    </section>
  `;
}

function renderAccountPanelMarkup() {
  if (!state.currentUser) return "";
  const user = state.currentUser;
  const nickname = user.displayName || user.nickname || "";
  const riotId = user.riotId || user.riot_id || "";
  const availableAt = user.nicknameChangeAvailableAt || user.nickname_change_available_at || "";
  const availableText = availableAt ? formatDateTime(availableAt) : "변경 가능";
  const needsNickname = Boolean(user.needsNickname || user.nicknameSetupRequired || user.nickname_setup_required);
  const roleLabel = isAdminUser() ? "관리자 계정" : (isCoachUser() ? "코치 계정" : "수강생 계정");
  const discordConnected = Boolean(user.discordConnected || user.discord_connected || user.discordDisplayName || user.discord_display_name);
  return `
    <section class="account-overview">
      <div class="account-avatar">${escapeHtml((nickname || "L").slice(0, 1).toUpperCase())}</div>
      <div class="account-identity">
        <span class="account-role-badge">${escapeHtml(roleLabel)}</span>
        <strong>${escapeHtml(nickname || "닉네임 미설정")}</strong>
        <small>${escapeHtml(user.email || "")}</small>
      </div>
      ${isCoachUser()
        ? `<button class="secondary account-coach-link" type="button" id="accountCoachCenterBtn">코치센터</button>`
        : `<button class="secondary account-coach-link" type="button" id="accountStudentQuickBtn">내 수강</button>`}
    </section>

    ${renderAccountDashboardMarkup()}

    <section class="student-panel account-panel" id="accountPanel">
      <div class="account-section-head settings">
        <div><span>계정 설정</span><strong>프로필 · 게임 계정</strong></div>
      </div>
      ${needsNickname ? `<p class="account-required">닉네임을 설정해주세요.</p>` : ""}
      <div class="account-settings-grid">
        <form class="account-setting-card" id="accountNicknameForm">
          <div><span>닉네임</span><small>${escapeHtml(availableText)}</small></div>
          <div class="account-inline-field"><input id="accountNickname" name="nickname" required minlength="1" maxlength="12" pattern=".{1,12}" value="${escapeHtml(nickname)}"><button class="secondary" type="submit" id="accountNicknameSaveBtn">저장</button></div>
          <span class="save-status" id="accountNicknameStatus" aria-live="polite"></span>
        </form>
        <form class="account-setting-card" id="accountRiotForm">
          <div><span>Riot ID</span><small>게임이름#태그</small></div>
          <div class="account-inline-field"><input id="accountRiotId" name="riotId" maxlength="40" placeholder="예: Lucid#KR1" value="${escapeHtml(riotId)}"><button class="secondary" type="submit" id="accountRiotSaveBtn">저장</button></div>
          <span class="save-status" id="accountRiotStatus" aria-live="polite"></span>
        </form>
      </div>
      <div class="account-link-row">
        <span class="account-link-title">계정 연동</span>
        <button class="account-provider google" type="button" data-account-oauth="google"><img src="assets/google-logo.jpg" alt=""><span>Google</span></button>
        <button class="account-provider naver" type="button" data-account-oauth="naver"><img src="assets/naver.jpg" alt=""><span>Naver</span></button>
        <button class="account-provider discord ${discordConnected ? "connected" : ""}" type="button" data-account-oauth="discord"><img src="assets/discord-login.png" alt=""><span>${discordConnected ? "Discord 연결됨" : "Discord 연결"}</span></button>
      </div>
      <details class="account-danger-compact">
        <summary>계정 관리</summary>
        <div><span>회원탈퇴</span><button class="danger mini" type="button" id="accountDeleteBtn">탈퇴</button></div>
      </details>
    </section>
  `;
}

function mountAccountPanel(container) {
  if (!container || !state.currentUser) return;
  container.insertAdjacentHTML("afterbegin", renderAccountPanelMarkup());
  $("accountNicknameForm")?.addEventListener("submit", saveAccountNickname);
  $("accountRiotForm")?.addEventListener("submit", saveAccountRiotId);
  document.querySelectorAll("[data-account-oauth]").forEach((button) => button.addEventListener("click", () => startAccountOAuth(button.dataset.accountOauth)));
  const openCoachCenter = () => { state.coachSelfKey = getFallbackCoachKey(); state.activeView = "coachSelf"; renderApp(); };
  const openStudentCenter = () => { state.activeView = "student"; renderApp(); };
  $("accountCoachCenterBtn")?.addEventListener("click", openCoachCenter);
  $("accountCoachCenterBtn2")?.addEventListener("click", openCoachCenter);
  const toggleAccountSchedule = (expanded) => {
    state.accountScheduleExpanded = expanded;
    const wrap = $("accountScheduleEditorWrap");
    if (wrap) {
      wrap.hidden = !expanded;
      wrap.classList.toggle("open", expanded);
    }
    if (expanded) renderCoachAvailabilityPanel();
  };
  $("accountScheduleEditBtn")?.addEventListener("click", () => toggleAccountSchedule(true));
  $("accountScheduleCloseBtn")?.addEventListener("click", () => toggleAccountSchedule(false));
  $("accountCoachDashboardBtn")?.addEventListener("click", openStudentCenter);
  $("accountStudentCenterBtn")?.addEventListener("click", openStudentCenter);
  $("accountStudentQuickBtn")?.addEventListener("click", openStudentCenter);
  $("accountDeleteBtn")?.addEventListener("click", deleteCurrentAccount);
}

async function saveAccountNickname(event) {
  event.preventDefault();
  const input = $("accountNickname");
  const status = $("accountNicknameStatus");
  const button = $("accountNicknameSaveBtn");
  const nickname = String(input?.value || "").trim();
  if (!nickname || [...nickname].length > 12) {
    if (status) status.textContent = "닉네임은 1~12자로 입력해주세요.";
    return;
  }
  if (button) button.disabled = true;
  if (status) {
    status.textContent = "저장 중...";
    status.className = "save-status loading";
  }
  try {
    const user = await updateCurrentUser({ displayName: nickname, nickname });
    state.currentUser = user;
    if (status) {
      status.textContent = `저장 완료 · 다음 변경 가능: ${formatDateTime(user.nicknameChangeAvailableAt || user.nickname_change_available_at || "") || "변경 가능"}`;
      status.className = "save-status success";
    }
    renderApp();
  } catch (error) {
    if (status) {
      const retryText = error.retryAt ? ` 다시 변경 가능: ${formatDateTime(error.retryAt)}` : "";
      status.textContent = `${getAuthErrorMessage(error.message)}${retryText}`;
      status.className = "save-status error";
    }
  } finally {
    if (button) button.disabled = false;
  }
}

function startAccountOAuth(provider) {
  if (!state.currentUser || !["google", "naver", "discord"].includes(provider)) return;
  window.location.assign(`${API_BASE_URL.replace(/\/$/, "")}/api/auth/oauth/${provider}/start`);
}

async function saveAccountRiotId(event) {
  event.preventDefault();
  const input = $("accountRiotId");
  const status = $("accountRiotStatus");
  const button = $("accountRiotSaveBtn");
  const riotId = String(input?.value || "").trim();
  if (riotId && (!riotId.includes("#") || riotId.startsWith("#") || riotId.endsWith("#"))) {
    if (status) { status.textContent = "게임이름#태그 형식으로 입력해주세요."; status.className = "save-status error"; }
    return;
  }
  if (button) button.disabled = true;
  if (status) { status.textContent = "저장 중..."; status.className = "save-status loading"; }
  try {
    const user = await updateCurrentUser({ riotId });
    state.currentUser = user;
    if (status) { status.textContent = "저장 완료"; status.className = "save-status success"; }
    renderApp();
  } catch (error) {
    if (status) { status.textContent = getAuthErrorMessage(error.message); status.className = "save-status error"; }
  } finally {
    if (button) button.disabled = false;
  }
}

async function deleteCurrentAccount() {
  if (!state.currentUser || !window.confirm("정말 회원탈퇴할까요? 계정과 로그인 세션을 사용할 수 없게 됩니다.")) return;
  try {
    await deleteCurrentUserApi();
    state.currentUser = null;
    state.activeView = "market";
    state.bookings = [];
    alert("회원탈퇴가 완료되었습니다.");
    renderApp();
  } catch (error) {
    alert(`회원탈퇴를 처리하지 못했습니다.\n${getAuthErrorMessage(error.message)}`);
  }
}

async function loadCurrentUser() {
  if (!API_BASE_URL || API_BASE_URL.includes("YOUR-COACH-API")) return;
  const requestId = ++state.authRequestId;
  state.authLoadState = "loading";
  try {
    const user = await fetchCurrentUser();
    if (requestId !== state.authRequestId) return;
    state.currentUser = user;
    state.coachSelfLessons = null;
    if (state.currentUser?.coachKey) state.coachSelfKey = state.currentUser.coachKey;
    state.coachSchedule = { weekly: [], overrides: [], slots: [] };
    state.coachScheduleDraft = null;
    state.coachScheduleLoadState = "idle";
    state.coachScheduleLoadError = "";
    state.coachDashboardLoadState = "idle";
    state.coachDashboardLoadError = "";
    state.studentReservationLoadState = "idle";
    state.studentReservationLoadError = "";
    state.bookings = [];
    state.refundRequests = [];
    state.submittedReviewIds = [];
    state.authLoadState = "loaded";
    if (state.currentUser?.needsNickname || state.currentUser?.nicknameSetupRequired) state.activeView = "student";
    renderApp();
    if (isCoachUser()) await loadCoachProfile();
    await handlePaymentReturn();
  } catch {
    if (requestId !== state.authRequestId) return;
    state.currentUser = null;
    state.coachSelfLessons = null;
    state.authLoadState = "error";
    renderApp();
  }
}

async function logoutUser() {
  state.authRequestId += 1;
  try {
    await logoutAuthSessions();
  } finally {
    sessionStorage.removeItem(ADMIN_TOKEN_KEY);
    state.currentUser = null;
    state.coachDashboardLoadState = "idle";
    state.coachDashboardLoadError = "";
    state.studentReservationLoadState = "idle";
    state.studentReservationLoadError = "";
    state.bookings = [];
    state.refundRequests = [];
    state.submittedReviewIds = [];
    state.coachProfile = null;
    state.coachSelfLessons = null;
    state.coachProfileLoadState = "idle";
    state.coachProfileLoadError = "";
    state.coachSchedule = { weekly: [], overrides: [], slots: [] };
    state.coachScheduleDraft = null;
    state.coachScheduleLoadState = "idle";
    state.coachScheduleLoadError = "";
    renderApp();
  }
}

function getAuthErrorMessage(error) {
  const messages = {
    invalid_email: "이메일 형식을 확인해주세요.",
    weak_password: "비밀번호는 8자 이상이어야 합니다.",
    password_too_long: "비밀번호는 128자 이하로 입력해주세요.",
    missing_display_name: "닉네임을 입력해주세요.",
    invalid_display_name: "닉네임은 1~12자로 입력해주세요.",
    display_name_too_short: "닉네임은 1~12자로 입력해주세요.",
    display_name_too_long: "닉네임은 1~12자로 입력해주세요.",
    email_already_exists: "이미 가입된 이메일입니다.",
    display_name_already_exists: "이미 사용 중인 닉네임입니다.",
    nickname_change_too_soon: "닉네임은 24시간에 한 번만 변경할 수 있습니다.",
    nickname_change_locked: "닉네임 변경 가능 시간이 아직 지나지 않았습니다.",
    display_name_change_limited: "닉네임은 24시간에 한 번만 변경할 수 있습니다.",
    nickname_already_exists: "이미 사용 중인 닉네임입니다.",
    account_inactive: "탈퇴한 계정입니다.",
    cannot_delete_account: "현재 계정은 회원탈퇴를 처리할 수 없습니다.",
    missing_credentials: "이메일과 비밀번호를 입력해주세요.",
    invalid_credentials: "이메일 또는 비밀번호가 맞지 않습니다.",
    invalid_riot_id: "Riot ID는 게임이름#태그 형식으로 입력해주세요.",
  };
  return messages[error] || "처리하지 못했습니다. 잠시 후 다시 시도해주세요.";
}

async function ensureAdminAccess() {
  if (isAdminUser()) return true;
  if (sessionStorage.getItem(ADMIN_TOKEN_KEY)) return true;
  return loginForReservations();
}

async function loginForReservations() {
  const password = window.prompt("관리자 비밀번호를 입력하세요.");
  if (!password) return false;

  try {
    const result = await loginAdmin(password);
    if (result.adminToken) {
      sessionStorage.setItem(ADMIN_TOKEN_KEY, result.adminToken);
    }
    if (!result.adminToken) {
      alert("관리자 인증 응답에 토큰이 없습니다. 서버를 최신 코드로 다시 배포해주세요.");
      return false;
    }
    return true;
  } catch (error) {
    alert(error.status === 401
      ? "관리자 비밀번호가 맞지 않거나 인증 서버에 연결할 수 없습니다."
      : "관리자 인증 요청이 브라우저에서 차단되었습니다. 백엔드 CORS 허용 도메인에 현재 사이트 주소를 추가하고 서버를 다시 배포해야 합니다.");
    console.warn("관리자 인증 실패", error);
    return false;
  }
}

  return {
    showOAuthResult,
    hasCoachMenuAccess,
    getUserRoles,
    isAdminUser,
    isCoachUser,
    getFallbackCoachKey,
    getKnownCoachKeyForUser,
    hasCoachLikeAccount,
    renderRoleMenu,
    renderUserActions,
    handleLoginButtonClick,
    handleDiscordButtonClick,
    startDiscordOAuth,
    applyTheme,
    toggleTheme,
    closeAuthModal,
    openAuthModal,
    bindPasswordToggles,
    renderAuthMarkup,
    bindAuthForm,
    bindGuestConsultForm,
    renderAccountPanelMarkup,
    mountAccountPanel,
    saveAccountNickname,
    deleteCurrentAccount,
    loadCurrentUser,
    logoutUser,
    getAuthErrorMessage,
    ensureAdminAccess,
    loginForReservations,
  };
}
