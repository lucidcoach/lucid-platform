import { API_BASE_URL, RESERVATION_STATUSES } from "./config.js";
import { apiFetch, getAdminHeaders } from "./api.js";
import { formatDateTime } from "./utils.js";

async function requestJson(path, init, errorPrefix = "") {
  const response = await apiFetch(`${API_BASE_URL}${path}`, init);
  const result = await response.json().catch(() => ({}));
  if (!response.ok || !result.ok) {
    const message = result.error ? `${errorPrefix}${result.error}` : `HTTP ${response.status}`;
    const error = new Error(message);
    error.status = response.status;
    throw error;
  }
  return result;
}

export function paymentStatus(booking) {
  return String(booking.payment?.status || "").toUpperCase();
}

export function paymentStatusLabel(booking) {
  return ({ PAID: "결제 완료", PARTIALLY_REFUNDED: "부분 환불", CANCELED: "결제 취소", REFUNDED: "환불 완료" })[paymentStatus(booking)]
    || ({ "결제대기": "결제 대기", "코치확정대기": "코치 확정 대기", "예약확정": "결제 가능" }[booking.status] || "일정 확인 후 결제");
}

export function buildReservationPayload(coach, data) {
  const reservation = {
    coachId: coach.id,
    coachName: coach.name,
    coachCategory: coach.category,
    coachPrice: coach.price,
    student: data.get("student"),
    contact: data.get("contact"),
    time: data.get("time"),
    memo: data.get("memo") || "",
  };
  const availabilitySlotId = data.get("availabilitySlotId");
  if (availabilitySlotId) {
    reservation.availabilitySlotId = availabilitySlotId;
    reservation.slotId = availabilitySlotId;
  }
  return reservation;
}

export function filterReservations(bookings, status, query) {
  return bookings.filter((booking) => {
    const statusMatches = status === "all" || booking.status === status;
    const haystack = [booking.studentName, booking.coachName, booking.contact, booking.memo].join(" ").toLowerCase();
    return statusMatches && (!query || haystack.includes(query));
  });
}

export function renderStatusOptions(selectedStatus) {
  return RESERVATION_STATUSES.map((status) => `<option value="${status}" ${status === selectedStatus ? "selected" : ""}>${status}</option>`).join("");
}

export async function submitReservation(reservation) {
  if (!API_BASE_URL || API_BASE_URL.includes("YOUR-COACH-API")) throw new Error("예약 API 주소가 아직 설정되지 않았습니다.");
  const result = await requestJson("/api/reservations", {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(reservation),
  }, "오류: ");
  return result.reservation || {};
}

export async function submitGuestConsultation({ selectedCoach, riotId, contact, feedbackPoint, lessonStyle }) {
  const cleanRiotId = String(riotId || "").trim();
  const cleanContact = String(contact || "").trim();
  const cleanFeedbackPoint = String(feedbackPoint || "").trim();
  const cleanLessonStyle = String(lessonStyle || "").trim();
  if (!cleanRiotId || !cleanContact || !cleanFeedbackPoint || !cleanLessonStyle) throw new Error("필수 항목을 모두 입력해주세요.");
  return submitReservation({
    coachId: selectedCoach?.id || "guest-consultation",
    coachName: selectedCoach ? `${selectedCoach.name} 강의 구매` : "비회원 강의 구매",
    coachCategory: selectedCoach?.category || "league",
    coachPrice: selectedCoach?.price || "가격 상담",
    student: cleanRiotId,
    contact: cleanContact,
    time: cleanLessonStyle,
    memo: cleanFeedbackPoint,
    source: "guest-consultation",
    feedbackMetadata: {
      inquiry: cleanFeedbackPoint,
      lesson_style: cleanLessonStyle,
      selected_lesson: selectedCoach ? {
        id: selectedCoach.id,
        name: selectedCoach.name,
        price: selectedCoach.price,
        coach: selectedCoach.coachProfileName || selectedCoach.name,
      } : null,
    },
  });
}

export async function fetchReservations() {
  const result = await requestJson("/api/reservations", { method: "GET", credentials: "include", headers: getAdminHeaders() });
  return (result.reservations || []).map(mapReservationFromApi);
}

export async function fetchCoachReservations() {
  const result = await requestJson("/api/coach/reservations", { method: "GET", credentials: "include" });
  return (result.reservations || []).map(mapReservationFromApi);
}

export async function fetchMyReservations() {
  const result = await requestJson("/api/my/reservations", { credentials: "include" });
  return (result.reservations || []).map(mapReservationFromApi);
}

export async function fetchMyRefundRequests() {
  const result = await requestJson("/api/my/refund-requests", { credentials: "include" });
  return result.requests || result.refundRequests || [];
}

export function refundRequestLabel(request) {
  return ({ pending: "환불 요청 검토 중", approved: "환불 승인", rejected: "환불 요청 거절" })[String(request?.status || "").toLowerCase()] || "";
}

export function refundAdminStatusLabel(status) {
  return ({ pending: "대기중", approved: "승인", rejected: "거절" })[String(status || "").toLowerCase()] || status || "-";
}

export async function createReservationCancelRequest(reservationId, reason) {
  return requestJson(`/api/my/reservations/${encodeURIComponent(reservationId)}/cancel-request`, {
    method: "POST", credentials: "include", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ reason }),
  });
}

export async function createReservationReview(reservationId, rating, content) {
  return requestJson(`/api/reservations/${encodeURIComponent(reservationId)}/review`, {
    method: "POST", credentials: "include", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ rating, content }),
  });
}

export async function createPaymentOrder(reservationId) {
  return requestJson("/api/payments/orders", {
    method: "POST", credentials: "include", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ reservationId }),
  });
}

export async function confirmCoachReservationRequest(reservationId) {
  return requestJson(`/api/coach/reservations/${encodeURIComponent(reservationId)}/confirm`, { method: "POST", credentials: "include" });
}

export async function confirmPayment(payload) {
  return requestJson("/api/payments/confirm", {
    method: "POST", credentials: "include", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload),
  });
}

export function clearPaymentQuery(url) {
  ["payment", "paymentKey", "orderId", "amount", "code", "message"].forEach((key) => url.searchParams.delete(key));
  globalThis.history.replaceState({}, "", `${url.pathname}${url.search}${url.hash}`);
}

export function getPaymentErrorMessage(code) {
  return ({
    payment_not_configured: "토스 결제 키가 설정되지 않았습니다.",
    live_payments_disabled: "사업자 심사 전에는 테스트 키만 사용할 수 있습니다.",
    reservation_not_confirmed: "일정이 확정된 예약만 결제할 수 있습니다.",
    invalid_payment_amount: "서버 상품 가격을 확인해주세요.",
    amount_mismatch: "결제 금액이 서버 주문과 일치하지 않습니다.",
    PAY_PROCESS_CANCELED: "결제가 취소되었습니다.",
    PAY_PROCESS_ABORTED: "결제 인증에 실패했습니다.",
  })[code] || code || "결제 처리 중 오류가 발생했습니다.";
}

export function mapReservationFromApi(reservation) {
  const feedback = reservation.feedback_metadata || {};
  return {
    id: reservation.id || "", coachId: reservation.coach_id || reservation.coachId || "", status: reservation.status || "신규",
    createdAt: reservation.created_at || "", createdAtText: formatDateTime(reservation.created_at), coachName: reservation.coach_name || "-",
    coachPrice: reservation.coach_price || "-", source: reservation.source || "-", feedback,
    isDiscordFeedback: reservation.source === "discord-feedback", isGuestConsultation: reservation.source === "guest-consultation",
    studentName: reservation.student_name || "-", preferredTime: reservation.preferred_time || "-", student: reservation.student_name || "-",
    lesson: reservation.coach_name || "-", time: reservation.preferred_time || "-", contact: reservation.contact || "-", memo: reservation.memo || "-",
    payment: reservation.payment || null, review: reservation.review || reservation.review_data || reservation.review_metadata || null,
    refundRequest: reservation.refundRequest || reservation.refund_request || null,
  };
}

export function normalizeRefundRequest(request) {
  const reservation = request.reservation || {};
  const reservationId = String(request.reservationId || request.reservation_id || reservation.id || "");
  return {
    id: String(request.id || request.requestId || request.request_id || ""), reservationId,
    status: String(request.status || "pending").toLowerCase(), reason: request.reason || request.cancelReason || request.cancel_reason || "-",
    note: request.note || request.adminNote || request.admin_note || "", createdAt: request.createdAt || request.created_at || "",
    studentName: request.studentName || request.student_name || reservation.studentName || reservation.student_name || `예약 ${reservationId.slice(0, 8)}`,
    coachName: request.coachName || request.coach_name || reservation.coachName || reservation.coach_name || "-",
    preferredTime: request.preferredTime || request.preferred_time || reservation.preferredTime || reservation.preferred_time || "-",
    amount: request.amount || request.refundAmount || request.refund_amount || reservation.payment?.amount || "",
  };
}

export async function fetchAdminRefundRequests() {
  const result = await requestJson("/api/refund-requests", { method: "GET", headers: getAdminHeaders(), credentials: "include" });
  const rows = result.requests || result.refundRequests || result.items || [];
  return Array.isArray(rows) ? rows.map(normalizeRefundRequest).filter((request) => request.id) : [];
}

export async function updateRefundRequest(requestId, status, note) {
  const result = await requestJson(`/api/refund-requests/${encodeURIComponent(requestId)}`, {
    method: "PATCH", headers: getAdminHeaders(true), credentials: "include", body: JSON.stringify({ status, note }),
  });
  return normalizeRefundRequest(result.request || result.refundRequest || { id: requestId, status, note });
}

export async function updateReservationStatus(id, status) {
  const result = await requestJson(`/api/reservations/${encodeURIComponent(id)}`, {
    method: "PATCH", headers: getAdminHeaders(true), credentials: "include", body: JSON.stringify({ status }),
  });
  return mapReservationFromApi(result.reservation || {});
}

export async function deleteReservation(id) {
  await requestJson(`/api/reservations/${encodeURIComponent(id)}`, { method: "DELETE", headers: getAdminHeaders(), credentials: "include" });
}

export async function cancelPayment(orderId, reason) {
  return requestJson(`/api/payments/${encodeURIComponent(orderId)}/cancel`, {
    method: "POST", credentials: "include", headers: getAdminHeaders(true), body: JSON.stringify({ reason }),
  });
}
