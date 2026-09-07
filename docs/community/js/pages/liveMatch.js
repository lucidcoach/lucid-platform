import { apiGet } from "../api.js?v=20260907current1";
import { championIcon } from "../assets.js?v=20260907current1";
import { $, escapeHtml, tierClass } from "../utils.js?v=20260907current1";

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

function compactCard(game) {
  return `<article class="current-game-card">
    <div class="current-versus"><strong class="blue">블루팀</strong><span>VS</span><strong class="red">레드팀</strong></div>
    <p class="current-time"><span>${startText(game.startedAt)} ${game.startTimeSource === "game" ? "시작" : "라인업 확정"}</span><b>·</b><span>${elapsedText(game.startedAt)}</span></p>
    <div class="current-team-averages">
      <span><i>BLUE</i><strong>${esc(game.blueAverageTier || "미배치")}</strong><small>${Math.round(game.blueAverageMmr || 0)} MMR</small></span>
      <span><i>RED</i><strong>${esc(game.redAverageTier || "미배치")}</strong><small>${Math.round(game.redAverageMmr || 0)} MMR</small></span>
    </div>
    <button class="current-detail-button" type="button" data-current-game="${esc(game.gameId)}">자세히 보기</button>
  </article>`;
}

function mostChampions(player) {
  const rows = player.mostChampions || [];
  if (!rows.length) return `<span class="current-no-data">기록 없음</span>`;
  return rows.map((row) => {
    const icon = championIcon(row.champion);
    return `<span class="current-most" title="${esc(row.champion)} · ${Number(row.games || 0)}게임">${icon ? `<img src="${esc(icon)}" alt="">` : ""}<b>${esc(row.champion)}</b></span>`;
  }).join("");
}

function playerRow(player, side) {
  const rank = player.positionRank || {};
  const metricName = player.role === "원딜" ? "DPM" : "킬관여";
  const metric = player.metrics?.[player.role === "원딜" ? "dpm" : "kp"] || {};
  return `<article class="current-player-row ${side}">
    <div class="current-player-head"><span>${esc(player.role || "미정")}</span><button type="button" data-player-profile data-user-id="${esc(player.userId)}" data-guild-id="${esc(player.guildId)}">${esc(player.name)}</button>${player.mainRole ? `<small>주 ${esc(player.mainRole)}</small>` : ""}</div>
    <div class="current-player-tier"><strong class="${tierClass(player.tier)}">${esc(player.tier || "미배치")}</strong><span>${Math.round(player.mmr || 0)} MMR</span>${rank.rank ? `<small>${esc(player.role)} ${rank.rank}위 · 상위 ${rank.topPercent}%</small>` : ""}</div>
    <div class="current-player-recent"><span>최근 ${Number(player.recentGames || 0)}전 <strong>${Number(player.recentWinRate || 0).toFixed(0)}%</strong></span><span class="current-form">${(player.recentForm || []).map((value) => `<i class="${value === "W" ? "win" : "loss"}">${value}</i>`).join("") || "기록 없음"}</span></div>
    <div class="current-player-metrics"><span>${metricName} ${metric.value == null ? "-" : Number(metric.value).toFixed(1)}${metricName === "킬관여" ? "%" : ""}</span>${metric.rank ? `<small>${metric.rank}/${metric.total}위</small>` : ""}</div>
    <div class="current-player-mosts">${mostChampions(player)}</div>
  </article>`;
}

function renderList() {
  const root = $("liveMatchRoot");
  if (!root) return;
  root.innerHTML = currentGames.length
    ? `<div class="current-game-list">${currentGames.map(compactCard).join("")}</div>`
    : `<p class="current-empty">현재 진행 중인 내전이 없습니다</p>`;
  root.querySelectorAll("[data-current-game]").forEach((button) => button.addEventListener("click", () => renderPreview(button.dataset.currentGame)));
}

function renderPreview(gameId) {
  const game = currentGames.find((item) => String(item.gameId) === String(gameId));
  const root = $("liveMatchRoot");
  if (!game || !root) return;
  const matchups = game.keyMatchups || [];
  root.innerHTML = `<div class="current-preview">
    <button class="current-back-button" type="button" data-current-back>← 진행 경기 목록</button>
    <div class="current-preview-summary"><div><strong class="blue">BLUE ${Math.round(game.blueAverageMmr || 0)}</strong><span>VS</span><strong class="red">RED ${Math.round(game.redAverageMmr || 0)}</strong></div><p>${startText(game.startedAt)} ${game.startTimeSource === "game" ? "시작" : "라인업 확정"} · ${elapsedText(game.startedAt)}</p></div>
    <section class="current-team-block"><h3>블루팀 <span>${esc(game.blueAverageTier || "미배치")} · 평균 ${Math.round(game.blueAverageMmr || 0)}</span></h3>${(game.blue || []).map((player) => playerRow(player, "blue")).join("")}</section>
    <section class="current-team-block"><h3>레드팀 <span>${esc(game.redAverageTier || "미배치")} · 평균 ${Math.round(game.redAverageMmr || 0)}</span></h3>${(game.red || []).map((player) => playerRow(player, "red")).join("")}</section>
    <section class="current-matchups"><h3>핵심 매치업</h3>${matchups.length ? matchups.map((item) => `<div><span>${esc(item.role)}</span><strong>${esc(item.title)}</strong><small>${esc(item.detail)}</small></div>`).join("") : `<p>비교 가능한 포지션 기록이 없습니다.</p>`}</section>
    <p class="current-data-note">실시간 챔피언 픽 없이, 이 Discord 서버에 저장된 기존 내전 기록만 사용합니다.</p>
  </div>`;
  root.querySelector("[data-current-back]")?.addEventListener("click", renderList);
}

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
