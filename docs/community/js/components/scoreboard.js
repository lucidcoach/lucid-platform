import { championIcon } from "../assets.js?v=20260904d";
import { escapeHtml, focusKda, kdaClass, scoreClass, tierClass } from "../utils.js?v=20260904d";
import { renderLoadout, renderRuneSpells } from "./loadout.js?v=20260904d";

export function renderScoreboardRows(match, focusUserId = "") {
  const order = [...(match?.players || [])].sort((a,b) => a.team === b.team ? 0 : (a.team === "blue" ? -1 : 1));
  const maxDamage = Math.max(1, ...order.map((row) => Number(row.damage || 0)));
  return order.map((player) => {
    const champion = championIcon(player.champion);
    const focus = String(player.userId) === String(focusUserId) ? " focus-row" : "";
    const damagePct = Math.max(4, Math.min(100, Number(player.damage || 0) / maxDamage * 100));
    const award = player.award === "MVP" ? `<span class="score-award mvp" title="MVP" aria-label="MVP"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 7.5 8.3 11 12 5l3.7 6L20 7.5l-1.3 9H5.3L4 7.5Z"/><path d="M6.2 18.5h11.6"/></svg></span>` : (player.award === "ACE" ? `<span class="score-award ace" title="ACE" aria-label="ACE"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3.5 15 8l5 .8-3.6 3.6.8 5.1-5.2-2.4-5.2 2.4.8-5.1L4 8.8 9 8l3-4.5Z"/><circle cx="12" cy="11.5" r="2.1"/></svg></span>` : "");
    const runeSpells = renderRuneSpells(player);
    return `<tr class="${player.result === "win" ? "win-row" : "loss-row"}${focus}">
      <td><div class="player-cell"><span class="score-champion-wrap">${champion ? `<img class="champion-icon" src="${escapeHtml(champion)}" alt="" loading="lazy">` : `<span class="champion-icon"></span>`}${Number(player.level || 0) > 0 ? `<i class="score-level">${Number(player.level)}</i>` : ""}</span><span><span class="player-name"><button class="player-profile-link scoreboard-profile-link" type="button" data-player-profile data-user-id="${escapeHtml(player.userId)}" data-guild-id="${escapeHtml(match.guildId || "")}" title="${escapeHtml(player.name)} 전적 보기">${escapeHtml(player.name)}</button>${award}</span><span class="player-sub"><span class="tier-badge ${tierClass(player.tier)}">${escapeHtml(player.tier || "-")}</span><span>${escapeHtml(player.role || "")}</span>${runeSpells ? `<span class="score-rune-spells">${runeSpells}</span>` : ""}</span></span></div></td>
      <td>${player.aiScore == null ? `<span class="numeric">-</span>` : `<span class="ai-score ${scoreClass(player.aiScore)}">${Math.round(player.aiScore)}</span>`}</td>
      <td><span class="kda">${focusKda(player)}</span><div class="player-sub ${player.deaths === 0 ? "kda-red" : kdaClass(player.kda)}">${player.deaths === 0 ? "Perfect" : `${Number(player.kda || 0).toFixed(2)} KDA`}</div></td>
      <td class="damage-score"><strong>${Number(player.damage || 0).toLocaleString()}</strong><div class="damage-track"><i style="width:${damagePct.toFixed(1)}%"></i></div><div class="player-sub">DPM ${Math.round(player.dpm || 0)}</div></td>
      <td class="numeric">${Number(player.cs || 0).toLocaleString()}<div class="player-sub">${Number(player.csm || 0).toFixed(1)}/분</div></td>
      <td>${renderLoadout(player)}</td>
    </tr>`;
  }).join("");
}

export function scoreboard(match, focusUserId = "") {
  return `<div class="match-details"><table class="scoreboard">
    <colgroup><col style="width:30%"><col style="width:10%"><col style="width:16%"><col style="width:15%"><col style="width:11%"><col style="width:18%"></colgroup>
    <thead><tr><th>플레이어</th><th>AI-Score</th><th>KDA</th><th>피해량</th><th>CS</th><th>아이템</th></tr></thead>
    <tbody>${renderScoreboardRows(match, focusUserId)}</tbody>
  </table></div>`;
}

export function bindExpanders(root = document) {
  root.querySelectorAll(".expand-match, .personal-expand").forEach((button) => {
    if (button.dataset.bound) return;
    button.dataset.bound = "1";
    button.addEventListener("click", () => {
      const card = button.closest(".match-card, .personal-match");
      card?.classList.toggle("expanded");
      button.textContent = card?.classList.contains("expanded") ? "⌃" : "⌄";
    });
  });
  root.querySelectorAll(".build-toggle").forEach((button) => {
    if (button.dataset.buildBound) return;
    button.dataset.buildBound = "1";
    button.addEventListener("click", () => {
      const card = button.closest(".personal-match");
      card?.classList.toggle("build-expanded");
      button.classList.toggle("active", Boolean(card?.classList.contains("build-expanded")));
    });
  });
}
