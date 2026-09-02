import { championIcon } from "../assets.js";
import { escapeHtml, focusKda, normalizeMode, relativeTime, scoreClass } from "../utils.js";
import { renderItems, renderRuneSpells } from "./loadout.js";
import { scoreboard } from "./scoreboard.js";

export function playerMatchCard(match, userId) {
  const player = (match.players || []).find((row) => String(row.userId) === String(userId));
  if (!player) return "";
  const allies = (match.players || []).filter((row) => row.team === player.team && String(row.userId) !== String(userId));
  const enemies = (match.players || []).filter((row) => row.team !== player.team);
  const champion = championIcon(player.champion);
  const won = player.result === "win";
  return `<article class="personal-match ${won ? "win" : "loss"}">
    <div class="personal-summary">
      <div class="result-meta"><strong>${won ? "승리" : "패배"}</strong><span>${escapeHtml(relativeTime(match.time))}</span><div>${escapeHtml(normalizeMode(match))}</div></div>
      <div class="focus-champion">${champion ? `<img src="${escapeHtml(champion)}" alt="${escapeHtml(player.champion)}" loading="lazy">` : ""}</div>
      <div class="focus-meta"><span class="tier-badge">${escapeHtml(player.tier || "-")}</span>${renderRuneSpells(player)}</div>
      <div class="focus-kda"><strong>${focusKda(player)}</strong><span>${player.deaths === 0 ? "Perfect" : `${Number(player.kda || 0).toFixed(2)} KDA`}</span></div>
      <div>${player.aiScore == null ? `<span class="numeric">-</span>` : `<span class="ai-score ${scoreClass(player.aiScore)}">${Math.round(player.aiScore)}</span>`}${player.award ? `<div class="player-sub">${escapeHtml(player.award)}</div>` : ""}</div>
      <div class="focus-cs numeric">${Number(player.damage || 0).toLocaleString()}<div class="player-sub">${Number(player.cs || 0)} CS · ${Number(player.csm || 0).toFixed(1)}/분</div></div>
      <div class="personal-items">${renderItems(player,6)}</div>
      <div class="roster-mini"><div>${allies.map((row) => `<span>${escapeHtml(row.name)}</span>`).join("")}</div><div>${enemies.map((row) => `<span>${escapeHtml(row.name)}</span>`).join("")}</div></div>
      <button class="personal-expand" type="button" aria-label="경기 상세 펼치기">⌄</button>
    </div>${scoreboard(match,userId)}</article>`;
}
