import { apiGet } from "../api.js?v=20260907current1";
import { $, escapeHtml } from "../utils.js?v=20260905ai";

const esc = (value) => escapeHtml(String(value ?? ""));
const emptyState = () => `<div class="home-empty-state"><strong>현재 모집 중인 내전이 없습니다.</strong><p>새로운 내전이 열리면 이곳에서 바로 확인할 수 있습니다.</p></div>`;
let queues = [];

function scheduleText(queue) {
  if (!queue.scheduledAt) return queue.queueDate ? `${queue.queueDate} · 모이면 바로 시작` : "모이면 바로 시작";
  const date = new Date(String(queue.scheduledAt).replace(" ", "T") + "+09:00");
  if (Number.isNaN(date.getTime())) return queue.scheduledAt;
  const today = new Date();
  const sameDay = date.toLocaleDateString("ko-KR") === today.toLocaleDateString("ko-KR");
  return `${sameDay ? "오늘" : date.toLocaleDateString("ko-KR", { month:"2-digit", day:"2-digit" })} ${date.toLocaleTimeString("ko-KR", { hour:"2-digit", minute:"2-digit" })}`;
}

function formatText(queue) {
  const bestOf = Number(queue.bestOf || 1);
  return bestOf > 1 ? `BO${bestOf}` : "단판 2경기";
}

function queueCard(queue) {
  const count = Number(queue.participantCount || 0);
  const waiting = Number(queue.waitingCount || 0);
  const capacity = Number(queue.capacity || 0);
  const type = queue.panelType === "event" ? "이벤트" : queue.queueType === "tournament" ? "토너먼트" : "일반 내전";
  const positions = Array.isArray(queue.requiredPositions) ? queue.requiredPositions.filter(Boolean) : [];
  return `<article class="recruitment-card">
    <div class="recruitment-card-badges"><span class="recruitment-status">모집 중</span></div>
    <time>${esc(scheduleText(queue))}</time>
    <h3>${esc(queue.title || "내전 모집")}</h3>
    <p>${esc(type)} · ${esc(formatText(queue))}</p>
    <div class="recruitment-card-foot"><strong>참가 인원 ${count}${capacity ? ` / ${capacity}` : ""}명${waiting ? ` · 대기 ${waiting}명` : ""}</strong>${positions.length ? `<span>${positions.map((position)=>`${esc(position)} 필요`).join(" · ")}</span>` : ""}</div>
    ${queue.joinUrl ? `<a class="recruitment-join" href="${esc(queue.joinUrl)}" target="_blank" rel="noopener noreferrer">참가하기 →</a>` : ""}
  </article>`;
}

function renderRecruitments() {
  const root = $("recruitmentRoot");
  if (!root) return;
  root.innerHTML = queues.length ? `<div class="recruitment-grid">${queues.map(queueCard).join("")}</div>` : emptyState();
}

export async function loadRecruitments() {
  const root = $("recruitmentRoot");
  if (!root) return;
  try {
    const data = await apiGet("/api/community/recruitments");
    queues = Array.isArray(data.queues) ? data.queues.slice(0, 3) : [];
    renderRecruitments();
  } catch (_error) {
    queues = [];
    renderRecruitments();
  }
}
