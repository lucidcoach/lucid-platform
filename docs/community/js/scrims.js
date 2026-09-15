import { apiGet } from "./api.js?v=20260904r";
import { loadGameAssets, championIcon } from "./assets.js?v=20260904r";
import { initCommunityAuth } from "./auth.js?v=20260914header1";
import { state } from "./state.js?v=20260904r";
import { escapeHtml } from "./utils.js?v=20260904r";
import { loadRecent } from "./pages/recentMatches.js?v=20260915reference1";

const home = new URL("../", location.href);
const profileUrl = (userId, guildId) => {
  const url = new URL(home);
  url.searchParams.set("player", userId);
  url.searchParams.set("guild", guildId);
  return url;
};

function setTheme(theme) {
  document.documentElement.dataset.theme = theme;
  localStorage.setItem("coach-theme", theme);
}

function matchTime(value) {
  const raw = String(value || "");
  return new Date(raw.replace(" ", "T") + (/[zZ]|[+-]\d\d:\d\d$/.test(raw) ? "" : "+09:00")).getTime();
}

async function loadWeeklyRanking() {
  const target = document.getElementById("weeklyRanking");
  try {
    const data = await apiGet("/api/community/matches?limit=200&offset=0&category=all");
    const cutoff = Date.now() - 7 * 86400000;
    const players = new Map();
    for (const match of data.matches || []) {
      if (matchTime(match.time) < cutoff) continue;
      for (const player of match.players || []) {
        const userId = String(player.userId || ""), guildId = String(match.guildId || player.guildId || "");
        if (!userId || !guildId) continue;
        const key = `${guildId}:${userId}`;
        const row = players.get(key) || { userId, guildId, name: player.name || "이름 없음", tier: player.tier || "미배치", score: 0, champion: player.champion || "" };
        row.score += Number(player.mmrDelta || 0);
        players.set(key, row);
      }
    }
    const rows = [...players.values()].sort((a, b) => b.score - a.score).slice(0, 5);
    target.innerHTML = rows.length ? rows.map((row, index) => {
      const icon = championIcon(row.champion);
      return `<div class="weekly-ranking-row"><span class="weekly-ranking-position">${index + 1}</span>${icon ? `<img src="${escapeHtml(icon)}" alt="${escapeHtml(row.champion)}">` : `<span></span>`}<button type="button" data-player-profile data-user-id="${escapeHtml(row.userId)}" data-guild-id="${escapeHtml(row.guildId)}">${escapeHtml(row.name)}<small>${escapeHtml(row.tier)}</small></button><strong>${row.score > 0 ? "+" : ""}${Math.round(row.score)}점</strong></div>`;
    }).join("") : `<div class="weekly-ranking-empty">최근 7일 랭킹 데이터가 없습니다.</div>`;
  } catch (_) {
    target.innerHTML = `<div class="weekly-ranking-empty">주간 랭킹을 불러오지 못했습니다.</div>`;
  }
}

document.getElementById("communityThemeBtn")?.addEventListener("click", () => setTheme(document.documentElement.dataset.theme === "dark" ? "light" : "dark"));
document.getElementById("scrimsSearchForm")?.addEventListener("submit", (event) => {
  event.preventDefault();
  const query = document.getElementById("scrimsSearchInput").value.trim();
  if (!query) return;
  const url = new URL(home);
  url.searchParams.set("q", query);
  location.assign(url);
});
document.querySelectorAll("[data-match-category]").forEach((button) => button.addEventListener("click", async () => {
  document.querySelectorAll("[data-match-category]").forEach((item) => item.classList.toggle("active", item === button));
  state.recentCategory = button.dataset.matchCategory;
  await loadRecent();
}));
document.getElementById("refreshMatchesBtn")?.addEventListener("click", () => Promise.all([loadRecent(), loadWeeklyRanking()]));
document.getElementById("loadMoreBtn")?.addEventListener("click", () => loadRecent({ append: true }));
document.addEventListener("click", (event) => {
  const button = event.target.closest("[data-player-profile]");
  if (button) location.assign(profileUrl(button.dataset.userId, button.dataset.guildId));
});
window.addEventListener("lucid:open-account", () => location.assign(new URL("?view=account", home)));
window.addEventListener("lucid:logged-out", () => location.reload());

await initCommunityAuth();
await loadGameAssets();
await Promise.all([loadRecent(), loadWeeklyRanking()]);
