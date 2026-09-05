import { apiGet } from "../api.js?v=20260904r";
import { $, escapeHtml, tierClass, tierLeaguePoints } from "../utils.js?v=20260905ai";
import { renderLoading } from "../view.js?v=20260904r";

let kind = "mmr";
let role = "";

function valueText(row) {
  if (kind === "games") return `${Number(row.games || 0)}전`;
  if (kind === "winrate") return `${Number(row.games || 0)}전 ${Number(row.wins || 0)}승 ${Number(row.losses || 0)}패`;
  if (kind === "streak") return `최고 ${Number(row.streak || 0)}연승`;
  if (kind === "awards") return `${Number(row.awardPoints || 0)}pt · MVP ${Number(row.mvp || 0)}회 · ACE ${Number(row.ace || 0)}회`;
  return `${tierLeaguePoints(row.tier, row.score).toLocaleString()}점`;
}

function noteText(total) {
  if (kind === "winrate") return `10전 이상 일반 내전 기준 · 총 ${total}명`;
  if (kind === "mmr") return `종합은 전체, 라인은 해당 라인 10게임 이상 기록 기준 · 총 ${total}명`;
  if (kind === "streak") return `일반 내전 역대 최고 연승 기준 · 총 ${total}명`;
  if (kind === "awards") return `MVP +100pt · ACE +50pt · 매주 일요일 초기화 · 총 ${total}명`;
  return `일반 내전 누적 기록 기준 · 총 ${total}명`;
}

export async function loadRankings() {
  const target = $("rankingResults");
  if (!target) return;
  renderLoading(target, 4);
  try {
    const data = await apiGet(`/api/community/rankings?kind=${encodeURIComponent(kind)}&role=${encodeURIComponent(role)}&limit=100`);
    const rows = data.rankings || [];
    const period = kind === "awards" && data.period ? `<div class="ranking-period">기준 기간 · ${escapeHtml(data.period)}</div>` : "";
    if (!rows.length) {
      target.innerHTML = `${period}<div class="empty-state"><strong>표시할 랭킹 기록이 없습니다.</strong><span>경기 기록이 쌓이면 자동으로 반영됩니다.</span></div>`;
      return;
    }
    target.innerHTML = `${period}<div class="ranking-table-head"><span>순위</span><span>소환사</span><span>티어</span><span style="text-align:right">${kind === "mmr" ? "점수" : "기록"}</span></div>${rows.map((row) => `<div class="ranking-row top-${Number(row.rank || 0)}"><span class="ranking-position">${Number(row.rank || 0)}위</span><button class="ranking-player" type="button" data-player-profile data-user-id="${escapeHtml(row.userId)}" data-guild-id="${escapeHtml(row.guildId)}">${escapeHtml(row.name)}</button><span class="ranking-tier ${tierClass(row.tier)}">${escapeHtml(row.tier || "-")}</span><span class="ranking-value">${escapeHtml(valueText(row))}</span></div>`).join("")}<div class="ranking-note">${escapeHtml(noteText(Number(data.total || rows.length)))}</div>`;
  } catch (error) {
    target.innerHTML = `<div class="empty-state"><strong>랭킹을 불러오지 못했습니다.</strong><span>${escapeHtml(error.message)}</span></div>`;
  }
}

export function bindRankingPage() {
  document.querySelectorAll("[data-ranking-kind]").forEach((button) => button.addEventListener("click", () => {
    kind = button.dataset.rankingKind || "mmr";
    document.querySelectorAll("[data-ranking-kind]").forEach((item) => item.classList.toggle("active", item === button));
    $("rankingRoleFilters").hidden = kind !== "mmr";
    loadRankings();
  }));
  document.querySelectorAll("[data-ranking-role]").forEach((button) => button.addEventListener("click", () => {
    role = button.dataset.rankingRole || "";
    document.querySelectorAll("[data-ranking-role]").forEach((item) => item.classList.toggle("active", item === button));
    loadRankings();
  }));
  $("refreshRankingsBtn")?.addEventListener("click", loadRankings);
}
