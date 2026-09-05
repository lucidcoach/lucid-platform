import { adminLineOptions, adminFieldOptions, badgeOptions, filterSets, priceUnits, samples, state } from "../catalog.js";
import {
  createCoachRequest,
  decideCoachRequest,
  deleteCoachFromApi,
  fetchAdminCoachSettings,
  fetchCoachRequests,
  fetchUsers,
  normalizeAdminCoachSetting,
  resetCoachesInApi,
  saveAdminCoachSettings,
  saveCoachToApi,
  updateUserRole,
} from "../admin.js";
import { byId as $, escapeHtml } from "../utils.js";

export function createAdminDashboardPage({
  render: renderApp,
  renderMarket,
  loadCoachesFromApi,
  runAdminRequest,
  isAdminUser,
  isCoachUser,
  getCoachKey,
  getCoachIdentities,
  getPublicCatalogCoaches,
  migrateCoachImages,
  openAuthModal,
  renderRoleMenu,
}) {
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


async function resetCoachesToSamples() {
  const nextCoaches = structuredClone(samples);
  try {
    const response = await runAdminRequest(() => resetCoachesInApi(nextCoaches));
    state.coaches = migrateCoachImages(response.coaches || nextCoaches);
    state.selectedCoachId = null;
    renderApp();
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
  $("coachSaleType").value = setting?.saleType || "brokerage";
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
    saleType: $("coachSaleType").value,
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
    renderApp();
  } catch (error) {
    alert(`코치 정보를 삭제하지 못했습니다.\n${error.message}`);
  }
}


  return {
    loadAdminCoachSettings,
    resetCoachesToSamples,
    loadUsers,
    saveUserRole,
    submitCoachApplication,
    approveCoachRequest,
    rejectCoachRequest,
    getCoachRequestErrorMessage,
    renderAdmin,
    formatCommissionRate,
    selectAdminCoach,
    renderUsers,
    renderCoachRequests,
    getCoachRequestStatusLabel,
    getUserCoachLabel,
    getUserRoleFlags,
    getUserSaveClass,
    getRoleLabel,
    findUserCoachSelect,
    fillCoachForm,
    renderAdminChoiceControls,
    renderBadgePicker,
    addSelectedBadge,
    getCheckedValues,
    getTierFromBadges,
    setCoachSaveStatus,
    renderPriceUnitOptions,
    setPriceFields,
    updateCoachPriceValue,
    saveCoachFromForm,
    deleteSelectedCoach,
  };
}
