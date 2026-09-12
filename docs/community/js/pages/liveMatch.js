import { apiGet } from "../api.js?v=20260907current1";
import { championIcon } from "../assets.js?v=20260907current1";
import { getCurrentUser, getResolvedAnalysisPlayers } from "../auth.js?v=20260911authsingleton1";
import { $, escapeHtml, tierClass } from "../utils.js?v=20260905ai";

const esc = (value) => escapeHtml(String(value ?? ""));
let currentGames = [];

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

function compactCard(game) {
  const mine = isMyGame(game);
  return `<article class="current-game-card${mine ? " is-my-game" : ""}">
    <div class="current-game-title"><div><small>QUEUE</small><strong>${esc(queueName(game))}</strong></div>${mine ? `<span class="current-my-game-badge">내 경기</span>` : ""}</div>
    <div class="current-versus"><strong class="blue">블루팀</strong><span>VS</span><strong class="red">레드팀</strong></div>
    <p class="current-time"><span>${startText(game.startedAt)} ${game.startTimeSource === "game" ? "시작" : "라인업 확정"}</span><b>·</b><span>${elapsedText(game.startedAt)}</span></p>
    <div class="current-roster-preview"><span>${(game.blue || []).map((player) => esc(player.name)).join(" · ") || "라인업 확인 중"}</span><span>${(game.red || []).map((player) => esc(player.name)).join(" · ") || "라인업 확인 중"}</span></div>
    <div class="current-team-averages">
      <span><i>BLUE 평균 티어</i><strong>${esc(game.blueAverageTier || "미배치")}</strong></span>
      <span><i>RED 평균 티어</i><strong>${esc(game.redAverageTier || "미배치")}</strong></span>
    </div>
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

function recentSummary(player) {
  const games = Number(player.recentGames || 0);
  const wins = Number(player.recentWins || 0);
  const losses = Number(player.recentLosses || 0);
  const rate = Number(player.recentWinRate || 0);
  return `최근전적 ${wins}승 ${losses}패 (${rate.toFixed(0)}%)`;
}

function playerRow(player) {
  const form = Array.isArray(player.recentForm) ? player.recentForm : [];
  const totalGames = Number(player.totalGames || 0);
  const totalRate = Number(player.totalWinRate || 0);
  return `<article class="current-player-row">
    <div class="current-player-topline">
      <div class="current-player-head"><span class="current-role">${esc(player.role || "미정")}</span><img class="current-tier-icon" src="${esc(tierIcon(player.tier))}" alt=""><div class="current-player-name"><span class="tier-badge ${tierClass(player.tier)}">${esc(player.tier || "미배치")}</span><button type="button" data-player-profile data-user-id="${esc(player.userId)}" data-guild-id="${esc(player.guildId)}">${esc(player.name)}</button></div></div>
      <div class="current-player-recent"><span>${esc(recentSummary(player))}</span><span class="current-form">${form.map((value) => `<i class="${value === "W" ? "win" : "loss"}">${value}</i>`).join("") || `<em>기록 없음</em>`}</span></div>
    </div>
    <div class="current-player-tag">플레이 특징 분석 중</div>
    <div class="current-player-overall">전체승률 <strong>${totalGames}전, ${totalRate.toFixed(1)}%</strong></div>
    <div class="current-champion-groups"><div><small>모스트 챔피언</small><span>${champions(player.mostChampions)}</span></div><div><small>최근 ${esc(player.role || "배정 라인")}</small><span>${champions(player.recentChampions)}</span></div></div>
  </article>`;
}


function renderList() {
  const root = $("liveMatchRoot");
  if (!root) return;
  currentGames = sortedCurrentGames(currentGames);
  root.innerHTML = currentGames.length
    ? `<div class="current-game-list">${currentGames.map(compactCard).join("")}</div>`
    : `<p class="current-empty">현재 진행 중인 내전이 없습니다</p>`;
  root.querySelectorAll("[data-current-game]").forEach((button) => button.addEventListener("click", () => renderPreview(button.dataset.currentGame)));
}

function renderPreview(gameId) {
  const game = currentGames.find((item) => String(item.gameId) === String(gameId));
  if (!game) return;
  $("currentMatchDialog")?.remove();
  document.body.insertAdjacentHTML("beforeend", `<dialog id="currentMatchDialog" class="current-match-dialog" aria-labelledby="currentMatchTitle">
    <div class="current-match-modal">
      <button class="current-match-close" type="button" data-current-close aria-label="닫기">×</button>
      <header class="current-match-modal-head"><p>LIVE MATCH · ${esc(queueName(game))}</p><h2 id="currentMatchTitle"><span class="blue">BLUE TEAM</span><b>VS</b><span class="red">RED TEAM</span></h2><small>${startText(game.startedAt)} ${game.startTimeSource === "game" ? "시작" : "라인업 확정"} · ${elapsedText(game.startedAt)}</small></header>
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

window.addEventListener("lucid:auth-changed", () => { if (currentGames.length) renderList(); });

export async function loadLiveMatch() {
  const root = $("liveMatchRoot");
  if (!root) return;
  root.innerHTML = `<p class="current-empty">현재 진행 중인 내전을 확인하고 있습니다.</p>`;
  try {
    const data = await apiGet("/api/community/current-games");
    currentGames = Array.isArray(data.games) ? data.games : [];
    renderList();
  } catch (_error) {
    currentGames = [];
    root.innerHTML = `<p class="current-empty">현재 진행 중인 내전을 불러오지 못했습니다.</p>`;
  }
}
