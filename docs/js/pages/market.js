import { categories, filterSets, purposes, text, tierRank, state } from "../catalog.js";
import { fetchCoachAvailability, fetchCoachReviews } from "../coachService.js";
import { buildReservationPayload, submitReservation } from "../reservations.js";
import { addLocalDays, byId as $, escapeHtml, formatDateTime, isoDateOnly } from "../utils.js";

export function createMarketPage({
  render: renderApp,
  openAuthModal,
  startTossPayment,
  loadCoachesFromApi,
}) {
  function bindAuthButtons(root = document) {
    root.querySelectorAll("[data-open-auth]").forEach((button) => {
      button.addEventListener("click", () => openAuthModal(button.dataset.openAuth));
    });
  }

function getCoachKey(coach) {
  return String(coach?.coachKey || coach?.id || "");
}

function categoryLabel(id) {
  return categories.find((category) => category.id === id)?.label || id;
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
      renderApp();
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
      renderApp();
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
    $("coachList").innerHTML = `<div class="empty">코치 목록을 불러오지 못했습니다.<br><button class="secondary" type="button" id="retryCoachesBtn">다시 불러오기</button></div>`;
    $("retryCoachesBtn")?.addEventListener("click", loadCoachesFromApi);
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
  $("coachList").innerHTML = listed.length ? listed.map(renderCoachCard).join("") : `
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

function renderFeaturedCard(coach) {
  const originalPrice = getOriginalPrice(coach.price);
  const featuredImage = getFeaturedImage(coach);
  const purposeText = getPurposeLabels(coach.purpose).slice(0, 2).join(" · ");
  return `
    <article class="featured-card ${getTierClass(coach)}" data-coach-id="${escapeHtml(coach.id)}">
      <div class="featured-image">
        <img src="${escapeHtml(featuredImage)}" alt="" style="${escapeHtml(getWideImageStyle(coach, "featuredImagePosition"))}">
        <span class="ad-label">추천</span>
        <span class="tier-ribbon">${escapeHtml(coach.tier)}</span>
      </div>
      <div class="featured-body">
        <h3>${escapeHtml(coach.name)}</h3>
        <p class="coach-owner">${escapeHtml(coach.coachProfileName || coach.name)}</p>
        <p class="purpose-label">${escapeHtml(purposeText)}</p>
        <p class="featured-summary">${escapeHtml(coach.tagline)}</p>
        <div class="featured-rating">★ ${coach.rating.toFixed(1)} <span>(${coach.lessons || 0})</span></div>
        <div class="featured-price">
          <strong>${escapeHtml(coach.price)}</strong>
          ${originalPrice ? `<del>${escapeHtml(originalPrice)}</del>` : ""}
        </div>
        <button class="detail-link" type="button" data-detail-id="${escapeHtml(coach.id)}">상세보기</button>
      </div>
    </article>
  `;
}

function getOriginalPrice(price) {
  const amount = Number(String(price || "").replace(/[^\d]/g, ""));
  if (!amount) return "";
  return `${Math.round(amount * 1.7).toLocaleString("ko-KR")}원`;
}

function renderCoachCard(coach) {
  const badges = getCoachBadges(coach);
  const imageStyle = getImageStyle(coach);
  const purposeText = getPurposeLabels(coach.purpose).slice(0, 2).join(" · ");
  return `
    <article class="coach-card ${coach.id === state.selectedCoachId ? "active" : ""} ${getTierClass(coach)}" data-coach-id="${escapeHtml(coach.id)}">
      <div class="avatar-frame"><img class="avatar" src="${escapeHtml(coach.image)}" alt="" style="${escapeHtml(imageStyle)}"></div>
      <div class="coach-main">
        ${badges.length ? `<div class="rank-badges">${badges.map(renderBadge).join("")}</div>` : ""}
        <h3>${escapeHtml(coach.name)}</h3>
        <span class="coach-owner">${escapeHtml(coach.coachProfileName || coach.name)}</span>
        <span class="purpose-label">${escapeHtml(purposeText)}</span>
        <p>${escapeHtml(coach.tagline)}</p>
        <div class="chips">${(coach.roles || []).map((role) => `<span class="chip">${escapeHtml(role)}</span>`).join("")}</div>
      </div>
      <div class="card-foot">
        <span>★ ${coach.rating.toFixed(1)} · 후기 ${coach.reviews?.length || 0}</span>
        <span class="price">${escapeHtml(coach.price)}</span>
      </div>
      <button class="detail-link card-detail-link" type="button" data-detail-id="${escapeHtml(coach.id)}">상세보기</button>
    </article>
  `;
}

function getCoachBadges(coach) {
  if (coach.tier === "엠버서더") return ["추천", "엠버서더"];
  if (coach.tier === "최우수") return ["추천", "최우수"];
  if (coach.tier === "우수") return ["추천", "우수"];
  return coach.badges || [];
}

function renderBadge(label) {
  const className = label === "추천" ? "badge recommend" : ["최우수", "엠버서더"].includes(label) ? "badge best" : "badge good";
  return `<span class="${className}">${escapeHtml(label)}</span>`;
}

function getTierClass(coach) {
  if (["최우수", "엠버서더"].includes(coach.tier)) return "tier-best";
  if (coach.tier === "우수") return "tier-good";
  return "tier-normal";
}

function getImageStyle(coach) {
  return `object-position: ${coach.imagePosition || "center center"};`;
}

function getFeaturedImage(coach) {
  return coach.featuredImage || coach.bannerImage || coach.heroImage || coach.image || "assets/logo.jpg";
}

function getDetailImage(coach) {
  return coach.detailImage || coach.bannerImage || coach.heroImage || coach.featuredImage || coach.image || "assets/logo.jpg";
}

function getWideImageStyle(coach, positionKey) {
  return `object-position: ${coach[positionKey] || coach.bannerImagePosition || "center center"};`;
}

function getCoachPurposes(coach) {
  const raw = Array.isArray(coach?.purpose) ? coach.purpose : String(coach?.purpose || "").split(",");
  return raw.map((item) => String(item).trim()).filter(Boolean);
}

function getPurposeLabels(value) {
  const ids = Array.isArray(value) ? value : String(value || "").split(",");
  const labels = ids
    .map((id) => purposes.find((purpose) => purpose.id === String(id).trim())?.label || String(id).trim())
    .filter(Boolean);
  return labels.length ? labels : ["분류 미지정"];
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
  bindAuthButtons($("lessonDetailBody"));
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
    const raw = await fetchCoachAvailability(key, {
      from: isoDateOnly(fromDate),
      to: isoDateOnly(addLocalDays(fromDate, 30)),
    });
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
            <button class="primary" type="button" data-open-auth="login">강의 구매</button>
            <button class="secondary" type="button" data-open-auth="guest">비회원 상담 문의</button>
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
      renderApp();
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

  return {
    getCoachKey,
    getCoachIdentityFromGroup,
    getCoachIdentities,
    selectCoachIdentity,
    renderSidebarCoaches,
    openCoachExplorer,
    closeCoachExplorer,
    renderCoachExplorer,
    getVisibleCoaches,
    renderMarket,
    renderFeatured,
    renderDetail,
    openLessonDetail,
    closeLessonDetail,
    loadPublicAvailability,
    loadCoachReviews,
    mountBookingForm,
    normalizeAvailabilitySlot,
  };
}
