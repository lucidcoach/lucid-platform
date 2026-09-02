import { API_BASE_URL } from "../config.js";
import { adminLineOptions, adminFieldOptions, filterSets, priceUnits, state } from "../catalog.js";
import { saveCoachToApi } from "../admin.js";
import {
  createCoachLesson,
  deleteCoachLesson,
  fetchCoachLessons,
  fetchCoachProfile,
  fetchCoachSchedule,
  saveCoachLesson,
  saveCoachProfile,
  saveCoachSchedule as saveCoachScheduleApi,
} from "../coachService.js";
import { getCoachPurposes, getImageStyle } from "../components/coachCard.js";
import { addLocalDays, byId as $, escapeHtml, getIsoWeekday, isoDateOnly, localDateOnly } from "../utils.js";

export function createCoachSelfPage({
  render: renderApp,
  renderStudentHome,
  isCoachUser,
  isAdminUser,
  getFallbackCoachKey,
  getCoachKey,
  getCoachIdentities,
  getCoachIdentityFromGroup,
  loadCoachesFromApi,
  loadAdminCoachSettings,
  selectAdminCoach,
  runAdminRequest,
  getCheckedValues,
  migrateCoachImages,
  normalizeAvailabilitySlot,
  updateWideImagePreview,
  handleCoachSelfProfileImageFile,
  openCropModal,
}) {
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
  renderApp();
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
    renderApp();
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


function getSavedScheduleDraft() {
  return state.coachScheduleEditMode === "week"
    ? buildScheduleDraft(state.coachSchedule || { weekly: [], overrides: [], slots: [] })
    : buildScheduleDraft({ ...(state.coachSchedule || { weekly: [], overrides: [], slots: [] }), overrides: [] });
}

function isCoachScheduleDraftDirty() {
  if (!state.coachScheduleDraft) return false;
  const saved = getSavedScheduleDraft();
  for (let weekday = 1; weekday <= 7; weekday += 1) {
    for (let minute = 0; minute < 1440; minute += 60) {
      const key = `${weekday}:${minute}`;
      if (Boolean(saved[key]) !== Boolean(state.coachScheduleDraft[key])) return true;
    }
  }
  return false;
}

function resetCoachScheduleDraft() {
  state.coachScheduleDraft = getSavedScheduleDraft();
  state.coachScheduleLastCellKey = "";
  state.coachScheduleNotice = "저장된 일정으로 되돌렸습니다.";
  renderCoachAvailabilityPanel();
}

function toggleCoachScheduleCell(key, shiftKey = false) {
  if (!state.coachScheduleDraft) state.coachScheduleDraft = getSavedScheduleDraft();
  const [weekdayRaw, minuteRaw] = String(key || "").split(":");
  const weekday = Number(weekdayRaw);
  const minute = Number(minuteRaw);
  if (!weekday || Number.isNaN(minute)) return;

  const targetOpen = !Boolean(state.coachScheduleDraft[key]);
  const anchor = String(state.coachScheduleLastCellKey || "");
  const [anchorDayRaw, anchorMinuteRaw] = anchor.split(":");
  const anchorDay = Number(anchorDayRaw);
  const anchorMinute = Number(anchorMinuteRaw);

  if (shiftKey && anchor && anchorDay === weekday && !Number.isNaN(anchorMinute)) {
    const start = Math.min(anchorMinute, minute);
    const end = Math.max(anchorMinute, minute);
    const weekStart = getCoachScheduleWeekStart();
    const date = addLocalDays(weekStart, weekday - 1);
    for (let cursor = start; cursor <= end; cursor += 60) {
      const cell = getScheduleCell(state.coachSchedule, date, cursor);
      if (cell.booked) continue;
      state.coachScheduleDraft[`${weekday}:${cursor}`] = targetOpen;
    }
  } else {
    state.coachScheduleDraft[key] = targetOpen;
  }

  state.coachScheduleLastCellKey = key;
  state.coachScheduleNotice = "저장되지 않은 변경사항입니다. 저장 버튼을 눌러야 서버에 반영됩니다.";
  renderCoachAvailabilityPanel();
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
    state.coachScheduleNotice = "";
    state.coachScheduleLastCellKey = "";
  } catch (error) {
    state.coachScheduleLoadState = "error";
    state.coachScheduleLoadError = error instanceof TypeError
      ? "서버에 연결하지 못했습니다. 잠시 후 새로고침해주세요."
      : error.message || "주간 가능 시간을 불러오지 못했습니다.";
    state.coachScheduleDraft = buildScheduleDraft({ weekly: [], overrides: [], slots: [] });
  }
  renderCoachAvailabilityPanel();
  if (state.activeView === "student") renderStudentHome();
  if (state.activeView === "account") renderApp();
}

function renderScheduleSummaryMarkup() {
  const weekly = state.coachSchedule?.weekly || [];
  if (!weekly.length) return `<section class="student-panel schedule-summary"><div class="student-panel-head"><span>주간 일정</span><strong>예약 가능 시간</strong></div><p class="schedule-summary-empty">등록된 반복 일정이 없습니다. 코치센터에서 시간을 설정해주세요.</p></section>`;
  const labels = ["월", "화", "수", "목", "금", "토", "일"];
  const chunks = labels.map((label, index) => {
    const entries = weekly.filter((item) => item.weekday === index + 1).sort((a, b) => a.startMinute - b.startMinute);
    if (!entries.length) return "";
    return `<span><b>${label}</b> ${entries.map((item) => `${String(Math.floor(item.startMinute / 60)).padStart(2, "0")}~${String(Math.floor(item.endMinute / 60) % 24).padStart(2, "0")}`).join(", ")}</span>`;
  }).filter(Boolean).join("");
  return `<section class="student-panel schedule-summary"><div class="student-panel-head"><span>주간 일정</span><strong>예약 가능 시간</strong></div><div class="schedule-summary-list">${chunks}</div></section>`;
}

function renderCoachAvailabilityPanel() {
  const target = $("accountCoachAvailabilityPanel") || $("coachAvailabilityPanel");
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
  const scheduleDirty = isCoachScheduleDraftDirty();
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
      <div class="schedule-toolbar"><label class="schedule-mode">편집 범위<select id="scheduleEditMode"><option value="weekly" ${state.coachScheduleEditMode === "weekly" ? "selected" : ""}>매주 반복 기본값</option><option value="week" ${state.coachScheduleEditMode === "week" ? "selected" : ""}>이 주만 변경</option></select></label><button type="button" class="secondary mini" id="scheduleHourToggleBtn">${state.coachScheduleShowAllHours ? "06시 이후만 보기" : "전체 24시간 보기"}</button><span>Shift+클릭하면 같은 요일의 시간 구간을 한 번에 선택합니다.</span></div>
      <div class="schedule-grid-wrap"><div class="schedule-grid" style="--schedule-days: 7"><div class="schedule-corner">시간</div>${weekdayLabels.map((label, index) => `<div class="schedule-day-head">${label}<small>${isoDateOnly(addLocalDays(weekStart, index)).slice(5)}</small></div>`).join("")}${cells.join("")}</div></div>
      <div class="schedule-legend"><span><i class="open"></i>가능</span><span><i class="closed"></i>불가능</span><span><i class="booked"></i>예약됨</span></div>
      <div class="schedule-save-row">
        <span class="save-status ${scheduleDirty ? "warning" : (state.coachScheduleNotice ? "success" : "")}" id="coachScheduleStatus" aria-live="polite">${escapeHtml(state.coachScheduleNotice || (scheduleDirty ? "저장되지 않은 변경사항" : "저장된 일정"))}</span>
        <div class="schedule-save-actions">
          ${scheduleDirty ? `<button type="button" class="secondary" id="resetCoachScheduleBtn">변경 취소</button>` : ""}
          <button type="button" class="primary" id="saveCoachScheduleBtn" ${scheduleDirty ? "" : "disabled"}>주간 일정 저장</button>
        </div>
      </div>
    </section>
  `;
  document.querySelectorAll("[data-schedule-cell]").forEach((button) => button.addEventListener("click", (event) => {
    toggleCoachScheduleCell(button.dataset.scheduleCell, event.shiftKey);
  }));
  $("schedulePrevWeekBtn")?.addEventListener("click", () => changeCoachScheduleWeek(-7));
  $("scheduleNextWeekBtn")?.addEventListener("click", () => changeCoachScheduleWeek(7));
  $("scheduleTodayBtn")?.addEventListener("click", () => {
    if (isCoachScheduleDraftDirty() && !window.confirm("저장하지 않은 일정 변경이 있습니다. 저장하지 않고 이번 주로 이동할까요?")) return;
    state.coachScheduleWeekStart = "";
    state.coachScheduleLoadState = "idle";
    state.coachScheduleDraft = null;
    state.coachScheduleLastCellKey = "";
    state.coachScheduleNotice = "";
    loadCoachSchedule();
  });
  $("scheduleEditMode")?.addEventListener("change", (event) => {
    state.coachScheduleEditMode = event.target.value === "week" ? "week" : "weekly";
    state.coachScheduleDraft = getSavedScheduleDraft();
    state.coachScheduleLastCellKey = "";
    state.coachScheduleNotice = "";
    renderCoachAvailabilityPanel();
  });
  $("scheduleHourToggleBtn")?.addEventListener("click", () => { state.coachScheduleShowAllHours = !state.coachScheduleShowAllHours; renderCoachAvailabilityPanel(); });
  $("resetCoachScheduleBtn")?.addEventListener("click", resetCoachScheduleDraft);
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
  if (isCoachScheduleDraftDirty() && !window.confirm("저장하지 않은 일정 변경이 있습니다. 저장하지 않고 다른 주로 이동할까요?")) return;
  state.coachScheduleWeekStart = isoDateOnly(addLocalDays(getCoachScheduleWeekStart(), days));
  state.coachScheduleLoadState = "idle";
  state.coachScheduleDraft = null;
  state.coachScheduleLastCellKey = "";
  state.coachScheduleNotice = "";
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
    state.coachScheduleDraft = getSavedScheduleDraft();
    state.coachScheduleLoadState = "loaded";
    state.coachScheduleLastCellKey = "";
    state.coachScheduleNotice = state.coachScheduleEditMode === "week" ? "저장 완료 · 이 주에만 적용됩니다." : "저장 완료 · 매주 반복됩니다.";
    renderCoachAvailabilityPanel();
    if (state.activeView === "student") renderStudentHome();
  } catch (error) {
    const message = error instanceof TypeError ? "서버에 연결하지 못했습니다. 잠시 후 다시 시도해주세요." : error.message || "서버 오류";
    state.coachScheduleNotice = `저장 실패: ${message}`;
    if (status) { status.textContent = state.coachScheduleNotice; status.className = "save-status error"; }
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
    renderApp();
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


  return {
    applyCoachProfileToCatalog,
    loadCoachProfile,
    loadCoachSelfLessonsApi,
    saveCoachProfileApi,
    saveCoachLessonToApi,
    createCoachLessonApi,
    deleteCoachLessonApi,
    getCoachSelfLessons,
    getCoachProfileFormValue,
    renderCoachSelfProfile,
    renderCoachSelf,
    renderCoachSelfEditor,
    renderCoachSelfPriceUnitOptions,
    updateCoachSelfPriceValue,
    normalizeCoachAvailability,
    getCoachScheduleWeekStart,
    scheduleResultPayload,
    scheduleSlotDate,
    scheduleSlotMinute,
    scheduleSlotLabel,
    getScheduleCell,
    buildScheduleDraft,
    buildScheduleBaseDraft,
    buildScheduleOverridesFromDraft,
    buildWeeklyEntriesFromDraft,
    loadCoachSchedule,
    loadCoachAvailability,
    renderScheduleSummaryMarkup,
    renderCoachAvailabilityPanel,
    bindCoachSelfLessonPicker,
    changeCoachScheduleWeek,
    saveCoachSchedule,
    saveCoachSelfProfile,
    saveCoachSelfLesson,
  };
}
