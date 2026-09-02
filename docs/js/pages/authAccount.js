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
import { submitGuestConsultation } from "../reservations.js";
import { byId as $, escapeHtml, formatDateTime } from "../utils.js";

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
    ${canManageLessons ? `<button class="role-menu-button ${state.activeView === "coachSelf" ? "active" : ""}" id="openCoachSelfMenuBtn" type="button">내 강의 관리</button>` : ""}
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
    loginButton.textContent = state.currentUser.displayName || state.currentUser.email || "내 계정";
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
  state.activeView = "student";
  renderApp();
}

function handleDiscordButtonClick() {
  if (!state.currentUser) {
    openAuthModal("login");
    return;
  }
  const connected = Boolean(state.currentUser.discordConnected || state.currentUser.discord_connected || state.currentUser.discordDisplayName || state.currentUser.discord_display_name);
  if (connected) {
    state.activeView = "student";
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

function renderAccountPanelMarkup() {
  if (!state.currentUser) return "";
  const user = state.currentUser;
  const nickname = user.displayName || user.nickname || "";
  const availableAt = user.nicknameChangeAvailableAt || user.nickname_change_available_at || "";
  const availableText = availableAt ? formatDateTime(availableAt) : "변경 가능";
  const needsNickname = Boolean(user.needsNickname || user.nicknameSetupRequired || user.nickname_setup_required);
  return `
    <section class="student-panel account-panel" id="accountPanel">
      <div class="student-panel-head"><span>내 정보</span><strong>계정 설정</strong></div>
      ${needsNickname ? `<p class="account-required">서비스 이용을 위해 닉네임을 먼저 설정해주세요.</p>` : ""}
      <form class="account-form" id="accountNicknameForm">
        <label>닉네임<input id="accountNickname" name="nickname" required minlength="1" maxlength="12" pattern=".{1,12}" value="${escapeHtml(nickname)}"></label>
        <button class="secondary" type="submit" id="accountNicknameSaveBtn">닉네임 저장</button>
        <span class="save-status" id="accountNicknameStatus" aria-live="polite">다음 변경 가능: ${escapeHtml(availableText)}</span>
      </form>
      <div class="account-danger">
        <div><strong>회원탈퇴</strong><small>탈퇴하면 계정과 로그인 세션을 사용할 수 없습니다.</small></div>
        <button class="danger" type="button" id="accountDeleteBtn">회원탈퇴</button>
      </div>
    </section>
    ${isCoachUser() ? renderScheduleSummaryMarkup() : ""}
  `;
}

function mountAccountPanel(container) {
  if (!container || !state.currentUser) return;
  container.insertAdjacentHTML("afterbegin", renderAccountPanelMarkup());
  $("accountNicknameForm")?.addEventListener("submit", saveAccountNickname);
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
