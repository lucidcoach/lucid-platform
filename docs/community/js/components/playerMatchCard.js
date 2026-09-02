import { championIcon } from "../assets.js";
import { escapeHtml, focusKda, normalizeMode, relativeTime, scoreClass } from "../utils.js";
import { renderItems, renderRuneSpells } from "./loadout.js";
import { scoreboard } from "./scoreboard.js";

function rosterPlayer(row) {
  const icon = championIcon(row.champion);
  return `<span class="roster-player" title="${escapeHtml(row.name)}">${icon ? `<img src="${escapeHtml(icon)}" alt="" loading="lazy">` : `<span class="roster-icon-empty"></span>`}<span>${escapeHtml(row.name)}</span></span>`;
}

export function playerMatchCard(match, userId) {
  const player = (match.players || []).find((row) => String(row.userId) === String(userId));
  if (!player || !player.champion) return "";
  const allies = (match.players || []).filter((row) => row.team === player.team && String(row.userId) !== String(userId));
  const enemies = (match.players || []).filter((row) => row.team !== player.team);
  const champion = championIcon(player.champion);
  const won = player.result === "win";
  const maxDamage = Math.max(1, ...(match.players || []).map((row) => Number(row.damage || 0)));
  const damagePct = Math.max(4, Math.min(100, Number(player.damage || 0) / maxDamage * 100));
  const special = player.award === "MVP" || Number(player.aiScore || 0) >= 100;
  return `<article class="personal-match ${won ? "win" : "loss"}${special ? " special-match" : ""}">
    <div class="personal-summary">
      <div class="result-meta"><strong>${won ? "승리" : "패배"}</strong><span>${escapeHtml(relativeTime(match.time))}</span><div>${escapeHtml(normalizeMode(match))}</div></div>
      <div class="focus-champion">${champion ? `<img src="${escapeHtml(champion)}" alt="" loading="lazy">` : ""}<div class="focus-loadout">${renderRuneSpells(player)}</div></div>
      <div class="focus-kda"><strong>${focusKda(player)}</strong><span>${player.deaths === 0 ? "Perfect" : `${Number(player.kda || 0).toFixed(2)} KDA`}</span></div>
      <div class="focus-score">${player.aiScore == null ? `<span class="numeric">-</span>` : `<span class="ai-score ${scoreClass(player.aiScore)}">${Math.round(player.aiScore)}</span>`}${player.award ? `<span class="personal-award ${player.award.toLowerCase()}" title="${escapeHtml(player.award)}">${player.award === "MVP" ? "♛" : "◆"}</span>` : ""}</div>
      <div class="damage-cell"><strong>${Number(player.damage || 0).toLocaleString()}</strong><span>DPM ${Math.round(player.dpm || 0)}</span><div class="damage-track"><i style="width:${damagePct.toFixed(1)}%"></i></div></div>
      <div class="focus-cs"><strong>${Number(player.cs || 0).toLocaleString()} CS</strong><span>${Number(player.csm || 0).toFixed(1)}/분</span></div>
      <div class="personal-items">${renderItems(player,6)}</div>
      <div class="roster-mini"><div class="roster-team allies">${allies.map(rosterPlayer).join("")}</div><div class="roster-team enemies">${enemies.map(rosterPlayer).join("")}</div></div>
      <button class="personal-expand" type="button" aria-label="경기 상세 펼치기">⌄</button>
    </div>${scoreboard(match,userId)}</article>`;
}
