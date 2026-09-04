import { apiGet } from "../api.js?v=20260904r";
import { RECENT_PAGE_SIZE } from "../config.js?v=20260904r";
import { state } from "../state.js?v=20260904r";
import { $, escapeHtml } from "../utils.js?v=20260904r";
import { renderLoading, showStatus } from "../view.js?v=20260904r";
import { matchCard } from "../components/matchCard.js?v=20260904w";
import { bindExpanders } from "../components/scoreboard.js?v=20260904v";

export async function loadRecent({ append = false } = {}) {
  if (state.recentLoading) return;
  state.recentLoading = true;
  showStatus("");
  const target = $("recentMatches");
  if (!append) { state.recentOffset = 0; renderLoading(target,4); }
  try {
    const data = await apiGet(`/api/community/matches?limit=${RECENT_PAGE_SIZE}&offset=${state.recentOffset}&category=${encodeURIComponent(state.recentCategory || "all")}`);
    const html = (data.matches || []).map(matchCard).join("");
    if (append) target.insertAdjacentHTML("beforeend",html); else target.innerHTML = html || `<div class="empty-state"><strong>아직 표시할 내전 기록이 없습니다.</strong><span>Lucid Bot 경기 기록이 쌓이면 여기에 표시됩니다.</span></div>`;
    state.recentOffset += (data.matches || []).length;
    $("loadMoreBtn").hidden = state.recentOffset >= Number(data.total || 0) || !(data.matches || []).length;
    bindExpanders(target);
  } catch (error) {
    const notConfigured = error.code === "community_guild_not_configured";
    target.innerHTML = notConfigured
      ? `<div class="empty-state"><strong>커뮤니티 전적 연결을 기다리고 있습니다.</strong><span>공개할 Lucid 내전 서버를 연결하면 최근 경기부터 자동으로 표시됩니다.</span></div>`
      : `<div class="empty-state"><strong>내전 기록을 불러오지 못했습니다.</strong><span>${escapeHtml(error.message)}</span></div>`;
    if (!notConfigured) showStatus(error.message);
    else showStatus("");
    $("loadMoreBtn").hidden = true;
  } finally { state.recentLoading = false; }
}
