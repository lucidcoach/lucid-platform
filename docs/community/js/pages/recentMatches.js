import { apiGet } from "../api.js";
import { RECENT_PAGE_SIZE } from "../config.js";
import { state } from "../state.js";
import { $, escapeHtml } from "../utils.js";
import { renderLoading, showStatus } from "../view.js";
import { matchCard } from "../components/matchCard.js";
import { bindExpanders } from "../components/scoreboard.js";

export async function loadRecent({ append = false } = {}) {
  if (state.recentLoading) return;
  state.recentLoading = true;
  showStatus("");
  const target = $("recentMatches");
  if (!append) { state.recentOffset = 0; renderLoading(target,4); }
  try {
    const data = await apiGet(`/api/community/matches?limit=${RECENT_PAGE_SIZE}&offset=${state.recentOffset}`);
    const html = (data.matches || []).map(matchCard).join("");
    if (append) target.insertAdjacentHTML("beforeend",html); else target.innerHTML = html || `<div class="empty-state"><strong>아직 표시할 내전 기록이 없습니다.</strong><span>Lucid Bot 경기 기록이 쌓이면 여기에 표시됩니다.</span></div>`;
    state.recentOffset += (data.matches || []).length;
    $("loadMoreBtn").hidden = state.recentOffset >= Number(data.total || 0) || !(data.matches || []).length;
    bindExpanders(target);
  } catch (error) {
    target.innerHTML = `<div class="empty-state"><strong>내전 기록을 불러오지 못했습니다.</strong><span>${escapeHtml(error.message)}</span></div>`;
    showStatus(error.message); $("loadMoreBtn").hidden = true;
  } finally { state.recentLoading = false; }
}
