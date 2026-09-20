import {
  approveSafeLegacyCandidates, bulkUpdateLegacyCandidates, fetchLegacyImports, previewLegacyImport,
  rollbackLegacyImport, updateLegacyCandidate, uploadLegacyImport,
} from "../coachService.js?v=20260921legacyreview1";
import { fetchUsers } from "../admin.js";
import { escapeHtml } from "../utils.js";

const page = { batches: [], candidates: [], users: [], batchId: "", filter: "all", loading: false, error: "" };
const filters = {
  all: "전체", calendar_only: "캘린더 단독", lesson_high: "수업 A", lesson_medium: "수업 B", lesson_low: "수업 C",
  gray: "회색 시간대 후보", needs_review: "확인 필요", unmatched: "미연결", duplicate: "중복", note: "메모 있음", parse: "파싱 실패",
};
const confidenceLabel = { high: "A · 높은 신뢰도", medium: "B · 중간 신뢰도", low: "C · 낮은 신뢰도" };
const patternLabel = { scheduled: '"예정"', undecided: '"미정"', student_only: "학생명만 존재", time_only: "시간만 존재", appointment: "약속 관련", unavailable: "휴무 관련" };

function visible(candidate) {
  if (page.filter === "all") return true;
  if (page.filter === "calendar_only") return candidate.calendarStatus === "calendar_only_candidate" && !candidate.duplicate;
  if (page.filter.startsWith("lesson_")) return candidate.calendarStatus === "calendar_only_candidate" && candidate.eventType === "lesson" && candidate.confidence === page.filter.slice(7) && !candidate.duplicate;
  if (page.filter === "gray") return Boolean(candidate.grayTimeMatchCandidates?.length) && !candidate.duplicate;
  if (page.filter === "needs_review") return candidate.reviewStatus === "needs_review";
  if (page.filter === "unmatched") return candidate.eventType === "lesson" && candidate.memberMatch?.status !== "matched";
  if (page.filter === "duplicate") return candidate.duplicate;
  if (page.filter === "note") return Boolean(candidate.rawLegacyNote);
  return candidate.parsed?.ok !== true;
}

function summaryMarkup(summary = {}) {
  const values = [
    ["하단 표 수업", summary.table_records], ["상단 캘린더 후보", summary.calendar_candidates], ["캘린더↔표 병합", summary.calendar_table_matched],
    ["캘린더 단독", summary.calendar_only], ["수업 A", summary.lesson_high], ["수업 B", summary.lesson_medium], ["수업 C", summary.lesson_low],
    ["개인 일정", summary.calendar_only_personal], ["예약 불가", summary.calendar_only_unavailable], ["미분류", summary.calendar_unknown],
    ["회색 보조 매칭", summary.gray_auxiliary_matches], ["회색 검수 후보", summary.gray_time_candidates], ["캘린더 내부 중복", summary.calendar_internal_duplicates], ["중복 제외", summary.duplicates], ["원본 메모", summary.notes],
  ];
  return `<div class="legacy-summary">${values.map(([label, value]) => `<div><span>${label}</span><strong>${Number(value || 0).toLocaleString()}</strong></div>`).join("")}</div>`;
}

function candidateMarkup(candidate) {
  const parsed = candidate.parsed || {};
  const identified = candidate.memberMatch?.status === "matched" || candidate.legacyStudent;
  const needsStudent = candidate.noteClassification === "student_note" || (candidate.eventType || "lesson") === "lesson";
  const approvable = !candidate.duplicate && (!needsStudent || identified) && ((parsed.ok && candidate.coachMatch?.status === "matched" && ["lesson", "personal", "unavailable"].includes(candidate.eventType || "lesson")) || (candidate.noteClassification === "student_note" && candidate.rawLegacyNote));
  const calendarOnly = candidate.calendarStatus === "calendar_only_candidate" && !candidate.duplicate;
  const estimate = candidate.studentEstimate || {};
  const estimatedName = estimate.name || candidate.studentHint || candidate.studentName || "";
  const sourceRange = candidate.mergedRange || candidate.sourceCell;
  const confidence = confidenceLabel[candidate.confidence] || "신뢰도 미산정";
  const grayMatches = (candidate.grayTimeMatchCandidates || []).map((match) => `<article><div><strong>${escapeHtml(match.studentName || match.discordId || "학생 미상")}</strong><span>${escapeHtml(match.coachName || "-")} · ${escapeHtml(match.timeText || "-")}</span><small>${match.evidence.map(escapeHtml).join(" · ")}</small></div>${match.candidateId ? `<button class="primary mini" data-legacy-merge="${match.candidateId}" data-id="${candidate.id}">같은 수업으로 병합</button>` : ""}</article>`).join("");
  const progress = candidate.progressComparison;
  return `<details class="legacy-candidate ${candidate.reviewStatus} confidence-${candidate.confidence || "none"}">
    <summary><span><strong>${escapeHtml(candidate.rawLegacyNote || candidate.studentName || "미분류 기록")}</strong><small>${escapeHtml(candidate.sourceSheet)} · ${escapeHtml(sourceRange)}</small></span><span><strong>${parsed.ok ? `${escapeHtml(parsed.startsAt?.slice(0, 16).replace("T", " "))} ~ ${escapeHtml(parsed.endsAt?.slice(11, 16))}` : "시간 파싱 실패"}</strong><small>${escapeHtml(candidate.coachMatch?.coachName || candidate.coachName || "코치 미연결")}</small></span><span><strong>${escapeHtml(estimatedName || "학생 미상")}</strong><small>${candidate.memberMatch?.status === "matched" ? `회원 연결 · ${escapeHtml(candidate.memberMatch?.method || "exact")}` : estimate.name ? "Sales 학생 정확 연결" : candidate.studentHint ? "학생 식별자 후보" : "회원 미연결"}</small></span><b>${candidate.duplicate ? "중복" : confidence}</b></summary>
    <div class="legacy-quick-facts"><span>${candidate.eventType === "lesson" ? "수업" : candidate.eventType === "personal" ? "개인 일정" : candidate.eventType === "unavailable" ? "예약 불가" : "미분류"}</span><span>${candidate.grayBlock ? "회색 블록" : "일반 블록"}</span><span>${candidate.calendarStatus === "matched_table" ? "하단 표 매칭됨" : candidate.recordOrigin === "calendar" ? "하단 표 매칭 없음" : "하단 표 원본"}</span><span>${escapeHtml((candidate.confidenceReasons || []).join(" · ") || "근거 없음")}</span></div>
    <div class="legacy-detail">
      <section><h4>원본과 추정</h4><dl><dt>원본 텍스트</dt><dd>${escapeHtml(candidate.rawLegacyNote || "-")}</dd><dt>날짜</dt><dd>${escapeHtml(parsed.startsAt?.slice(0, 10) || candidate.dateText || "-")}</dd><dt>시작/종료</dt><dd>${parsed.ok ? `${escapeHtml(parsed.startsAt?.slice(11, 16))} ~ ${escapeHtml(parsed.endsAt?.slice(11, 16))}` : "-"}</dd><dt>추정 유형</dt><dd>${escapeHtml(candidate.eventType || "unknown")}</dd><dt>추정 학생</dt><dd>${escapeHtml(estimatedName || "-")} ${estimate.discordId ? `· ${escapeHtml(estimate.discordId)}` : ""}</dd><dt>추정 코치</dt><dd>${escapeHtml(candidate.coachMatch?.coachName || candidate.coachName || "-")}</dd><dt>회원 매칭</dt><dd>${escapeHtml(candidate.memberMatch?.status || "unmatched")} · ${escapeHtml(candidate.memberMatch?.method || "-")}</dd><dt>원본 위치</dt><dd>${escapeHtml(candidate.sourceSheet)} · ${escapeHtml(sourceRange)}</dd></dl></section>
      <section><h4>수동 검수</h4><div class="legacy-edit-grid"><label>학생<input data-legacy-field="studentName" value="${escapeHtml(candidate.studentName || estimate.name || "")}"></label><label>Discord<input data-legacy-field="discordId" value="${escapeHtml(candidate.discordId || estimate.discordId || "")}"></label><label>날짜<input data-legacy-field="dateText" value="${escapeHtml(parsed.startsAt?.slice(0, 10) || candidate.dateText || "")}"></label><label>시간<input data-legacy-field="timeText" value="${escapeHtml(candidate.timeText || "")}"></label><label>강의<input data-legacy-field="lessonType" value="${escapeHtml(candidate.lessonType || (candidate.recordOrigin === "calendar" ? candidate.rawLegacyNote : ""))}"></label><label>가격<input data-legacy-field="price" type="number" min="0" value="${Number(candidate.price || 0)}"></label></div>
        <label>회원 다시 선택<select data-legacy-user="${candidate.id}"><option value="">미연결</option>${page.users.map((user) => `<option value="${user.id}" ${candidate.memberMatch?.userId === user.id ? "selected" : ""}>${escapeHtml(user.displayName || user.name || user.email || user.id)}</option>`).join("")}</select></label>
        <label class="legacy-check"><input data-legacy-student="${candidate.id}" type="checkbox" ${candidate.legacyStudent ? "checked" : ""}> 현재 회원이 없는 Legacy 학생으로 보존</label>
        <label>코치 선택<select data-legacy-coach="${candidate.id}"><option value="">미연결</option>${[["coach-shineast", "샤이니스트"], ["coach-mireu", "정미르"], ["coach-mephi", "메피"], ["coach-persona", "페르소나"]].map(([id, name]) => `<option value="${id}" ${candidate.coachMatch?.coachId === id ? "selected" : ""}>${name}</option>`).join("")}</select></label>
        <label>일정 분류<select data-legacy-event-type="${candidate.id}"><option value="unknown" ${candidate.eventType === "unknown" ? "selected" : ""}>미분류</option><option value="lesson" ${(candidate.eventType || "lesson") === "lesson" ? "selected" : ""}>수업</option><option value="personal" ${candidate.eventType === "personal" ? "selected" : ""}>개인 일정</option><option value="unavailable" ${candidate.eventType === "unavailable" ? "selected" : ""}>예약 불가</option></select></label>
        <label>메모 분류<select data-legacy-note-class="${candidate.id}"><option value="student_note" ${candidate.noteClassification === "student_note" ? "selected" : ""}>학생 메모</option><option value="session_note" ${candidate.noteClassification === "session_note" ? "selected" : ""}>수업 메모</option><option value="unknown" ${candidate.noteClassification === "unknown" ? "selected" : ""}>미분류</option></select></label></section>
    </div>
    ${progress ? `<div class="legacy-progress ${progress.mismatch ? "warning" : ""}"><strong>장기 강의 비교 · ${escapeHtml(progress.identity)}</strong><span>원본 메모 ${Number(progress.originalCompletedHours || 0)}h / 복원 세션 ${Number(progress.restoredSessionHours || 0)}h / 목표 ${Number(progress.totalTargetHours || 0)}h</span><small>${progress.mismatch ? "진행시간 차이 검수 필요" : "진행시간 일치"} · ${escapeHtml(progress.noteSource?.sheet || "")} ${escapeHtml(progress.noteSource?.cell || "")}</small></div>` : ""}
    ${grayMatches ? `<div class="legacy-gray-match"><h4>회색 시간대 매칭 후보</h4>${grayMatches}<div class="legacy-gray-decisions"><button class="secondary mini" data-gray-separate data-id="${candidate.id}">별도 일정</button><button class="danger mini" data-legacy-action="excluded" data-id="${candidate.id}">무시</button></div></div>` : ""}
    ${calendarOnly ? `<div class="legacy-calendar-actions"><span>캘린더 단독 기록</span><button class="secondary mini" data-legacy-classify="lesson" data-id="${candidate.id}">수업으로 복원</button><button class="secondary mini" data-legacy-classify="personal" data-id="${candidate.id}">개인 일정</button><button class="secondary mini" data-legacy-classify="unavailable" data-id="${candidate.id}">예약 불가</button><button class="danger mini" data-legacy-action="excluded" data-id="${candidate.id}">무시</button></div>` : ""}
    <div class="legacy-actions"><button class="primary mini" data-legacy-action="approved" data-id="${candidate.id}" ${approvable ? "" : "disabled"}>확정</button><button class="secondary mini" data-legacy-action="needs_review" data-id="${candidate.id}">수정 후 재검수</button><button class="secondary mini" data-legacy-action="held" data-id="${candidate.id}">보류</button><button class="danger mini" data-legacy-action="excluded" data-id="${candidate.id}">이 기록 제외</button></div>
  </details>`;
}

function patternGroups() {
  const groups = new Map();
  page.candidates.filter((item) => item.calendarStatus === "calendar_only_candidate" && item.eventType === "unknown" && !item.duplicate && item.reviewStatus !== "excluded").forEach((item) => {
    const normalized = String(item.rawLegacyNote || "").trim().replace(/\s+/g, " ").toLowerCase();
    const key = item.calendarPattern && item.calendarPattern !== "other" ? item.calendarPattern : `text:${normalized}`;
    if (!groups.has(key)) groups.set(key, { key, label: patternLabel[key] || (normalized ? `반복 문구 · “${normalized.slice(0, 36)}”` : "기타 빈 문구"), items: [] });
    groups.get(key).items.push(item);
  });
  return [...groups.values()].sort((a, b) => b.items.length - a.items.length);
}

function patternsMarkup() {
  const groups = patternGroups();
  if (!groups.length) return "";
  return `<section class="legacy-patterns"><div><p class="eyebrow">미분류 패턴 분석</p><h3>그룹 단위 검수</h3><span>${groups.reduce((sum, group) => sum + group.items.length, 0).toLocaleString()}건 · 적용 전 실제 원본 최대 10건을 펼쳐 확인할 수 있습니다.</span></div>${groups.map((group, index) => `<details><summary><strong>${escapeHtml(group.label)}</strong><b>${group.items.length.toLocaleString()}건</b></summary><div class="legacy-pattern-samples">${group.items.slice(0, 10).map((item) => `<span>${escapeHtml(item.parsed?.startsAt?.slice(0, 16).replace("T", " ") || "-")} · ${escapeHtml(item.coachMatch?.coachName || item.coachName || "-")} · ${escapeHtml(item.rawLegacyNote || "(빈 문구)")}<small>${escapeHtml(item.sourceSheet)} · ${escapeHtml(item.mergedRange || item.sourceCell)}</small></span>`).join("")}</div><div class="legacy-pattern-actions">${[["lesson", "수업"], ["personal", "개인 일정"], ["unavailable", "예약 불가"], ["ignore", "무시"]].map(([type, label]) => `<button type="button" class="${type === "ignore" ? "danger" : "secondary"} mini" data-pattern-group="${index}" data-pattern-type="${type}">${label}</button>`).join("")}</div></details>`).join("")}</section>`;
}

export function createLegacyImportPage({ runAdminRequest }) {
  async function load(batchId = page.batchId) {
    page.loading = true; page.error = ""; render();
    try {
      const [result, users] = await Promise.all([runAdminRequest(() => fetchLegacyImports(batchId)), page.users.length ? page.users : runAdminRequest(fetchUsers)]);
      page.users = users; page.batches = result.batches || []; page.batchId = batchId || page.batches[0]?.id || "";
      if (page.batchId !== batchId) return load(page.batchId);
      page.candidates = result.candidates || [];
    } catch (error) { page.error = error.message || "이관 기록을 불러오지 못했습니다."; }
    page.loading = false; render();
  }

  async function upload(files) {
    page.loading = true; render();
    try { for (const file of files) { const result = await runAdminRequest(() => uploadLegacyImport(file)); page.batchId = result.batch.id; } await load(page.batchId); }
    catch (error) { page.loading = false; page.error = error.message; render(); }
  }

  async function patch(id, payload) { await runAdminRequest(() => updateLegacyCandidate(id, payload)); await load(); }

  async function previewOnly() {
    const value = (await runAdminRequest(() => previewLegacyImport(page.batchId, "all"))).preview;
    alert(`[수업]\n하단 표 기반: ${value.table_lessons}건\n캘린더와 병합: ${value.calendar_merged}건\n캘린더 단독 신규: ${value.calendar_new_lessons}건\n총 복원 수업: ${value.total_restored_lessons}건\n\n[기타 일정]\n개인 일정: ${value.personal_events}건\n예약 불가: ${value.unavailable_events}건\n\n[검수]\n안전 승인: ${value.safe_approved}건\n수동 승인: ${value.manually_approved}건\n미분류: ${value.unclassified}건\n무시: ${value.ignored}건\n중복 제외: ${value.duplicates}건\n회원 미연결: ${value.unlinked_members}건\n\n[메모]\n학생 메모: ${value.student_notes}건\n수업 메모: ${value.session_notes}건\n원본 메모 보존: ${value.raw_notes_preserved}건\n\n현재 단계에서는 운영 DB에 INSERT하지 않습니다.`);
  }

  function bind(target) {
    target.querySelector("#legacyUploadForm")?.addEventListener("submit", (event) => { event.preventDefault(); const files = [...event.currentTarget.elements.files.files]; if (files.length) upload(files); });
    target.querySelector("#legacyBatchSelect")?.addEventListener("change", (event) => load(event.target.value));
    target.querySelectorAll("[data-legacy-filter]").forEach((button) => button.addEventListener("click", () => { page.filter = button.dataset.legacyFilter; render(); }));
    target.querySelectorAll("[data-legacy-action]").forEach((button) => button.addEventListener("click", () => {
      const card = button.closest(".legacy-candidate");
      const fields = Object.fromEntries([...card.querySelectorAll("[data-legacy-field]")].map((input) => [input.dataset.legacyField, input.value]));
      patch(button.dataset.id, { ...fields, reviewStatus: button.dataset.legacyAction, matchedUserId: card.querySelector("[data-legacy-user]")?.value || "", legacyStudent: card.querySelector("[data-legacy-student]")?.checked || false, matchedCoachId: card.querySelector("[data-legacy-coach]")?.value || "", noteClassification: card.querySelector("[data-legacy-note-class]")?.value || "unknown", eventType: card.querySelector("[data-legacy-event-type]")?.value || "unknown" });
    }));
    target.querySelectorAll("[data-legacy-classify]").forEach((button) => button.addEventListener("click", () => patch(button.dataset.id, { eventType: button.dataset.legacyClassify, lessonType: button.dataset.legacyClassify === "lesson" ? button.closest(".legacy-candidate").querySelector('[data-legacy-field="lessonType"]').value : "", reviewStatus: "needs_review" })));
    target.querySelectorAll("[data-legacy-merge]").forEach((button) => button.addEventListener("click", () => patch(button.dataset.id, { mergeWithCandidateId: button.dataset.legacyMerge })));
    target.querySelectorAll("[data-gray-separate]").forEach((button) => button.addEventListener("click", () => patch(button.dataset.id, { grayMatchDecision: "separate", reviewStatus: "needs_review" })));
    const groups = patternGroups();
    target.querySelectorAll("[data-pattern-group]").forEach((button) => button.addEventListener("click", async () => { const group = groups[Number(button.dataset.patternGroup)]; const type = button.dataset.patternType; if (!group || !confirm(`${group.label} ${group.items.length}건을 '${button.textContent}' 처리할까요?`)) return; await runAdminRequest(() => bulkUpdateLegacyCandidates(page.batchId, { candidateIds: group.items.map((item) => item.id), eventType: type === "ignore" ? "unknown" : type, reviewStatus: type === "ignore" ? "excluded" : "needs_review" })); await load(); }));
    target.querySelector("#legacyApproveSafe")?.addEventListener("click", async () => { await runAdminRequest(() => approveSafeLegacyCandidates(page.batchId)); await load(); });
    target.querySelector("#legacyPreview")?.addEventListener("click", previewOnly);
    target.querySelector("#legacyRollback")?.addEventListener("click", async () => { if (prompt("롤백하려면 배치 ID를 입력하세요.") !== page.batchId) return; await runAdminRequest(() => rollbackLegacyImport(page.batchId)); await load(); });
  }

  function render() {
    const target = document.getElementById("legacyImportView"); if (!target) return;
    const batch = page.batches.find((item) => item.id === page.batchId); const rows = page.candidates.filter(visible);
    const safeCount = page.candidates.filter((item) => item.reviewStatus === "needs_review" && !item.duplicate && item.parsed?.ok && item.coachMatch?.status === "matched" && ((item.recordOrigin !== "calendar" && item.memberMatch?.status === "matched") || (item.recordOrigin === "calendar" && item.eventType === "lesson" && item.confidence === "high" && (item.memberMatch?.status === "matched" || item.studentEstimate)))).length;
    target.innerHTML = `<div class="section-head"><div><p class="eyebrow">코칭 관리자</p><h2>기존 기록 가져오기</h2></div></div>
      <form id="legacyUploadForm" class="legacy-upload"><label>XLSX 원본 선택<input name="files" type="file" accept=".xlsx" multiple required></label><button class="primary" type="submit">Dry-run 분석</button><small>원본 파일은 수정하거나 서버에 영구 보관하지 않습니다.</small></form>
      ${page.error ? `<p class="save-status error">${escapeHtml(page.error)}</p>` : ""}${page.loading ? `<p class="save-status">분석 중...</p>` : ""}
      ${page.batches.length ? `<div class="legacy-toolbar"><select id="legacyBatchSelect">${page.batches.map((item) => `<option value="${item.id}" ${item.id === page.batchId ? "selected" : ""}>${escapeHtml(item.fileName)} · ${escapeHtml(item.status)}</option>`).join("")}</select><button id="legacyApproveSafe" class="secondary" type="button" ${safeCount ? "" : "disabled"}>A/안전 항목 ${safeCount.toLocaleString()}건 일괄 승인</button><button id="legacyPreview" class="primary" type="button">최종 집계 확인</button>${batch?.status === "applied" ? `<button id="legacyRollback" class="danger" type="button">이 배치 롤백</button>` : ""}</div><p class="legacy-insert-lock">검수 단계 잠금 · 최종 집계 확인은 운영 DB에 INSERT하지 않습니다.</p>${summaryMarkup(batch?.summary)}${patternsMarkup()}<div class="legacy-filters">${Object.entries(filters).map(([key, label]) => `<button type="button" class="secondary mini ${page.filter === key ? "active" : ""}" data-legacy-filter="${key}">${label}</button>`).join("")}</div><div class="legacy-list">${rows.map(candidateMarkup).join("") || `<p class="save-status">조건에 맞는 기록이 없습니다.</p>`}</div>` : `<div class="student-empty"><strong>분석된 XLSX가 없습니다.</strong><span>원본 파일을 선택해 dry-run부터 실행하세요.</span></div>`}`;
    bind(target);
  }
  return { load, render };
}
