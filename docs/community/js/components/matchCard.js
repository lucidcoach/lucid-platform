import { championIcon } from "../assets.js";
import { escapeHtml, formatDuration, isWinner, normalizeMode, relativeTime, teamLabel } from "../utils.js";
import { scoreboard } from "./scoreboard.js";

function previewPlayer(player) {
  const icon = championIcon(player.champion);
  return `<div class="preview-player">${icon ? `<img src="${escapeHtml(icon)}" alt="${escapeHtml(player.champion)}" loading="lazy">` : `<span></span>`}<span class="name">${escapeHtml(player.name)}</span><span class="score">${player.aiScore == null ? "" : `AI ${Math.round(player.aiScore)}`}</span></div>`;
}

function renderTeamPreview(match, team) {
  const players = (match.players || []).filter((player) => player.team === team).slice(0,5);
  return `<div class="team-preview ${team} ${isWinner(match,team) ? "winner" : ""}"><div class="team-head"><span>${teamLabel(team)}</span><span>${isWinner(match,team) ? "승리" : "패배"}</span></div>${players.map(previewPlayer).join("") || `<div class="preview-player"><span></span><span class="name">기록 없음</span></div>`}</div>`;
}

function awardName(match, userId) {
  return (match.players || []).find((row) => String(row.userId) === String(userId))?.name || "";
}

export function matchCard(match) {
  const duration = formatDuration(match.durationSeconds);
  const mvp = awardName(match,match.mvpUserId);
  const ace = awardName(match,match.aceUserId);
  return `<article class="match-card" data-match-id="${escapeHtml(match.matchId)}"><div class="match-summary"><div class="match-meta"><span class="match-mode">${escapeHtml(normalizeMode(match))}</span><span class="match-time">${escapeHtml(relativeTime(match.time))}</span>${duration ? `<span class="match-duration">${duration}</span>` : ""}<div class="match-awards">${mvp ? `<span class="award-chip mvp">MVP · ${escapeHtml(mvp)}</span>` : ""}${ace ? `<span class="award-chip ace">ACE · ${escapeHtml(ace)}</span>` : ""}</div></div><div class="teams-preview">${renderTeamPreview(match,"blue")}${renderTeamPreview(match,"red")}</div><button class="expand-match" type="button" aria-label="경기 상세 펼치기">⌄</button></div>${scoreboard(match)}</article>`;
}
