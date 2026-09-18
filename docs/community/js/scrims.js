import { apiGet } from "./api.js?v=20260904r";
import { API_BASE_URL } from "./config.js?v=20260904d";
import { loadGameAssets, championIcon } from "./assets.js?v=20260904r";
import { initCommunityAuth } from "./auth.js?v=20260914header1";
import { state } from "./state.js?v=20260904r";
import { escapeHtml } from "./utils.js?v=20260904r";
import { loadRecent } from "./pages/recentMatches.js?v=20260915reference2";

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
  const button = document.getElementById("communityThemeBtn");
  button.textContent = theme === "dark" ? "☀" : "🌙";
  button.setAttribute("aria-pressed", String(theme === "dark"));
  button.title = theme === "dark" ? "라이트 모드로 전환" : "다크 모드로 전환";
  document.querySelector('meta[name="theme-color"]').content = theme === "dark" ? "#121212" : "#f6f7f9";
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
        const row = players.get(key) || { userId, guildId, name: player.name || "이름 없음", tier: player.tier || "미배치", score: 0 };
        row.score += Number(player.mmrDelta || 0);
        players.set(key, row);
      }
    }
    const rows = [...players.values()].sort((a, b) => b.score - a.score).slice(0, 5);
    target.innerHTML = rows.length ? rows.map((row, index) =>
      `<div class="weekly-ranking-row"><span class="weekly-ranking-position">${index + 1}</span><span class="weekly-ranking-avatar" aria-label="칭호 없음">◇</span><button type="button" data-player-profile data-user-id="${escapeHtml(row.userId)}" data-guild-id="${escapeHtml(row.guildId)}">${escapeHtml(row.name)}<small>${escapeHtml(row.tier)}</small></button><strong>${row.score > 0 ? "+" : ""}${Math.round(row.score)}점</strong></div>`
    ).join("") : `<div class="weekly-ranking-empty">최근 7일 랭킹 데이터가 없습니다.</div>`;
    if (!rows.length) return;
    const playersQuery = rows.map((row) => `${row.guildId}:${row.userId}`).join(",");
    const titleData = await apiGet(`/api/community/ranking-titles?players=${encodeURIComponent(playersQuery)}`).catch(() => ({ titles:[] }));
    rows.forEach((row, index) => {
      const title = titleData.titles?.[index];
      const titleIcon = title?.iconSource === "custom" && title.customIconUrl
        ? `<img class="weekly-title-icon" src="${escapeHtml(`${API_BASE_URL.replace(/\/$/, "")}${title.customIconUrl}`)}" alt="${escapeHtml(title.displayTitle || "칭호")}">`
        : title?.iconSource === "champion" && championIcon(title.championNames?.[0] || title.championName)
          ? `<img class="weekly-title-icon" src="${escapeHtml(championIcon(title.championNames?.[0] || title.championName))}" alt="${escapeHtml(title.displayTitle || "칭호")}">`
          : title?.iconSource === "emoji" && title.iconEmoji ? `<span class="weekly-title-icon" title="${escapeHtml(title.displayTitle || "칭호")}">${escapeHtml(title.iconEmoji)}</span>` : "";
      const avatar = target.isConnected && target.querySelectorAll(".weekly-ranking-avatar")[index];
      if (titleIcon && avatar) {
        avatar.innerHTML = titleIcon;
        avatar.setAttribute("aria-label", title.displayTitle || "칭호");
      }
    });
  } catch (_) {
    target.innerHTML = `<div class="weekly-ranking-empty">주간 랭킹을 불러오지 못했습니다.</div>`;
  }
}

setTheme(document.documentElement.dataset.theme);
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
