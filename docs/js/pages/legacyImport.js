import {
  applyLegacyImport, approveSafeLegacyCandidates, fetchLegacyImports, previewLegacyImport,
  rollbackLegacyImport, updateLegacyCandidate, uploadLegacyImport,
} from "../coachService.js?v=20260920legacyimport1";
import { fetchUsers } from "../admin.js";
import { escapeHtml } from "../utils.js";

const page = { batches: [], candidates: [], users: [], batchId: "", filter: "all", loading: false, error: "" };
const filters = { all: "전체", needs_review: "확인 필요", unmatched: "미연결", duplicate: "중복", note: "메모 있음", parse: "파싱 실패" };

function visible(candidate) {
  if (page.filter === "all") return true;
  if (page.filter === "needs_review") return candidate.reviewStatus === "needs_review";
  if (page.filter === "unmatched") return candidate.memberMatch?.status !== "matched";
  if (page.filter === "duplicate") return candidate.duplicate;
  if (page.filter === "note") return Boolean(candidate.rawLegacyNote);
  return candidate.parsed?.ok !== true;
}

function summaryMarkup(summary = {}) {
  const values = [
    ["총 기록", summary.total], ["자동 매칭", summary.auto_matched], ["확인 필요", summary.needs_review],
    ["미연결 학생", summary.unmatched], ["중복", summary.duplicates], ["메모 발견", summary.notes],
  ];
  return `<div class="legacy-summary">${values.map(([label, value]) => `<div><span>${label}</span><strong>${Number(value || 0).toLocaleString()}</strong></div>`).join("")}</div>`;
}

function candidateMarkup(candidate) {
  const parsed = candidate.parsed || {};
  const safe = parsed.ok && !candidate.duplicate && candidate.memberMatch?.status === "matched" && candidate.coachMatch?.status === "matched";
  const identified = candidate.memberMatch?.status === "matched" || candidate.legacyStudent;
  const approvable = !candidate.duplicate && identified && ((parsed.ok && candidate.coachMatch?.status === "matched") || (candidate.noteClassification === "student_note" && candidate.rawLegacyNote));
  return `<details class="legacy-candidate ${candidate.reviewStatus}">
    <summary><span><strong>${escapeHtml(candidate.studentName || candidate.rawLegacyNote?.slice(0, 30) || "미분류 기록")}</strong><small>${escapeHtml(candidate.sourceSheet)} · ${escapeHtml(candidate.sourceCell)}</small></span><span>${escapeHtml(candidate.coachMatch?.coachName || candidate.coachName || "코치 미연결")}</span><span>${parsed.ok ? `${escapeHtml(parsed.startsAt?.slice(0, 16).replace("T", " "))}` : "파싱 실패"}</span><b>${candidate.duplicate ? "중복" : candidate.reviewStatus === "approved" ? "승인" : safe ? "안전" : "확인 필요"}</b></summary>
    <div class="legacy-detail">
      <section><h4>원본</h4><dl><dt>학생</dt><dd>${escapeHtml(candidate.studentName || "-")}</dd><dt>Discord</dt><dd>${escapeHtml(candidate.discordId || "-")}</dd><dt>날짜</dt><dd>${escapeHtml(candidate.dateText || "-")}</dd><dt>시간</dt><dd>${escapeHtml(candidate.timeText || "-")}</dd><dt>강의</dt><dd>${escapeHtml(candidate.lessonType || "-")}</dd><dt>가격</dt><dd>${Number(candidate.price || 0).toLocaleString()}원</dd><dt>담당 코치</dt><dd>${escapeHtml(candidate.coachName || "-")}</dd></dl><label>원본 메모<textarea readonly>${escapeHtml(candidate.rawLegacyNote || "")}</textarea></label></section>
      <section><h4>자동 해석</h4><dl><dt>회원</dt><dd>${escapeHtml(candidate.memberMatch?.status || "unmatched")} ${escapeHtml(candidate.memberMatch?.method || "")}</dd><dt>코치</dt><dd>${escapeHtml(candidate.coachMatch?.coachName || candidate.coachMatch?.status || "unmatched")}</dd><dt>시작</dt><dd>${escapeHtml(parsed.startsAt || "-")}</dd><dt>종료</dt><dd>${escapeHtml(parsed.endsAt || "-")}</dd><dt>상태</dt><dd>${escapeHtml(candidate.status || "-")}</dd></dl>
        <div class="legacy-edit-grid"><label>학생<input data-legacy-field="studentName" value="${escapeHtml(candidate.studentName || "")}"></label><label>Discord<input data-legacy-field="discordId" value="${escapeHtml(candidate.discordId || "")}"></label><label>날짜<input data-legacy-field="dateText" value="${escapeHtml(parsed.startsAt?.slice(0, 10) || candidate.dateText || "")}"></label><label>시간<input data-legacy-field="timeText" value="${escapeHtml(candidate.timeText || "")}"></label><label>강의<input data-legacy-field="lessonType" value="${escapeHtml(candidate.lessonType || "")}"></label><label>가격<input data-legacy-field="price" type="number" min="0" value="${Number(candidate.price || 0)}"></label></div>
        <label>회원 다시 선택<select data-legacy-user="${candidate.id}"><option value="">미연결</option>${page.users.map((user) => `<option value="${user.id}" ${candidate.memberMatch?.userId === user.id ? "selected" : ""}>${escapeHtml(user.displayName || user.name || user.email || user.id)}</option>`).join("")}</select></label>
        <label class="legacy-check"><input data-legacy-student="${candidate.id}" type="checkbox" ${candidate.legacyStudent ? "checked" : ""}> 현재 회원이 없는 Legacy 학생으로 보존</label>
        <label>코치 선택<select data-legacy-coach="${candidate.id}"><option value="">미연결</option>${[["coach-shineast", "샤이니스트"], ["coach-mireu", "정미르"], ["coach-mephi", "메피"], ["coach-persona", "페르소나"]].map(([id, name]) => `<option value="${id}" ${candidate.coachMatch?.coachId === id ? "selected" : ""}>${name}</option>`).join("")}</select></label>
        <label>메모 분류<select data-legacy-note-class="${candidate.id}"><option value="student_note" ${candidate.noteClassification === "student_note" ? "selected" : ""}>학생 메모</option><option value="session_note" ${candidate.noteClassification === "session_note" ? "selected" : ""}>수업 메모</option><option value="unknown" ${candidate.noteClassification === "unknown" ? "selected" : ""}>미분류</option></select></label>
      </section>
    </div>
    <div class="legacy-actions"><button class="primary mini" data-legacy-action="approved" data-id="${candidate.id}" ${approvable ? "" : "disabled"}>확정</button><button class="secondary mini" data-legacy-action="needs_review" data-id="${candidate.id}">수정 후 재검수</button><button class="secondary mini" data-legacy-action="held" data-id="${candidate.id}">보류</button><button class="danger mini" data-legacy-action="excluded" data-id="${candidate.id}">이 기록 제외</button></div>
  </details>`;
}

export function createLegacyImportPage({ runAdminRequest }) {
  async function load(batchId = page.batchId) {
    page.loading = true; page.error = ""; render();
    try {
      const [result, users] = await Promise.all([runAdminRequest(() => fetchLegacyImports(batchId)), page.users.length ? page.users : runAdminRequest(fetchUsers)]);
      page.users = users;
      page.batches = result.batches || [];
      page.batchId = batchId || page.batches[0]?.id || "";
      if (page.batchId !== batchId) return load(page.batchId);
      page.candidates = result.candidates || [];
    } catch (error) { page.error = error.message || "이관 기록을 불러오지 못했습니다."; }
    page.loading = false; render();
  }

  async function upload(files) {
    page.loading = true; render();
    try {
      for (const file of files) {
        const result = await runAdminRequest(() => uploadLegacyImport(file));
        page.batchId = result.batch.id;
      }
      await load(page.batchId);
    } catch (error) { page.loading = false; page.error = error.message; render(); }
  }

  async function patch(id, payload) {
    await runAdminRequest(() => updateLegacyCandidate(id, payload));
    await load();
  }

  async function previewAndApply() {
    const result = await runAdminRequest(() => previewLegacyImport(page.batchId));
    const value = result.preview;
    const message = `신규 수업 생성: ${value.events}건\n기존 회원 연결: ${value.linked_users}명\nLegacy 학생: ${value.legacy_students}명\n학생 메모: ${value.student_notes}건\n수업 메모: ${value.session_notes}건\n제외: ${value.excluded}건\n중복 스킵: ${value.duplicates}건\n\n승인된 기록만 운영 DB에 반영할까요?`;
    if (!confirm(message)) return;
    await runAdminRequest(() => applyLegacyImport(page.batchId));
    await load();
  }

  function bind(target) {
    target.querySelector("#legacyUploadForm")?.addEventListener("submit", (event) => { event.preventDefault(); const files = [...event.currentTarget.elements.files.files]; if (files.length) upload(files); });
    target.querySelector("#legacyBatchSelect")?.addEventListener("change", (event) => load(event.target.value));
    target.querySelectorAll("[data-legacy-filter]").forEach((button) => button.addEventListener("click", () => { page.filter = button.dataset.legacyFilter; render(); }));
    target.querySelectorAll("[data-legacy-action]").forEach((button) => button.addEventListener("click", () => {
      const card = button.closest(".legacy-candidate");
      const fields = Object.fromEntries([...card.querySelectorAll("[data-legacy-field]")].map((input) => [input.dataset.legacyField, input.value]));
      patch(button.dataset.id, { ...fields, reviewStatus: button.dataset.legacyAction, matchedUserId: target.querySelector(`[data-legacy-user="${CSS.escape(button.dataset.id)}"]`)?.value || "", legacyStudent: target.querySelector(`[data-legacy-student="${CSS.escape(button.dataset.id)}"]`)?.checked || false, matchedCoachId: target.querySelector(`[data-legacy-coach="${CSS.escape(button.dataset.id)}"]`)?.value || "", noteClassification: target.querySelector(`[data-legacy-note-class="${CSS.escape(button.dataset.id)}"]`)?.value || "unknown" });
    }));
    target.querySelector("#legacyApproveSafe")?.addEventListener("click", async () => { await runAdminRequest(() => approveSafeLegacyCandidates(page.batchId)); await load(); });
    target.querySelector("#legacyApply")?.addEventListener("click", previewAndApply);
    target.querySelector("#legacyRollback")?.addEventListener("click", async () => { if (prompt("롤백하려면 배치 ID를 입력하세요.") !== page.batchId) return; await runAdminRequest(() => rollbackLegacyImport(page.batchId)); await load(); });
  }

  function render() {
    const target = document.getElementById("legacyImportView");
    if (!target) return;
    const batch = page.batches.find((item) => item.id === page.batchId);
    const rows = page.candidates.filter(visible);
    const safeCount = page.candidates.filter((item) => item.reviewStatus === "needs_review" && !item.duplicate && item.parsed?.ok && item.memberMatch?.status === "matched" && item.coachMatch?.status === "matched").length;
    target.innerHTML = `<div class="section-head"><div><p class="eyebrow">코칭 관리자</p><h2>기존 기록 가져오기</h2></div></div>
      <form id="legacyUploadForm" class="legacy-upload"><label>XLSX 원본 선택<input name="files" type="file" accept=".xlsx" multiple required></label><button class="primary" type="submit">Dry-run 분석</button><small>원본 파일은 수정하거나 서버에 영구 보관하지 않습니다.</small></form>
      ${page.error ? `<p class="save-status error">${escapeHtml(page.error)}</p>` : ""}${page.loading ? `<p class="save-status">분석 중...</p>` : ""}
      ${page.batches.length ? `<div class="legacy-toolbar"><select id="legacyBatchSelect">${page.batches.map((item) => `<option value="${item.id}" ${item.id === page.batchId ? "selected" : ""}>${escapeHtml(item.fileName)} · ${escapeHtml(item.status)}</option>`).join("")}</select><button id="legacyApproveSafe" class="secondary" type="button" ${safeCount ? "" : "disabled"}>안전한 항목 ${safeCount.toLocaleString()}건 일괄 승인</button><button id="legacyApply" class="primary" type="button">최종 반영 Preview</button>${batch?.status === "applied" ? `<button id="legacyRollback" class="danger" type="button">이 배치 롤백</button>` : ""}</div>${summaryMarkup(batch?.summary)}<div class="legacy-filters">${Object.entries(filters).map(([key, label]) => `<button type="button" class="secondary mini ${page.filter === key ? "active" : ""}" data-legacy-filter="${key}">${label}</button>`).join("")}</div><div class="legacy-list">${rows.map(candidateMarkup).join("") || `<p class="save-status">조건에 맞는 기록이 없습니다.</p>`}</div>` : `<div class="student-empty"><strong>분석된 XLSX가 없습니다.</strong><span>원본 파일을 선택해 dry-run부터 실행하세요.</span></div>`}`;
    bind(target);
  }

  return { load, render };
}
