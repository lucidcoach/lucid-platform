import { championIcon } from "../assets.js?v=20260904d";
import { escapeHtml, focusKda, kdaClass, normalizeMode, relativeTime, scoreClass, tierClass } from "../utils.js?v=20260904d";
import { renderItems, renderProfileRuneSpells, renderBuildSummary } from "./loadout.js?v=20260904d";
import { scoreboard } from "./scoreboard.js?v=20260904d";

function rosterPlayer(row, guildId, focusUserId) {
  const icon = championIcon(row.champion);
  return `<span class="roster-player ${String(row.userId) === String(focusUserId) ? "is-focus" : ""}" title="${escapeHtml(row.name)}">${icon ? `<img src="${escapeHtml(icon)}" alt="" loading="lazy">` : `<span class="roster-icon-empty"></span>`}<button class="player-profile-link roster-profile-link" type="button" data-player-profile data-user-id="${escapeHtml(row.userId)}" data-guild-id="${escapeHtml(guildId || "")}">${escapeHtml(row.name)}</button></span>`;
}

export function playerMatchCard(match, userId) {
  const player = (match.players || []).find((row) => String(row.userId) === String(userId));
  if (!player || !player.champion) return "";
  const allies = (match.players || []).filter((row) => row.team === player.team);
  const enemies = (match.players || []).filter((row) => row.team !== player.team);
  const champion = championIcon(player.champion);
  const won = player.result === "win";
  const maxDamage = Math.max(1, ...(match.players || []).map((row) => Number(row.damage || 0)));
  const damagePct = Math.max(4, Math.min(100, Number(player.damage || 0) / maxDamage * 100));
  const special = player.award === "MVP" || Number(player.aiScore || 0) >= 100;
  const runeSpells = renderProfileRuneSpells(player);
  return `<article class="personal-match ${won ? "win" : "loss"}${special ? " special-match" : ""}">
    <div class="personal-summary">
      <div class="result-meta"><strong>${won ? "승리" : "패배"}</strong><span>${escapeHtml(relativeTime(match.time))}</span><div>${escapeHtml(normalizeMode(match))}</div></div>
      <div class="focus-champion-loadout"><div class="focus-champion">${champion ? `<img src="${escapeHtml(champion)}" alt="" loading="lazy">` : ""}${Number(player.level || 0) > 0 ? `<span class="champion-level">${Number(player.level)}</span>` : ""}</div>${runeSpells ? `<div class="focus-loadout-side">${runeSpells}</div>` : ""}</div>
      <div class="focus-kda"><div class="match-tier-line"><span class="match-tier-badge ${tierClass(player.tier)}">${escapeHtml(player.tier || "-")}</span><span>${escapeHtml(player.role || "")}</span></div><strong>${focusKda(player)}</strong><span class="${player.deaths === 0 ? "kda-red" : kdaClass(player.kda)}">${player.deaths === 0 ? "Perfect" : `${Number(player.kda || 0).toFixed(2)} KDA`}</span></div>
      <div class="focus-score">${player.aiScore == null ? `<span class="numeric">-</span>` : `<span class="ai-score ${scoreClass(player.aiScore)}">${Math.round(player.aiScore)}</span>`}${player.award ? `<span class="personal-award ${player.award.toLowerCase()}" title="${escapeHtml(player.award)}" aria-label="${escapeHtml(player.award)}">${player.award === "MVP" ? `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 7.5 8.3 11 12 5l3.7 6L20 7.5l-1.3 9H5.3L4 7.5Z"/><path d="M6.2 18.5h11.6"/></svg>` : `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3.5 15 8l5 .8-3.6 3.6.8 5.1-5.2-2.4-5.2 2.4.8-5.1L4 8.8 9 8l3-4.5Z"/></svg>`}</span>` : ""}</div>
      <div class="damage-cell"><strong>${Number(player.damage || 0).toLocaleString()}</strong><span>DPM ${Math.round(player.dpm || 0)}</span><div class="damage-track"><i style="width:${damagePct.toFixed(1)}%"></i></div></div>
      <div class="focus-cs"><strong>${Number(player.cs || 0).toLocaleString()} CS</strong><span>${Number(player.csm || 0).toFixed(1)}/분</span></div>
      <div class="personal-items">${(player.items || []).length ? renderItems(player,6) : ""}</div>
      <div class="roster-mini"><div class="roster-team allies">${allies.map((row) => rosterPlayer(row, match.guildId, userId)).join("")}</div><div class="roster-team enemies">${enemies.map((row) => rosterPlayer(row, match.guildId, userId)).join("")}</div></div>
      <div class="personal-actions"><button class="build-toggle" type="button" aria-label="경기 빌드 상세 보기" title="빌드 상세">⌕</button><button class="personal-expand" type="button" aria-label="경기 상세 펼치기">⌄</button></div>
    </div><div class="build-detail-panel">${renderBuildSummary(player)}</div>${scoreboard(match,userId)}</article>`;
}
