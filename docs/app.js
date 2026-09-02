
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
import { createMarketPage } from "./js/pages/market.js";
import { createStudentDashboardPage } from "./js/pages/studentDashboard.js";
import { createReservationPage } from "./js/pages/reservationPage.js";
import { createAuthAccountPage } from "./js/pages/authAccount.js";
import { createAdminDashboardPage } from "./js/pages/adminDashboard.js";
import { createCoachSelfPage } from "./js/pages/coachSelf.js";
import { createImageCropController } from "./js/components/imageCrop.js";


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
  applyTheme(localStorage.getItem(THEME_KEY) || "dark");
  Object.entries(text).forEach(([id, value]) => {
    const el = $(id);
    if (!el) return;
    if (el.tagName === "INPUT") el.placeholder = value;
    else el.textContent = value;
  });
  $("navStudent").textContent = "내 수강";
  $("navCoachSearch").textContent = "코치 찾기";
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

  document.querySelectorAll("[data-view-jump]").forEach((button) => {
    button.addEventListener("click", () => {
      const nextView = button.dataset.viewJump;
      if (!nextView || !document.getElementById(`${nextView}View`)) return;
      state.activeView = nextView;
      render();
      window.scrollTo({ top: 0, behavior: "smooth" });
    });
  });

  $("heroCoachSearchBtn")?.addEventListener("click", () => {
    openCoachExplorer();
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
  renderAccountView();
  renderBookings();
  renderAdmin();
  renderUsers();
  renderCoachRequests();
  renderCoachSelf();
  maybeLoadCoachDashboardReservations();
  maybeLoadStudentReservations();
}

function renderAccountView() {
  const container = $("accountViewContent");
  if (!container) return;
  container.innerHTML = "";
  if (!state.currentUser) {
    container.innerHTML = `<div class="student-empty account-login-empty"><strong>로그인이 필요합니다.</strong><button class="primary" id="accountLoginBtn" type="button">로그인</button></div>`;
    $("accountLoginBtn")?.addEventListener("click", () => openAuthModal("login"));
    return;
  }
  mountAccountPanel(container);
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

let imageCropController;
function updateCoachImagePreview(...args) { return imageCropController.updateCoachImagePreview(...args); }
function updateWideImagePreview(...args) { return imageCropController.updateWideImagePreview(...args); }
function handleCoachImageFile(...args) { return imageCropController.handleCoachImageFile(...args); }
function handleCoachSelfProfileImageFile(...args) { return imageCropController.handleCoachSelfProfileImageFile(...args); }
function handleWideCoachImageFile(...args) { return imageCropController.handleWideCoachImageFile(...args); }
function openCropModal(...args) { return imageCropController.openCropModal(...args); }
function closeCropModal(...args) { return imageCropController.closeCropModal(...args); }
function getCropRect(...args) { return imageCropController.getCropRect(...args); }
function updateCropBox(...args) { return imageCropController.updateCropBox(...args); }
function setCropCenterFromPointer(...args) { return imageCropController.setCropCenterFromPointer(...args); }
function moveCropToPointer(...args) { return imageCropController.moveCropToPointer(...args); }
function startCropDrag(...args) { return imageCropController.startCropDrag(...args); }
function applyImageCrop(...args) { return imageCropController.applyImageCrop(...args); }

imageCropController = createImageCropController();

let marketPage;

function getCoachKey(...args) { return marketPage.getCoachKey(...args); }
function getCoachIdentityFromGroup(...args) { return marketPage.getCoachIdentityFromGroup(...args); }
function getCoachIdentities(...args) { return marketPage.getCoachIdentities(...args); }
function selectCoachIdentity(...args) { return marketPage.selectCoachIdentity(...args); }
function renderSidebarCoaches(...args) { return marketPage.renderSidebarCoaches(...args); }
function openCoachExplorer(...args) { return marketPage.openCoachExplorer(...args); }
function closeCoachExplorer(...args) { return marketPage.closeCoachExplorer(...args); }
function renderCoachExplorer(...args) { return marketPage.renderCoachExplorer(...args); }
function getVisibleCoaches(...args) { return marketPage.getVisibleCoaches(...args); }
function renderMarket(...args) { return marketPage.renderMarket(...args); }
function renderFeatured(...args) { return marketPage.renderFeatured(...args); }
function renderDetail(...args) { return marketPage.renderDetail(...args); }
function openLessonDetail(...args) { return marketPage.openLessonDetail(...args); }
function closeLessonDetail(...args) { return marketPage.closeLessonDetail(...args); }
function loadPublicAvailability(...args) { return marketPage.loadPublicAvailability(...args); }
function loadCoachReviews(...args) { return marketPage.loadCoachReviews(...args); }
function mountBookingForm(...args) { return marketPage.mountBookingForm(...args); }
function normalizeAvailabilitySlot(...args) { return marketPage.normalizeAvailabilitySlot(...args); }

let reservationPage;
function maybeLoadStudentReservations(...args) { return reservationPage.maybeLoadStudentReservations(...args); }
function loadStudentReservations(...args) { return reservationPage.loadStudentReservations(...args); }
function getRefundRequestFor(...args) { return reservationPage.getRefundRequestFor(...args); }
function requestReservationCancel(...args) { return reservationPage.requestReservationCancel(...args); }
function submitReservationReview(...args) { return reservationPage.submitReservationReview(...args); }
function startTossPayment(...args) { return reservationPage.startTossPayment(...args); }
function handlePaymentReturn(...args) { return reservationPage.handlePaymentReturn(...args); }
function maybeLoadCoachDashboardReservations(...args) { return reservationPage.maybeLoadCoachDashboardReservations(...args); }
function loadCoachReservations(...args) { return reservationPage.loadCoachReservations(...args); }
function loadReservations(...args) { return reservationPage.loadReservations(...args); }
function loadAdminRefundRequests(...args) { return reservationPage.loadAdminRefundRequests(...args); }
function renderRefundAdminPanel(...args) { return reservationPage.renderRefundAdminPanel(...args); }
function decideRefundRequest(...args) { return reservationPage.decideRefundRequest(...args); }
function runAdminRequest(...args) { return reservationPage.runAdminRequest(...args); }
function getFilteredBookings(...args) { return reservationPage.getFilteredBookings(...args); }
function renderBookingDetail(...args) { return reservationPage.renderBookingDetail(...args); }
function refundPayment(...args) { return reservationPage.refundPayment(...args); }
function renderBookings(...args) { return reservationPage.renderBookings(...args); }

let authAccountPage;
function showOAuthResult(...args) { return authAccountPage.showOAuthResult(...args); }
function hasCoachMenuAccess(...args) { return authAccountPage.hasCoachMenuAccess(...args); }
function getUserRoles(...args) { return authAccountPage.getUserRoles(...args); }
function isAdminUser(...args) { return authAccountPage.isAdminUser(...args); }
function isCoachUser(...args) { return authAccountPage.isCoachUser(...args); }
function getFallbackCoachKey(...args) { return authAccountPage.getFallbackCoachKey(...args); }
function getKnownCoachKeyForUser(...args) { return authAccountPage.getKnownCoachKeyForUser(...args); }
function hasCoachLikeAccount(...args) { return authAccountPage.hasCoachLikeAccount(...args); }
function renderRoleMenu(...args) { return authAccountPage.renderRoleMenu(...args); }
function renderUserActions(...args) { return authAccountPage.renderUserActions(...args); }
function handleLoginButtonClick(...args) { return authAccountPage.handleLoginButtonClick(...args); }
function handleDiscordButtonClick(...args) { return authAccountPage.handleDiscordButtonClick(...args); }
function startDiscordOAuth(...args) { return authAccountPage.startDiscordOAuth(...args); }
function applyTheme(...args) { return authAccountPage.applyTheme(...args); }
function toggleTheme(...args) { return authAccountPage.toggleTheme(...args); }
function closeAuthModal(...args) { return authAccountPage.closeAuthModal(...args); }
function openAuthModal(...args) { return authAccountPage.openAuthModal(...args); }
function bindPasswordToggles(...args) { return authAccountPage.bindPasswordToggles(...args); }
function renderAuthMarkup(...args) { return authAccountPage.renderAuthMarkup(...args); }
function bindAuthForm(...args) { return authAccountPage.bindAuthForm(...args); }
function bindGuestConsultForm(...args) { return authAccountPage.bindGuestConsultForm(...args); }
function renderAccountPanelMarkup(...args) { return authAccountPage.renderAccountPanelMarkup(...args); }
function mountAccountPanel(...args) { return authAccountPage.mountAccountPanel(...args); }
function saveAccountNickname(...args) { return authAccountPage.saveAccountNickname(...args); }
function deleteCurrentAccount(...args) { return authAccountPage.deleteCurrentAccount(...args); }
function loadCurrentUser(...args) { return authAccountPage.loadCurrentUser(...args); }
function logoutUser(...args) { return authAccountPage.logoutUser(...args); }
function getAuthErrorMessage(...args) { return authAccountPage.getAuthErrorMessage(...args); }
function ensureAdminAccess(...args) { return authAccountPage.ensureAdminAccess(...args); }
function loginForReservations(...args) { return authAccountPage.loginForReservations(...args); }

let adminDashboardPage;
function loadAdminCoachSettings(...args) { return adminDashboardPage.loadAdminCoachSettings(...args); }
function resetCoachesToSamples(...args) { return adminDashboardPage.resetCoachesToSamples(...args); }
function loadUsers(...args) { return adminDashboardPage.loadUsers(...args); }
function saveUserRole(...args) { return adminDashboardPage.saveUserRole(...args); }
function submitCoachApplication(...args) { return adminDashboardPage.submitCoachApplication(...args); }
function approveCoachRequest(...args) { return adminDashboardPage.approveCoachRequest(...args); }
function rejectCoachRequest(...args) { return adminDashboardPage.rejectCoachRequest(...args); }
function getCoachRequestErrorMessage(...args) { return adminDashboardPage.getCoachRequestErrorMessage(...args); }
function renderAdmin(...args) { return adminDashboardPage.renderAdmin(...args); }
function formatCommissionRate(...args) { return adminDashboardPage.formatCommissionRate(...args); }
function selectAdminCoach(...args) { return adminDashboardPage.selectAdminCoach(...args); }
function renderUsers(...args) { return adminDashboardPage.renderUsers(...args); }
function renderCoachRequests(...args) { return adminDashboardPage.renderCoachRequests(...args); }
function getCoachRequestStatusLabel(...args) { return adminDashboardPage.getCoachRequestStatusLabel(...args); }
function getUserCoachLabel(...args) { return adminDashboardPage.getUserCoachLabel(...args); }
function getUserRoleFlags(...args) { return adminDashboardPage.getUserRoleFlags(...args); }
function getUserSaveClass(...args) { return adminDashboardPage.getUserSaveClass(...args); }
function getRoleLabel(...args) { return adminDashboardPage.getRoleLabel(...args); }
function findUserCoachSelect(...args) { return adminDashboardPage.findUserCoachSelect(...args); }
function fillCoachForm(...args) { return adminDashboardPage.fillCoachForm(...args); }
function renderAdminChoiceControls(...args) { return adminDashboardPage.renderAdminChoiceControls(...args); }
function renderBadgePicker(...args) { return adminDashboardPage.renderBadgePicker(...args); }
function addSelectedBadge(...args) { return adminDashboardPage.addSelectedBadge(...args); }
function getCheckedValues(...args) { return adminDashboardPage.getCheckedValues(...args); }
function getTierFromBadges(...args) { return adminDashboardPage.getTierFromBadges(...args); }
function setCoachSaveStatus(...args) { return adminDashboardPage.setCoachSaveStatus(...args); }
function renderPriceUnitOptions(...args) { return adminDashboardPage.renderPriceUnitOptions(...args); }
function setPriceFields(...args) { return adminDashboardPage.setPriceFields(...args); }
function updateCoachPriceValue(...args) { return adminDashboardPage.updateCoachPriceValue(...args); }
function saveCoachFromForm(...args) { return adminDashboardPage.saveCoachFromForm(...args); }
function deleteSelectedCoach(...args) { return adminDashboardPage.deleteSelectedCoach(...args); }

let coachSelfPage;
function applyCoachProfileToCatalog(...args) { return coachSelfPage.applyCoachProfileToCatalog(...args); }
function loadCoachProfile(...args) { return coachSelfPage.loadCoachProfile(...args); }
function loadCoachSelfLessonsApi(...args) { return coachSelfPage.loadCoachSelfLessonsApi(...args); }
function saveCoachProfileApi(...args) { return coachSelfPage.saveCoachProfileApi(...args); }
function saveCoachLessonToApi(...args) { return coachSelfPage.saveCoachLessonToApi(...args); }
function createCoachLessonApi(...args) { return coachSelfPage.createCoachLessonApi(...args); }
function deleteCoachLessonApi(...args) { return coachSelfPage.deleteCoachLessonApi(...args); }
function getCoachSelfLessons(...args) { return coachSelfPage.getCoachSelfLessons(...args); }
function getCoachProfileFormValue(...args) { return coachSelfPage.getCoachProfileFormValue(...args); }
function renderCoachSelfProfile(...args) { return coachSelfPage.renderCoachSelfProfile(...args); }
function renderCoachSelf(...args) { return coachSelfPage.renderCoachSelf(...args); }
function renderCoachSelfEditor(...args) { return coachSelfPage.renderCoachSelfEditor(...args); }
function renderCoachSelfPriceUnitOptions(...args) { return coachSelfPage.renderCoachSelfPriceUnitOptions(...args); }
function updateCoachSelfPriceValue(...args) { return coachSelfPage.updateCoachSelfPriceValue(...args); }
function normalizeCoachAvailability(...args) { return coachSelfPage.normalizeCoachAvailability(...args); }
function getCoachScheduleWeekStart(...args) { return coachSelfPage.getCoachScheduleWeekStart(...args); }
function scheduleResultPayload(...args) { return coachSelfPage.scheduleResultPayload(...args); }
function scheduleSlotDate(...args) { return coachSelfPage.scheduleSlotDate(...args); }
function scheduleSlotMinute(...args) { return coachSelfPage.scheduleSlotMinute(...args); }
function scheduleSlotLabel(...args) { return coachSelfPage.scheduleSlotLabel(...args); }
function getScheduleCell(...args) { return coachSelfPage.getScheduleCell(...args); }
function buildScheduleDraft(...args) { return coachSelfPage.buildScheduleDraft(...args); }
function buildScheduleBaseDraft(...args) { return coachSelfPage.buildScheduleBaseDraft(...args); }
function buildScheduleOverridesFromDraft(...args) { return coachSelfPage.buildScheduleOverridesFromDraft(...args); }
function buildWeeklyEntriesFromDraft(...args) { return coachSelfPage.buildWeeklyEntriesFromDraft(...args); }
function loadCoachSchedule(...args) { return coachSelfPage.loadCoachSchedule(...args); }
function renderScheduleSummaryMarkup(...args) { return coachSelfPage.renderScheduleSummaryMarkup(...args); }
function renderCoachAvailabilityPanel(...args) { return coachSelfPage.renderCoachAvailabilityPanel(...args); }
function bindCoachSelfLessonPicker(...args) { return coachSelfPage.bindCoachSelfLessonPicker(...args); }
function changeCoachScheduleWeek(...args) { return coachSelfPage.changeCoachScheduleWeek(...args); }
function saveCoachSchedule(...args) { return coachSelfPage.saveCoachSchedule(...args); }
function loadCoachAvailability(...args) { return coachSelfPage.loadCoachAvailability(...args); }
function saveCoachSelfProfile(...args) { return coachSelfPage.saveCoachSelfProfile(...args); }
function saveCoachSelfLesson(...args) { return coachSelfPage.saveCoachSelfLesson(...args); }

let studentDashboardPage;
function renderStudentHome(...args) { return studentDashboardPage.renderStudentHome(...args); }
function setStudentHeader(...args) { return studentDashboardPage.setStudentHeader(...args); }
function renderCoachDashboard(...args) { return studentDashboardPage.renderCoachDashboard(...args); }
function confirmCoachReservation(...args) { return studentDashboardPage.confirmCoachReservation(...args); }

marketPage = createMarketPage({
  render: (...args) => render(...args),
  openAuthModal: (...args) => openAuthModal(...args),
  startTossPayment: (...args) => startTossPayment(...args),
  loadCoachesFromApi: (...args) => loadCoachesFromApi(...args),
});
reservationPage = createReservationPage({
  isCoachUser: (...args) => isCoachUser(...args),
  renderApp: (...args) => render(...args),
  renderStudentHome: (...args) => renderStudentHome(...args),
  renderMetrics: (...args) => renderMetrics(...args),
  loginForReservations: (...args) => loginForReservations(...args),
});
coachSelfPage = createCoachSelfPage({
  render: (...args) => render(...args),
  renderStudentHome: (...args) => renderStudentHome(...args),
  isCoachUser: (...args) => isCoachUser(...args),
  isAdminUser: (...args) => isAdminUser(...args),
  getFallbackCoachKey: (...args) => getFallbackCoachKey(...args),
  getCoachKey: (...args) => getCoachKey(...args),
  getCoachIdentities: (...args) => getCoachIdentities(...args),
  getCoachIdentityFromGroup: (...args) => getCoachIdentityFromGroup(...args),
  loadCoachesFromApi: (...args) => loadCoachesFromApi(...args),
  loadAdminCoachSettings: (...args) => loadAdminCoachSettings(...args),
  selectAdminCoach: (...args) => selectAdminCoach(...args),
  runAdminRequest: (...args) => runAdminRequest(...args),
  getCheckedValues: (...args) => getCheckedValues(...args),
  migrateCoachImages: (...args) => migrateCoachImages(...args),
  normalizeAvailabilitySlot: (...args) => normalizeAvailabilitySlot(...args),
  updateWideImagePreview: (...args) => updateWideImagePreview(...args),
  handleCoachSelfProfileImageFile: (...args) => handleCoachSelfProfileImageFile(...args),
  openCropModal: (...args) => openCropModal(...args),
});
authAccountPage = createAuthAccountPage({
  render: (...args) => render(...args),
  loadCoachProfile: (...args) => loadCoachProfile(...args),
  handlePaymentReturn: (...args) => handlePaymentReturn(...args),
  renderScheduleSummaryMarkup: (...args) => renderScheduleSummaryMarkup(...args),
});
adminDashboardPage = createAdminDashboardPage({
  render: (...args) => render(...args),
  renderMarket: (...args) => renderMarket(...args),
  loadCoachesFromApi: (...args) => loadCoachesFromApi(...args),
  runAdminRequest: (...args) => runAdminRequest(...args),
  isAdminUser: (...args) => isAdminUser(...args),
  isCoachUser: (...args) => isCoachUser(...args),
  getCoachKey: (...args) => getCoachKey(...args),
  getCoachIdentities: (...args) => getCoachIdentities(...args),
  getPublicCatalogCoaches: (...args) => getPublicCatalogCoaches(...args),
  migrateCoachImages: (...args) => migrateCoachImages(...args),
  openAuthModal: (...args) => openAuthModal(...args),
  renderRoleMenu: (...args) => renderRoleMenu(...args),
});
studentDashboardPage = createStudentDashboardPage({
  isCoachUser: (...args) => isCoachUser(...args),
  openAuthModal: (...args) => openAuthModal(...args),
  mountAccountPanel: (...args) => mountAccountPanel(...args),
  loadCoachSchedule: (...args) => loadCoachSchedule(...args),
  loadCoachReservations: (...args) => loadCoachReservations(...args),
  startTossPayment: (...args) => startTossPayment(...args),
  requestReservationCancel: (...args) => requestReservationCancel(...args),
  submitReservationReview: (...args) => submitReservationReview(...args),
  getRefundRequestFor: (...args) => getRefundRequestFor(...args),
});
boot();
