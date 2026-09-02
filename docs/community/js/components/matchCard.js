import { championIcon } from "../assets.js";
import { escapeHtml, formatDuration, isWinner, normalizeMode, relativeTime, teamLabel } from "../utils.js";
import { scoreboard } from "./scoreboard.js";

function awardMark(player) {
  if (player.award === "MVP") return `<span class="award-mark mvp" title="MVP" aria-label="MVP">♛</span>`;
  if (player.award === "ACE") return `<span class="award-mark ace" title="ACE" aria-label="ACE">◆</span>`;
  return "";
}

function previewPlayer(player) {
  const icon = championIcon(player.champion);
  return `<div class="preview-player">${icon ? `<img src="${escapeHtml(icon)}" alt="" loading="lazy">` : `<span class="preview-icon-empty"></span>`}<span class="name">${escapeHtml(player.name)}</span>${awardMark(player)}</div>`;
}

function renderTeamPreview(match, team) {
  const players = (match.players || []).filter((player) => player.team === team).slice(0,5);
  const won = isWinner(match,team);
  return `<div class="team-preview ${won ? "result-win" : "result-loss"}"><div class="team-head"><span>${won ? "승리" : "패배"}</span><small>${teamLabel(team)}</small></div>${players.map(previewPlayer).join("") || `<div class="preview-player"><span></span><span class="name">상세 기록 없음</span></div>`}</div>`;
}

export function matchCard(match) {
  const duration = formatDuration(match.durationSeconds);
  return `<article class="match-card" data-match-id="${escapeHtml(match.matchId)}"><div class="match-summary"><div class="match-meta"><span class="match-mode">${escapeHtml(normalizeMode(match))}</span><span class="match-time">${escapeHtml(relativeTime(match.time))}</span>${duration ? `<span class="match-duration">${duration}</span>` : ""}</div><div class="teams-preview">${renderTeamPreview(match,"blue")}${renderTeamPreview(match,"red")}</div><button class="expand-match" type="button" aria-label="경기 상세 펼치기">⌄</button></div>${scoreboard(match)}</article>`;
}
