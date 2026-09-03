import { championIcon } from "../assets.js?v=20260904g";
import { escapeHtml, focusKda, kdaClass, normalizeMode, relativeTime, scoreClass, tierClass } from "../utils.js?v=20260904g";
import { renderInventoryGrid, renderProfileRuneSpells, renderBuildSummary } from "./loadout.js?v=20260904g";
import { scoreboard } from "./scoreboard.js?v=20260904g";

function rosterPlayer(row, guildId, focusUserId) {
  const icon = championIcon(row.champion);
  return `<span class="roster-player ${String(row.userId) === String(focusUserId) ? "is-focus" : ""}" title="${escapeHtml(row.name)}">${icon ? `<img src="${escapeHtml(icon)}" alt="" loading="lazy">` : `<span class="roster-icon-empty"></span>`}<button class="player-profile-link roster-profile-link" type="button" data-player-profile data-user-id="${escapeHtml(row.userId)}" data-guild-id="${escapeHtml(guildId || "")}">${escapeHtml(row.name)}</button></span>`;
}

function achievementBadges(player) {
  const badges = [];
  if (Number(player?.pentaKills || 0) > 0) badges.push(`<span class="match-achievement multikill penta">펜타킬</span>`);
  else if (Number(player?.quadraKills || 0) > 0) badges.push(`<span class="match-achievement multikill quadra">쿼드라킬</span>`);
  if (player?.award === "MVP") badges.push(`<span class="match-achievement award mvp">MVP</span>`);
  else if (player?.award === "ACE") badges.push(`<span class="match-achievement award ace">ACE</span>`);
  return badges.join("");
}

export function playerMatchCard(match, userId) {
  const player = (match.players || []).find((row) => String(row.userId) === String(userId));
  if (!player || !player.champion) return "";
  const allies = (match.players || []).filter((row) => row.team === player.team);
  const enemies = (match.players || []).filter((row) => row.team !== player.team);
  const champion = championIcon(player.champion);
  const won = player.result === "win";
  const special = player.award === "MVP" || Number(player.aiScore || 0) >= 100;
  const runeSpells = renderProfileRuneSpells(player);
  const achievements = achievementBadges(player);
  return `<article class="personal-match ${won ? "win" : "loss"}${special ? " special-match" : ""}">
    <div class="personal-summary">
      <div class="result-meta"><strong>${won ? "승리" : "패배"}</strong><span>${escapeHtml(relativeTime(match.time))}</span><div>${escapeHtml(normalizeMode(match))}</div></div>
      <div class="focus-visual compact-focus-layout">
        <div class="focus-champion">${champion ? `<img src="${escapeHtml(champion)}" alt="" loading="lazy">` : ""}${Number(player.level || 0) > 0 ? `<span class="champion-level">${Number(player.level)}</span>` : ""}</div>
        ${runeSpells ? `<div class="focus-loadout-side">${runeSpells}</div>` : `<div class="focus-loadout-side"></div>`}
      </div>
      <div class="focus-kda"><strong>${focusKda(player)}</strong><span class="${player.deaths === 0 ? "kda-red" : kdaClass(player.kda)}">${player.deaths === 0 ? "Perfect" : `${Number(player.kda || 0).toFixed(2)} KDA`}</span>${achievements ? `<div class="match-achievements kda-achievements">${achievements}</div>` : ""}</div>
      <div class="personal-inventory">${renderInventoryGrid(player)}</div>
      <div class="focus-score"><small>AI</small>${player.aiScore == null ? `<span class="numeric">-</span>` : `<span class="ai-score ${scoreClass(player.aiScore)}">${Math.round(player.aiScore)}</span>`}</div>
      <div class="focus-cs"><strong>CS ${Number(player.cs || 0).toLocaleString()}</strong><span>${Number(player.csm || 0).toFixed(1)}/분</span></div>
      <div class="roster-mini"><div class="roster-team allies">${allies.map((row) => rosterPlayer(row, match.guildId, userId)).join("")}</div><div class="roster-team enemies">${enemies.map((row) => rosterPlayer(row, match.guildId, userId)).join("")}</div></div>
      <div class="personal-actions"><button class="build-toggle" type="button" aria-label="경기 빌드 상세 보기" title="빌드 상세">⌕</button><button class="personal-expand" type="button" aria-label="경기 상세 펼치기">⌄</button></div>
    </div><div class="build-detail-panel">${renderBuildSummary(player)}</div>${scoreboard(match,userId)}</article>`;
}
