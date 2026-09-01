
import { categories, filterSets, purposes, adminLineOptions, adminFieldOptions, priceUnits, badgeOptions, text, samples, imageMigration, tierRank, leagueLessonOverrides, legacyCoachKeys, state } from "./js/catalog.js";
import {
  ADMIN_TOKEN_KEY,
  API_BASE_URL,
  COACH_API_TIMEOUT_MS,
  EMAIL_MAX_LENGTH,
  PASSWORD_MAX_LENGTH,
  PASSWORD_MIN_LENGTH,
  THEME_KEY,
} from "./js/config.js";
import { apiFetch as fetch } from "./js/api.js";
import {
  createCoachRequest,
  decideCoachRequest,
  deleteCoachFromApi,
  fetchAdminCoachSettings,
  fetchCoachRequests,
  fetchUsers,
  loginAdmin,
  normalizeAdminCoachSetting,
  resetCoachesInApi,
  saveAdminCoachSettings,
  saveCoachToApi,
  updateUserRole,
} from "./js/admin.js";
import { deleteCurrentUser as deleteCurrentUserApi, fetchCurrentUser, loginUser, logoutAuthSessions, signupUser, updateCurrentUser, userIsAdmin, userIsCoach, userRoles } from "./js/auth.js";
import {
  getCoachBadges,
  getCoachPurposes,
  getDetailImage,
  getFeaturedImage,
  getImageStyle,
  getPurposeLabels,
  getTierClass,
  getWideImageStyle,
  renderBadge,
  renderCoachCard,
  renderFeaturedCard,
} from "./js/components/coachCard.js";
import {
  createCoachLesson,
  deleteCoachLesson,
  fetchCoachAvailability,
  fetchCoachCatalog,
  fetchCoachLessons,
  fetchCoachProfile,
  fetchCoachReviews,
  fetchCoachSchedule,
  saveCoachLesson,
  saveCoachProfile,
  saveCoachSchedule as saveCoachScheduleApi,
} from "./js/coachService.js";
import {
  buildReservationPayload,
  cancelPayment,
  clearPaymentQuery,
  confirmCoachReservationRequest,
  confirmPayment,
  createPaymentOrder,
  createReservationCancelRequest,
  createReservationReview,
  deleteReservation,
  fetchAdminRefundRequests,
  fetchCoachReservations,
  fetchMyRefundRequests,
  fetchMyReservations,
  fetchReservations,
  filterReservations,
  getPaymentErrorMessage,
  paymentStatus,
  paymentStatusLabel,
  refundAdminStatusLabel,
  refundRequestLabel,
  renderStatusOptions,
  submitGuestConsultation,
  submitReservation,
  updateRefundRequest,
  updateReservationStatus,
} from "./js/reservations.js";
import {
  addLocalDays,
  byId as $,
  escapeHtml,
  formatDateTime,
  formatWon,
  getIsoWeekday,
  isoDateOnly,
  localDateOnly,
  parseReservationPrice,
  splitCsv,
} from "./js/utils.js";


function migrateCoachImages(coaches) {
  return normalizeCoachProfiles(coaches.map((coach) => ({
    ...coach,
    image: imageMigration[coach.image] || coach.image || "assets/logo.jpg",
    featuredImage: imageMigration[coach.featuredImage] || coach.featuredImage || "",
    detailImage: imageMigration[coach.detailImage] || coach.detailImage || "",
    bannerImage: imageMigration[coach.bannerImage] || coach.bannerImage || "",
    imagePosition: coach.imagePosition || "center 8%",
  })));
}

function getPublicCatalogCoaches(coaches) {
  return migrateCoachImages(coaches);
}

function inferLeagueCoachKey(coach) {
  if (coach.coachKey) return coach.coachKey;
  const id = String(coach.id || "");
  if (leagueLessonOverrides[id]?.coachKey) return leagueLessonOverrides[id].coachKey;
  return legacyCoachKeys[id] || id;
}

function normalizeCoachProfiles(coaches) {
  return coaches.map((coach) => {
    if (coach.category !== "league") {
      return {
        ...coach,
        coachKey: coach.coachKey || coach.id,
        coachProfileName: coach.coachProfileName || coach.name,
      };
    }
    const override = leagueLessonOverrides[coach.id] || {};
    const common = coach.coachProfile || coach.profile || {};
    const coachKey = coach.coachKey || override.coachKey || inferLeagueCoachKey(coach);
    const profileName = coach.coachProfileName || coach.coachNickname || coach.nickname || common.nickname || common.name || coach.name || "신규 코치";
    const profileTier = coach.coachTier || coach.profileTier || common.tier || coach.tier || "일반";
    const profileSummary = coach.coachSummary || coach.coachIntro || coach.intro || common.intro || common.tagline || coach.tagline || "";
    const imagePath = imageMigration[coach.image] || coach.image || "";
    const fallbackPurpose = Array.isArray(coach.purpose) && coach.purpose.length ? coach.purpose : override.purpose;
    return {
      ...coach,
      coachKey,
      coachProfileName: profileName,
      coachTier: profileTier,
      coachSummary: profileSummary,
      coachRoles: Array.isArray(common.roles) ? common.roles : coach.coachRoles,
      tier: coach.tier || profileTier,
      purpose: fallbackPurpose || [],
      image: imagePath || common.image || common.profileImage || "assets/logo.jpg",
      imagePosition: coach.imagePosition || "center 8%",
      featuredImagePosition: coach.featuredImagePosition || coach.imagePosition || "center center",
      detailImagePosition: coach.detailImagePosition || coach.imagePosition || "center center",
      badges: [profileTier, ...(coach.badges || []).filter((badge) => badge !== profileTier)].slice(0, 3),
    };
  });
}

function boot() {
  applyTheme(localStorage.getItem(THEME_KEY) || "light");
  Object.entries(text).forEach(([id, value]) => {
    const el = $(id);
    if (!el) return;
    if (el.tagName === "INPUT") el.placeholder = value;
    else el.textContent = value;
  });
  $("navStudent").textContent = "내 정보";
  $("navCoachSearch").textContent = "맞춤 강의 검색";
  $("searchInput").placeholder = text.searchPlaceholder;
  $("coachImagePosition").placeholder = "예: center 8%, 72% 12%";
  state.coaches = [];
  state.coachLoadState = "loading";
  render();
  bindEvents();
  showOAuthResult();
  loadCurrentUser();
  loadCoachesFromApi();
}

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

let eventsBound = false;

function bindEvents() {
  if (eventsBound) return;
  eventsBound = true;
  $("homeLogo").addEventListener("click", () => {
    state.activeView = "market";
    state.category = "league";
    state.type = "all";
    state.segment = "all";
    state.selectedCoachId = null;
    state.selectedCoachKey = null;
    state.query = "";
    $("searchInput").value = "";
    render();
  });

  document.querySelectorAll(".nav-item").forEach((button) => {
    button.addEventListener("click", async () => {
      if (button.dataset.action === "coachSearch") {
        openCoachExplorer();
        return;
      }
      let nextView = button.dataset.view;
      if (!nextView) return;
      if (["bookings", "admin"].includes(nextView)) {
        const allowed = await ensureAdminAccess();
        if (!allowed) return;
      }
      state.activeView = nextView;
      render();
      if (state.activeView === "bookings") {
        loadReservations({ promptForLogin: false });
        loadAdminRefundRequests();
      } else if (state.activeView === "admin") {
        loadAdminCoachSettings();
      }
    });
  });

  document.querySelectorAll("[data-admin-view]").forEach((button) => {
    button.addEventListener("click", async () => {
      await openAdminView(button.dataset.adminView);
    });
  });

  $("searchInput").addEventListener("input", (event) => {
    state.query = event.target.value.trim().toLowerCase();
    renderMarket();
  });
  $("coachExplorerCloseBtn")?.addEventListener("click", closeCoachExplorer);
  $("coachExplorerModal")?.addEventListener("click", (event) => {
    if (event.target.id === "coachExplorerModal") closeCoachExplorer();
  });
  $("coachExplorerSearch")?.addEventListener("input", (event) => {
    state.coachExplorerQuery = event.target.value.trim().toLowerCase();
    renderCoachExplorer();
  });
  $("lessonDetailCloseBtn")?.addEventListener("click", closeLessonDetail);
  $("lessonDetailModal")?.addEventListener("click", (event) => {
    if (event.target.id === "lessonDetailModal") closeLessonDetail();
  });
  $("themeToggleBtn")?.addEventListener("click", toggleTheme);
  $("loginOpenBtn")?.addEventListener("click", handleLoginButtonClick);
  $("discordConnectBtn")?.addEventListener("click", handleDiscordButtonClick);
  $("guestBuyOpenBtn")?.addEventListener("click", () => {
    if (state.currentUser) logoutUser();
    else openAuthModal("guest");
  });
  $("authCloseBtn")?.addEventListener("click", closeAuthModal);
  $("authModal")?.addEventListener("click", (event) => {
    if (event.target.id === "authModal") closeAuthModal();
  });
  document.querySelectorAll("[data-auth-mode]").forEach((button) => {
    button.addEventListener("click", () => openAuthModal(button.dataset.authMode));
  });

  $("coachForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    await saveCoachFromForm();
  });

  $("coachCategory").addEventListener("change", () => {
    renderAdminChoiceControls([], [], []);
  });
  if ($("addCoachBadgeBtn")) $("addCoachBadgeBtn").addEventListener("click", addSelectedBadge);
  if ($("coachBadgeChoices")) {
    $("coachBadgeChoices").addEventListener("change", () => {
      renderBadgePicker(getCheckedValues("coachBadgeChoice"));
    });
  }
  $("coachPriceUnitType").addEventListener("change", () => {
    renderPriceUnitOptions($("coachPriceUnitType").value);
    updateCoachPriceValue();
  });
  $("coachPriceAmount").addEventListener("input", updateCoachPriceValue);
  $("coachPriceUnit").addEventListener("change", updateCoachPriceValue);
  $("clearBookingsBtn").addEventListener("click", () => {
    loadReservations();
  });
  $("coachImage")?.addEventListener("input", () => updateCoachImagePreview());
  $("coachImageFile").addEventListener("change", handleCoachImageFile);
  $("coachFeaturedImageFile").addEventListener("change", (event) => handleWideCoachImageFile(event, "coachFeaturedImage", "coachFeaturedImagePreview", "상단 추천 이미지"));
  $("coachDetailImageFile").addEventListener("change", (event) => handleWideCoachImageFile(event, "coachDetailImage", "coachDetailImagePreview", "상세 설명 이미지"));
  $("openFeaturedCropBtn").addEventListener("click", () => openCropModal({
    inputId: "coachFeaturedImage",
    previewId: "coachFeaturedImagePreview",
    width: 1200,
    height: 675,
    label: "상단 추천 이미지",
  }));
  $("openCropBtn").addEventListener("click", () => openCropModal({
    inputId: "coachImage",
    previewId: "coachImagePreview",
    width: 520,
    height: 520,
    label: "일반 목록 이미지",
  }));
  $("openDetailCropBtn").addEventListener("click", () => openCropModal({
    inputId: "coachDetailImage",
    previewId: "coachDetailImagePreview",
    width: 1200,
    height: 675,
    label: "상세 설명 이미지",
  }));
  $("cropCloseBtn").addEventListener("click", closeCropModal);
  $("applyCropBtn").addEventListener("click", applyImageCrop);
  $("cropImage").addEventListener("load", updateCropBox);
  ["cropX", "cropY", "cropSize"].forEach((id) => $(id).addEventListener("input", updateCropBox));
  $("cropBox").addEventListener("pointerdown", startCropDrag);
  document.querySelector(".crop-stage").addEventListener("pointerdown", moveCropToPointer);
  $("bookingStatusFilter").addEventListener("change", (event) => {
    state.bookingFilterStatus = event.target.value;
    renderBookings();
  });
  $("bookingSearchInput").addEventListener("input", (event) => {
    state.bookingQuery = event.target.value.trim().toLowerCase();
    renderBookings();
  });
  $("userSearchInput")?.addEventListener("input", (event) => {
    state.userQuery = event.target.value.trim().toLowerCase();
    renderUsers();
  });
  $("adminCoachSearchInput")?.addEventListener("input", (event) => {
    state.adminCoachQuery = event.target.value.trim().toLowerCase();
    renderAdmin();
  });
  $("reloadAdminCoachSettingsBtn")?.addEventListener("click", () => loadAdminCoachSettings());
  $("reloadUsersBtn")?.addEventListener("click", () => loadUsers());
  $("coachApplyForm")?.addEventListener("submit", submitCoachApplication);
}

function render() {
  if (["bookings", "admin", "users"].includes(state.activeView) && !isAdminUser()) state.activeView = "market";
  document.querySelectorAll(".nav-item").forEach((button) => {
    button.classList.toggle("active", button.dataset.view === state.activeView);
  });
  document.querySelectorAll(".view").forEach((view) => view.classList.remove("active"));
  $(`${state.activeView}View`).classList.add("active");
  renderMetrics();
  renderUserActions();
  renderRoleMenu();
  renderSidebarCoaches();
  renderMarket();
  renderStudentHome();
  renderBookings();
  renderAdmin();
  renderUsers();
  renderCoachRequests();
  renderCoachSelf();
  maybeLoadCoachDashboardReservations();
  maybeLoadStudentReservations();
}

function renderMetrics() {
  const ratings = state.coaches.map((coach) => coach.rating).filter(Boolean);
  const average = ratings.length ? ratings.reduce((a, b) => a + b, 0) / ratings.length : 0;
  if ($("metricCoaches")) $("metricCoaches").textContent = state.coaches.length;
  if ($("metricBookings")) $("metricBookings").textContent = state.bookings.length;
  if ($("metricRating")) $("metricRating").textContent = average.toFixed(1);
}

async function openAdminView(nextView) {
  if (!["bookings", "admin", "users", "coachSelf"].includes(nextView)) return;
  const allowed = nextView === "coachSelf" && isCoachUser()
    ? true
    : await ensureAdminAccess();
  if (!allowed) return;
  if (nextView === "coachSelf" && !isAdminUser()) {
    state.coachSelfKey = getFallbackCoachKey();
  }
  state.activeView = nextView;
  document.querySelector(".admin-menu")?.removeAttribute("open");
  render();
  if (nextView === "bookings") {
    loadReservations({ promptForLogin: false });
    loadAdminRefundRequests();
  } else if (nextView === "admin") {
    loadAdminCoachSettings();
  } else if (nextView === "users") {
    loadUsers();
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
    render();
  });
  $("openCoachApplyMenuBtn")?.addEventListener("click", () => {
    state.activeView = "coachApply";
    render();
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
  render();
}

function handleDiscordButtonClick() {
  if (!state.currentUser) {
    openAuthModal("login");
    return;
  }
  const connected = Boolean(state.currentUser.discordConnected || state.currentUser.discord_connected || state.currentUser.discordDisplayName || state.currentUser.discord_display_name);
  if (connected) {
    state.activeView = "student";
    render();
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
      render();
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
    state.currentUser = await updateCurrentUser({ displayName: nickname, nickname });
    if (status) {
      status.textContent = `저장 완료 · 다음 변경 가능: ${formatDateTime(state.currentUser.nicknameChangeAvailableAt || state.currentUser.nickname_change_available_at || "") || "변경 가능"}`;
      status.className = "save-status success";
    }
    render();
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
    render();
  } catch (error) {
    alert(`회원탈퇴를 처리하지 못했습니다.\n${getAuthErrorMessage(error.message)}`);
  }
}

function renderStudentHome() {
  const container = $("studentViewContent");
  if (!container) return;
  if (isCoachUser()) {
    renderCoachDashboard(container);
    mountAccountPanel(container);
    if (state.coachScheduleLoadState === "idle") loadCoachSchedule();
    return;
  }
  setStudentHeader(false);
  if (!state.currentUser) {
    container.innerHTML = `<div class="student-empty"><strong>로그인이 필요합니다.</strong><span>로그인하면 실제 예약과 결제 내역을 확인할 수 있습니다.</span><button class="primary" id="studentLoginBtn" type="button">로그인</button></div>`;
    $("studentLoginBtn")?.addEventListener("click", () => openAuthModal("login"));
    return;
  }
  if (state.studentReservationLoadState === "loading" || state.studentReservationLoadState === "idle") {
    container.innerHTML = `<div class="student-empty"><strong>예약 내역을 불러오는 중입니다.</strong></div>`;
    mountAccountPanel(container);
    return;
  }
  if (state.studentReservationLoadState === "error") {
    container.innerHTML = `<div class="student-empty"><strong>예약 내역을 불러오지 못했습니다.</strong><span>${escapeHtml(state.studentReservationLoadError)}</span></div>`;
    mountAccountPanel(container);
    return;
  }
  const historyRows = state.bookings;
  const paidRows = historyRows.filter((row) => ["PAID", "PARTIALLY_REFUNDED"].includes(paymentStatus(row)));
  const payableRows = historyRows.filter((row) => ["신규", "상담중", "결제대기", "코치확정대기", "예약확정"].includes(row.status) && !["PAID", "PARTIALLY_REFUNDED", "CANCELED", "REFUNDED"].includes(paymentStatus(row)));
  const reviewableRows = historyRows.filter((row) => row.status === "완료" && paymentStatus(row) === "PAID" && !row.review && !state.submittedReviewIds.includes(row.id));
  const nextLesson = historyRows.find((row) => !["완료", "취소"].includes(row.status));
  const paidAmount = paidRows.reduce((sum, row) => sum + Number(row.payment?.amount || 0), 0);

  container.innerHTML = `
    <section class="student-hero">
      <article class="student-hero-card">
        <span>결제 완료</span>
        <strong>${formatWon(paidAmount)}</strong>
        <p>토스페이먼츠 승인이 완료된 실제 결제 합계입니다.</p>
        <em>${paidRows.length}건 결제 완료</em>
      </article>
      <article class="student-hero-card highlight">
        <span>다음 일정</span>
        <strong>${nextLesson ? escapeHtml(nextLesson.time || "시간 확인 중") : "예약 대기"}</strong>
        <p>${nextLesson ? escapeHtml(nextLesson.lesson || "예약 강의") : "강의 상세보기에서 신청하면 이곳에 표시됩니다."}</p>
        <em>${nextLesson ? escapeHtml(nextLesson.status || "접수") : "예약된 강의 없음"}</em>
      </article>
      <article class="student-hero-card reward">
        <span>결제 대기</span>
        <strong>${payableRows.length}건</strong>
        <p>운영진이 예약 시간을 확정하면 안전하게 결제할 수 있습니다.</p>
        <em>현재는 테스트 결제만 가능</em>
      </article>
    </section>

    <section class="student-flow">
      <div><span>1</span><strong>강의 선택</strong><p>목록이나 맞춤 검색에서 코치를 고릅니다.</p></div>
      <div><span>2</span><strong>일정 확정</strong><p>운영진과 가능한 시간을 먼저 확정합니다.</p></div>
      <div><span>3</span><strong>안전 결제</strong><p>확정된 예약만 토스 결제창으로 결제합니다.</p></div>
    </section>

    <section class="student-main-grid">
      <article class="student-panel student-history-panel">
        <div class="student-panel-head">
          <span>내역</span>
          <strong>강의 구매 / 신청 내역</strong>
        </div>
        <div class="student-timeline">
          ${historyRows.map((row) => `
            <div class="student-row">
              <em>${escapeHtml(row.status)}</em>
              <span>
                <strong>${escapeHtml(row.lesson)}</strong>
                <small>${escapeHtml(row.coachName)} · ${escapeHtml(row.coachPrice)} · ${escapeHtml(row.time)}</small>
                <small class="student-review-state">${escapeHtml(paymentStatusLabel(row))}</small>
              </span>
              <div class="student-actions">
                ${["신규", "상담중", "결제대기", "코치확정대기", "예약확정"].includes(row.status) && !["PAID", "PARTIALLY_REFUNDED", "CANCELED", "REFUNDED"].includes(paymentStatus(row)) ? `<button class="primary mini" type="button" data-pay-reservation="${escapeHtml(row.id)}">결제하기</button>` : ""}
                ${!['완료', '취소'].includes(row.status) && !getRefundRequestFor(row) ? `<button class="secondary mini" type="button" data-cancel-request="${escapeHtml(row.id)}">취소·환불 요청</button>` : ""}
                ${getRefundRequestFor(row) ? `<small class="student-review-state">${escapeHtml(refundRequestLabel(getRefundRequestFor(row)))}</small>` : ""}
              </div>
            </div>
          `).join("") || `
            <div class="student-empty">
              <strong>내역이 없습니다.</strong>
              <span>구매나 예약이 생기면 이 목록에서 확인합니다.</span>
            </div>
          `}
        </div>
      </article>

      <article class="student-panel student-review-panel">
        <div class="student-panel-head">
          <span>후기</span>
          <strong>후기 / 결제 안내</strong>
        </div>
        ${reviewableRows.length ? `
          <div class="student-review-list">
            ${reviewableRows.map((row) => `
              <form class="student-review-card" data-review-form="${escapeHtml(row.id)}">
                <strong>${escapeHtml(row.lesson)}</strong>
                <span>수업 완료 · 후기 작성</span>
                <label>별점<select name="rating"><option value="5">5점</option><option value="4">4점</option><option value="3">3점</option><option value="2">2점</option><option value="1">1점</option></select></label>
                <label>후기<textarea name="content" rows="3" required placeholder="수업에서 도움받은 점을 남겨주세요."></textarea></label>
                <button class="primary" type="submit">후기 등록</button>
              </form>
            `).join("")}
          </div>
        ` : ""}
        ${payableRows.length ? `
          <div class="student-review-list">
            ${payableRows.map((row) => `
              <div class="student-review-card">
                <strong>${escapeHtml(row.lesson)}</strong>
                <span>${escapeHtml(row.coachPrice)} · ${escapeHtml(row.time)}</span>
                <p>서버에 저장된 상품 가격으로 주문을 만들며, 브라우저에서 보낸 금액은 사용하지 않습니다.</p>
                <button class="primary" type="button" data-pay-reservation="${escapeHtml(row.id)}">토스로 결제하기</button>
              </div>
            `).join("")}
          </div>
        ` : ""}
        ${!reviewableRows.length && !payableRows.length ? `
          <div class="student-empty">
            <strong>결제할 예약이 없습니다.</strong>
            <span>예약이 확정되면 결제 버튼이 표시됩니다.</span>
          </div>
        ` : ""}
      </article>
    </section>
  `;
  mountAccountPanel(container);
  document.querySelectorAll("[data-pay-reservation]").forEach((button) => {
    button.addEventListener("click", () => startTossPayment(button.dataset.payReservation, button));
  });
  document.querySelectorAll("[data-cancel-request]").forEach((button) => {
    button.addEventListener("click", () => requestReservationCancel(button.dataset.cancelRequest));
  });
  document.querySelectorAll("[data-review-form]").forEach((form) => {
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      submitReservationReview(form.dataset.reviewForm, form);
    });
  });
}

function setStudentHeader(isCoach) {
  const head = $("studentView")?.querySelector(".student-head");
  if (!head) return;
  const eyebrow = head.querySelector(".eyebrow");
  const title = head.querySelector("h2");
  const balance = head.querySelector(".student-balance");
  if (isCoach) {
    if (eyebrow) eyebrow.textContent = "코치 개인 화면";
    if (title) title.textContent = "내 정보";
    if (balance) balance.innerHTML = "<span>집계 기준</span><strong>완료 예약</strong>";
  } else {
    if (eyebrow) eyebrow.textContent = "수강생 화면";
    if (title) title.textContent = "내 강의 홈";
    if (balance) balance.innerHTML = "<span>사용 가능 포인트</span><strong>0원</strong>";
  }
}

function renderCoachDashboard(container) {
  setStudentHeader(true);
  if (state.coachDashboardLoadState === "loading") {
    container.innerHTML = `
      <section class="student-panel coach-dashboard-state">
        <strong>코치 예약 통계를 불러오는 중입니다.</strong>
        <span>완료된 예약과 수강생 목록을 확인하고 있습니다.</span>
      </section>
    `;
    return;
  }
  if (state.coachDashboardLoadState === "error") {
    container.innerHTML = `
      <section class="student-panel coach-dashboard-state error">
        <strong>코치 예약 통계를 불러오지 못했습니다.</strong>
        <span>${escapeHtml(state.coachDashboardLoadError || "잠시 후 다시 시도해주세요.")}</span>
      </section>
    `;
    return;
  }

  const reservations = state.bookings;
  const completed = reservations.filter((booking) => String(booking.status || "") === "완료");
  const active = reservations.filter((booking) => String(booking.status || "") !== "취소");
  const totals = completed.reduce((result, booking) => {
    const parsed = parseReservationPrice(booking.coachPrice);
    result.hours += parsed.hours;
    result.revenue += parsed.amount;
    return result;
  }, { hours: 0, revenue: 0 });
  const students = new Set(completed.map((booking) => `${booking.student || ""}|${booking.contact || ""}`).filter((value) => value !== "|"));
  const history = reservations.slice(0, 30);

  container.innerHTML = `
    <section class="coach-summary-grid">
      <article class="coach-summary-card"><span>판매 시간</span><strong>${totals.hours.toLocaleString("ko-KR")}시간</strong><small>완료된 시간제 강의 기준</small></article>
      <article class="coach-summary-card"><span>예상 매출</span><strong>${formatWon(totals.revenue)}</strong><small>결제 연동 전 예약 금액 합계</small></article>
      <article class="coach-summary-card"><span>완료 수강생</span><strong>${students.size.toLocaleString("ko-KR")}명</strong><small>완료 예약의 고유 수강생</small></article>
      <article class="coach-summary-card"><span>전체 예약</span><strong>${active.length.toLocaleString("ko-KR")}건</strong><small>취소 제외 · 완료 ${completed.length.toLocaleString("ko-KR")}건</small></article>
    </section>
    <section class="student-panel coach-history-panel">
      <div class="student-panel-head">
        <span>예약 내역</span>
        <strong>내 강의 수강생 목록</strong>
      </div>
      <p class="coach-dashboard-note">매출과 판매 시간은 현재 <b>완료</b> 상태인 예약만 집계합니다. 결제 연동 후 실제 결제 금액으로 교체됩니다.</p>
      <div class="coach-history-list">
        ${history.length ? history.map((booking) => `
          <div class="coach-history-row">
            <em>${escapeHtml(booking.status || "신규")}</em>
            <span><strong>${escapeHtml(booking.student || "수강생")}</strong><small>${escapeHtml(booking.lesson || booking.coachName || "강의")} · ${escapeHtml(booking.time || "시간 미정")} · ${escapeHtml(booking.contact || "연락처 없음")}</small></span>
            <small>${escapeHtml(booking.createdAtText || "-")} · ${escapeHtml(booking.coachPrice || "가격 상담")}</small>
            ${booking.status === "코치확정대기" && paymentStatus(booking) === "PAID" ? `<button class="primary mini" type="button" data-coach-confirm-reservation="${escapeHtml(booking.id)}">구매 확정</button>` : ""}
          </div>
        `).join("") : `
          <div class="student-empty"><strong>예약 내역이 없습니다.</strong><span>예약이 접수되면 이곳에서 수강생과 상태를 확인할 수 있습니다.</span></div>
        `}
      </div>
    </section>
  `;
  document.querySelectorAll("[data-coach-confirm-reservation]").forEach((button) => {
    button.addEventListener("click", () => confirmCoachReservation(button.dataset.coachConfirmReservation, button));
  });
}

async function confirmCoachReservation(reservationId, button) {
  if (!reservationId || !window.confirm("이 강의 일정과 구매를 확정할까요?")) return;
  const originalText = button.textContent;
  button.disabled = true;
  button.textContent = "확정 중";
  try {
    await confirmCoachReservationRequest(reservationId);
    await loadCoachReservations();
    alert("구매와 일정이 확정되었습니다.");
  } catch (error) {
    alert(`구매를 확정하지 못했습니다.\n${error.message}`);
    button.disabled = false;
    button.textContent = originalText;
  }
}

function getCoachKey(coach) {
  return String(coach?.coachKey || coach?.id || "");
}

function getCoachIdentityFromGroup(coachKey, coaches) {
  const first = coaches[0] || {};
  return {
    key: coachKey,
    name: first.coachProfileName || first.coachNickname || first.nickname || first.name || "코치",
    tier: first.coachTier || first.profileTier || first.tier || "일반",
    tagline: first.coachSummary || first.coachIntro || first.intro || first.tagline || "코칭 상품",
    roles: first.coachRoles || first.roles || [],
    image: first.coachImage || first.profileImage || first.image || "assets/logo.jpg",
    imagePosition: first.coachImagePosition || first.imagePosition || "center 8%",
    lessons: coaches.length,
    rating: coaches.reduce((sum, coach) => sum + Number(coach.rating || 0), 0) / Math.max(coaches.length, 1),
    products: coaches,
  };
}

function getCoachIdentities(category = state.category, includeInactive = false) {
  const grouped = new Map();
  state.coaches
    .filter((coach) => coach.category === category && (includeInactive || coach.active !== false))
    .forEach((coach) => {
      const key = getCoachKey(coach);
      if (!grouped.has(key)) grouped.set(key, []);
      grouped.get(key).push(coach);
    });
  return Array.from(grouped.entries())
    .map(([key, coaches]) => getCoachIdentityFromGroup(key, coaches))
    .sort((a, b) => (tierRank[a.tier] ?? 9) - (tierRank[b.tier] ?? 9) || a.name.localeCompare(b.name, "ko-KR"));
}

function selectCoachIdentity(coachKey) {
  state.selectedCoachKey = coachKey;
  state.selectedCoachId = null;
  state.query = "";
  state.type = "all";
  state.segment = "all";
  state.recentCoachKeys = [coachKey, ...state.recentCoachKeys.filter((key) => key !== coachKey)].slice(0, 3);
  if ($("searchInput")) $("searchInput").value = "";
}

function renderSidebarCoaches() {
  const target = $("sideCoachList");
  if (!target) return;
  const identities = getCoachIdentities();
  const selected = identities.find((coach) => coach.key === state.selectedCoachKey);
  const recent = state.recentCoachKeys
    .map((key) => identities.find((coach) => coach.key === key))
    .filter(Boolean)
    .slice(0, 3);

  target.innerHTML = `
    <button class="coach-explorer-open" id="openCoachExplorerBtn" type="button">
      <span>
        <strong>코치 목록 열기</strong>
        <small>${escapeHtml(categoryLabel(state.category))} ${identities.length}명 · ${state.coaches.filter((coach) => coach.category === state.category).length}개 강의</small>
      </span>
      <em>선택</em>
    </button>
    ${selected ? `
      <button class="selected-side-coach active" type="button" data-side-coach-key="${escapeHtml(selected.key)}">
        <img src="${escapeHtml(selected.image)}" alt="">
        <span>
          <strong>${escapeHtml(selected.name)}</strong>
          <small>${escapeHtml(selected.lessons)}개 강의 · ${escapeHtml(selected.tier)}</small>
        </span>
      </button>
    ` : `<p class="side-empty">아직 선택한 코치가 없습니다.</p>`}
    ${recent.length ? `
      <div class="recent-side-coaches">
        <span>최근 선택</span>
        ${recent.map((coach) => `
          <button class="recent-side-coach ${coach.key === state.selectedCoachKey ? "active" : ""}" type="button" data-side-coach-key="${escapeHtml(coach.key)}">
            <img src="${escapeHtml(coach.image)}" alt="">
            <strong>${escapeHtml(coach.name)}</strong>
          </button>
        `).join("")}
      </div>
    ` : ""}
  `;

  $("openCoachExplorerBtn")?.addEventListener("click", openCoachExplorer);
  target.querySelectorAll("[data-side-coach-key]").forEach((button) => {
    button.addEventListener("click", () => {
      selectCoachIdentity(button.dataset.sideCoachKey);
      state.activeView = "market";
      render();
    });
  });
}

function openCoachExplorer() {
  const modal = $("coachExplorerModal");
  if (!modal) return;
  modal.hidden = false;
  if ($("coachExplorerSearch")) $("coachExplorerSearch").value = state.coachExplorerQuery;
  renderCoachExplorer();
  setTimeout(() => $("coachExplorerSearch")?.focus(), 0);
}

function closeCoachExplorer() {
  const modal = $("coachExplorerModal");
  if (modal) modal.hidden = true;
}

function getCoachExplorerFilters() {
  const activeSet = getActiveFilterSet();
  const roleFilters = activeSet.segment.filter((item) => item.id !== "all");
  const tierFilters = ["엠버서더", "최우수", "우수", "일반"]
    .filter((tier) => getCoachIdentities().some((coach) => coach.tier === tier))
    .map((tier) => ({ id: tier, label: tier }));
  return { roleFilters, tierFilters };
}

function getVisibleExplorerCoaches() {
  return getCoachIdentities().filter((coach) => {
    const products = coach.products || [];
    const inRole = state.coachExplorerRole === "all" || products.some((product) => getCoachPurposes(product).includes(state.coachExplorerRole));
    const inTier = state.coachExplorerTier === "all" || coach.tier === state.coachExplorerTier;
    const productText = products.map((product) => {
      const purposeLabel = getPurposeLabels(product.purpose).join(" ");
      return [product.name, product.tagline, product.bio, purposeLabel, ...(product.roles || []), ...(product.badges || [])].join(" ");
    }).join(" ");
    const haystack = [coach.name, coach.tier, coach.tagline, ...(coach.roles || []), productText].join(" ").toLowerCase();
    return inRole && inTier && (!state.coachExplorerQuery || haystack.includes(state.coachExplorerQuery));
  });
}

function renderCoachExplorer() {
  const modal = $("coachExplorerModal");
  if (!modal || modal.hidden) return;
  const { roleFilters, tierFilters } = getCoachExplorerFilters();
  if (state.coachExplorerRole !== "all" && !roleFilters.some((filter) => filter.id === state.coachExplorerRole)) {
    state.coachExplorerRole = "all";
  }
  if (state.coachExplorerTier !== "all" && !tierFilters.some((filter) => filter.id === state.coachExplorerTier)) {
    state.coachExplorerTier = "all";
  }
  $("coachExplorerTitle").textContent = `${categoryLabel(state.category)} 코치 목록`;
  $("coachExplorerMeta").textContent = `${getCoachIdentities().length}명 · ${state.coaches.filter((coach) => coach.category === state.category).length}개 강의`;
  $("coachExplorerRoleFilters").innerHTML = [{ id: "all", label: "전체" }, ...roleFilters].map((filter) => `
    <button class="explorer-filter ${state.coachExplorerRole === filter.id ? "active" : ""}" type="button" data-explorer-role="${escapeHtml(filter.id)}">
      ${escapeHtml(filter.label)}
    </button>
  `).join("");
  $("coachExplorerTierFilters").innerHTML = [{ id: "all", label: "전체 등급" }, ...tierFilters].map((filter) => `
    <button class="explorer-filter ${state.coachExplorerTier === filter.id ? "active" : ""}" type="button" data-explorer-tier="${escapeHtml(filter.id)}">
      ${escapeHtml(filter.label)}
    </button>
  `).join("");

  const visible = getVisibleExplorerCoaches();
  $("coachExplorerGrid").innerHTML = visible.length ? visible.map(renderCoachExplorerCard).join("") : `
    <div class="empty">조건에 맞는 코치가 없습니다.</div>
  `;
  document.querySelectorAll("[data-explorer-role]").forEach((button) => {
    button.addEventListener("click", () => {
      state.coachExplorerRole = button.dataset.explorerRole;
      renderCoachExplorer();
    });
  });
  document.querySelectorAll("[data-explorer-tier]").forEach((button) => {
    button.addEventListener("click", () => {
      state.coachExplorerTier = button.dataset.explorerTier;
      renderCoachExplorer();
    });
  });
  document.querySelectorAll("[data-explorer-coach-key]").forEach((button) => {
    button.addEventListener("click", () => {
      selectCoachIdentity(button.dataset.explorerCoachKey);
      closeCoachExplorer();
      state.activeView = "market";
      render();
      $("coachDetail")?.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  });
}

function renderCoachExplorerCard(coach) {
  const productCount = coach.lessons || 0;
  const roleText = (coach.roles || []).slice(0, 4).join(" · ");
  const badges = ["추천", coach.tier].slice(0, 2).map((badge) => `<span>${escapeHtml(badge)}</span>`).join("");
  return `
    <button class="explorer-coach-card ${coach.key === state.selectedCoachKey ? "active" : ""}" type="button" data-explorer-coach-key="${escapeHtml(coach.key)}">
      <img src="${escapeHtml(coach.image)}" alt="" style="object-position: ${escapeHtml(coach.imagePosition)};">
      <span class="explorer-coach-body">
        <span class="explorer-card-head">
          <strong>${escapeHtml(coach.name)}</strong>
          <em>${escapeHtml(coach.tier)}</em>
        </span>
        <small>${escapeHtml(coach.tagline || "코칭 상품")}</small>
        <span class="explorer-card-meta">${escapeHtml(roleText || "강의")}</span>
        <span class="explorer-card-foot">
          <span>${badges}</span>
          <b>${productCount}개 강의</b>
        </span>
      </span>
    </button>
  `;
}

function getVisibleCoaches() {
  return state.coaches.filter((coach) => {
    if (coach.active === false) return false;
    const inCategory = coach.category === state.category;
    const inSelectedCoach = !state.selectedCoachKey || getCoachKey(coach) === state.selectedCoachKey;
    const coachPurposes = getCoachPurposes(coach);
    const inType = state.type === "all" || coachPurposes.includes(state.type);
    const inSegment = state.segment === "all" || coachPurposes.includes(state.segment);
    const purposeLabel = getPurposeLabels(coach.purpose).join(" ");
    const haystack = [coach.name, coach.coachProfileName, coach.tier, coach.tagline, coach.coachSummary, coach.bio, purposeLabel, ...(coach.coachRoles || []), ...(coach.roles || []), ...(coach.badges || [])]
      .join(" ")
      .toLowerCase();
    return inCategory && inSelectedCoach && inType && inSegment && (!state.query || haystack.includes(state.query));
  }).sort((a, b) => {
    const tierDiff = (tierRank[a.tier] ?? 9) - (tierRank[b.tier] ?? 9);
    if (tierDiff) return tierDiff;
    return (b.rating || 0) - (a.rating || 0);
  });
}

function renderMarket() {
  const filters = getActiveFilterSet();
  $("categoryTabs").innerHTML = categories.map((category) => `
    <button class="tab ${category.id === state.category ? "active" : ""}" data-category="${category.id}">
      ${category.label}
    </button>
  `).join("");

  document.querySelectorAll(".tab").forEach((tab) => {
    tab.addEventListener("click", () => {
      state.category = tab.dataset.category;
      state.type = "all";
      state.segment = "all";
      state.selectedCoachId = null;
      state.selectedCoachKey = null;
      renderMarket();
      renderSidebarCoaches();
    });
  });

  $("typeTabs").innerHTML = filters.type.map((filter) => `
    <button class="purpose-tab ${filter.id === state.type ? "active" : ""}" data-type="${filter.id}">
      ${filter.label}
    </button>
  `).join("");

  $("segmentTabs").innerHTML = filters.segment.map((filter) => `
    <button class="purpose-tab ${filter.id === state.segment ? "active" : ""}" data-segment="${filter.id}">
      ${filter.label}
    </button>
  `).join("");

  document.querySelectorAll("[data-type]").forEach((tab) => {
    tab.addEventListener("click", () => {
      state.type = tab.dataset.type;
      state.selectedCoachId = null;
      state.selectedCoachKey = null;
      renderMarket();
    });
  });

  document.querySelectorAll("[data-segment]").forEach((tab) => {
    tab.addEventListener("click", () => {
      state.segment = tab.dataset.segment;
      state.selectedCoachId = null;
      state.selectedCoachKey = null;
      renderMarket();
    });
  });

  if (state.coachLoadState === "idle" || state.coachLoadState === "loading") {
    $("featuredSection").hidden = true;
    $("featuredList").innerHTML = "";
    $("coachList").innerHTML = `<div class="empty">코치 목록을 불러오는 중입니다.</div>`;
    state.selectedCoachId = null;
    renderDetail();
    return;
  }

  if (state.coachLoadState === "error") {
    $("featuredSection").hidden = true;
    $("featuredList").innerHTML = "";
    $("coachList").innerHTML = `<div class="empty">코치 목록을 불러오지 못했습니다.<br><button class="secondary" type="button" onclick="loadCoachesFromApi()">다시 불러오기</button></div>`;
    state.selectedCoachId = null;
    renderDetail();
    return;
  }

  const visible = getVisibleCoaches();
  if (state.selectedCoachId && !visible.some((coach) => coach.id === state.selectedCoachId)) {
    state.selectedCoachId = null;
    renderSidebarCoaches();
  }
  if (state.selectedCoachKey && !state.selectedCoachId && visible.length) {
    state.selectedCoachId = visible[0].id;
  }

  renderFeatured(visible);
  const featuredIds = new Set(
    Array.from(document.querySelectorAll("#featuredList [data-coach-id]")).map((card) => card.dataset.coachId)
  );
  const listed = visible.filter((coach) => !featuredIds.has(coach.id));
  $("coachList").innerHTML = listed.length ? listed.map((coach) => renderCoachCard(coach, state.selectedCoachId)).join("") : `
    <div class="empty">검색 결과가 없습니다.</div>
  `;
  document.querySelectorAll("[data-coach-id]").forEach((card) => {
    card.addEventListener("click", (event) => {
      if (event.target.closest("[data-detail-id]")) return;
      state.selectedCoachId = card.dataset.coachId;
      renderMarket();
    });
  });
  document.querySelectorAll("[data-detail-id]").forEach((button) => {
    button.addEventListener("click", (event) => {
      event.stopPropagation();
      openLessonDetail(button.dataset.detailId);
    });
  });
  renderDetail();
}

function getActiveFilterSet() {
  return filterSets[state.category] || filterSets.league;
}

function renderFeatured(visible) {
  const featured = getFeaturedCoachSlots(visible);
  const section = $("featuredSection");
  const isMainCatalog = !state.query && !state.selectedCoachKey && state.type === "all" && state.segment === "all";
  if (!featured.length || !isMainCatalog) {
    section.hidden = true;
    $("featuredList").innerHTML = "";
    return;
  }
  section.hidden = false;
  $("featuredList").innerHTML = featured.map(renderFeaturedCard).join("");
}

function getFeaturedScore(coach) {
  return Number(coach.lessons || 0) * 10 + Number(coach.reviews?.length || 0);
}

function chooseFeaturedCoachLesson(coaches) {
  const promoted = coaches
    .filter((coach) => coach.featuredAd)
    .sort((a, b) => String(b.featuredAdUpdatedAt || "").localeCompare(String(a.featuredAdUpdatedAt || "")) || getFeaturedScore(b) - getFeaturedScore(a))[0];
  if (promoted) return promoted;
  return [...coaches].sort((a, b) => getFeaturedScore(b) - getFeaturedScore(a))[0];
}

function getFeaturedCoachSlots(visible) {
  const eligible = visible.filter((coach) => coach.category === state.category && ["엠버서더", "최우수"].includes(coach.tier));
  const grouped = new Map();
  eligible.forEach((coach) => {
    const key = getCoachKey(coach);
    if (!grouped.has(key)) grouped.set(key, []);
    grouped.get(key).push(coach);
  });
  return [...grouped.values()]
    .map(chooseFeaturedCoachLesson)
    .filter(Boolean)
    .sort((a, b) => (tierRank[a.tier] ?? 9) - (tierRank[b.tier] ?? 9) || getFeaturedScore(b) - getFeaturedScore(a));
}


function renderDetail() {
  const coach = state.coaches.find((item) => item.id === state.selectedCoachId);
  if (!coach) {
    $("coachDetail").innerHTML = `
      <div class="detail-empty">
        <strong>상품을 선택하면 미리보기가 표시됩니다.</strong>
        <span>상세보기에서 설명, 후기, 강의 구매를 한 번에 확인할 수 있습니다.</span>
      </div>
    `;
    return;
  }

  const reviews = coach.reviews || [];
  $("coachDetail").innerHTML = `
    <div class="detail-hero"><img src="${escapeHtml(getDetailImage(coach))}" alt="" style="${escapeHtml(getWideImageStyle(coach, "detailImagePosition"))}"></div>
    <div class="detail-body">
      <div class="rank-badges">${getCoachBadges(coach).map(renderBadge).join("")}</div>
      <h2>${escapeHtml(coach.name)}</h2>
      <p class="detail-owner">${escapeHtml(coach.coachProfileName || coach.name)} · ${escapeHtml(coach.coachSummary || coach.tier || "코치")}</p>
      <div class="detail-trust">
        <strong>★ ${coach.rating.toFixed(1)} <span>(${coach.lessons || 0})</span></strong>
        <em>${reviews.length}개 후기</em>
      </div>
      <p>${escapeHtml(coach.tagline || coach.bio)}</p>
      <div class="detail-summary">
        <div><span>가격</span><strong>${escapeHtml(coach.price)}</strong></div>
        <div><span>전문 분야</span><strong>${escapeHtml((coach.roles || []).slice(0, 4).join(", "))}</strong></div>
      </div>
      <button class="primary detail-panel-button" type="button" data-detail-id="${escapeHtml(coach.id)}">상세보기</button>
    </div>
  `;
  $("coachDetail").querySelector("[data-detail-id]")?.addEventListener("click", () => openLessonDetail(coach.id));
}

function openLessonDetail(coachId) {
  const coach = state.coaches.find((item) => item.id === coachId);
  const modal = $("lessonDetailModal");
  if (!coach || !modal) return;
  state.selectedCoachId = coach.id;
  $("lessonDetailBody").innerHTML = renderLessonDetailMarkup(coach);
  mountBookingForm("lessonBookingMount", coach);
  loadPublicAvailability(coach.id);
  loadCoachReviews(coach.id);
  modal.hidden = false;
}

function closeLessonDetail() {
  const modal = $("lessonDetailModal");
  if (modal) modal.hidden = true;
}

function getLessonFocusItems(coach) {
  const roles = (coach.roles || []).slice(0, 4);
  const purposeLabels = getPurposeLabels(coach.purpose).slice(0, 3);
  const fallback = ["리플레이 핵심 장면 점검", "라인전 습관 교정", "다음 게임 적용 과제 정리"];
  return [...roles, ...purposeLabels, ...fallback]
    .map((item) => String(item).trim())
    .filter(Boolean)
    .filter((item, index, array) => array.indexOf(item) === index)
    .slice(0, 6);
}

function getCoachDetailTone(coach) {
  const key = getCoachKey(coach);
  if (key === "shineast") return "프로팀 운영 관점으로 라인전, 오더, 팀게임 판단까지 넓게 봅니다.";
  if (key === "mephi") return "전프로 바텀 라이너 관점으로 전 라인 피드백과 팀게임 리뷰까지 가능합니다.";
  if (key === "mireu") return "저티어와 일반 수강생이 바로 따라 할 수 있게 동선과 판단 기준을 쉽게 정리합니다.";
  if (key === "persona") return "탑 라인 중심의 이론과 매치업 이해도를 차분하게 정리합니다.";
  return "현재 플레이에서 바로 고칠 수 있는 습관과 다음 연습 과제를 정리합니다.";
}

function normalizeAvailabilitySlot(slot) {
  const startsAt = slot.startsAt || slot.starts_at || slot.start || slot.startAt || "";
  const endsAt = slot.endsAt || slot.ends_at || slot.end || slot.endAt || "";
  return {
    id: String(slot.id || slot.slotId || slot.slot_id || ""),
    startsAt,
    endsAt,
    status: String(slot.status || "open").toLowerCase(),
    label: slot.label || formatDateTime(startsAt) + (endsAt ? ` ~ ${formatDateTime(endsAt)}` : ""),
    available: slot.available !== false && slot.isAvailable !== false && !["cancelled", "canceled"].includes(String(slot.status || "").toLowerCase()),
  };
}

async function loadPublicAvailability(coachId) {
  const key = String(coachId || "");
  if (!key || state.availabilityLoadStates[key] === "loading") return;
  state.availabilityLoadStates[key] = "loading";
  try {
    const fromDate = new Date();
    const range = new URLSearchParams({ from: isoDateOnly(fromDate), to: isoDateOnly(addLocalDays(fromDate, 30)) });
    const raw = await fetchCoachAvailability(key, Object.fromEntries(range));
    state.availabilityByCoach[key] = Array.isArray(raw) ? raw.map(normalizeAvailabilitySlot).filter((slot) => slot.id && slot.available && slot.status === "open") : [];
    state.availabilityLoadStates[key] = "loaded";
  } catch (error) {
    state.availabilityByCoach[key] = [];
    state.availabilityLoadStates[key] = "error";
  }
  if (String(state.selectedCoachId) === key) {
    renderAvailabilityPicker(state.coaches.find((coach) => String(coach.id) === key));
  }
}

function renderAvailabilityPicker(coach) {
  const picker = $("bookingAvailabilityPicker");
  const select = $("bookingAvailabilitySlot");
  const error = $("bookingAvailabilityError");
  const timeInput = $("bookingForm")?.elements?.time;
  const timeField = $("bookingTimeField");
  if (!picker || !select || !coach) return;
  const slots = state.availabilityByCoach[String(coach.id)] || [];
  if (!slots.length) {
    picker.hidden = true;
    if (error) error.hidden = true;
    if (timeField) timeField.hidden = false;
    select.required = false;
    if (timeInput) {
      timeInput.readOnly = false;
      timeInput.required = true;
      timeInput.placeholder = "예: 2026-08-20 21:00 (코치와 협의)";
    }
    return;
  }
  picker.hidden = false;
  if (error) error.hidden = true;
  if (timeField) timeField.hidden = true;
  select.required = true;
  select.innerHTML = `<option value="">가능한 시간을 선택하세요</option>${slots.map((slot) => `<option value="${escapeHtml(slot.id)}" data-time="${escapeHtml(slot.label)}">${escapeHtml(slot.label)}</option>`).join("")}`;
  if (timeInput) {
    timeInput.readOnly = true;
    timeInput.required = false;
    timeInput.value = "";
    select.addEventListener("change", () => {
      const option = select.selectedOptions[0];
      timeInput.value = option?.dataset.time || "";
    });
  }
}

async function loadCoachReviews(coachId) {
  const key = String(coachId || "");
  if (!key || state.reviewsByCoach[key]) return;
  try {
    const reviews = await fetchCoachReviews(key);
    state.reviewsByCoach[key] = Array.isArray(reviews) ? reviews : [];
    const coach = state.coaches.find((item) => String(item.id) === key);
    if (coach) {
      coach.reviews = state.reviewsByCoach[key].map((review) => [review.author || review.displayName || review.studentName || "수강생", review.content || review.body || ""]);
      if (String(state.selectedCoachId) === key && $("lessonDetailModal") && !$("lessonDetailModal").hidden) {
        $("lessonDetailBody").innerHTML = renderLessonDetailMarkup(coach);
        mountBookingForm("lessonBookingMount", coach);
      }
    }
  } catch {
    // Public reviews are optional; keep the catalog fallback.
  }
}

function renderLessonInfoBlocks(coach) {
  const focusItems = getLessonFocusItems(coach);
  const reviewCount = coach.reviews?.length || 0;
  return `
    <section class="lesson-info-grid">
      <article>
        <span>이 강의에서 보는 것</span>
        <ul>${focusItems.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>
      </article>
      <article>
        <span>진행 방식</span>
        <ul>
          <li>디스코드 화면공유 또는 리플레이 리뷰</li>
          <li>핵심 장면 위주로 원인과 대안을 정리</li>
          <li>끝나기 전 다음 연습 과제 확인</li>
        </ul>
      </article>
      <article>
        <span>추천 대상</span>
        <p>${escapeHtml(getCoachDetailTone(coach))}</p>
        <small>판매 ${coach.lessons || 0}회 · 후기 ${reviewCount}개 · 평점 ${coach.rating.toFixed(1)}</small>
      </article>
    </section>
  `;
}

function renderLessonDetailMarkup(coach) {
  const reviews = coach.reviews || [];
  return `
    <div class="lesson-detail-hero"><img src="${escapeHtml(getDetailImage(coach))}" alt="" style="${escapeHtml(getWideImageStyle(coach, "detailImagePosition"))}"></div>
    <div class="lesson-detail-body">
      <div class="rank-badges">${getCoachBadges(coach).map(renderBadge).join("")}</div>
      <h2 id="lessonDetailTitle">${escapeHtml(coach.name)}</h2>
      <p class="detail-owner">${escapeHtml(coach.coachProfileName || coach.name)} · ${escapeHtml(coach.coachSummary || coach.tier || "코치")}</p>
      <div class="detail-trust">
        <strong>★ ${coach.rating.toFixed(1)} <span>(${coach.lessons || 0})</span></strong>
        <em>${reviews.length}개 후기</em>
      </div>
      <p>${escapeHtml(coach.bio || coach.tagline || "")}</p>
      <div class="detail-summary">
        <div><span>가격</span><strong>${escapeHtml(coach.price)}</strong></div>
        <div><span>전문 분야</span><strong>${escapeHtml((coach.roles || []).slice(0, 5).join(", "))}</strong></div>
      </div>
      ${renderLessonInfoBlocks(coach)}
      ${reviews.length ? `
        <section class="review-preview full">
          <div>
            <strong>후기</strong>
            <span>${reviews.length}개</span>
          </div>
          ${reviews.slice(0, 3).map(([name, body]) => `<p><b>${escapeHtml(name)}</b> ${escapeHtml(body)}</p>`).join("")}
        </section>
      ` : ""}
      <section class="booking-panel">
        <div class="booking-panel-head">
          <div>
             <strong>구매하기</strong>
             <span>구매 정보를 남기면 운영진과 코치가 일정을 확인합니다.</span>
          </div>
          <em>${escapeHtml(coach.price)}</em>
        </div>
        <div class="booking-note">
          디스코드 화면공유 또는 리플레이 리뷰로 진행됩니다.
        </div>
        ${state.currentUser ? "" : `
          <div class="booking-route">
            <button class="primary" type="button" onclick="openAuthModal('login')">강의 구매</button>
            <button class="secondary" type="button" onclick="openAuthModal('guest')">비회원 강의 구매</button>
          </div>
        `}
        <div id="lessonBookingMount"></div>
      </section>
    </div>
  `;
}

function mountBookingForm(mountId, coach) {
  const mount = $(mountId);
  if (!mount) return;
  const form = $("bookingFormTemplate").content.cloneNode(true);
  mount.appendChild(form);
  $("bookingContactLabel").textContent = text.bookingContactLabel;
  $("bookingTimeLabel").textContent = text.bookingTimeLabel;
  $("bookingMemoLabel").textContent = text.bookingMemoLabel;
  $("bookingSubmitBtn").textContent = text.bookingSubmitBtn;
  $("bookingForm").contact.placeholder = "예: Discord ID";
  $("bookingForm").time.placeholder = "예: 8/10 21:00";
  $("bookingForm").memo.placeholder = "라인, 챔피언, 고민을 적어주세요.";
  const studentAuto = $("bookingStudentAuto");
  if (state.currentUser) {
    const displayName = state.currentUser.displayName || state.currentUser.nickname || state.currentUser.email || "수강생";
    $("bookingForm").student.value = displayName;
    if (studentAuto) {
      studentAuto.hidden = false;
      studentAuto.textContent = `수강생 닉네임 · ${displayName}`;
    }
    $("bookingForm").contact.value = state.currentUser.email || "";
  }
  renderAvailabilityPicker(coach);
  $("bookingForm").noValidate = true;
  $("bookingAvailabilitySlot")?.addEventListener("change", () => {
    const error = $("bookingAvailabilityError");
    if (error) error.hidden = Boolean($("bookingAvailabilitySlot").value);
  });
  $("bookingForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!state.currentUser) {
      openAuthModal("login");
      return;
    }
    if (state.currentUser.needsNickname || state.currentUser.nicknameSetupRequired || state.currentUser.nickname_setup_required) {
      alert("구매 전에 내 정보에서 닉네임을 설정해주세요.");
      state.activeView = "student";
      render();
      return;
    }
    const availabilitySlot = $("bookingAvailabilitySlot");
    if (availabilitySlot?.required && !availabilitySlot.value) {
      const error = $("bookingAvailabilityError");
      if (error) error.hidden = false;
      availabilitySlot.focus();
      return;
    }
    if (!event.target.checkValidity()) {
      event.target.reportValidity();
      return;
    }
    const submitButton = $("bookingSubmitBtn");
    const originalText = submitButton.textContent;
    submitButton.disabled = true;
    submitButton.textContent = "예약 전송 중";
    const reservation = buildReservationPayload(coach, new FormData(event.target));

    try {
      const savedReservation = await submitReservation(reservation);
      if (!savedReservation.id) throw new Error("생성된 구매 정보를 확인하지 못했습니다.");
      await startTossPayment(savedReservation.id, submitButton);
    } catch (error) {
      alert(`강의 구매를 저장하지 못했습니다.\n${error.message}`);
    } finally {
      submitButton.disabled = false;
      submitButton.textContent = originalText;
    }
  });
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
    render();
    if (isCoachUser()) await loadCoachProfile();
    await handlePaymentReturn();
  } catch {
    if (requestId !== state.authRequestId) return;
    state.currentUser = null;
    state.coachSelfLessons = null;
    state.authLoadState = "error";
    render();
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
    render();
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

function maybeLoadStudentReservations() {
  if (state.activeView !== "student" || !state.currentUser || isCoachUser() || state.studentReservationLoadState !== "idle") return;
  loadStudentReservations();
}

async function loadStudentReservations() {
  if (!state.currentUser || isCoachUser()) return;
  const requestId = state.authRequestId;
  const userId = String(state.currentUser.id || "");
  state.studentReservationLoadState = "loading";
  state.studentReservationLoadError = "";
  renderStudentHome();
  try {
    const [reservations, refundRequests] = await Promise.all([
      fetchMyReservations(),
      fetchMyRefundRequests().catch(() => []),
    ]);
    if (requestId !== state.authRequestId || userId !== String(state.currentUser?.id || "")) return;
    state.bookings = reservations;
    state.refundRequests = refundRequests;
    state.studentReservationLoadState = "loaded";
  } catch (error) {
    if (requestId !== state.authRequestId || userId !== String(state.currentUser?.id || "")) return;
    state.bookings = [];
    state.refundRequests = [];
    state.studentReservationLoadState = "error";
    state.studentReservationLoadError = error.message || "예약 API를 사용할 수 없습니다.";
  }
  renderStudentHome();
}

function getRefundRequestFor(booking) {
  return booking.refundRequest || state.refundRequests.find((request) => String(request.reservationId || request.reservation_id || request.reservation?.id || "") === String(booking.id)) || null;
}

async function requestReservationCancel(reservationId) {
  const reason = window.prompt("취소·환불 사유를 입력해주세요.", "일정 변경");
  if (!reason) return;
  try {
    await createReservationCancelRequest(reservationId, reason);
    await loadStudentReservations();
    alert("취소·환불 요청이 접수되었습니다.");
  } catch (error) {
    alert(`취소·환불 요청을 보내지 못했습니다.\n${error.message}`);
  }
}

async function submitReservationReview(reservationId, form) {
  const rating = Number(form.querySelector("[name='rating']")?.value || 0);
  const content = String(form.querySelector("[name='content']")?.value || "").trim();
  if (!rating || !content) {
    alert("별점과 후기를 입력해주세요.");
    return;
  }
  const button = form.querySelector("button[type='submit']");
  if (button) button.disabled = true;
  try {
    await createReservationReview(reservationId, rating, content);
    if (!state.submittedReviewIds.includes(reservationId)) state.submittedReviewIds.push(reservationId);
    await loadStudentReservations();
    alert("후기가 등록되었습니다.");
  } catch (error) {
    alert(`후기를 등록하지 못했습니다.\n${error.message}`);
  } finally {
    if (button) button.disabled = false;
  }
}

async function startTossPayment(reservationId, button) {
  if (!state.currentUser || typeof window.TossPayments !== "function") {
    alert("결제 모듈을 불러오지 못했습니다. 페이지를 새로고침해주세요.");
    return;
  }
  const originalText = button.textContent;
  button.disabled = true;
  button.textContent = "결제 준비 중";
  try {
    const result = await createPaymentOrder(reservationId);
    const order = result.order || {};
    const returnUrl = new URL(window.location.href);
    ["payment", "paymentKey", "orderId", "amount", "code", "message"].forEach((key) => returnUrl.searchParams.delete(key));
    returnUrl.hash = "";
    const separator = returnUrl.search ? "&" : "?";
    const payment = window.TossPayments(result.clientKey).payment({ customerKey: state.currentUser.id });
    await payment.requestPayment({
      method: "CARD",
      amount: { currency: "KRW", value: Number(order.amount) },
      orderId: order.orderId,
      orderName: order.orderName,
      successUrl: `${returnUrl.href}${separator}payment=success`,
      failUrl: `${returnUrl.href}${separator}payment=fail`,
      customerEmail: state.currentUser.email,
      customerName: state.currentUser.displayName,
    });
  } catch (error) {
    alert(`결제를 시작하지 못했습니다.\n${getPaymentErrorMessage(error.message)}`);
    button.disabled = false;
    button.textContent = originalText;
  }
}

async function handlePaymentReturn() {
  const url = new URL(window.location.href);
  const outcome = url.searchParams.get("payment");
  if (!outcome) return;
  if (outcome === "fail") {
    const code = url.searchParams.get("code") || "payment_failed";
    clearPaymentQuery(url);
    alert(getPaymentErrorMessage(code));
    return;
  }
  if (!state.currentUser) return;
  try {
    await confirmPayment({
      paymentKey: url.searchParams.get("paymentKey"),
      orderId: url.searchParams.get("orderId"),
      amount: Number(url.searchParams.get("amount")),
    });
    clearPaymentQuery(url);
    state.activeView = "student";
    state.studentReservationLoadState = "idle";
    render();
    alert("결제가 완료되었습니다.");
  } catch (error) {
    alert(`결제 승인을 완료하지 못했습니다. 페이지를 새로고침하면 다시 확인합니다.\n${getPaymentErrorMessage(error.message)}`);
  }
}

function maybeLoadCoachDashboardReservations() {
  if (state.activeView !== "student" || !isCoachUser() || state.coachDashboardLoadState !== "idle") return;
  loadCoachReservations();
}

async function loadCoachReservations() {
  if (!isCoachUser()) return;
  if (!API_BASE_URL || API_BASE_URL.includes("YOUR-COACH-API")) {
    state.coachDashboardLoadState = "error";
    state.coachDashboardLoadError = "예약 API 주소가 아직 설정되지 않았습니다.";
    renderStudentHome();
    return;
  }
  state.coachDashboardLoadState = "loading";
  state.coachDashboardLoadError = "";
  state.bookings = [];
  renderStudentHome();
  try {
    state.bookings = await fetchCoachReservations();
    state.coachDashboardLoadState = "loaded";
    renderMetrics();
    renderStudentHome();
  } catch (error) {
    state.bookings = [];
    state.coachDashboardLoadState = "error";
    state.coachDashboardLoadError = error.status === 401
      ? "코치 계정 인증이 만료되었습니다. 다시 로그인해주세요."
      : "코치 전용 예약 API가 배포되지 않았거나 일시적으로 사용할 수 없습니다.";
    renderStudentHome();
  }
}

async function loadReservations(options = {}) {
  const { promptForLogin = true, silent = false } = options;
  if (!API_BASE_URL || API_BASE_URL.includes("YOUR-COACH-API")) return;
  const requestId = ++state.bookingRequestId;
  if (!silent) {
    state.bookingLoadState = "loading";
    state.bookingLoadError = "";
    renderBookings();
  }

  try {
    const bookings = await fetchReservations();
    if (requestId !== state.bookingRequestId) return;
    state.bookings = bookings;
    state.bookingPendingStatuses = {};
    state.bookingLoadState = "loaded";
    state.bookingLoadError = "";
    renderMetrics();
    renderBookings();
  } catch (error) {
    if (error.status === 401 && promptForLogin) {
      const loggedIn = await loginForReservations();
      if (loggedIn) {
        return loadReservations({ promptForLogin: false, silent });
      }
    }
    if (!silent) {
      state.bookingLoadState = "error";
      state.bookingLoadError = "예약 목록을 불러오지 못했습니다.";
      renderBookings();
    }
  }
}

async function loadAdminRefundRequests() {
  if (state.activeView !== "bookings") return;
  const requestId = state.bookingRequestId;
  state.refundAdminLoadState = "loading";
  state.refundAdminLoadError = "";
  renderRefundAdminPanel();
  try {
    state.adminRefundRequests = await runAdminRequest(() => fetchAdminRefundRequests());
    state.refundAdminLoadState = "loaded";
  } catch (error) {
    if (requestId !== state.bookingRequestId) return;
    state.adminRefundRequests = [];
    state.refundAdminLoadState = "error";
    state.refundAdminLoadError = error.message || "환불 요청을 불러오지 못했습니다.";
  }
  renderRefundAdminPanel();
}

function renderRefundAdminPanel() {
  const panel = $("refundAdminPanel");
  if (!panel) return;
  if (state.refundAdminLoadState === "idle") {
    panel.innerHTML = `<div class="refund-admin-empty">환불 요청을 불러오려면 새로고침을 눌러주세요.</div>`;
    return;
  }
  if (state.refundAdminLoadState === "loading") {
    panel.innerHTML = `<div class="refund-admin-empty">환불 요청을 불러오는 중입니다.</div>`;
    return;
  }
  if (state.refundAdminLoadState === "error") {
    panel.innerHTML = `<div class="refund-admin-empty error">${escapeHtml(state.refundAdminLoadError || "환불 요청을 불러오지 못했습니다.")} <button type="button" class="secondary mini" id="reloadRefundRequestsBtn">다시 시도</button></div>`;
    $("reloadRefundRequestsBtn")?.addEventListener("click", loadAdminRefundRequests);
    return;
  }
  const requests = state.adminRefundRequests || [];
  panel.innerHTML = `
    <div class="refund-admin-head"><div><span>환불 관리</span><strong>수강생 취소·환불 요청</strong></div><button type="button" class="secondary" id="reloadRefundRequestsBtn">새로고침</button></div>
    ${requests.length ? `<div class="refund-admin-list">${requests.map((request) => `
      <article class="refund-admin-row">
        <div><strong>${escapeHtml(request.studentName)} · ${escapeHtml(request.coachName)}</strong><small>${escapeHtml(request.preferredTime)} · ${escapeHtml(request.createdAt ? formatDateTime(request.createdAt) : "접수 시간 미상")}</small></div>
        <div><span class="chip">${escapeHtml(refundAdminStatusLabel(request.status))}</span><small>${escapeHtml(request.reason)}</small></div>
        ${request.status === "pending" ? `<div class="booking-actions"><button type="button" class="mini primary-mini" data-refund-approve="${escapeHtml(request.id)}">승인</button><button type="button" class="mini danger-mini" data-refund-reject="${escapeHtml(request.id)}">거절</button></div>` : `<small>${escapeHtml(request.note || "처리 메모 없음")}</small>`}
      </article>
    `).join("")}</div>` : `<div class="refund-admin-empty">환불 요청이 없습니다.</div>`}
  `;
  $("reloadRefundRequestsBtn")?.addEventListener("click", loadAdminRefundRequests);
  document.querySelectorAll("[data-refund-approve]").forEach((button) => button.addEventListener("click", async () => {
    const controls = [...(button.closest("article")?.querySelectorAll("button") || [])];
    controls.forEach((item) => { item.disabled = true; });
    try { await decideRefundRequest(button.dataset.refundApprove, "approved"); }
    finally { controls.forEach((item) => { item.disabled = false; }); }
  }));
  document.querySelectorAll("[data-refund-reject]").forEach((button) => button.addEventListener("click", async () => {
    const controls = [...(button.closest("article")?.querySelectorAll("button") || [])];
    controls.forEach((item) => { item.disabled = true; });
    try { await decideRefundRequest(button.dataset.refundReject, "rejected"); }
    finally { controls.forEach((item) => { item.disabled = false; }); }
  }));
}

async function decideRefundRequest(requestId, status) {
  const label = status === "approved" ? "승인" : "거절";
  if (!window.confirm(`이 환불 요청을 ${label} 처리할까요?`)) return;
  const note = window.prompt("처리 메모(선택)", status === "approved" ? "환불 승인" : "환불 정책에 따른 거절");
  if (note === null) return;
  try {
    const updated = await updateRefundRequest(requestId, status, note);
    state.adminRefundRequests = state.adminRefundRequests.map((request) => request.id === requestId ? { ...request, ...updated } : request);
    renderRefundAdminPanel();
    await loadReservations({ promptForLogin: false, silent: true });
  } catch (error) {
    if (error.status === 401) {
      const loggedIn = await loginForReservations();
      if (loggedIn) return decideRefundRequest(requestId, status);
    }
    alert(`환불 요청을 처리하지 못했습니다.\n${error.message}`);
  }
}

async function runAdminRequest(callback) {
  try {
    return await callback();
  } catch (error) {
    if (error.status === 401) {
      sessionStorage.removeItem(ADMIN_TOKEN_KEY);
      const loggedIn = await loginForReservations();
      if (loggedIn) return callback();
    }
    throw error;
  }
}

async function loadCoachesFromApi() {
  if (!API_BASE_URL || API_BASE_URL.includes("YOUR-COACH-API")) {
    state.coaches = [];
    state.coachLoadState = "error";
    render();
    return;
  }
  const hasLoadedCoaches = state.coaches.length > 0;
  if (!hasLoadedCoaches) {
    state.coachLoadState = "loading";
    render();
  }
  let lastError;
  for (let attempt = 0; attempt < 2; attempt += 1) {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), COACH_API_TIMEOUT_MS);
    try {
      const coaches = await fetchCoachCatalog({ signal: controller.signal });
      if (Array.isArray(coaches)) {
        state.coaches = getPublicCatalogCoaches(coaches);
        if (state.selectedCoachId && !state.coaches.some((coach) => coach.id === state.selectedCoachId)) {
          state.selectedCoachId = null;
        }
        state.coachLoadState = state.coaches.length ? "loaded" : "empty";
        render();
        return;
      }
    } catch (error) {
      lastError = error;
    } finally {
      clearTimeout(timeoutId);
    }
  }
  state.coachLoadState = hasLoadedCoaches ? "loaded" : "error";
  console.warn("코치 목록을 불러오지 못했습니다.", lastError);
  render();
}

async function loadAdminCoachSettings() {
  const requestId = ++state.adminCoachSettingsRequestId;
  state.adminCoachSettingsLoadState = "loading";
  state.adminCoachSettingsLoadError = "";
  renderAdmin();
  try {
    const settings = await runAdminRequest(() => fetchAdminCoachSettings(state.coaches));
    if (requestId !== state.adminCoachSettingsRequestId) return;
    state.adminCoachSettings = settings;
    state.adminCoachSettingsLoadState = "loaded";
    if (state.adminSelectedCoachKey && !state.adminCoachSettings.some((item) => item.coachKey === state.adminSelectedCoachKey)) {
      state.adminSelectedCoachKey = "";
    }
  } catch (error) {
    if (requestId !== state.adminCoachSettingsRequestId) return;
    state.adminCoachSettings = [];
    state.adminCoachSettingsLoadState = "error";
    state.adminCoachSettingsLoadError = error.message || "코치 목록을 불러오지 못했습니다.";
  }
  renderAdmin();
}

function applyCoachProfileToCatalog(profile) {
  if (!profile) return;
  const coachKey = String(profile.coachKey || profile.coach_key || state.currentUser?.coachKey || getFallbackCoachKey());
  if (!coachKey) return;
  const hasRoles = Array.isArray(profile.roles);
  state.coaches = migrateCoachImages(state.coaches.map((coach) => {
    if (getCoachKey(coach) !== coachKey) return coach;
    return {
      ...coach,
      coachKey,
      coachProfileName: profile.nickname || profile.name || profile.displayName || coach.coachProfileName,
      coachSummary: profile.intro || profile.tagline || coach.coachSummary,
      coachTier: profile.tier || coach.coachTier,
      tier: profile.tier || coach.tier,
      coachRoles: hasRoles ? profile.roles : coach.coachRoles,
      coachImage: profile.image || profile.profileImage || coach.coachImage,
      active: profile.active !== undefined ? Boolean(profile.active) : coach.active,
    };
  }));
}

async function loadCoachProfile() {
  if (!state.currentUser || !isCoachUser() || !API_BASE_URL || API_BASE_URL.includes("YOUR-COACH-API")) return;
  state.coachProfile = null;
  state.coachProfileLoadState = "loading";
  state.coachProfileLoadError = "";
  renderCoachSelf();
  try {
    state.coachProfile = await fetchCoachProfile();
    await loadCoachSelfLessonsApi();
    applyCoachProfileToCatalog(state.coachProfile);
    state.coachProfileLoadState = "loaded";
  } catch (error) {
    state.coachProfileLoadState = "error";
    state.coachProfileLoadError = error.message || "프로필을 불러오지 못했습니다.";
    console.warn("코치 프로필을 불러오지 못했습니다.", error);
  }
  render();
}

async function loadCoachSelfLessonsApi() {
  state.coachSelfLessons = migrateCoachImages(await fetchCoachLessons());
  return state.coachSelfLessons;
}

async function saveCoachProfileApi(payload) {
  return saveCoachProfile(payload);
}

async function saveCoachLessonToApi(lesson) {
  return saveCoachLesson(lesson);
}

async function createCoachLessonApi(name) {
  return createCoachLesson(name);
}

async function deleteCoachLessonApi(id) {
  await deleteCoachLesson(id);
}

async function resetCoachesToSamples() {
  const nextCoaches = structuredClone(samples);
  try {
    const response = await runAdminRequest(() => resetCoachesInApi(nextCoaches));
    state.coaches = migrateCoachImages(response.coaches || nextCoaches);
    state.selectedCoachId = null;
    render();
  } catch (error) {
    alert(`코치 샘플을 DB에 저장하지 못했습니다.\n${error.message}`);
  }
}

async function loadUsers() {
  const requestId = ++state.userRequestId;
  state.userLoadState = "loading";
  state.coachRequestLoadState = "loading";
  state.userLoadError = "";
  state.coachRequestLoadError = "";
  renderUsers();
  renderCoachRequests();
  try {
    const [users, requests] = await Promise.all([
      runAdminRequest(fetchUsers),
      runAdminRequest(fetchCoachRequests),
    ]);
    if (requestId !== state.userRequestId) return;
    state.users = users;
    state.coachRequests = requests;
    state.userLoadState = "loaded";
    state.coachRequestLoadState = "loaded";
    renderUsers();
    renderCoachRequests();
  } catch (error) {
    if (requestId !== state.userRequestId) return;
    state.userLoadState = "error";
    state.coachRequestLoadState = "error";
    state.userLoadError = "회원 목록을 불러오지 못했습니다.";
    state.coachRequestLoadError = "코치 등록 요청을 불러오지 못했습니다.";
    renderUsers();
    renderCoachRequests();
  }
}

async function saveUserRole(id) {
  const isCoach = document.querySelector(`[data-user-coach-role="${CSS.escape(id)}"]`)?.checked || false;
  const isAdmin = document.querySelector(`[data-user-admin-role="${CSS.escape(id)}"]`)?.checked || false;
  const role = isCoach ? "coach" : (isAdmin ? "admin" : "student");
  const coachKey = isCoach ? (findUserCoachSelect(id)?.value || "") : "";
  if (isCoach && !coachKey) {
    state.userSaveStates = { ...state.userSaveStates, [id]: "코치 선택 필요" };
    renderUsers();
    return;
  }
  state.userSaveStates = { ...state.userSaveStates, [id]: "저장 중..." };
  renderUsers();
  try {
    const roles = [...(isCoach ? ["coach"] : []), ...(isAdmin ? ["admin"] : [])];
    const user = await runAdminRequest(() => updateUserRole(id, { role, roles, isCoach, isAdmin, coachKey }));
    state.users = state.users.map((item) => item.id === id ? user : item);
    state.userSaveStates = { ...state.userSaveStates, [id]: "저장 완료" };
    renderUsers();
    if (user.id === state.currentUser?.id) {
      state.currentUser = user;
      if (user.coachKey) state.coachSelfKey = user.coachKey;
      renderRoleMenu();
    }
  } catch (error) {
    state.userSaveStates = { ...state.userSaveStates, [id]: `저장 실패: ${error.message || "서버 오류"}` };
    renderUsers();
  }
}

async function submitCoachApplication(event) {
  event.preventDefault();
  if (!state.currentUser) {
    openAuthModal("login");
    return;
  }
  const form = event.currentTarget;
  const button = $("coachApplySubmitBtn");
  const status = $("coachApplyStatus");
  const originalText = button?.textContent || "요청 보내기";
  const data = new FormData(form);
  if (button) {
    button.disabled = true;
    button.textContent = "전송 중";
  }
  if (status) {
    status.textContent = "";
    status.className = "save-status loading";
  }
  try {
    await createCoachRequest({
      coachName: data.get("coachName"),
      game: data.get("game"),
      mainRole: data.get("mainRole"),
      tier: data.get("tier"),
      price: data.get("price"),
      contact: data.get("contact"),
      intro: data.get("intro"),
      sample: data.get("sample"),
    });
    form.reset();
    if (status) {
      status.textContent = "요청이 접수되었습니다. 관리자가 확인 후 승인합니다.";
      status.className = "save-status success";
    }
  } catch (error) {
    if (status) {
      status.textContent = getCoachRequestErrorMessage(error.message);
      status.className = "save-status error";
    }
  } finally {
    if (button) {
      button.disabled = false;
      button.textContent = originalText;
    }
  }
}

async function approveCoachRequest(id) {
  try {
    const result = await runAdminRequest(() => decideCoachRequest(id, "approve"));
    state.coachRequests = state.coachRequests.map((item) => item.id === id ? result.request : item);
    if (result.user) state.users = state.users.map((item) => item.id === result.user.id ? result.user : item);
    if (result.coach) {
      state.coaches = getPublicCatalogCoaches([...state.coaches.filter((coach) => coach.id !== result.coach.id), result.coach]);
    }
    renderUsers();
    renderCoachRequests();
    renderMarket();
  } catch (error) {
    alert(`코치 등록 요청을 승인하지 못했습니다.\n${error.message}`);
  }
}

async function rejectCoachRequest(id) {
  try {
    const result = await runAdminRequest(() => decideCoachRequest(id, "reject"));
    state.coachRequests = state.coachRequests.map((item) => item.id === id ? result.request : item);
    renderCoachRequests();
  } catch (error) {
    alert(`코치 등록 요청을 거절하지 못했습니다.\n${error.message}`);
  }
}

function getCoachRequestErrorMessage(error) {
  const messages = {
    login_required: "로그인 후 코치 등록 요청을 보낼 수 있습니다.",
    already_coach: "이미 코치 권한이 있는 계정입니다.",
    missing_coach_name: "코치 이름을 입력해주세요.",
    pending_request_exists: "이미 확인 대기 중인 코치 등록 요청이 있습니다.",
  };
  return messages[error] || "요청을 보내지 못했습니다. 잠시 후 다시 시도해주세요.";
}

async function changeReservationStatus(id, status) {
  const previousBookings = structuredClone(state.bookings);
  state.bookings = state.bookings.map((booking) => booking.id === id ? { ...booking, status } : booking);
  renderBookings();

  try {
    const updated = await updateReservationStatus(id, status);
    state.bookings = state.bookings.map((booking) => booking.id === id ? updated : booking);
    delete state.bookingPendingStatuses[id];
    renderBookings();
  } catch (error) {
    state.bookings = previousBookings;
    renderBookings();
    if (error.status === 401) {
      const loggedIn = await loginForReservations();
      if (loggedIn) return changeReservationStatus(id, status);
    }
    alert(`예약 상태를 저장하지 못했습니다.\n${getReservationErrorMessage(error.message)}`);
  }
}

function queueReservationStatus(id, status) {
  const booking = state.bookings.find((item) => item.id === id);
  if (!booking) return;
  state.bookingPendingStatuses[id] = status === booking.status ? "" : status;
  renderBookings();
}

async function saveReservationStatus(id) {
  const status = state.bookingPendingStatuses[id];
  if (!status) return;
  await changeReservationStatus(id, status);
}

async function removeReservation(id) {
  if (!window.confirm("이 예약을 완전히 삭제할까요? 삭제하면 목록에서 사라집니다.")) return;
  try {
    await runAdminRequest(() => deleteReservation(id));
    state.bookings = state.bookings.filter((booking) => booking.id !== id);
    if (state.selectedBookingId === id) state.selectedBookingId = null;
    renderMetrics();
    renderBookings();
  } catch (error) {
    alert(`예약을 삭제하지 못했습니다.\n${getReservationErrorMessage(error.message)}`);
  }
}

function getReservationErrorMessage(error) {
  const messages = {
    payment_refund_required: "결제된 예약은 먼저 환불 처리해야 삭제할 수 있습니다.",
    payment_history_retained: "결제 기록 보존 정책 때문에 이 예약은 삭제할 수 없습니다.",
    payment_order_exists: "결제 주문 기록이 있어 삭제할 수 없습니다. 환불 또는 결제 기록 정리가 필요합니다.",
    reservation_not_found: "예약이 이미 삭제됐거나 존재하지 않습니다.",
    invalid_status: "선택할 수 없는 예약 상태입니다.",
    unauthorized: "관리자 인증이 필요합니다.",
  };
  return messages[error] || error || "서버에서 요청을 거부했습니다.";
}

function getFilteredBookings() {
  return filterReservations(state.bookings, state.bookingFilterStatus, state.bookingQuery);
}

function renderBookingDetail() {
  const panel = $("bookingDetail");
  const booking = state.bookings.find((item) => item.id === state.selectedBookingId);
  if (!booking) {
    panel.hidden = true;
    panel.innerHTML = "";
    return;
  }
  if (booking.isDiscordFeedback) {
    const attachment = booking.feedback?.attachment || {};
    panel.hidden = false;
    panel.innerHTML = `
      <h3>Discord / ROFL 접수</h3>
      <div class="booking-detail-grid">
        ${renderDetailItem("요청 시간", booking.createdAtText)}
        ${renderDetailItem("수강생 / Riot ID", booking.studentName)}
        ${renderDetailItem("챔피언 및 K/D/A", booking.coachPrice)}
        ${renderDetailItem("현재 상태", booking.status)}
        ${renderDetailItem("Discord 요청자", `${booking.feedback?.discord_display_name || "-"} (${booking.feedback?.discord_user_id || "-"})`)}
        ${renderDetailItem("서버 / 채널", `${booking.feedback?.guild_name || "-"} / ${booking.feedback?.channel_name || "-"}`)}
        ${renderDetailLink("ROFL 파일", attachment.filename, attachment.url)}
        ${renderDetailItem("문의사항", booking.feedback?.inquiry || booking.memo, true)}
      </div>
    `;
    return;
  }
  if (booking.isGuestConsultation) {
    const selected = booking.feedback?.selected_lesson || {};
    panel.hidden = false;
    panel.innerHTML = `
      <h3>비회원 강의 구매 문의</h3>
      <div class="booking-detail-grid">
        ${renderDetailItem("접수 시간", booking.createdAtText)}
        ${renderDetailItem("Riot 닉네임#태그", booking.studentName)}
        ${renderDetailItem("연락처", booking.contact)}
        ${renderDetailItem("선택 강의", selected.name ? `${selected.name} · ${selected.price || "-"}` : booking.coachName)}
        ${renderDetailItem("현재 상태", booking.status)}
        ${renderDetailItem("받고싶은 피드백 라인 및 포인트", booking.feedback?.inquiry || booking.memo, true)}
        ${renderDetailItem("강의 방식", booking.feedback?.lesson_style || booking.preferredTime, true)}
      </div>
    `;
    return;
  }
  panel.hidden = false;
  panel.innerHTML = `
    <h3>예약 상세</h3>
    <div class="booking-detail-grid">
      ${renderDetailItem("예약 ID", booking.id)}
      ${renderDetailItem("요청 시간", booking.createdAtText)}
      ${renderDetailItem("코치명", booking.coachName)}
      ${renderDetailItem("상품 가격", booking.coachPrice)}
      ${renderDetailItem("접수 경로", booking.source)}
      ${renderDetailItem("수강생 / Riot ID", booking.studentName)}
      ${renderDetailItem("연락처", booking.contact)}
      ${renderDetailItem("희망 시간", booking.preferredTime)}
      ${renderDetailItem("현재 상태", booking.status)}
      ${renderDetailItem("결제 상태", paymentStatusLabel(booking))}
      ${renderDetailItem("요청사항", booking.memo, true)}
    </div>
    ${paymentStatus(booking) === "PAID" ? `<button class="danger" type="button" id="refundPaymentBtn">전액 환불</button>` : ""}
  `;
  $("refundPaymentBtn")?.addEventListener("click", () => refundPayment(booking));
}

async function refundPayment(booking) {
  if (!booking.payment?.orderId || !window.confirm("이 결제를 전액 환불할까요? 토스 승인 취소 후 예약도 취소됩니다.")) return;
  const reason = window.prompt("환불 사유를 입력하세요.", "관리자 전액 환불");
  if (!reason) return;
  try {
    await runAdminRequest(() => cancelPayment(booking.payment.orderId, reason));
    await loadReservations({ promptForLogin: false });
    alert("전액 환불이 완료되었습니다.");
  } catch (error) {
    alert(`환불하지 못했습니다.\n${getPaymentErrorMessage(error.message)}`);
  }
}

function renderDetailItem(label, value, wide = false) {
  return `
    <div class="booking-detail-item ${wide ? "wide" : ""}">
      <span>${label}</span>
      <strong>${escapeHtml(value || "-")}</strong>
    </div>
  `;
}

function renderDetailLink(label, text, url) {
  const link = url ? `<a href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(text || "다운로드")}</a>` : "-";
  return `
    <div class="booking-detail-item">
      <span>${label}</span>
      <strong>${link}</strong>
    </div>
  `;
}

function renderBookings() {
  $("bookingStatusFilter").innerHTML = `
    <option value="all">전체 상태</option>
    ${renderStatusOptions(state.bookingFilterStatus)}
  `;
  $("bookingStatusFilter").value = state.bookingFilterStatus;
  $("bookingSearchInput").value = state.bookingQuery;

  if (state.bookingLoadState === "loading") {
    $("bookingRows").innerHTML = `<tr><td colspan="7">예약 목록을 불러오는 중입니다.</td></tr>`;
    renderBookingDetail();
    renderRefundAdminPanel();
    return;
  }
  if (state.bookingLoadState === "error") {
    $("bookingRows").innerHTML = `<tr><td colspan="7">${state.bookingLoadError || "예약 목록을 불러오지 못했습니다."}</td></tr>`;
    renderBookingDetail();
    renderRefundAdminPanel();
    return;
  }
  const visibleBookings = getFilteredBookings();
  if (state.selectedBookingId && !state.bookings.some((booking) => booking.id === state.selectedBookingId)) {
    state.selectedBookingId = null;
  }

  $("bookingRows").innerHTML = visibleBookings.length ? visibleBookings.map((booking) => {
    const pendingStatus = state.bookingPendingStatuses[booking.id] || booking.status;
    const hasPendingStatus = Boolean(state.bookingPendingStatuses[booking.id]);
    return `
    <tr class="booking-row" data-booking-id="${escapeHtml(booking.id)}">
      <td>
        <select class="status-select" data-booking-status="${escapeHtml(booking.id)}">
          ${renderStatusOptions(pendingStatus)}
        </select>
      </td>
      <td>${escapeHtml(booking.student)}</td>
      <td>${escapeHtml(booking.lesson)}</td>
      <td>${escapeHtml(booking.time)}</td>
      <td>${escapeHtml(booking.contact)}</td>
      <td>${escapeHtml(booking.memo)}</td>
      <td>
        <div class="booking-actions">
          <button type="button" class="mini primary-mini" data-booking-save="${escapeHtml(booking.id)}" ${hasPendingStatus ? "" : "disabled"}>저장</button>
          <button type="button" class="mini danger-mini" data-booking-delete="${escapeHtml(booking.id)}">삭제</button>
        </div>
      </td>
    </tr>
  `;
  }).join("") : `<tr><td colspan="7">예약이 없습니다.</td></tr>`;

  document.querySelectorAll("[data-booking-id]").forEach((row) => {
    row.addEventListener("click", () => {
      state.selectedBookingId = row.dataset.bookingId;
      renderBookingDetail();
    });
  });
  document.querySelectorAll("[data-booking-status]").forEach((select) => {
    select.addEventListener("click", (event) => event.stopPropagation());
    select.addEventListener("change", (event) => {
      queueReservationStatus(select.dataset.bookingStatus, event.target.value);
    });
  });
  document.querySelectorAll("[data-booking-save]").forEach((button) => {
    button.addEventListener("click", (event) => {
      event.stopPropagation();
      button.disabled = true;
      saveReservationStatus(button.dataset.bookingSave);
    });
  });
  document.querySelectorAll("[data-booking-delete]").forEach((button) => {
    button.addEventListener("click", (event) => {
      event.stopPropagation();
      removeReservation(button.dataset.bookingDelete);
    });
  });
  renderBookingDetail();
  renderRefundAdminPanel();
}

function renderAdmin() {
  const target = $("adminCoachList");
  if (!target) return;
  const query = state.adminCoachQuery;
  const settings = state.adminCoachSettings.length
    ? state.adminCoachSettings
    : [...new Map(state.coaches.map((coach) => [getCoachKey(coach), normalizeAdminCoachSetting({ coachKey: getCoachKey(coach), badges: coach.badges }, state.coaches)])).values()];
  const visible = settings.filter((coach) => !query || [coach.name, coach.coachKey].join(" ").toLowerCase().includes(query));
  const search = $("adminCoachSearchInput");
  if (search && search.value !== state.adminCoachQuery) search.value = state.adminCoachQuery;
  if (state.adminCoachSettingsLoadState === "loading") {
    target.innerHTML = `<div class="empty">코치 목록을 불러오는 중입니다.</div>`;
  } else if (state.adminCoachSettingsLoadState === "error") {
    target.innerHTML = `<div class="empty error">${escapeHtml(state.adminCoachSettingsLoadError || "코치 목록을 불러오지 못했습니다.")}<br><button type="button" class="secondary mini" id="retryAdminCoachSettingsBtn">다시 시도</button></div>`;
    $("retryAdminCoachSettingsBtn")?.addEventListener("click", loadAdminCoachSettings);
  } else {
    target.innerHTML = visible.length ? visible.map((coach) => `
      <button class="admin-row admin-coach-select ${coach.coachKey === state.adminSelectedCoachKey ? "active" : ""}" type="button" data-admin-coach-key="${escapeHtml(coach.coachKey)}">
        <span>
          <h4>${escapeHtml(coach.name)}</h4>
          <p>${escapeHtml(coach.coachKey)} · ${coach.lessonCount}개 강의 · 수수료 ${formatCommissionRate(coach.commissionRate)}%</p>
        </span>
        <span class="chip">${coach.coachKey === state.adminSelectedCoachKey ? "선택됨" : "관리"}</span>
      </button>
    `).join("") : `<div class="empty">${query ? "검색 결과가 없습니다." : "등록된 코치가 없습니다."}</div>`;
    document.querySelectorAll("[data-admin-coach-key]").forEach((row) => {
      row.addEventListener("click", () => selectAdminCoach(row.dataset.adminCoachKey));
    });
  }
  const selected = settings.find((coach) => coach.coachKey === state.adminSelectedCoachKey);
  if (selected) fillCoachForm(selected);
  else fillCoachForm(null);
}

function formatCommissionRate(value) {
  const rate = Number(value);
  return Number.isFinite(rate) ? rate.toLocaleString("ko-KR", { maximumFractionDigits: 2 }) : "0";
}

function selectAdminCoach(coachKey) {
  const selected = state.adminCoachSettings.find((coach) => coach.coachKey === coachKey);
  if (!selected) return;
  state.adminSelectedCoachKey = coachKey;
  renderAdmin();
}

function renderUsers() {
  const target = $("userRows");
  if (!target) return;
  if (state.userLoadState === "idle") {
    target.innerHTML = `<tr><td colspan="5">회원 목록을 불러오려면 새로고침을 눌러주세요.</td></tr>`;
    return;
  }
  if (state.userLoadState === "loading") {
    target.innerHTML = `<tr><td colspan="5">회원 목록을 불러오는 중입니다.</td></tr>`;
    return;
  }
  if (state.userLoadState === "error") {
    target.innerHTML = `<tr><td colspan="5">${escapeHtml(state.userLoadError || "회원 목록을 불러오지 못했습니다.")}</td></tr>`;
    return;
  }
  const coachOptions = getCoachIdentities("league");
  const query = state.userQuery;
  const visibleUsers = state.users.filter((user) => {
    const coachName = coachOptions.find((coach) => coach.key === user.coachKey)?.name || "";
    return !query || [user.displayName, user.email, user.coachKey, coachName, user.role, user.discordDisplayName, ...(user.roles || [])].join(" ").toLowerCase().includes(query);
  });
  target.innerHTML = visibleUsers.length ? visibleUsers.map((user) => {
    const flags = getUserRoleFlags(user);
    return `
    <tr>
      <td>${escapeHtml(user.displayName || "-")}</td>
      <td>${escapeHtml(user.email || "-")}</td>
      <td>
        <div class="user-role-checks">
          <label><input type="checkbox" data-user-coach-role="${escapeHtml(user.id)}" ${flags.isCoach ? "checked" : ""}> 코치</label>
          <label><input type="checkbox" data-user-admin-role="${escapeHtml(user.id)}" ${flags.isAdmin ? "checked" : ""}> 관리자</label>
        </div>
        <div class="user-coach-picker" data-user-coach-picker="${escapeHtml(user.id)}" ${flags.isCoach ? "" : "hidden"}>
          <select data-user-coach="${escapeHtml(user.id)}" aria-label="연결할 코치 선택">
            <option value="">코치 선택</option>
            ${coachOptions.map((coach) => `<option value="${escapeHtml(coach.key)}" ${coach.key === user.coachKey ? "selected" : ""}>${escapeHtml(coach.name)}</option>`).join("")}
          </select>
        </div>
        ${flags.isCoach ? `<small>${escapeHtml(getUserCoachLabel(user))}</small>` : ""}
      </td>
      <td>
        <span class="discord-status ${user.discordConnected || user.discord_connected ? "connected" : "disconnected"}">${user.discordConnected || user.discord_connected ? "연결됨" : "미연결"}</span>
        ${user.discordDisplayName || user.discord_display_name ? `<small>${escapeHtml(user.discordDisplayName || user.discord_display_name)}</small>` : ""}
      </td>
      <td>
        <div class="inline-save">
          <button class="mini primary-mini" type="button" data-user-save="${escapeHtml(user.id)}" ${state.userSaveStates[user.id] === "저장 중..." ? "disabled" : ""}>저장</button>
          <span class="save-status ${getUserSaveClass(user.id)}">${escapeHtml(state.userSaveStates[user.id] || "")}</span>
        </div>
      </td>
    </tr>
  `;
  }).join("") : `<tr><td colspan="5">${query ? "검색 결과가 없습니다." : "가입한 회원이 없습니다."}</td></tr>`;

  document.querySelectorAll("[data-user-save]").forEach((button) => {
    button.addEventListener("click", () => saveUserRole(button.dataset.userSave));
  });
  document.querySelectorAll("[data-user-coach-role]").forEach((checkbox) => {
    checkbox.addEventListener("change", () => {
      const picker = document.querySelector(`[data-user-coach-picker="${CSS.escape(checkbox.dataset.userCoachRole)}"]`);
      if (picker) picker.hidden = !checkbox.checked;
    });
  });
}

function renderCoachRequests() {
  const target = $("coachRequestRows");
  if (!target) return;
  if (state.coachRequestLoadState === "idle") {
    target.innerHTML = `<tr><td colspan="5">회원 목록 새로고침을 누르면 코치 등록 요청도 함께 불러옵니다.</td></tr>`;
    return;
  }
  if (state.coachRequestLoadState === "loading") {
    target.innerHTML = `<tr><td colspan="5">코치 등록 요청을 불러오는 중입니다.</td></tr>`;
    return;
  }
  if (state.coachRequestLoadState === "error") {
    target.innerHTML = `<tr><td colspan="5">${escapeHtml(state.coachRequestLoadError || "코치 등록 요청을 불러오지 못했습니다.")}</td></tr>`;
    return;
  }
  target.innerHTML = state.coachRequests.length ? state.coachRequests.map((request) => `
    <tr>
      <td>
        <strong>${escapeHtml(request.displayName || "-")}</strong>
        <small>${escapeHtml(request.email || "")}</small>
      </td>
      <td>
        <strong>${escapeHtml(request.coachName || "-")}</strong>
        <small>${escapeHtml([request.game, request.mainRole, request.tier].filter(Boolean).join(" · "))}</small>
      </td>
      <td>
        <span>${escapeHtml(request.intro || "-")}</span>
        <small>${escapeHtml(request.price || "가격 미입력")} · ${escapeHtml(request.contact || "연락처 없음")}</small>
      </td>
      <td>${getCoachRequestStatusLabel(request.status)}</td>
      <td>
        ${request.status === "pending" ? `
          <div class="booking-actions">
            <button class="mini primary-mini" type="button" data-request-approve="${escapeHtml(request.id)}">승인</button>
            <button class="mini danger-mini" type="button" data-request-reject="${escapeHtml(request.id)}">거절</button>
          </div>
        ` : `<span class="chip">${escapeHtml(request.coachKey || "-")}</span>`}
      </td>
    </tr>
  `).join("") : `<tr><td colspan="5">접수된 코치 등록 요청이 없습니다.</td></tr>`;

  document.querySelectorAll("[data-request-approve]").forEach((button) => {
    button.addEventListener("click", async () => {
      const controls = [...(button.closest("tr")?.querySelectorAll("button") || [])];
      controls.forEach((item) => { item.disabled = true; });
      try { await approveCoachRequest(button.dataset.requestApprove); }
      finally { controls.forEach((item) => { item.disabled = false; }); }
    });
  });
  document.querySelectorAll("[data-request-reject]").forEach((button) => {
    button.addEventListener("click", async () => {
      const controls = [...(button.closest("tr")?.querySelectorAll("button") || [])];
      controls.forEach((item) => { item.disabled = true; });
      try { await rejectCoachRequest(button.dataset.requestReject); }
      finally { controls.forEach((item) => { item.disabled = false; }); }
    });
  });
}

function getCoachRequestStatusLabel(status) {
  return { pending: "대기중", approved: "승인됨", rejected: "거절됨" }[status] || status;
}

function getUserCoachLabel(user) {
  const key = user.coachKey;
  const coach = getCoachIdentities("league").find((item) => item.key === key);
  return coach ? `${coach.name} 연결됨` : "코치 프로필 자동 생성 대상";
}

function getUserRoleFlags(user) {
  const roles = Array.isArray(user?.roles) ? user.roles.map((role) => String(role).toLowerCase()) : [];
  return {
    isCoach: Boolean(user?.isCoach || user?.is_coach || user?.coachKey || user?.coach_key || user?.role === "coach" || roles.includes("coach") || roles.includes("코치")),
    isAdmin: Boolean(user?.isAdmin || user?.is_admin || user?.role === "admin" || roles.includes("admin") || roles.includes("관리자")),
  };
}

function getUserSaveClass(id) {
  const message = state.userSaveStates[id] || "";
  if (message.includes("완료")) return "success";
  if (message.includes("실패")) return "error";
  if (message.includes("저장 중")) return "loading";
  return "";
}

function getRoleLabel(role) {
  return { student: "수강생", coach: "코치", admin: "관리자" }[role] || role;
}

function findUserCoachSelect(id) {
  return [...document.querySelectorAll("[data-user-coach]")].find((select) => select.dataset.userCoach === id);
}

function getCoachSelfLessons() {
  const allowedKey = !isAdminUser() ? getFallbackCoachKey() : state.coachSelfKey;
  const lessons = !isAdminUser() && Array.isArray(state.coachSelfLessons) ? state.coachSelfLessons : state.coaches;
  return lessons.filter((coach) => coach.category === "league" && getCoachKey(coach) === allowedKey);
}

function getCoachProfileFormValue(current) {
  const profile = state.coachProfile || {};
  return {
    nickname: profile.nickname || profile.name || profile.displayName || current?.name || "",
    image: profile.image || profile.profileImage || "",
    intro: profile.intro || profile.tagline || current?.tagline || "",
    tier: profile.tier || current?.tier || "일반",
    roles: Array.isArray(profile.roles) ? profile.roles : (current?.coachRoles || current?.roles || []),
    active: profile.active !== undefined ? Boolean(profile.active) : current?.active !== false,
  };
}

function renderCoachSelfProfile(current) {
  const target = $("coachSelfProfile");
  if (!target) return;
  if (!isCoachUser()) {
    target.innerHTML = "";
    return;
  }
  const profile = getCoachProfileFormValue(current);
  const roleOptions = [...new Set([...(adminLineOptions.league || []), ...(adminFieldOptions.league || [])])];
  const loading = state.coachProfileLoadState === "loading" ? "<small>프로필을 불러오는 중입니다...</small>" : "";
  const loadError = state.coachProfileLoadState === "error" ? `<small class="profile-load-error">${escapeHtml(state.coachProfileLoadError || "프로필을 불러오지 못했습니다.")}</small>` : "";
  target.innerHTML = `
    <form class="coach-self-profile-form" id="coachSelfProfileForm">
      <div class="coach-self-profile-head">
        <div><strong>내 코치 프로필</strong>${loading}${loadError}</div>
        <button type="submit" class="secondary" id="coachSelfProfileSaveBtn">저장</button>
      </div>
      <div class="coach-self-profile-grid">
        <div class="coach-self-profile-media">
          <span class="coach-self-profile-label">프로필 이미지</span>
          <input id="coachSelfProfileImage" type="hidden" value="${escapeHtml(profile.image)}">
          <div class="image-preview thumbnail-preview"><div class="image-preview-frame" id="coachSelfProfileImagePreview"><span class="image-preview-empty" ${profile.image ? "hidden" : ""}>선택된 파일 없음</span></div></div>
          <label class="coach-self-file-button"><span>파일 선택</span><input id="coachSelfProfileImageFile" type="file" accept="image/*"></label>
          <button type="button" class="secondary image-crop-button" id="openCoachSelfProfileCropBtn">이미지 범위 지정</button>
        </div>
        <div class="coach-self-profile-fields">
          <label>닉네임<input id="coachSelfProfileNickname" required value="${escapeHtml(profile.nickname)}"></label>
          <label>한 줄 소개<textarea id="coachSelfProfileIntro" rows="3" required>${escapeHtml(profile.intro)}</textarea></label>
          <div class="coach-self-tier"><span>티어</span><strong>${escapeHtml(profile.tier || "일반")}</strong><small>관리자 지정</small></div>
        </div>
      </div>
      <fieldset class="choice-field">
        <legend>태그</legend>
        <div class="choice-grid">
          ${roleOptions.map((role) => `<label><input type="checkbox" name="coachSelfProfileRole" value="${escapeHtml(role)}" ${profile.roles.includes(role) ? "checked" : ""}> ${escapeHtml(role)}</label>`).join("")}
        </div>
      </fieldset>
      <label class="toggle-line"><input id="coachSelfProfileActive" type="checkbox" ${profile.active ? "checked" : ""}><span>홈페이지에 코치와 강의를 공개합니다</span></label>
      <span class="save-status" id="coachSelfProfileStatus" aria-live="polite"></span>
    </form>
  `;
  updateWideImagePreview("coachSelfProfileImage", "coachSelfProfileImagePreview");
  $("coachSelfProfileImageFile")?.addEventListener("change", handleCoachSelfProfileImageFile);
  $("openCoachSelfProfileCropBtn")?.addEventListener("click", () => openCropModal({
    inputId: "coachSelfProfileImage",
    previewId: "coachSelfProfileImagePreview",
    width: 520,
    height: 520,
    label: "프로필 이미지",
  }));
  $("coachSelfProfileForm")?.addEventListener("submit", saveCoachSelfProfile);
}

function renderCoachSelf() {
  if (!$("coachSelfTabs") || !$("coachSelfEditor")) return;
  const currentCoachKey = getFallbackCoachKey();
  const publicIdentities = getCoachIdentities("league", true);
  const ownLessons = getCoachSelfLessons();
  const ownIdentity = ownLessons.length ? getCoachIdentityFromGroup(currentCoachKey, ownLessons) : null;
  const identities = [...publicIdentities, ...(ownIdentity && !publicIdentities.some((coach) => coach.key === currentCoachKey) ? [ownIdentity] : [])].filter((coach) => (
    isAdminUser() || coach.key === currentCoachKey
  ));
  if (!identities.some((coach) => coach.key === state.coachSelfKey)) {
    state.coachSelfKey = identities[0]?.key || currentCoachKey || "shineast";
  }
  const current = identities.find((coach) => coach.key === state.coachSelfKey);
  const canSwitchCoach = isAdminUser();
  $("coachSelfTabs").hidden = !canSwitchCoach;
  $("coachSelfTabs").innerHTML = canSwitchCoach ? identities.map((coach) => `
    <button class="coach-self-tab ${coach.key === state.coachSelfKey ? "active" : ""}" type="button" data-self-coach-key="${escapeHtml(coach.key)}">
      ${escapeHtml(coach.name)}
    </button>
  `).join("") : "";
  $("coachSelfName").textContent = current ? current.name : "코치 선택";
  $("coachSelfHint").textContent = current ? `${current.tier} · ${current.lessons}개 강의` : "강의를 선택하면 오른쪽에서 수정할 수 있습니다.";
  renderCoachSelfProfile(current);
  renderCoachAvailabilityPanel();
  if (isCoachUser() && state.coachScheduleLoadState === "idle") loadCoachSchedule();

  const lessons = getCoachSelfLessons();
  if (state.coachSelfLessonId && !lessons.some((lesson) => lesson.id === state.coachSelfLessonId)) {
    state.coachSelfLessonId = null;
  }
  document.querySelectorAll("[data-self-coach-key]").forEach((button) => {
    button.addEventListener("click", () => {
      state.coachSelfKey = button.dataset.selfCoachKey;
      state.coachSelfLessonId = null;
      renderCoachSelf();
    });
  });
  renderCoachSelfEditor(lessons);
}

function renderCoachSelfEditor(lessons = getCoachSelfLessons()) {
  const editor = $("coachSelfEditor");
  const lesson = lessons.find((coach) => coach.id === state.coachSelfLessonId);
  const picker = `
    <div class="coach-self-lesson-picker">
      <div class="coach-self-picker-head"><strong>강의 선택</strong><span>${lessons.length}/5</span><button type="button" class="secondary mini" id="coachSelfNewLessonBtn" ${lessons.length >= 5 ? "disabled" : ""}>새 강의 만들기</button></div>
      <div class="coach-self-grid" id="coachSelfLessonGrid">
        ${lessons.length ? lessons.map((item) => `
          <button class="coach-self-card ${item.id === state.coachSelfLessonId ? "active" : ""}" type="button" data-self-lesson-id="${escapeHtml(item.id)}">
            <img src="${escapeHtml(item.image)}" alt="" style="${escapeHtml(getImageStyle(item))}">
            <span><strong>${escapeHtml(item.name)}${item.published === false ? " · 비공개" : ""}</strong><small>${escapeHtml(item.tagline || "강의 설명 없음")}</small><em>${escapeHtml(item.price || "가격 상담")}</em></span>
          </button>
        `).join("") : `<div class="empty">이 코치에게 연결된 강의가 없습니다.</div>`}
      </div>
    </div>
  `;
  if (!lesson) {
    editor.innerHTML = `${picker}
      <div class="detail-empty">
        <strong>강의를 선택해주세요.</strong>
        <span>선택한 코치의 강의만 여기에서 개별 수정할 수 있습니다.</span>
      </div>
    `;
    bindCoachSelfLessonPicker(editor);
    return;
  }
  const amount = String(lesson.price || "").match(/[\d,]+/)?.[0]?.replace(/[^\d]/g, "") || "";
  const unitType = String(lesson.price || "").includes("게임") ? "game" : "time";
  const unit = String(lesson.price || "").split("/")[1]?.trim() || (unitType === "game" ? "1게임" : "1시간");
  const filters = filterSets.league;
  const purposeOptions = filters.type.filter((item) => item.id !== "all");
  const selectedPurposes = getCoachPurposes(lesson);
  const selectedRoles = lesson.roles || [];
  editor.innerHTML = `${picker}
    <form class="coach-self-form" id="coachSelfForm">
      <input type="hidden" id="coachSelfLessonId" value="${escapeHtml(lesson.id)}">
      <div class="coach-self-editor-head">
        <div>
          <span>${escapeHtml(lesson.coachProfileName || "코치")}</span>
          <h3>${escapeHtml(lesson.name)}</h3>
        </div>
        <div class="coach-self-editor-actions">
          <span class="save-status" id="coachSelfSaveStatus" aria-live="polite"></span>
          <button type="submit" class="primary" id="coachSelfSaveBtn">저장</button>
        </div>
      </div>
      <div class="coach-self-lesson-image">
        <div class="image-preview-frame" id="coachSelfLessonImagePreview"><span class="image-preview-empty">선택된 이미지 없음</span></div>
        <div class="coach-self-lesson-image-actions">
          <input id="coachSelfLessonImage" type="hidden" value="${escapeHtml(lesson.image || "")}">
          <label class="coach-self-file-button">파일 선택<input id="coachSelfLessonImageFile" type="file" accept="image/*"></label>
          <button type="button" class="secondary mini image-crop-button" id="openCoachSelfLessonCropBtn">이미지 범위 지정</button>
        </div>
      </div>
      <label class="toggle-line">
        <input id="coachSelfLessonPublished" type="checkbox" ${lesson.published !== false ? "checked" : ""}>
        <span>이 강의를 홈페이지에 공개합니다</span>
      </label>
      <label>강의명<input id="coachSelfLessonName" required value="${escapeHtml(lesson.name)}"></label>
      <label>한 줄 소개<input id="coachSelfTagline" ${lesson.published !== false ? "required" : ""} value="${escapeHtml(lesson.tagline || "")}"></label>
      <div class="price-builder">
        <label><span>가격</span><input id="coachSelfPriceAmount" inputmode="numeric" value="${escapeHtml(amount)}"></label>
        <label><span>기준</span>
          <select id="coachSelfPriceUnitType">
            <option value="time" ${unitType === "time" ? "selected" : ""}>시간</option>
            <option value="game" ${unitType === "game" ? "selected" : ""}>게임</option>
          </select>
        </label>
        <label><span>단위</span><select id="coachSelfPriceUnit"></select></label>
        <input id="coachSelfPrice" type="hidden">
      </div>
      <fieldset class="choice-field">
        <legend>분류</legend>
        <div class="choice-grid">
          ${purposeOptions.map((item) => `<label><input type="checkbox" name="coachSelfPurposeChoice" value="${item.id}" ${selectedPurposes.includes(item.id) ? "checked" : ""}> ${item.label}</label>`).join("")}
        </div>
      </fieldset>
      <fieldset class="choice-field">
        <legend>태그</legend>
        <div class="choice-grid">
          ${[...adminLineOptions.league, ...adminFieldOptions.league].map((role) => `<label><input type="checkbox" name="coachSelfRoleChoice" value="${role}" ${selectedRoles.includes(role) ? "checked" : ""}> ${role}</label>`).join("")}
        </div>
      </fieldset>
      <label>상세 설명<textarea id="coachSelfBio" rows="7">${escapeHtml(lesson.bio || "")}</textarea></label>
      <div class="form-actions">
        ${!isAdminUser() ? `<button type="button" class="danger" id="coachSelfDeleteLessonBtn">강의 삭제</button>` : ""}
        ${isAdminUser() ? `<button type="button" class="secondary" id="coachSelfOpenFullEditBtn">전체 편집 화면에서 열기</button>` : ""}
      </div>
    </form>
  `;
  bindCoachSelfLessonPicker(editor);
  updateWideImagePreview("coachSelfLessonImage", "coachSelfLessonImagePreview");
  $("coachSelfLessonImageFile").addEventListener("change", (event) => handleCoachSelfProfileImageFile(event, "coachSelfLessonImage", "coachSelfLessonImagePreview", "강의 이미지"));
  $("openCoachSelfLessonCropBtn").addEventListener("click", () => openCropModal({ inputId: "coachSelfLessonImage", previewId: "coachSelfLessonImagePreview", width: 520, height: 520, label: "강의 이미지" }));
  $("coachSelfLessonPublished").addEventListener("change", (event) => { $("coachSelfTagline").required = event.target.checked; });
  renderCoachSelfPriceUnitOptions(unitType, unit);
  updateCoachSelfPriceValue();
  $("coachSelfPriceUnitType").addEventListener("change", () => {
    renderCoachSelfPriceUnitOptions($("coachSelfPriceUnitType").value);
    updateCoachSelfPriceValue();
  });
  $("coachSelfPriceAmount").addEventListener("input", updateCoachSelfPriceValue);
  $("coachSelfPriceUnit").addEventListener("change", updateCoachSelfPriceValue);
  $("coachSelfForm").addEventListener("submit", saveCoachSelfLesson);
  $("coachSelfDeleteLessonBtn")?.addEventListener("click", async (event) => {
    if (!confirm(`'${lesson.name}' 강의를 삭제할까요?`)) return;
    event.currentTarget.disabled = true;
    try {
      await deleteCoachLessonApi(lesson.id);
      state.coachSelfLessons = (state.coachSelfLessons || []).filter((item) => item.id !== lesson.id);
      state.coachSelfLessonId = null;
      await loadCoachesFromApi();
      renderCoachSelf();
    } catch (error) {
      alert(`강의를 삭제하지 못했습니다.\n${error.message}`);
      event.currentTarget.disabled = false;
    }
  });
  $("coachSelfOpenFullEditBtn")?.addEventListener("click", () => {
    state.activeView = "admin";
    render();
    loadAdminCoachSettings().then(() => selectAdminCoach(getCoachKey(lesson)));
  });
}

function renderCoachSelfPriceUnitOptions(type, selected = "") {
  const units = priceUnits[type] || priceUnits.time;
  $("coachSelfPriceUnit").innerHTML = units.map((item) => `<option value="${item}" ${item === selected ? "selected" : ""}>${item}</option>`).join("");
}

function updateCoachSelfPriceValue() {
  const amount = Number(String($("coachSelfPriceAmount")?.value || "").replace(/[^\d]/g, ""));
  const amountText = amount ? `${amount.toLocaleString("ko-KR")}원` : "가격 상담";
  if ($("coachSelfPrice")) $("coachSelfPrice").value = `${amountText} / ${$("coachSelfPriceUnit").value}`;
}

function normalizeCoachAvailability(slot) {
  const normalized = normalizeAvailabilitySlot(slot);
  return {
    ...normalized,
    coachId: slot.coachId || slot.coach_id || "",
    lessonName: slot.lessonName || slot.lesson_name || slot.lesson || slot.bookingLesson || "",
    reservationId: slot.reservationId || slot.reservation_id || "",
  };
}

function getCoachScheduleWeekStart() {
  const current = state.coachScheduleWeekStart ? localDateOnly(state.coachScheduleWeekStart) : new Date();
  const monday = addLocalDays(current, -(getIsoWeekday(current) - 1));
  monday.setHours(0, 0, 0, 0);
  state.coachScheduleWeekStart = isoDateOnly(monday);
  return monday;
}

function scheduleResultPayload(result) {
  const source = result?.schedule && typeof result.schedule === "object" ? result.schedule : result || {};
  const weekly = Array.isArray(source.weekly) ? source.weekly : [];
  const overrides = Array.isArray(source.overrides) ? source.overrides : [];
  const rawSlots = source.slots || source.availability || source.items || [];
  return {
    weekly: weekly.map((item) => ({
      weekday: Math.min(7, Math.max(1, Number(item.weekday ?? item.day ?? 1))),
      startMinute: Number(item.startMinute ?? item.start_minute ?? item.start ?? 0),
      endMinute: Number(item.endMinute ?? item.end_minute ?? item.end ?? 0),
      enabled: item.enabled !== false && item.available !== false,
    })).filter((item) => item.endMinute > item.startMinute),
    overrides: overrides.map((item) => ({
      date: String(item.date || item.scheduleDate || item.schedule_date || "").slice(0, 10),
      startMinute: item.startMinute == null && item.start_minute == null ? null : Number(item.startMinute ?? item.start_minute),
      endMinute: item.endMinute == null && item.end_minute == null ? null : Number(item.endMinute ?? item.end_minute),
      enabled: item.enabled !== false && item.available !== false,
    })).filter((item) => item.date),
    slots: Array.isArray(rawSlots) ? rawSlots.map(normalizeCoachAvailability).filter((slot) => slot.id || slot.startsAt) : [],
  };
}

function scheduleSlotDate(slot) {
  const raw = String(slot.startsAt || slot.start || slot.date || "");
  if (/^\d{4}-\d{2}-\d{2}$/.test(raw)) return raw;
  const date = new Date(raw);
  return Number.isNaN(date.getTime()) ? raw.slice(0, 10) : isoDateOnly(date);
}

function scheduleSlotMinute(slot) {
  const raw = slot.startsAt || slot.start || "";
  const date = new Date(raw);
  if (!Number.isNaN(date.getTime())) return date.getHours() * 60 + date.getMinutes();
  const match = String(raw).match(/(?:T|\s)(\d{1,2}):(\d{2})/);
  return match ? Number(match[1]) * 60 + Number(match[2]) : -1;
}

function scheduleSlotLabel(slot) {
  return slot.lessonName || slot.lesson || slot.bookingLesson || slot.title || slot.label || "예약된 강의";
}

function getScheduleCell(schedule, date, minute) {
  const dateKey = isoDateOnly(date);
  const slot = (schedule.slots || []).find((item) => {
    const start = scheduleSlotMinute(item);
    const endDate = new Date(item.endsAt || item.end || "");
    const end = Number.isNaN(endDate.getTime()) ? start + 60 : endDate.getHours() * 60 + endDate.getMinutes();
    return scheduleSlotDate(item) === dateKey && start >= 0 && minute >= start && minute < end;
  });
  if (slot) {
    const booked = String(slot.status || "open") !== "open" || Boolean(slot.lessonName || slot.reservationId);
    return { open: !booked, booked, slot };
  }
  const override = (schedule.overrides || []).find((item) => item.date === dateKey && (item.startMinute == null || (minute >= item.startMinute && minute < item.endMinute)));
  if (override) return { open: Boolean(override.enabled), booked: false, override };
  const weekday = getIsoWeekday(date);
  const weekly = (schedule.weekly || []).some((item) => item.enabled !== false && item.weekday === weekday && minute >= item.startMinute && minute < item.endMinute);
  return { open: weekly, booked: false };
}

function buildScheduleDraft(schedule) {
  const draft = {};
  for (let weekday = 1; weekday <= 7; weekday += 1) {
    for (let minute = 0; minute < 1440; minute += 60) {
      const date = addLocalDays(getCoachScheduleWeekStart(), weekday - 1);
      draft[`${weekday}:${minute}`] = getScheduleCell(schedule, date, minute).open;
    }
  }
  return draft;
}

function buildScheduleBaseDraft(schedule) {
  const draft = {};
  for (let weekday = 1; weekday <= 7; weekday += 1) {
    for (let minute = 0; minute < 1440; minute += 60) {
      const date = addLocalDays(getCoachScheduleWeekStart(), weekday - 1);
      const weekly = (schedule.weekly || []).some((item) => item.enabled !== false && item.weekday === weekday && minute >= item.startMinute && minute < item.endMinute);
      draft[`${weekday}:${minute}`] = weekly;
    }
  }
  return draft;
}

function buildScheduleOverridesFromDraft() {
  const weekStart = getCoachScheduleWeekStart();
  const base = buildScheduleBaseDraft(state.coachSchedule || { weekly: [] });
  const preserved = (state.coachSchedule?.overrides || []).filter((item) => {
    const date = localDateOnly(item.date);
    return date < weekStart || date > addLocalDays(weekStart, 6);
  });
  const current = [];
  for (let weekday = 1; weekday <= 7; weekday += 1) {
    for (let minute = 0; minute < 1440; minute += 60) {
      const key = `${weekday}:${minute}`;
      if (Boolean(state.coachScheduleDraft?.[key]) === Boolean(base[key])) continue;
      current.push({ date: isoDateOnly(addLocalDays(weekStart, weekday - 1)), startMinute: minute, endMinute: minute + 60, enabled: Boolean(state.coachScheduleDraft?.[key]) });
    }
  }
  return [...preserved, ...current];
}

function buildWeeklyEntriesFromDraft() {
  const entries = [];
  for (let weekday = 1; weekday <= 7; weekday += 1) {
    let start = null;
    for (let minute = 0; minute <= 1440; minute += 60) {
      const enabled = minute < 1440 && Boolean(state.coachScheduleDraft?.[`${weekday}:${minute}`]);
      if (enabled && start == null) start = minute;
      if ((!enabled || minute === 1440) && start != null) {
        entries.push({ weekday, startMinute: start, endMinute: minute, enabled: true });
        start = null;
      }
    }
  }
  return entries;
}

async function loadCoachSchedule() {
  if (!state.currentUser || !isCoachUser()) return;
  const weekStart = getCoachScheduleWeekStart();
  const from = isoDateOnly(weekStart);
  const to = isoDateOnly(addLocalDays(weekStart, 6));
  state.coachScheduleLoadState = "loading";
  state.coachScheduleLoadError = "";
  renderCoachAvailabilityPanel();
  try {
    const coachId = getFallbackCoachKey();
    const result = await fetchCoachSchedule({ coachId, from, to });
    state.coachSchedule = scheduleResultPayload(result);
    state.coachAvailability = state.coachSchedule.slots;
    state.coachScheduleDraft = state.coachScheduleEditMode === "week"
      ? buildScheduleDraft(state.coachSchedule)
      : buildScheduleDraft({ ...state.coachSchedule, overrides: [] });
    state.coachScheduleLoadState = "loaded";
  } catch (error) {
    state.coachScheduleLoadState = "error";
    state.coachScheduleLoadError = error instanceof TypeError
      ? "서버에 연결하지 못했습니다. 잠시 후 새로고침해주세요."
      : error.message || "주간 가능 시간을 불러오지 못했습니다.";
    state.coachScheduleDraft = buildScheduleDraft({ weekly: [], overrides: [], slots: [] });
  }
  renderCoachAvailabilityPanel();
  if (state.activeView === "student") renderStudentHome();
}

function renderScheduleSummaryMarkup() {
  const weekly = state.coachSchedule?.weekly || [];
  if (!weekly.length) return `<section class="student-panel schedule-summary"><div class="student-panel-head"><span>주간 일정</span><strong>예약 가능 시간</strong></div><p class="schedule-summary-empty">등록된 반복 일정이 없습니다. 내 강의 관리에서 시간을 설정해주세요.</p></section>`;
  const labels = ["월", "화", "수", "목", "금", "토", "일"];
  const chunks = labels.map((label, index) => {
    const entries = weekly.filter((item) => item.weekday === index + 1).sort((a, b) => a.startMinute - b.startMinute);
    if (!entries.length) return "";
    return `<span><b>${label}</b> ${entries.map((item) => `${String(Math.floor(item.startMinute / 60)).padStart(2, "0")}~${String(Math.floor(item.endMinute / 60) % 24).padStart(2, "0")}`).join(", ")}</span>`;
  }).filter(Boolean).join("");
  return `<section class="student-panel schedule-summary"><div class="student-panel-head"><span>주간 일정</span><strong>예약 가능 시간</strong></div><div class="schedule-summary-list">${chunks}</div></section>`;
}

function renderCoachAvailabilityPanel() {
  const target = $("coachAvailabilityPanel");
  if (!target || !isCoachUser()) {
    if (target) target.innerHTML = "";
    return;
  }
  if (state.coachScheduleLoadState === "loading") {
    target.innerHTML = `<section class="availability-panel"><strong>주간 시간표를 불러오는 중...</strong></section>`;
    return;
  }
  const weekStart = getCoachScheduleWeekStart();
  const from = isoDateOnly(weekStart);
  const to = isoDateOnly(addLocalDays(weekStart, 6));
  const firstHour = state.coachScheduleShowAllHours ? 0 : 6;
  const lastHour = 24;
  const weekdays = [1, 2, 3, 4, 5, 6, 7];
  const weekdayLabels = ["월", "화", "수", "목", "금", "토", "일"];
  const cells = [];
  for (let hour = firstHour; hour < lastHour; hour += 1) {
    cells.push(`<div class="schedule-time-label">${String(hour).padStart(2, "0")}:00</div>`);
    weekdays.forEach((weekday) => {
      const date = addLocalDays(weekStart, weekday - 1);
      const minute = hour * 60;
      const cell = getScheduleCell(state.coachSchedule, date, minute);
      const key = `${weekday}:${minute}`;
      const open = state.coachScheduleDraft?.[key] ?? cell.open;
      const disabled = cell.booked;
      cells.push(`<button type="button" class="schedule-cell ${open ? "open" : "closed"} ${disabled ? "booked" : ""}" data-schedule-cell="${key}" ${disabled ? "disabled" : ""} title="${disabled ? escapeHtml(scheduleSlotLabel(cell.slot)) : (open ? "예약 가능 · 클릭하여 닫기" : "예약 불가 · 클릭하여 열기")}">${disabled ? `<small>${escapeHtml(scheduleSlotLabel(cell.slot))}</small>` : (open ? "가능" : "")}</button>`);
    });
  }
  target.innerHTML = `
    <section class="availability-panel schedule-panel">
      <div class="availability-head"><div><span>예약 일정</span><strong>주간 시간표</strong></div><div class="schedule-actions"><button type="button" class="secondary mini" id="schedulePrevWeekBtn">이전 주</button><button type="button" class="secondary mini" id="scheduleTodayBtn">이번 주</button><button type="button" class="secondary mini" id="scheduleNextWeekBtn">다음 주</button></div></div>
      <div class="schedule-week-title"><strong>${from} ~ ${to}</strong><span>${state.coachScheduleEditMode === "week" ? "이 주에만 적용됩니다." : "다음 주에도 같은 시간으로 반복됩니다."} 예약된 칸은 수정할 수 없습니다.</span></div>
      ${state.coachScheduleLoadState === "error" ? `<small class="save-status error">${escapeHtml(state.coachScheduleLoadError)}</small>` : ""}
      <div class="schedule-toolbar"><label class="schedule-mode">편집 범위<select id="scheduleEditMode"><option value="weekly" ${state.coachScheduleEditMode === "weekly" ? "selected" : ""}>매주 반복 기본값</option><option value="week" ${state.coachScheduleEditMode === "week" ? "selected" : ""}>이 주만 변경</option></select></label><button type="button" class="secondary mini" id="scheduleHourToggleBtn">${state.coachScheduleShowAllHours ? "06시 이후만 보기" : "전체 24시간 보기"}</button><span>기본 화면은 06:00~24:00이며 내부에서만 스크롤됩니다.</span></div>
      <div class="schedule-grid-wrap"><div class="schedule-grid" style="--schedule-days: 7"><div class="schedule-corner">시간</div>${weekdayLabels.map((label, index) => `<div class="schedule-day-head">${label}<small>${isoDateOnly(addLocalDays(weekStart, index)).slice(5)}</small></div>`).join("")}${cells.join("")}</div></div>
      <div class="schedule-legend"><span><i class="open"></i>가능</span><span><i class="closed"></i>불가능</span><span><i class="booked"></i>예약됨</span></div>
      <div class="schedule-save-row"><span class="save-status" id="coachScheduleStatus" aria-live="polite"></span><button type="button" class="primary" id="saveCoachScheduleBtn">주간 일정 저장</button></div>
    </section>
  `;
  document.querySelectorAll("[data-schedule-cell]").forEach((button) => button.addEventListener("click", () => {
    const key = button.dataset.scheduleCell;
    if (!state.coachScheduleDraft) state.coachScheduleDraft = buildScheduleDraft(state.coachSchedule);
    state.coachScheduleDraft[key] = !state.coachScheduleDraft[key];
    renderCoachAvailabilityPanel();
  }));
  $("schedulePrevWeekBtn")?.addEventListener("click", () => changeCoachScheduleWeek(-7));
  $("scheduleNextWeekBtn")?.addEventListener("click", () => changeCoachScheduleWeek(7));
  $("scheduleTodayBtn")?.addEventListener("click", () => { state.coachScheduleWeekStart = ""; state.coachScheduleLoadState = "idle"; loadCoachSchedule(); });
  $("scheduleEditMode")?.addEventListener("change", (event) => {
    state.coachScheduleEditMode = event.target.value === "week" ? "week" : "weekly";
    state.coachScheduleDraft = state.coachScheduleEditMode === "week" ? buildScheduleDraft(state.coachSchedule) : buildScheduleDraft({ ...state.coachSchedule, overrides: [] });
    renderCoachAvailabilityPanel();
  });
  $("scheduleHourToggleBtn")?.addEventListener("click", () => { state.coachScheduleShowAllHours = !state.coachScheduleShowAllHours; renderCoachAvailabilityPanel(); });
  $("saveCoachScheduleBtn")?.addEventListener("click", saveCoachSchedule);
}

function bindCoachSelfLessonPicker(editor) {
  editor.querySelectorAll("[data-self-lesson-id]").forEach((button) => button.addEventListener("click", () => {
    state.coachSelfLessonId = button.dataset.selfLessonId;
    renderCoachSelf();
  }));
  editor.querySelector("#coachSelfNewLessonBtn")?.addEventListener("click", async (event) => {
    if (getCoachSelfLessons().length >= 5) return alert("코치 한 명당 강의는 최대 5개까지 등록할 수 있습니다.");
    const name = window.prompt("새 강의 이름을 입력하세요.", "새 강의");
    if (!name?.trim()) return;
    event.currentTarget.disabled = true;
    try {
      const lesson = await createCoachLessonApi(name.trim());
      await Promise.all([loadCoachSelfLessonsApi(), loadCoachesFromApi()]);
      state.coachSelfLessonId = lesson.id;
      renderCoachSelf();
    } catch (error) {
      alert(error.message === "coach_lesson_limit_reached" ? "코치 한 명당 강의는 최대 5개까지 등록할 수 있습니다." : `강의를 만들지 못했습니다.\n${error.message}`);
      event.currentTarget.disabled = false;
    }
  });
}

function changeCoachScheduleWeek(days) {
  state.coachScheduleWeekStart = isoDateOnly(addLocalDays(getCoachScheduleWeekStart(), days));
  state.coachScheduleLoadState = "idle";
  state.coachScheduleDraft = null;
  loadCoachSchedule();
}

async function saveCoachSchedule() {
  const button = $("saveCoachScheduleBtn");
  const status = $("coachScheduleStatus");
  const weekStart = getCoachScheduleWeekStart();
  const from = isoDateOnly(weekStart);
  const to = isoDateOnly(addLocalDays(weekStart, 6));
  if (button) button.disabled = true;
  if (status) { status.textContent = "저장 중..."; status.className = "save-status loading"; }
  try {
    const coachId = getFallbackCoachKey();
    const result = await saveCoachScheduleApi({ coachId, from, to }, {
        coachId,
        from,
        to,
        weekly: state.coachScheduleEditMode === "weekly" ? buildWeeklyEntriesFromDraft() : (state.coachSchedule.weekly || []),
        overrides: state.coachScheduleEditMode === "week" ? buildScheduleOverridesFromDraft() : (state.coachSchedule.overrides || []),
    });
    state.coachSchedule = scheduleResultPayload(result);
    state.coachScheduleDraft = buildScheduleDraft(state.coachSchedule);
    state.coachScheduleLoadState = "loaded";
    if (status) { status.textContent = "저장 완료 · 매주 반복됩니다."; status.className = "save-status success"; }
    renderCoachAvailabilityPanel();
    if (state.activeView === "student") renderStudentHome();
  } catch (error) {
    const message = error instanceof TypeError ? "서버에 연결하지 못했습니다. 잠시 후 다시 시도해주세요." : error.message || "서버 오류";
    if (status) { status.textContent = `저장 실패: ${message}`; status.className = "save-status error"; }
  } finally {
    if (button) button.disabled = false;
  }
}

// Kept as a compatibility alias for older callers.
const loadCoachAvailability = loadCoachSchedule;

async function saveCoachSelfProfile(event) {
  event.preventDefault();
  const button = $("coachSelfProfileSaveBtn");
  const status = $("coachSelfProfileStatus");
  if (!button || !status) return;
  button.disabled = true;
  status.textContent = "저장 중...";
  status.className = "save-status loading";
  const payload = {
    nickname: $("coachSelfProfileNickname").value.trim(),
    image: $("coachSelfProfileImage").value.trim(),
    intro: $("coachSelfProfileIntro").value.trim(),
    roles: getCheckedValues("coachSelfProfileRole"),
    active: Boolean($("coachSelfProfileActive").checked),
  };
  try {
    const profile = await saveCoachProfileApi(payload);
    state.coachProfile = profile;
    applyCoachProfileToCatalog(profile);
    if (profile.active !== false) await loadCoachesFromApi();
    state.coachProfileLoadState = "loaded";
    render();
    const refreshedStatus = $("coachSelfProfileStatus");
    if (refreshedStatus) {
      refreshedStatus.textContent = "저장 완료";
      refreshedStatus.className = "save-status success";
    }
  } catch (error) {
    status.textContent = "저장 실패";
    status.className = "save-status error";
    alert(`프로필 정보를 저장하지 못했습니다.\n${error.message}`);
  } finally {
    button.disabled = false;
  }
}

async function saveCoachSelfLesson(event) {
  event.preventDefault();
  const id = $("coachSelfLessonId").value;
  const previous = getCoachSelfLessons().find((coach) => coach.id === id);
  if (!previous) return;
  const saveButton = $("coachSelfSaveBtn");
  saveButton.disabled = true;
  $("coachSelfSaveStatus").textContent = "저장 중...";
  $("coachSelfSaveStatus").className = "save-status loading";
  const next = {
    ...previous,
    manualCoachEdit: true,
    name: $("coachSelfLessonName").value.trim(),
    tagline: $("coachSelfTagline").value.trim(),
    image: $("coachSelfLessonImage").value.trim(),
    published: Boolean($("coachSelfLessonPublished").checked),
    price: (updateCoachSelfPriceValue(), $("coachSelfPrice").value.trim() || "가격 상담"),
    purpose: getCheckedValues("coachSelfPurposeChoice"),
    roles: getCheckedValues("coachSelfRoleChoice"),
    bio: $("coachSelfBio").value.trim(),
  };
  const previousIndex = state.coaches.findIndex((coach) => coach.id === id);
  try {
    const savedCoach = isAdminUser()
      ? await runAdminRequest(() => saveCoachToApi(next, previousIndex))
      : await saveCoachLessonToApi(next);
    const normalized = migrateCoachImages([savedCoach])[0];
    if (Array.isArray(state.coachSelfLessons)) {
      state.coachSelfLessons = state.coachSelfLessons.map((coach) => coach.id === id ? normalized : coach);
    }
    await loadCoachesFromApi();
    renderCoachSelf();
    const refreshedStatus = $("coachSelfSaveStatus");
    if (refreshedStatus) {
      refreshedStatus.textContent = "저장되었습니다!";
      refreshedStatus.className = "save-status success";
    }
  } catch (error) {
    $("coachSelfSaveStatus").textContent = "저장 실패";
    $("coachSelfSaveStatus").className = "save-status error";
    alert(`강의 정보를 저장하지 못했습니다.\n${error.message}`);
  } finally {
    saveButton.disabled = false;
  }
}

function fillCoachForm(coach) {
  const setting = coach && coach.coachKey
    ? normalizeAdminCoachSetting(coach, state.coaches)
    : null;
  $("coachForm").hidden = !setting;
  $("coachId").value = setting?.coachKey || "";
  $("adminSelectedCoach").innerHTML = setting
    ? `<strong>${escapeHtml(setting.name)}</strong><span>${escapeHtml(setting.coachKey)} · ${setting.lessonCount}개 강의</span>`
    : "코치 목록에서 관리할 코치를 선택하세요.";
  renderBadgePicker(setting?.badges || []);
  $("coachCommissionRate").value = setting ? formatCommissionRate(setting.commissionRate) : "";
  $("coachAdminNote").value = setting?.adminNote || "";
  $("saveCoachBtn").disabled = !setting;
}

function renderAdminChoiceControls(selectedPurposes = [], selectedRoles = [], selectedBadges = []) {
  const category = $("coachCategory").value || state.category || "league";
  const filters = filterSets[category] || filterSets.league;
  const purposeOptions = filters.type.filter((item) => item.id !== "all");
  if ($("coachPurposeChoices")) $("coachPurposeChoices").innerHTML = purposeOptions.map((item) => `
    <label><input type="checkbox" name="coachPurposeChoice" value="${item.id}" ${selectedPurposes.includes(item.id) ? "checked" : ""}> ${item.label}</label>
  `).join("");

  const lineOptions = adminLineOptions[category] || adminLineOptions.league;
  const fieldOptions = adminFieldOptions[category] || adminFieldOptions.league;
  if ($("coachRoleChoices")) $("coachRoleChoices").innerHTML = `
    <div class="choice-subgroup">
      <span>라인</span>
      <div class="choice-grid">
        ${lineOptions.map((role) => `<label><input type="checkbox" name="coachRoleChoice" value="${role}" ${selectedRoles.includes(role) ? "checked" : ""}> ${role}</label>`).join("")}
      </div>
    </div>
    <div class="choice-subgroup">
      <span>분야</span>
      <div class="choice-grid">
        ${fieldOptions.map((role) => `<label><input type="checkbox" name="coachRoleChoice" value="${role}" ${selectedRoles.includes(role) ? "checked" : ""}> ${role}</label>`).join("")}
      </div>
    </div>
  `;

  if ($("coachBadgeChoices") && $("coachBadgeSelect")) {
    renderBadgePicker(selectedBadges);
  } else if ($("coachBadges")) {
    $("coachBadges").value = selectedBadges.join(", ");
  }
}

function renderBadgePicker(selectedBadges = []) {
  const selected = [...new Set(selectedBadges.filter(Boolean))];
  if (!$("coachBadgeSelect") || !$("coachBadgeChoices")) return;
  $("coachBadgeSelect").innerHTML = `
    <option value="">배지 선택</option>
    ${badgeOptions
      .filter((badge) => !selected.includes(badge))
      .map((badge) => `<option value="${badge}">${badge}</option>`)
      .join("")}
  `;
  $("coachBadgeChoices").innerHTML = selected.length ? selected.map((badge) => `
    <label><input type="checkbox" name="coachBadgeChoice" value="${badge}" checked> ${badge}</label>
  `).join("") : `<span class="choice-empty">선택한 배지 없음</span>`;
}

function addSelectedBadge() {
  if (!$("coachBadgeSelect")) return;
  const badge = $("coachBadgeSelect").value;
  if (!badge) return;
  renderBadgePicker([...getCheckedValues("coachBadgeChoice"), badge]);
}

function getCheckedValues(name) {
  return Array.from(document.querySelectorAll(`input[name="${name}"]:checked`)).map((input) => input.value);
}

function getTierFromBadges(badges, fallback = "일반") {
  if (badges.includes("엠버서더")) return "엠버서더";
  if (badges.includes("최우수")) return "최우수";
  if (badges.includes("우수")) return "우수";
  if (badges.includes("일반")) return "일반";
  return fallback || "일반";
}

function setCoachSaveStatus(message = "", type = "") {
  const status = $("coachSaveStatus");
  if (!status) return;
  status.textContent = message;
  status.className = `save-status ${type}`.trim();
}

function renderPriceUnitOptions(type, selected = "") {
  const units = priceUnits[type] || priceUnits.time;
  $("coachPriceUnit").innerHTML = units.map((unit) => `<option value="${unit}" ${unit === selected ? "selected" : ""}>${unit}</option>`).join("");
}

function setPriceFields(price) {
  const textPrice = String(price || "");
  const amount = textPrice.match(/[\d,]+/)?.[0]?.replace(/[^\d]/g, "") || "";
  const unit = textPrice.includes("게임") ? "game" : "time";
  const unitText = textPrice.split("/")[1]?.trim() || (unit === "game" ? "1게임" : "1시간");
  $("coachPriceAmount").value = amount;
  $("coachPriceUnitType").value = unit;
  renderPriceUnitOptions(unit, unitText);
  updateCoachPriceValue();
}

function updateCoachPriceValue() {
  const amount = Number(String($("coachPriceAmount").value || "").replace(/[^\d]/g, ""));
  const amountText = amount ? `${amount.toLocaleString("ko-KR")}원` : "가격 상담";
  $("coachPrice").value = `${amountText} / ${$("coachPriceUnit").value}`;
}

function updateCoachImagePreview() {
  const preview = $("coachImagePreview");
  preview.style.backgroundImage = `url("${$("coachImage").value.trim() || "assets/logo.jpg"}")`;
  preview.style.backgroundPosition = "center center";
  preview.style.backgroundSize = "cover";
}

function updateWideImagePreview(inputId, previewId) {
  const preview = $(previewId);
  if (!preview) return;
  const image = $(inputId).value.trim();
  preview.style.backgroundImage = image ? `url("${image}")` : "none";
  preview.style.backgroundPosition = "center center";
  preview.style.backgroundSize = "cover";
  const empty = preview.querySelector(".image-preview-empty");
  if (empty) empty.hidden = Boolean(image);
}

function handleCoachImageFile(event) {
  const file = event.target.files?.[0];
  if (!file) return;
  if (!file.type.startsWith("image/")) {
    alert("이미지 파일만 선택할 수 있습니다.");
    event.target.value = "";
    return;
  }
  if (file.size > 1024 * 1024) {
    alert("이미지는 1MB 이하로 올려주세요. 큰 이미지는 저장 공간을 빠르게 채울 수 있습니다.");
    event.target.value = "";
    return;
  }
  const reader = new FileReader();
  reader.addEventListener("load", () => {
    state.cropSourceImage = String(reader.result || "");
    $("coachImage").value = state.cropSourceImage;
    updateCoachImagePreview();
    openCropModal({
      inputId: "coachImage",
      previewId: "coachImagePreview",
      width: 520,
      height: 520,
      label: "일반 목록 이미지",
    });
  });
  reader.readAsDataURL(file);
}

function handleCoachSelfProfileImageFile(event, inputId = "coachSelfProfileImage", previewId = "coachSelfProfileImagePreview", label = "프로필 이미지") {
  const file = event.target.files?.[0];
  if (!file) return;
  if (!file.type.startsWith("image/")) {
    alert("이미지 파일만 선택할 수 있습니다.");
    event.target.value = "";
    return;
  }
  if (file.size > 1024 * 1024) {
    alert("이미지는 1MB 이하로 올려주세요.");
    event.target.value = "";
    return;
  }
  const reader = new FileReader();
  reader.addEventListener("load", () => {
    state.cropSourceImage = String(reader.result || "");
    $(inputId).value = state.cropSourceImage;
    updateWideImagePreview(inputId, previewId);
    openCropModal({
      inputId,
      previewId,
      width: 520,
      height: 520,
      label,
    });
  });
  reader.readAsDataURL(file);
}

function handleWideCoachImageFile(event, inputId, previewId, label) {
  const file = event.target.files?.[0];
  if (!file) return;
  if (!file.type.startsWith("image/")) {
    alert("이미지 파일만 선택할 수 있습니다.");
    event.target.value = "";
    return;
  }
  if (file.size > 3 * 1024 * 1024) {
    alert(`${label}는 3MB 이하로 올려주세요.`);
    event.target.value = "";
    return;
  }
  const reader = new FileReader();
  reader.addEventListener("load", () => {
    state.cropSourceImage = String(reader.result || "");
    $(inputId).value = state.cropSourceImage;
    updateWideImagePreview(inputId, previewId);
    openCropModal({ inputId, previewId, width: 1200, height: 675, label });
  });
  reader.readAsDataURL(file);
}

function openCropModal(target = null) {
  state.cropTarget = target || {
    inputId: "coachImage",
    previewId: "coachImagePreview",
    width: 520,
    height: 520,
    label: "일반 목록 이미지",
  };
  const image = state.cropSourceImage || $(state.cropTarget.inputId).value.trim();
  if (!image) return;
  $("cropImage").src = image;
  $("cropTitle").textContent = `${state.cropTarget.label} 범위 지정`;
  $("cropModal").hidden = false;
  $("cropX").value = 50;
  $("cropY").value = 50;
  $("cropSize").value = 60;
  setTimeout(updateCropBox, 0);
}

function closeCropModal() {
  $("cropModal").hidden = true;
}

function getCropRect() {
  const image = $("cropImage");
  const stage = image.getBoundingClientRect();
  const target = state.cropTarget || { width: 520, height: 520 };
  const ratio = target.width / target.height;
  const scale = Number($("cropSize").value) / 100;
  let maxWidth = stage.width;
  let maxHeight = maxWidth / ratio;
  if (maxHeight > stage.height) {
    maxHeight = stage.height;
    maxWidth = maxHeight * ratio;
  }
  const width = maxWidth * scale;
  const height = maxHeight * scale;
  const maxX = Math.max(0, stage.width - width);
  const maxY = Math.max(0, stage.height - height);
  const left = stage.left + maxX * (Number($("cropX").value) / 100);
  const top = stage.top + maxY * (Number($("cropY").value) / 100);
  return { left, top, width, height, imageRect: stage };
}

function updateCropBox() {
  const rect = getCropRect();
  const parentRect = document.querySelector(".crop-stage").getBoundingClientRect();
  const box = $("cropBox");
  box.style.width = `${rect.width}px`;
  box.style.height = `${rect.height}px`;
  box.style.left = `${rect.left - parentRect.left}px`;
  box.style.top = `${rect.top - parentRect.top}px`;
}

function setCropCenterFromPointer(event) {
  const rect = getCropRect();
  const imageRect = rect.imageRect;
  const maxX = Math.max(1, imageRect.width - rect.width);
  const maxY = Math.max(1, imageRect.height - rect.height);
  const left = Math.max(0, Math.min(maxX, event.clientX - imageRect.left - rect.width / 2));
  const top = Math.max(0, Math.min(maxY, event.clientY - imageRect.top - rect.height / 2));
  $("cropX").value = Math.round((left / maxX) * 100);
  $("cropY").value = Math.round((top / maxY) * 100);
  updateCropBox();
}

function moveCropToPointer(event) {
  if (event.target === $("cropImage")) {
    setCropCenterFromPointer(event);
  }
}

function startCropDrag(event) {
  event.preventDefault();
  event.stopPropagation();
  $("cropBox").setPointerCapture(event.pointerId);
  const onMove = (moveEvent) => setCropCenterFromPointer(moveEvent);
  const onEnd = () => {
    $("cropBox").removeEventListener("pointermove", onMove);
    $("cropBox").removeEventListener("pointerup", onEnd);
    $("cropBox").removeEventListener("pointercancel", onEnd);
  };
  $("cropBox").addEventListener("pointermove", onMove);
  $("cropBox").addEventListener("pointerup", onEnd);
  $("cropBox").addEventListener("pointercancel", onEnd);
}

function applyImageCrop() {
  const image = $("cropImage");
  if (!image.complete || !image.naturalWidth) return;
  const rect = getCropRect();
  const scaleX = image.naturalWidth / rect.imageRect.width;
  const scaleY = image.naturalHeight / rect.imageRect.height;
  const sourceX = Math.max(0, (rect.left - rect.imageRect.left) * scaleX);
  const sourceY = Math.max(0, (rect.top - rect.imageRect.top) * scaleY);
  const sourceWidth = rect.width * scaleX;
  const sourceHeight = rect.height * scaleY;
  const target = state.cropTarget || {
    inputId: "coachImage",
    previewId: "coachImagePreview",
    width: 520,
    height: 520,
  };
  const canvas = document.createElement("canvas");
  canvas.width = target.width;
  canvas.height = target.height;
  const context = canvas.getContext("2d");
  context.drawImage(image, sourceX, sourceY, sourceWidth, sourceHeight, 0, 0, canvas.width, canvas.height);
  $(target.inputId).value = canvas.toDataURL("image/jpeg", 0.78);
  if (target.inputId === "coachImage") {
    $("coachImagePosition").value = "center center";
    updateCoachImagePreview();
  } else {
    updateWideImagePreview(target.inputId, target.previewId);
  }
  state.cropSourceImage = "";
  state.cropTarget = null;
  closeCropModal();
}

async function saveCoachFromForm() {
  const saveButton = $("saveCoachBtn");
  const coachKey = $("coachId").value || state.adminSelectedCoachKey;
  if (!coachKey) {
    setCoachSaveStatus("코치를 먼저 선택하세요.", "error");
    return;
  }
  const commissionRate = Number($("coachCommissionRate").value);
  if (!Number.isInteger(commissionRate) || commissionRate < 0 || commissionRate > 100) {
    setCoachSaveStatus("수수료율은 0~100 사이의 정수로 입력하세요.", "error");
    $("coachCommissionRate").focus();
    return;
  }
  saveButton.disabled = true;
  setCoachSaveStatus("저장 중...", "loading");
  const payload = {
    badges: getCheckedValues("coachBadgeChoice"),
    commissionRate,
    adminNote: $("coachAdminNote").value.trim(),
  };
  try {
    const saved = await runAdminRequest(() => saveAdminCoachSettings(coachKey, payload, state.coaches));
    state.adminCoachSettings = state.adminCoachSettings.map((item) => item.coachKey === coachKey ? saved : item);
    state.adminSelectedCoachKey = coachKey;
    await loadCoachesFromApi();
    renderAdmin();
    setCoachSaveStatus("저장 완료", "success");
    setTimeout(() => {
      if ($("coachSaveStatus")?.textContent === "저장 완료") setCoachSaveStatus();
    }, 2200);
  } catch (error) {
    setCoachSaveStatus("저장 실패", "error");
    alert(`코치 관리자 설정을 저장하지 못했습니다.\n${error.message}`);
  } finally {
    saveButton.disabled = false;
  }
}

async function deleteSelectedCoach() {
  const id = $("coachId").value;
  if (!id) return;
  try {
    await runAdminRequest(() => deleteCoachFromApi(id));
    state.coaches = state.coaches.filter((coach) => coach.id !== id);
    state.selectedCoachId = null;
    fillCoachForm();
    render();
  } catch (error) {
    alert(`코치 정보를 삭제하지 못했습니다.\n${error.message}`);
  }
}

function categoryLabel(id) {
  return categories.find((category) => category.id === id)?.label || id;
}

boot();
