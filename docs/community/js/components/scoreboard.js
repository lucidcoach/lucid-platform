import { championIcon } from "../assets.js?v=20260904p";
import { escapeHtml, focusKda, kdaClass, normalizeRoleKey, scoreClass, tierClass } from "../utils.js?v=20260904p";
import { renderInventoryGrid, renderProfileRuneSpells } from "./loadout.js?v=20260904p";

const ROLE_ORDER = new Map([["탑",0],["정글",1],["미드",2],["원딜",3],["서폿",4]]);


function tierShortLabel(tier = "") {
  const raw = String(tier || "").trim();
  if (!raw || ["-","미배치","언랭","UNRANKED","UNPLACED"].includes(raw.toUpperCase())) return "U";
  const compact = raw.toUpperCase().replace(/[\s_-]+/g, "");
  const divisionMatch = compact.match(/([1-4])$/);
  const division = divisionMatch ? divisionMatch[1] : "";
  if (compact.startsWith("CHALLENGER") || raw.includes("챌린저")) return "C";
  if (compact.startsWith("GRANDMASTER") || compact.startsWith("GM") || raw.includes("그랜드마스터")) return "GM";
  if (compact.startsWith("MASTER") || raw.includes("마스터")) return "M";
  if (compact.startsWith("DIAMOND") || compact.startsWith("D") || raw.includes("다이아")) return `D${division}`;
  if (compact.startsWith("EMERALD") || compact.startsWith("E") || raw.includes("에메랄드")) return `E${division}`;
  if (compact.startsWith("PLATINUM") || compact.startsWith("P") || raw.includes("플래티넘") || raw.includes("플레티넘")) return `P${division}`;
  if (compact.startsWith("GOLD") || compact.startsWith("G") || raw.includes("골드")) return `G${division}`;
  if (compact.startsWith("SILVER") || compact.startsWith("S") || raw.includes("실버")) return `S${division}`;
  if (compact.startsWith("BRONZE") || compact.startsWith("B") || raw.includes("브론즈")) return `B${division}`;
  if (compact.startsWith("IRON") || compact.startsWith("I") || raw.includes("아이언")) return `I${division}`;
  return raw.slice(0,3).toUpperCase();
}
function achievementLine(player) {
  const tags=[];
  if (Number(player?.pentaKills || 0)>0) tags.push(`<span class="score-tag penta">펜타킬</span>`);
  else if (Number(player?.quadraKills || 0)>0) tags.push(`<span class="score-tag quadra">쿼드라킬</span>`);
  if (player?.award === "MVP") tags.push(`<span class="score-tag award mvp">MVP</span>`);
  else if (player?.award === "ACE") tags.push(`<span class="score-tag award ace">ACE</span>`);
  return tags.join("");
}

function sortTeam(players = []) {
  return [...players].sort((a,b) => (ROLE_ORDER.get(normalizeRoleKey(a?.role)) ?? 99) - (ROLE_ORDER.get(normalizeRoleKey(b?.role)) ?? 99));
}

function teamMaxDamage(match, team) {
  return Math.max(1, ...(match?.players || [])
    .filter((row) => String(row?.team || "").toLowerCase() === String(team || "").toLowerCase())
    .map((row) => Number(row?.damage || 0)));
}

function aiRank(match, player) {
  const score = Number(player?.aiScore);
  const rows = (match?.players || []).filter((row) => Number.isFinite(Number(row?.aiScore)));
  if (!Number.isFinite(score) || !rows.length) return null;
  const rank = 1 + rows.filter((row) => Number(row.aiScore) > score).length;
  return { rank, total: rows.length };
}

function playerRow(match, player, focusUserId = "") {
  const champion = championIcon(player.champion);
  const focus = String(player.userId) === String(focusUserId) ? " focus-row" : "";
  const runeSpells = renderProfileRuneSpells(player);
  const achievements = achievementLine(player);
  const damage = Math.max(0, Number(player?.damage || 0));
  const maxDamage = teamMaxDamage(match, player?.team);
  const damagePct = Math.max(3, Math.min(100, Math.round((damage / maxDamage) * 100)));
  const rank = aiRank(match, player);
  return `<div class="score-player-row${focus}">
    <div class="score-identity">
      <span class="score-tier-text ${tierClass(player.tier)}" title="${escapeHtml(player.tier || "미배치")}">${escapeHtml(tierShortLabel(player.tier))}</span>
      <button class="player-profile-link scoreboard-profile-link" type="button" data-player-profile data-user-id="${escapeHtml(player.userId)}" data-guild-id="${escapeHtml(match.guildId || "")}" title="${escapeHtml(player.name)} 전적 보기">${escapeHtml(player.name)}</button>
    </div>
    <div class="score-combat-loadout">
      <span class="score-champion-wrap">${champion ? `<img class="champion-icon" src="${escapeHtml(champion)}" alt="" loading="lazy">` : `<span class="champion-icon"></span>`}${Number(player.level || 0)>0 ? `<i class="score-level">${Number(player.level)}</i>` : ""}</span>
      <span class="score-rune-spells">${runeSpells || ""}</span>
    </div>
    <div class="score-ai-cell">${player.aiScore==null ? `<span class="numeric">-</span>` : `<span class="ai-score ${scoreClass(player.aiScore)}">${Math.round(player.aiScore)}</span>`}${rank ? `<small>${rank.rank}위</small>` : ""}</div>
    <div class="score-kda-cell"><strong>${focusKda(player)}</strong><span>${player.deaths===0 ? "Perfect" : `${Number(player.kda || 0).toFixed(2)} KDA`}</span><div class="score-achievements">${achievements}</div></div>
    <div class="score-inventory">${renderInventoryGrid(player)}</div>
    <div class="score-cs-cell"><strong>CS ${Number(player.cs || 0).toLocaleString()} <em>(${Number(player.csm || 0).toFixed(1)})</em></strong></div>
    <div class="score-damage-cell" title="챔피언 피해량 ${damage.toLocaleString()}"><span class="score-damage-track"><i style="width:${damagePct}%"></i></span><strong>${damage.toLocaleString()}</strong></div>
  </div>`;
}

function teamPanel(match, team, focusUserId = "") {
  const players = sortTeam((match?.players || []).filter((player) => String(player.team || "").toLowerCase() === team));
  const label = team === "blue" ? "블루팀" : "레드팀";
  const winner = String(match?.winner || "").toLowerCase();
  const isWinner = winner === team || (team === "blue" && winner.includes("블루")) || (team === "red" && winner.includes("레드"));
  const resultLabel = winner ? (isWinner ? "승리팀" : "패배팀") : "";
  return `<section class="score-team-panel ${team}${isWinner ? " winner-team" : " loser-team"}"><div class="score-team-head"><span>${label}</span>${resultLabel ? `<b>${resultLabel}</b>` : ""}</div><div class="score-team-players">${players.map((player)=>playerRow(match,player,focusUserId)).join("")}</div></section>`;
}

export function renderScoreboardRows(match, focusUserId = "") {
  return `${teamPanel(match,"blue",focusUserId)}${teamPanel(match,"red",focusUserId)}`;
}

export function scoreboard(match, focusUserId = "") {
  const hasPersonalAnalysis = Boolean(String(focusUserId || "").trim());
  const analysisPanel = hasPersonalAnalysis
    ? `<aside class="personal-analysis-panel"><div><strong>상세전적 분석 예정</strong><span>검색한 플레이어의 상세 분석과 피드백이 표시될 영역입니다.</span></div></aside>`
    : "";
  return `<div class="match-details"><div class="scoreboard-layout${hasPersonalAnalysis ? " has-personal-analysis" : ""}"><div class="scoreboard-teams">${renderScoreboardRows(match, focusUserId)}</div>${analysisPanel}</div></div>`;
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
