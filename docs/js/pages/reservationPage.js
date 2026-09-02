import { ADMIN_TOKEN_KEY, API_BASE_URL } from "../config.js";
import { state } from "../catalog.js";
import {
  cancelPayment,
  clearPaymentQuery,
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
  updateRefundRequest,
  updateReservationStatus,
} from "../reservations.js";
import { byId as $, escapeHtml, formatDateTime } from "../utils.js";

export function createReservationPage({
  isCoachUser,
  renderApp,
  renderStudentHome,
  renderMetrics,
  loginForReservations,
}) {
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
    renderApp();
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
  state.refundAdminLoadState = "loading";
  state.refundAdminLoadError = "";
  renderRefundAdminPanel();
  try {
    state.adminRefundRequests = await runAdminRequest(() => fetchAdminRefundRequests());
    state.refundAdminLoadState = "loaded";
  } catch (error) {
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

  return {
    maybeLoadStudentReservations,
    loadStudentReservations,
    getRefundRequestFor,
    requestReservationCancel,
    submitReservationReview,
    startTossPayment,
    handlePaymentReturn,
    maybeLoadCoachDashboardReservations,
    loadCoachReservations,
    loadReservations,
    loadAdminRefundRequests,
    renderRefundAdminPanel,
    decideRefundRequest,
    runAdminRequest,
    getFilteredBookings,
    renderBookingDetail,
    refundPayment,
    renderBookings,
  };
}
