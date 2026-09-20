import { championIcon } from "../assets.js?v=20260905ab";
import { escapeHtml, focusKda, kdaClass, normalizeMode, relativeTime, scoreClass, tierClass } from "../utils.js?v=20260914seriesmatch1";
import { renderInventoryGrid, renderProfileRuneSpells, renderBuildSummary } from "./loadout.js?v=20260905ab";
import { aiRank, aiStanding, scoreboard } from "./scoreboard.js?v=20260920matchreadability1";

function rosterPlayer(row, guildId, focusUserId) {
  const icon = championIcon(row.champion);
  return `<span class="roster-player ${String(row.userId) === String(focusUserId) ? "is-focus" : ""}" title="${escapeHtml(row.name)}">${icon ? `<img src="${escapeHtml(icon)}" alt="" loading="lazy">` : `<span class="roster-icon-empty"></span>`}<button class="player-profile-link roster-profile-link" type="button" data-player-profile data-user-id="${escapeHtml(row.userId)}" data-guild-id="${escapeHtml(guildId || "")}">${escapeHtml(row.name)}</button></span>`;
}


function achievementBadges(player) {
  const badges = [];
  if (Number(player?.pentaKills || 0) > 0) badges.push(`<span class="match-achievement multikill penta">펜타킬</span>`);
  else if (Number(player?.quadraKills || 0) > 0) badges.push(`<span class="match-achievement multikill quadra">쿼드라킬</span>`);
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
  const rank = aiRank(match, player);
  const mmrDelta = Math.round(Number(player.mmrDelta || 0));
  const replay = match.replay?.id ? match.replay : null;
  const hasBuild = Boolean(player.itemTimeline?.length || player.skillBuild?.length || player.items?.some((id)=>Number(id)>0));
  const hasDetails = match.source === "RIOT_API" ? Array.isArray(match.players) && match.players.length > 0 : Boolean(match.matchId && match.guildId);
  const details = match.source === "RIOT_API"
    ? scoreboard(match)
    : `<div class="match-details"><span class="mobile-score-scroll-hint">상세 지표는 좌우로 스크롤해 확인하세요.</span><div class="scoreboard-layout has-personal-analysis"><div class="scoreboard-teams" data-lazy-scoreboard></div><aside class="personal-analysis-panel" data-compact-analysis><div class="compact-analysis-empty"><strong>간단 분석</strong><span>상세를 펼치면 같은 라인 상대와 핵심 지표를 비교합니다.</span></div></aside></div></div>`;
  const resultText = `${won ? "승리" : "패배"}${mmrDelta ? ` (${mmrDelta > 0 ? "+" : ""}${mmrDelta})` : ""}`;
  return `<article class="personal-match ${won ? "win" : "loss"}${special ? " special-match" : ""}" data-analysis-user-id="${escapeHtml(userId)}" data-analysis-guild-id="${escapeHtml(match.guildId || "")}" data-analysis-match-id="${escapeHtml(match.matchId || "")}" data-analysis-champion="${escapeHtml(player.champion || "")}" data-analysis-role="${escapeHtml(player.role || "")}">
    <div class="personal-summary">
      <div class="result-meta"><strong>${resultText}</strong><span>${escapeHtml(relativeTime(match.time))}</span><div>${escapeHtml(normalizeMode(match))}</div></div>
      <div class="focus-visual compact-focus-layout">
        <div class="focus-champion">${champion ? `<img src="${escapeHtml(champion)}" alt="" loading="lazy">` : ""}${Number(player.level || 0) > 0 ? `<span class="champion-level">${Number(player.level)}</span>` : ""}</div>
        ${runeSpells ? `<div class="focus-loadout-side">${runeSpells}</div>` : `<div class="focus-loadout-side"></div>`}
      </div>
      <div class="personal-combat-group">
        <div class="focus-kda"><strong>${focusKda(player)}</strong><span class="personal-kda-value ${player.deaths === 0 ? "kda-red" : kdaClass(player.kda)}">${player.deaths === 0 ? "Perfect" : `${Number(player.kda || 0).toFixed(2)} KDA`}</span>${achievements ? `<div class="match-achievements kda-achievements">${achievements}</div>` : ""}</div>
        <div class="focus-score">${player.aiScore == null ? `<span class="numeric">-</span>` : `<span class="ai-score ${scoreClass(player.aiScore)}${Number(player.aiScore) >= 100 ? " over-100" : ""}">${Math.round(player.aiScore)}</span>`}${aiStanding(player, rank)}</div>
        <div class="personal-inventory">${renderInventoryGrid(player)}</div>
        <div class="focus-cs"><strong>CS ${Number(player.cs || 0).toLocaleString()} <em>(${Number(player.csm || 0).toFixed(1)})</em></strong></div>
      </div>
      <div class="roster-mini"><div class="roster-team allies">${allies.map((row) => rosterPlayer(row, match.guildId, userId)).join("")}</div><div class="roster-team enemies">${enemies.map((row) => rosterPlayer(row, match.guildId, userId)).join("")}</div></div>
      <div class="personal-actions"><button class="build-toggle" type="button" aria-label="경기 빌드 상세 보기" title="${hasBuild ? "빌드 상세" : "빌드 데이터 없음"}" ${hasBuild ? "" : "disabled"}>⌕</button><button class="personal-expand" type="button" aria-label="경기 상세 펼치기" title="${hasDetails ? "경기 상세 보기" : "상세 데이터 없음"}" ${hasDetails ? "" : "disabled"}>⌄</button>${replay ? `<button class="replay-download" type="button" data-replay-download="${escapeHtml(replay.id)}" data-replay-filename="${escapeHtml(replay.filename || "lucid-replay.rofl")}" aria-label="ROFL 다운로드" title="ROFL 다운로드"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3v12m-4-4 4 4 4-4M5 19h14"/></svg></button>` : ""}</div>
    </div><div class="build-detail-panel">${renderBuildSummary(player)}</div>${details}</article>`;
}
