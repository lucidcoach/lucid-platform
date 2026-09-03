import { championIcon } from "../assets.js?v=20260904b";
import { escapeHtml, formatDuration, isWinner, normalizeMode, relativeTime, teamLabel } from "../utils.js?v=20260904b";
import { scoreboard } from "./scoreboard.js?v=20260904b";
import { renderRuneSpells } from "./loadout.js?v=20260904b";

function awardMark(player) {
  if (player.award === "MVP") return `<span class="award-mark mvp" title="MVP" aria-label="MVP"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 7.5 8.3 11 12 5l3.7 6L20 7.5l-1.3 9H5.3L4 7.5Z"/><path d="M6.2 18.5h11.6"/></svg></span>`;
  if (player.award === "ACE") return `<span class="award-mark ace" title="ACE" aria-label="ACE"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3.5 15 8l5 .8-3.6 3.6.8 5.1-5.2-2.4-5.2 2.4.8-5.1L4 8.8 9 8l3-4.5Z"/><circle cx="12" cy="11.5" r="2.1"/></svg></span>`;
  return "";
}

function previewPlayer(player, guildId) {
  const icon = championIcon(player.champion);
  return `<div class="preview-player">
    <span class="preview-champion-wrap">${icon ? `<img src="${escapeHtml(icon)}" alt="" loading="lazy">` : `<span class="preview-icon-empty"></span>`}${Number(player.level || 0) > 0 ? `<i class="preview-level">${Number(player.level)}</i>` : ""}</span>
    <span class="preview-name-wrap"><button class="player-profile-link" type="button" data-player-profile data-user-id="${escapeHtml(player.userId)}" data-guild-id="${escapeHtml(guildId || "")}" title="${escapeHtml(player.name)} 전적 보기">${escapeHtml(player.name)}</button>${awardMark(player)}</span>
    <span class="preview-loadout">${renderRuneSpells(player)}</span>
  </div>`;
}

function renderTeamPreview(match, team) {
  const players = (match.players || []).filter((player) => player.team === team).slice(0,5);
  const won = isWinner(match,team);
  return `<div class="team-preview ${team} ${won ? "result-win" : "result-loss"}"><div class="team-head"><span class="team-result-label">${won ? "승리" : "패배"}</span><small>${teamLabel(team)}</small></div>${players.map((player) => previewPlayer(player, match.guildId)).join("") || `<div class="preview-player"><span></span><span class="name">상세 기록 없음</span></div>`}</div>`;
}

export function matchCard(match) {
  const duration = formatDuration(match.durationSeconds);
  return `<article class="match-card" data-match-id="${escapeHtml(match.matchId)}"><div class="match-summary"><div class="match-meta"><span class="match-mode">${escapeHtml(normalizeMode(match))}</span><span class="match-time">${escapeHtml(relativeTime(match.time))}</span>${duration ? `<span class="match-duration">${duration}</span>` : ""}</div><div class="teams-preview">${renderTeamPreview(match,"blue")}${renderTeamPreview(match,"red")}</div><button class="expand-match" type="button" aria-label="경기 상세 펼치기">⌄</button></div>${scoreboard(match)}</article>`;
}
