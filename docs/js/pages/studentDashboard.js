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

  return { renderStudentHome, setStudentHeader, renderCoachDashboard, confirmCoachReservation };
}

