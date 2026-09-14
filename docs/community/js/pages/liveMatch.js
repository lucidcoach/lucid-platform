import { apiGet } from "../api.js?v=20260907current1";
import { championIcon } from "../assets.js?v=20260907current1";
import { getCurrentUser, getResolvedAnalysisPlayers } from "../auth.js?v=20260914header1";
import { $, escapeHtml, tierClass } from "../utils.js?v=20260905ai";

const esc = (value) => escapeHtml(String(value ?? ""));
let currentGames = [];
let currentGamesSignature = "";

function parsedDate(value) {
  if (!value) return null;
  const text = String(value);
  const date = new Date(text.replace(" ", "T") + (/[zZ]|[+-]\d\d:\d\d$/.test(text) ? "" : "+09:00"));
  return Number.isNaN(date.getTime()) ? null : date;
}

function startText(value) {
  const date = parsedDate(value);
  return date ? date.toLocaleTimeString("ko-KR", { hour: "2-digit", minute: "2-digit" }) : "시작 시각 미확인";
}

function elapsedText(value) {
  const date = parsedDate(value);
  if (!date) return "진행 시간 미확인";
  const minutes = Math.max(0, Math.floor((Date.now() - date.getTime()) / 60000));
  return `${Math.floor(minutes / 60) ? `${Math.floor(minutes / 60)}시간 ` : ""}${minutes % 60}분 진행`;
}

function queueName(game) {
  return String(game?.queueName || game?.queueLabel || game?.queueKey || "내전").trim() || "내전";
}

function ownedPlayerKeys() {
  const user = getCurrentUser();
  const directDiscordId = String(user?.discordUserId || user?.discord_user_id || "").trim();
  const keys = new Set();
  if (directDiscordId) keys.add(`*:${directDiscordId}`);
  for (const row of getResolvedAnalysisPlayers()) {
    const userId = String(row?.userId || "").trim();
    if (!userId) continue;
    keys.add(`${String(row?.guildId || "").trim()}:${userId}`);
  }
  return keys;
}

function isMyGame(game, owned = ownedPlayerKeys()) {
  if (!owned.size) return false;
  const guildId = String(game?.guildId || "").trim();
  return [...(game?.blue || []), ...(game?.red || [])].some((player) => {
    const userId = String(player?.userId || "").trim();
    return userId && (owned.has(`*:${userId}`) || owned.has(`${guildId}:${userId}`));
  });
}

function sortedCurrentGames(games) {
  const owned = ownedPlayerKeys();
  return games
    .map((game, index) => ({ game, index, mine: isMyGame(game, owned) }))
    .sort((a, b) => Number(b.mine) - Number(a.mine) || a.index - b.index)
    .map(({ game }) => game);
}

function seriesSummary(game) {
  const series = game?.series;
  if (!series || Number(series.bestOf || 1) <= 1) return "";
  const score = `1팀 ${Number(series.team1Score || 0)} : ${Number(series.team2Score || 0)} 2팀`;
  const state = series.sideChoicePending
    ? `${Number(series.currentSet || 1)}세트 진영 선택 대기 · ${series.choosingTeam || "패배팀"}`
    : `${Number(series.currentSet || 1)}세트 진행 중`;
  return `<div class="current-series-summary"><strong>BO${Number(series.bestOf)} · ${esc(score)}</strong><span>${esc(state)}</span></div>`;
}

function compactCard(game) {
  const mine = isMyGame(game);
  const blueTier = game.blueAverageTier || "미배치";
  const redTier = game.redAverageTier || "미배치";
  return `<article class="current-game-card${mine ? " is-my-game" : ""}">
    <div class="current-game-title"><div><small>LIVE MATCH</small><strong>${esc(queueName(game))}</strong></div>${mine ? `<span class="current-my-game-badge">내 경기</span>` : ""}</div>
    ${seriesSummary(game)}
    <div class="current-versus"><strong class="blue">BLUE ${esc(game.series?.blueTeam || "블루팀")}</strong><span>VS</span><strong class="red">RED ${esc(game.series?.redTeam || "레드팀")}</strong></div>
    <p class="current-time"><span>${startText(game.startedAt)} ${game.startTimeSource === "game" ? "시작" : "라인업 확정"}</span><b>·</b><span>${elapsedText(game.startedAt)}</span></p>
    <div class="current-average-tier">${blueTier === redTier ? `평균 티어 <strong>${esc(blueTier)}</strong>` : `BLUE <strong>${esc(blueTier)}</strong><b>·</b> RED <strong>${esc(redTier)}</strong>`}</div>
    <button class="current-detail-button" type="button" data-current-game="${esc(game.gameId)}">자세히 보기</button>
  </article>`;
}

const TIER_ICONS = {C:"challenger.png",GM:"grandmaster.png",M:"master.png",D:"diamond.png",E:"emerald.png",P:"platinum.png",G:"gold.png",S:"silver.png",B:"bronze.png",I:"iron.png"};

function tierIcon(tier = "") {
  const key = String(tier).toUpperCase().match(/^(GM|[CMDEPGSBI])/)?.[1] || "I";
  return `assets/tiers/${TIER_ICONS[key] || TIER_ICONS.I}`;
}

function champions(rows = []) {
  if (!rows.length) return `<span class="current-no-data">기록 없음</span>`;
  return rows.map((row) => {
    const name = typeof row === "string" ? row : row.champion;
    const icon = championIcon(name);
    const detail = typeof row === "string" ? name : `${name} · ${Number(row.games || 0)}게임`;
    return `<span class="current-most" title="${esc(detail)}">${icon ? `<img src="${esc(icon)}" alt="${esc(name)}">` : `<b>${esc(name)}</b>`}</span>`;
  }).join("");
}

function playerRow(player) {
  const form = Array.isArray(player.recentForm) ? player.recentForm.slice(0, 5) : [];
  const mainRole = Number(player.mainRoleGames || 0) > 0 ? player.mainRole : "";
  const role = player.role || "배정 라인";
  const roleWinRate = Number(player.roleWinRate || 0);
  return `<article class="current-player-row">
    <div class="current-player-topline">
      <div class="current-player-head"><span class="current-role">${esc(player.role || "미정")}</span><img class="current-tier-icon" src="${esc(tierIcon(player.tier))}" alt=""><div class="current-player-name"><span class="tier-badge ${tierClass(player.tier)}">${esc(player.tier || "미배치")}</span><button type="button" data-player-profile data-user-id="${esc(player.userId)}" data-guild-id="${esc(player.guildId)}">${esc(player.name)}</button></div></div>
      <div class="current-player-recent"><span>최근 전적</span><span class="current-form">${form.length ? `<b>(</b>${form.map((value) => `<i class="${value === "W" ? "win" : "loss"}">${value}</i>`).join("")}<b>)</b>` : `<em>기록 없음</em>`}</span></div>
    </div>
    <div class="current-player-context"><span>주 포지션 <strong>${esc(mainRole || "기록 없음")}</strong></span><span>${esc(role)} 승률 <strong>${Number(player.roleGames || 0) ? `${roleWinRate.toFixed(1)}%` : "기록 없음"}</strong></span></div>
    <div class="current-champion-groups"><div><small>모스트</small><span>${champions(player.mostChampions)}</span></div><div><small>최근 ${esc(role)}</small><span>${champions(player.recentChampions)}</span></div></div>
  </article>`;
}


function renderList() {
  const root = $("liveMatchRoot");
  if (!root) return;
  currentGames = sortedCurrentGames(currentGames);
  root.innerHTML = currentGames.length
    ? `<div class="current-game-list">${currentGames.map(compactCard).join("")}</div>`
    : `<p class="current-empty">현재 진행 중인 내전이 없습니다</p>`;
  root.querySelectorAll("[data-current-game]").forEach((button) => button.addEventListener("click", () => openCurrentGame(button.dataset.currentGame)));
}

export function openCurrentGame(gameId) {
  const game = currentGames.find((item) => String(item.gameId) === String(gameId));
  if (!game) return;
  $("currentMatchDialog")?.remove();
  document.body.insertAdjacentHTML("beforeend", `<dialog id="currentMatchDialog" class="current-match-dialog" aria-labelledby="currentMatchTitle">
    <div class="current-match-modal">
      <button class="current-match-close" type="button" data-current-close aria-label="닫기">×</button>
      <header class="current-match-modal-head"><p>LIVE MATCH</p><h2 id="currentMatchTitle">${esc(queueName(game))}</h2>${seriesSummary(game)}<div class="current-modal-versus"><span class="blue">BLUE ${esc(game.series?.blueTeam || "TEAM")}</span><b>VS</b><span class="red">RED ${esc(game.series?.redTeam || "TEAM")}</span></div><small>${startText(game.startedAt)} ${game.startTimeSource === "game" ? "시작" : "라인업 확정"} · ${elapsedText(game.startedAt)}</small></header>
      <div class="current-match-teams">
        <section class="current-team-block blue-team"><h3>블루팀 <span>평균 티어 ${esc(game.blueAverageTier || "미배치")}</span></h3>${(game.blue || []).map(playerRow).join("")}</section>
        <div class="current-match-vs" aria-hidden="true">VS</div>
        <section class="current-team-block red-team"><h3>레드팀 <span>평균 티어 ${esc(game.redAverageTier || "미배치")}</span></h3>${(game.red || []).map(playerRow).join("")}</section>
      </div>
    </div>
  </dialog>`);
  const dialog = $("currentMatchDialog");
  dialog.querySelector("[data-current-close]")?.addEventListener("click", () => dialog.close());
  dialog.addEventListener("click", (event) => { if (event.target === dialog) dialog.close(); });
  dialog.addEventListener("close", () => dialog.remove(), { once: true });
  dialog.showModal();
}

export function currentGameForPlayer(userId, guildId) {
  const priorities = { IN_GAME: 4, ACTIVE: 4, SERIES_ACTIVE: 3, SIDE_CHOICE: 3, READY: 2, LINEUP_CREATED: 1 };
  return currentGames
    .filter((game) => String(game.guildId) === String(guildId)
      && [...(game.blue || []), ...(game.red || [])].some((player) => String(player.userId) === String(userId)))
    .sort((a, b) => (priorities[String(b.status || "ACTIVE").toUpperCase()] || 0) - (priorities[String(a.status || "ACTIVE").toUpperCase()] || 0)
      || (parsedDate(b.startedAt)?.getTime() || 0) - (parsedDate(a.startedAt)?.getTime() || 0))[0] || null;
}

window.addEventListener("lucid:auth-changed", () => { if (currentGames.length) renderList(); });

export async function loadLiveMatch({ quiet = false } = {}) {
  const root = $("liveMatchRoot");
  if (!root) return;
  if (!quiet) root.innerHTML = `<p class="current-empty">현재 진행 중인 내전을 확인하고 있습니다.</p>`;
  try {
    const data = await apiGet("/api/community/current-games");
    const nextGames = Array.isArray(data.games) ? data.games : [];
    const signature = JSON.stringify(nextGames);
    if (quiet && signature === currentGamesSignature) return;
    currentGames = nextGames;
    currentGamesSignature = signature;
    renderList();
    window.dispatchEvent(new CustomEvent("lucid:current-games-updated"));
  } catch (_error) {
    currentGames = [];
    currentGamesSignature = "";
    root.innerHTML = `<p class="current-empty">현재 진행 중인 내전을 불러오지 못했습니다.</p>`;
    window.dispatchEvent(new CustomEvent("lucid:current-games-updated"));
  }
}

window.setInterval(() => {
  if (!document.hidden && document.querySelector("#recentView.active, #searchView.active")) loadLiveMatch({ quiet: true });
}, 30000);
