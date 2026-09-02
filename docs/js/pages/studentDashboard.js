import { state } from "../catalog.js";
import { confirmCoachReservationRequest, paymentStatus, paymentStatusLabel, refundRequestLabel } from "../reservations.js";
import { byId as $, escapeHtml, formatWon, parseReservationPrice } from "../utils.js";

export function createStudentDashboardPage({
  isCoachUser,
  openAuthModal,
  mountAccountPanel,
  loadCoachSchedule,
  loadCoachReservations,
  startTossPayment,
  requestReservationCancel,
  submitReservationReview,
  getRefundRequestFor,
}) {
function renderStudentHome() {
  const container = $("studentViewContent");
  if (!container) return;
  if (isCoachUser()) {
    renderCoachDashboard(container);
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
    return;
  }
  if (state.studentReservationLoadState === "error") {
    container.innerHTML = `<div class="student-empty"><strong>예약 내역을 불러오지 못했습니다.</strong><span>${escapeHtml(state.studentReservationLoadError)}</span></div>`;
    return;
  }
  const historyRows = state.bookings;
  const paidRows = historyRows.filter((row) => ["PAID", "PARTIALLY_REFUNDED"].includes(paymentStatus(row)));
  const payableRows = historyRows.filter((row) => ["신규", "상담중", "결제대기", "코치확정대기", "예약확정"].includes(row.status) && !["PAID", "PARTIALLY_REFUNDED", "CANCELED", "REFUNDED"].includes(paymentStatus(row)));
  const reviewableRows = historyRows.filter((row) => row.status === "완료" && paymentStatus(row) === "PAID" && !row.review && !state.submittedReviewIds.includes(row.id));
  const nextLesson = historyRows.find((row) => !["완료", "취소"].includes(row.status));
  const paidAmount = paidRows.reduce((sum, row) => sum + Number(row.payment?.amount || 0), 0);

  container.innerHTML = `
    <section class="student-summary-strip">
      <article><span>총 결제</span><strong>${formatWon(paidAmount)}</strong><em>${paidRows.length}건</em></article>
      <article class="wide"><span>다음 코칭</span><strong>${nextLesson ? escapeHtml(nextLesson.time || "시간 확인 중") : "일정 없음"}</strong><em>${nextLesson ? `${escapeHtml(nextLesson.coachName || "코치")} · ${escapeHtml(nextLesson.lesson || "예약 강의")}` : ""}</em></article>
      <article><span>결제 필요</span><strong>${payableRows.length}건</strong><em>${payableRows.length ? "확인 필요" : "없음"}</em></article>
    </section>

    <section class="student-main-grid">
      <article class="student-panel student-history-panel">
        <div class="student-panel-head">
          <span>내역</span>
          <strong>예약 · 수강 내역</strong>
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
          <strong>처리할 항목</strong>
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
                <button class="primary" type="button" data-pay-reservation="${escapeHtml(row.id)}">토스로 결제하기</button>
              </div>
            `).join("")}
          </div>
        ` : ""}
        ${!reviewableRows.length && !payableRows.length ? `
          <div class="student-empty">
            <strong>지금 처리할 항목이 없습니다.</strong>
            <span>결제나 후기 작성이 필요하면 여기에 표시됩니다.</span>
          </div>
        ` : ""}
      </article>
    </section>
  `;
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
  if (isCoach) {
    if (eyebrow) eyebrow.textContent = "코치 계정";
    if (title) title.textContent = "코치 현황";
  } else {
    if (eyebrow) eyebrow.textContent = "예약 · 결제 · 후기";
    if (title) title.textContent = "내 수강";
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
      <article class="coach-summary-card"><span>판매 시간</span><strong>${totals.hours.toLocaleString("ko-KR")}시간</strong><small>완료 기준</small></article>
      <article class="coach-summary-card"><span>완료 강의 매출</span><strong>${formatWon(totals.revenue)}</strong><small>정산 전</small></article>
      <article class="coach-summary-card"><span>완료 수강생</span><strong>${students.size.toLocaleString("ko-KR")}명</strong><small>고유 수강생</small></article>
      <article class="coach-summary-card"><span>전체 예약</span><strong>${active.length.toLocaleString("ko-KR")}건</strong><small>완료 ${completed.length.toLocaleString("ko-KR")}건</small></article>
    </section>
    <section class="student-panel coach-history-panel">
      <div class="student-panel-head">
        <span>예약 내역</span>
        <strong>내 강의 수강생 목록</strong>
      </div>
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

  return { renderStudentHome, setStudentHeader, renderCoachDashboard, confirmCoachReservation };
}

