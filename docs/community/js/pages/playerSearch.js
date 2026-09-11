import { apiGet } from "../api.js?v=20260907permissions1";
import { API_BASE_URL, PLAYER_MATCH_LIMIT } from "../config.js?v=20260904r";
import { championIcon } from "../assets.js?v=20260904r";
import { $, escapeHtml, kdaClass, normalizeRoleKey, tierClass, tierLeaguePoints, winRateClass } from "../utils.js?v=20260911public1";
import { renderLoading, switchView } from "../view.js?v=20260904r";
import { playerMatchCard } from "../components/playerMatchCard.js?v=20260911public1";
import { bindExpanders } from "../components/scoreboard.js?v=20260907hotfix1";
import { canAnalyzePlayer, canAnalyzeAllPlayers, getCurrentUser, isCommunityAdmin, isCommunityCoach, isCommunityServerAdmin } from "../auth.js?v=20260907oauth1";


function updateUrl(params, mode = "push") {
  if (mode === "none") return;
  const url = new URL(window.location.href);
  url.search = "";
  for (const [key, value] of Object.entries(params || {})) {
    if (value != null && String(value)) url.searchParams.set(key, String(value));
  }
  history[mode === "replace" ? "replaceState" : "pushState"]({}, "", `${url.pathname}${url.search}`);
}

function candidate(row) {
  const alias = row.matchedName && row.matchedName !== row.name
    ? `<small class="matched-alias">${escapeHtml(row.matchedName)}로 검색됨</small>`
    : "";
  return `<button class="search-candidate" type="button" data-user-id="${escapeHtml(row.userId)}" data-guild-id="${escapeHtml(row.guildId)}"><span><strong>${escapeHtml(row.name)}</strong>${alias}<span>${escapeHtml(row.tier)} · ${Number(row.games || 0)}경기</span></span><span>전적 보기 ›</span></button>`;
}

const TIER_ICON = {
  C: "challenger.png",
  GM: "grandmaster.png",
  M: "master.png",
  D: "diamond.png",
  E: "emerald.png",
  P: "platinum.png",
  G: "gold.png",
  S: "silver.png",
  B: "bronze.png",
  I: "iron.png",
};

function equippedTitleBadge(title) {
  if (!title?.displayTitle) return "";
  let icons = "";
  if (title.iconSource === "custom" && title.customIconUrl) {
    icons = `<img src="${escapeHtml(`${API_BASE_URL.replace(/\/$/, "")}${title.customIconUrl}`)}" alt="">`;
  } else if (title.iconSource === "champion") {
    icons = (title.championNames || []).map((name) => {
      const url = championIcon(name);
      return url ? `<img src="${escapeHtml(url)}" alt="${escapeHtml(name)}">` : "";
    }).join("");
  } else if (title.iconSource === "emoji" && title.iconEmoji) {
    icons = `<span>${escapeHtml(title.iconEmoji)}</span>`;
  }
  const name = title.iconEmoji && String(title.displayTitle).startsWith(title.iconEmoji)
    ? String(title.displayTitle).slice(String(title.iconEmoji).length).trim()
    : title.displayTitle;
  return `<div class="profile-equipped-title">${icons ? `<i>${icons}</i>` : ""}<b>${escapeHtml(name)}</b></div>`;
}

function roleBadges(rows = []) {
  return rows.length ? `<div class="profile-role-badges">${rows.map((role) => `<span>${escapeHtml(role.icon || "")} ${escapeHtml(role.label || "")}</span>`).join("")}</div>` : "";
}

function titleProfileIcon(title, fallback) {
  if (title?.iconSource === "custom" && title.customIconUrl) {
    return `<img class="summoner-profile-icon title-icon" src="${escapeHtml(`${API_BASE_URL.replace(/\/$/, "")}${title.customIconUrl}`)}" alt="${escapeHtml(title.displayTitle || "장착 칭호")}">`;
  }
  if (title?.iconSource === "champion" && title.championNames?.length) {
    const url = championIcon(title.championNames[0]);
    if (url) return `<img class="summoner-profile-icon title-icon" src="${escapeHtml(url)}" alt="${escapeHtml(title.championNames[0])}">`;
  }
  if (title?.iconSource === "emoji" && title.iconEmoji) {
    return `<span class="summoner-profile-icon fallback title-icon" aria-label="${escapeHtml(title.displayTitle || "장착 칭호")}">${escapeHtml(title.iconEmoji)}</span>`;
  }
  return fallback;
}

function tierIcon(tier = "") {
  const key = String(tier || "").match(/^(GM|[CMDEP G S B I])/i)?.[1]?.replaceAll(" ", "").toUpperCase()
    || String(tier || "").match(/^(GM|[CMDEPGSBI])/i)?.[1]?.toUpperCase()
    || "I";
  return `assets/tiers/${TIER_ICON[key] || TIER_ICON.I}`;
}

function isFavoriteLocal(userId, guildId) {
  try {
    const rows = JSON.parse(localStorage.getItem("lucid-community-favorite-searches-v1") || "[]");
    return Array.isArray(rows) && rows.some((row) => String(row?.userId) === String(userId) && String(row?.guildId) === String(guildId));
  } catch (_) { return false; }
}

function profileIconUrl(player = {}) {
  const direct = String(player?.profileIconUrl || "").trim();
  if (direct) return direct;
  const iconId = Number(player?.profileIconId || 0);
  return iconId > 0
    ? `https://raw.communitydragon.org/latest/plugins/rcp-be-lol-game-data/global/default/v1/profile-icons/${iconId}.jpg`
    : "";
}

function roleDelta(row = {}) {
  const delta = Number(row?.recent10Delta || 0);
  if (!Number.isFinite(delta) || Math.round(delta) === 0) return "";
  const up = delta > 0;
  return `<span class="role-tier-delta ${up ? "up" : "down"}">${up ? "▲" : "▼"}${Math.abs(Math.round(delta))}점</span>`;
}

function roleTierBoard(rows = [], embedded = false) {
  const roles = ["탑", "정글", "미드", "원딜", "서폿"];
  const list = Array.isArray(rows)
    ? rows
    : Object.entries(rows || {}).map(([role, value]) => ({ role, ...(value && typeof value === "object" ? value : { tier:value }) }));
  const byRole = new Map(list.map((row) => [normalizeRoleKey(row?.role || row?.position || row?.lane), row]));
  return `<${embedded?"div":"section"} class="role-tier-board role-tier-compact" aria-label="라인별 내전 티어">
    ${embedded?"":`<div class="profile-section-title"><strong>라인별 내전 티어</strong></div>`}
    <div class="role-tier-list">${roles.map((role) => {
      const row = byRole.get(role) || { role, tier: "미배치", wins: 0, losses: 0 };
      const tier = String(row?.tier || row?.tierName || row?.rank || "").trim();
      const compactTier = tier.toUpperCase().replace(/[\s_-]+/g, "");
      const hasTier = Boolean(tier) && !["-","미배치","언랭","UNRANKED","UNPLACED","NONE","NULL"].includes(compactTier);
      if (!hasTier) {
        return `<div class="role-tier-line unplaced">
          <span class="role-tier-role">${escapeHtml(role)}</span>
          <span class="role-tier-unplaced">미배치</span>
        </div>`;
      }
      const lp = tierLeaguePoints(tier, row.mmr || row.score || 0);
      return `<div class="role-tier-line ${tierClass(tier)}">
        <span class="role-tier-role">${escapeHtml(role)}</span>
        <span class="role-tier-main">
          <span class="role-tier-rank"><img src="${escapeHtml(tierIcon(tier))}" alt="" loading="lazy"><strong class="tier-text ${tierClass(tier)}">${escapeHtml(tier)}</strong><span class="role-tier-mmr">${lp.toLocaleString()}점</span></span>
          <span class="role-tier-record"><em>${Number(row.wins || row.win || 0)}승</em><b>${Number(row.losses || row.loss || 0)}패</b><i>${Number(row.winRate || 0).toFixed(1)}%</i></span>
          ${roleDelta(row)}
        </span>
      </div>`;
    }).join("")}</div>
  </${embedded?"div":"section"}>`;
}

function championRow(row) {
  const icon = championIcon(row.champion);
  return `<div class="champion-stat-row">
    <div class="champion-stat-name">${icon ? `<img src="${escapeHtml(icon)}" alt="" loading="lazy">` : ""}<strong>${escapeHtml(row.champion)}</strong></div>
    <span>${Number(row.games || 0)}게임</span>
    <span class="${winRateClass(row.winRate)}">${Number(row.winRate || 0).toFixed(1)}%</span>
    <span class="${kdaClass(row.kda)}">${Number(row.kda || 0).toFixed(2)}</span>
  </div>`;
}

function championStatsPanel(groups = {}) {
  const tabs = ["전체", "탑", "정글", "미드", "원딜", "서폿"];
  return `<section class="champion-stats-panel">
    <div class="profile-section-title"><strong>챔피언 통계</strong></div>
    <div class="champion-role-tabs" role="tablist">${tabs.map((role, i) => `<button type="button" class="champion-role-tab${i === 0 ? " active" : ""}" data-champion-role="${escapeHtml(role)}">${escapeHtml(role)}</button>`).join("")}</div>
    <div class="champion-stat-head"><span>챔피언</span><span>게임</span><span>승률</span><span>KDA</span></div>
    <div class="champion-stat-list" data-champion-list></div>
    <button class="champion-more-button" type="button" data-champion-more hidden>더 보기</button>
  </section>`;
}

function associateRow(row) {
  return `<div class="associate-row"><button type="button" data-player-profile data-user-id="${escapeHtml(row.userId)}" data-guild-id="${escapeHtml(row.guildId)}" title="${escapeHtml(row.name)} 전적 보기">${escapeHtml(row.name)}</button><span>${Number(row.wins || 0)}승</span><span>${Number(row.losses || 0)}패</span><strong class="${winRateClass(row.winRate)}">${Number(row.winRate || 0).toFixed(1)}%</strong></div>`;
}

function associatesPanel(data = {}) {
  return `<section class="associate-stats-panel">
    <div class="profile-section-title"><strong>최근 같이 게임한 소환사</strong><span>최근 ${Number(data.sampleGames || 0)}게임 · 2판 이상</span></div>
    <div class="associate-tabs" role="tablist"><button class="associate-tab active" type="button" data-associate-kind="allies">같은 팀</button><button class="associate-tab" type="button" data-associate-kind="opponents">상대 팀</button></div>
    <div class="associate-list" data-associate-list></div>
  </section>`;
}

function bindAssociates(target, data = {}) {
  const list = target.querySelector("[data-associate-list]");
  const tabs = [...target.querySelectorAll("[data-associate-kind]")];
  if (!list) return;
  const render = (kind) => {
    const rows = Array.isArray(data?.[kind]) ? data[kind].slice(0, 6) : [];
    list.innerHTML = rows.length ? rows.map(associateRow).join("") : `<div class="associate-empty">최근 20게임에서 2판 이상 만난 소환사가 없습니다.</div>`;
  };
  tabs.forEach((button) => button.addEventListener("click", () => {
    tabs.forEach((item) => item.classList.toggle("active", item === button));
    render(button.dataset.associateKind || "allies");
  }));
  render("allies");
}


function percentileText(row={}){
  const pct=Number(row.topPercent??row.percentileTop??row.percentile);
  if(Number.isFinite(pct)&&pct>0)return `상위 ${pct.toFixed(pct<10?1:0)}%`;
  const rank=Number(row.rank||0),total=Number(row.total||row.population||0);
  if(rank>0&&total>0)return `${rank}위 / ${total}명`;
  if(rank>0)return `${rank}위`;
  return "집계 중";
}
function serverStatCard(row={}){
  const label=row.label||row.name||row.metric||"지표";
  const value=row.displayValue??row.value??"-";
  const rank=percentileText(row);
  const tone=Number(row.topPercent||100)<=20?"elite":Number(row.topPercent||100)<=40?"good":"";
  return `<article class="server-stat-card ${tone}"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong><div><b>${escapeHtml(rank)}</b><small>${escapeHtml(row.note||row.scope||"")}</small></div></article>`;
}
function serverStatsPanel(data={}){
  const rows=data.stats||data.metrics||data.rankings||[];
  const role=data.role||data.position||"주 포지션";
  const sample=Number(data.sampleGames||data.games||0);
  return `<section class="server-stats-panel"><div class="server-stats-head"><div><small>SERVER PERFORMANCE</small><h2>${escapeHtml(role)} 서버 내 지표</h2><p>같은 Discord 서버의 같은 포지션 유저와 비교합니다.</p></div><span>${sample?`${sample}경기 기준`:"서버 표본"}</span></div><div class="server-stat-grid">${rows.length?rows.slice(0,6).map(serverStatCard).join(""):`<div class="server-stat-empty"><strong>서버 통계가 쌓이는 중입니다.</strong><span>DPM, 15분 킬관여, 갱킹 성공률 같은 포지션별 지표가 여기에 표시됩니다.</span></div>`}</div></section>`;
}
async function loadServerStats(userId,guildId){
  try{return await apiGet(`/api/community/players/${encodeURIComponent(userId)}/server-stats?guildId=${encodeURIComponent(guildId)}`);}catch(_){return null;}
}

function bindChampionStats(target, groups = {}) {
  const list = target.querySelector("[data-champion-list]");
  const more = target.querySelector("[data-champion-more]");
  const tabs = [...target.querySelectorAll("[data-champion-role]")];
  if (!list || !more) return;
  let role = "전체";
  let expanded = false;

  const render = () => {
    const rows = Array.isArray(groups?.[role]) ? groups[role] : [];
    const visible = expanded ? rows : rows.slice(0, 6);
    list.innerHTML = visible.length
      ? visible.map(championRow).join("")
      : `<div class="champion-stat-empty">해당 라인의 저장된 상세 기록이 없습니다.</div>`;
    more.hidden = rows.length <= 6;
    more.textContent = expanded ? "접기" : `더 보기 (${rows.length})`;
  };

  tabs.forEach((button) => button.addEventListener("click", () => {
    tabs.forEach((item) => item.classList.toggle("active", item === button));
    role = button.dataset.championRole || "전체";
    expanded = false;
    render();
  }));
  more.addEventListener("click", () => {
    expanded = !expanded;
    render();
  });
  render();
}


function personalMatchChampion(match, userId) {
  const player = (match?.players || []).find((row) => String(row?.userId) === String(userId));
  return String(player?.champion || "").trim();
}

function isDiscordLinkedUser(user) {
  return Boolean(user?.discordConnected || user?.discord_connected || user?.discordDisplayName || user?.discord_display_name || user?.discordId || user?.discord_id);
}

function canAnalyzeSearchedPlayer(userId, guildId) {
  if (isCommunityAdmin() || isCommunityCoach() || isCommunityServerAdmin(guildId)) return { ok:true };
  const user = getCurrentUser();
  if (!user) return { ok:false, message:"로그인 후 Discord 연동이 필요합니다." };
  if (!isDiscordLinkedUser(user)) return { ok:false, message:"Discord 연동 후 본인이 등록한 계정만 분석할 수 있습니다." };
  if (!Array.isArray(user.analysisPlayers) || !user.analysisPlayers.length) return { ok:false, message:"Discord에서 /소환사등록을 먼저 해주세요." };
  if (!canAnalyzePlayer(userId, guildId)) return { ok:false, message:"본인이 등록한 계정만 볼 수 있습니다. 다른 회원 분석은 관리자 권한이 필요합니다." };
  return { ok:true };
}

function personalHistoryFilters(matches = [], userId, guildId, riotId="") {
  const champions = [...new Set(
    matches.map((match) => personalMatchChampion(match, userId)).filter(Boolean)
  )].sort((a, b) => a.localeCompare(b, "ko"));
  const options = champions.map((champion) => `<option value="${escapeHtml(champion)}"></option>`).join("");
  return `<div class="personal-history-toolbar" aria-label="개인 전적 필터">
    <label class="personal-champion-filter personal-champion-search-filter">
      <span>챔피언</span>
      <input type="search" data-personal-champion-filter list="personalChampionOptions-${escapeHtml(userId)}" placeholder="챔피언 검색" autocomplete="off" aria-label="챔피언 검색">
      <datalist id="personalChampionOptions-${escapeHtml(userId)}">${options}</datalist>
    </label>
    <div class="personal-queue-filter" role="group" aria-label="게임 유형 필터">
      <span class="personal-filter-label">게임 유형</span>
      <div class="personal-queue-buttons">
        ${[["all","전체"],["internal","내전"],["solo","솔랭"],["flex","자랭"],["normal","일반"],["aram","칼바람"]].map(([value,label],i)=>`<button type="button" data-personal-queue="${value}" class="${i===0?"active":""}">${label}</button>`).join("")}
      </div>
    </div>
    <button class="personal-admin-analysis-button" type="button" data-admin-analyze-player data-user-id="${escapeHtml(userId)}" data-guild-id="${escapeHtml(guildId)}" data-riot-id="${escapeHtml(riotId)}">분석하기</button>
  </div>`;
}

function bindPersonalHistoryFilters(target, matches = [], userId) {
  const input = target.querySelector("[data-personal-champion-filter]");
  const feed = target.querySelector("[data-personal-match-feed]");
  if (!input || !feed) return;
  let category = "all";

  const render = () => {
    const query = String(input.value || "").trim().toLowerCase();
    const visible = matches.filter((match) =>
      (!query || personalMatchChampion(match, userId).toLowerCase().includes(query))
      && (category === "all" || String(match.category || "internal") === category)
    );
    feed.innerHTML = visible.map((match) => playerMatchCard(match, userId)).join("")
      || `<div class="empty-state"><strong>${query ? "검색한 챔피언의 저장된 경기 기록이 없습니다." : "상세 스탯이 있는 경기 기록이 없습니다."}</strong></div>`;
    bindExpanders(feed);
    bindReplayDownloads(feed);
  };

  input.addEventListener("input", render);
  input.addEventListener("change", render);
  target.querySelectorAll("[data-personal-queue]").forEach((button) => button.addEventListener("click", () => {
    category = button.dataset.personalQueue || "all";
    target.querySelectorAll("[data-personal-queue]").forEach((item) => item.classList.toggle("active", item === button));
    render();
  }));
}

function officialRanksPanel(rows = [], embedded = false) {
  const labels = {RANKED_SOLO_5x5:"솔로랭크", RANKED_FLEX_SR:"자유랭크"};
  const visible = rows.filter((row) => row.tier);
  if (!visible.length) return "";
  return `<${embedded?"div":"section"} class="official-rank-panel">${embedded?"":`<div class="profile-section-title"><strong>Riot 공식 랭크</strong></div>`}<div class="official-rank-list">${visible.map((row) => `<div><span>${escapeHtml(labels[row.queueType] || row.queueType)}${Number(row.accountSlot) > 0 ? ` · 부계정 ${Number(row.accountSlot)}` : ""}</span><strong>${escapeHtml(`${row.tier} ${row.rank}`)} ${Number(row.leaguePoints || 0)} LP</strong><small>${Number(row.wins || 0)}승 ${Number(row.losses || 0)}패</small></div>`).join("")}</div></${embedded?"div":"section"}>`;
}

function profileRanksPanel(roleRows = [], officialRows = []) {
  const official = officialRanksPanel(officialRows, true);
  if (!official) return roleTierBoard(roleRows);
  return `<section class="profile-rank-switcher"><div class="profile-section-title"><strong data-rank-switch-title>라인별 내전 티어</strong><button class="profile-favorite-button" style="margin-left:auto" type="button" data-rank-switch="riot" aria-label="Riot 공식 랭크 보기" title="Riot 공식 랭크 보기">⇄</button></div><div class="profile-rank-switcher-body"><div data-rank-panel="internal">${roleTierBoard(roleRows,true)}</div><div data-rank-panel="riot" hidden>${official}</div></div></section>`;
}

function bindRankSwitch(target) {
  const button = target.querySelector("[data-rank-switch]");
  const title = target.querySelector("[data-rank-switch-title]");
  if (!button || !title) return;
  button.addEventListener("click", () => {
    const showRiot = button.dataset.rankSwitch === "riot";
    target.querySelectorAll("[data-rank-panel]").forEach(panel=>{panel.hidden=panel.dataset.rankPanel!==(showRiot?"riot":"internal");});
    title.textContent=showRiot?"Riot 공식 랭크":"라인별 내전 티어";
    button.dataset.rankSwitch=showRiot?"internal":"riot";
    button.title=showRiot?"라인별 내전 티어 보기":"Riot 공식 랭크 보기";
    button.setAttribute("aria-label",button.title);
  });
}

function bindReplayDownloads(target) {
  target.querySelectorAll("[data-replay-download]").forEach((button) => button.addEventListener("click", async () => {
    if (button.disabled) return;
    button.disabled = true;
    try {
      const response = await fetch(`${API_BASE_URL.replace(/\/$/, "")}/api/community/admin/replays/${encodeURIComponent(button.dataset.replayDownload)}`, { credentials:"include" });
      if (!response.ok) throw new Error();
      const url = URL.createObjectURL(await response.blob());
      const link = document.createElement("a");
      link.href = url;
      link.download = button.dataset.replayFilename || "lucid-replay.rofl";
      link.click();
      URL.revokeObjectURL(url);
    } catch (_) {
      window.alert("ROFL 다운로드에 실패했습니다.");
    } finally {
      button.disabled = false;
    }
  }));
}

export async function openPlayer(userId,guildId,{historyMode="push"}={}) {
  updateUrl({ player: userId, guild: guildId }, historyMode);
  switchView("search");
  const target=$("searchResults");
  renderLoading(target,4);
  try {
    const [data, serverStats, replayData] = await Promise.all([
      apiGet(`/api/community/players/${encodeURIComponent(userId)}?guildId=${encodeURIComponent(guildId)}&limit=${PLAYER_MATCH_LIMIT}`),
      loadServerStats(userId,guildId),
      isCommunityAdmin() ? apiGet("/api/community/admin/replays?limit=500").catch(() => ({ replays:[] })) : Promise.resolve({ replays:[] }),
    ]);
    const replayMap = new Map((replayData.replays || []).map((row) => [`${row.guildId}:${row.matchId}`, row]));
    const internalMatches = (data.matches || []).map((match) => ({ ...match, source:match.source || "LUCID_INTERNAL", category:"internal", replay:replayMap.get(`${match.guildId}:${match.matchId}`) || null }));
    const matches = [...internalMatches, ...(data.publicMatches || [])].sort((a,b) => new Date(b.time || 0) - new Date(a.time || 0));
    const p=data.player;
    const scrimIconUrl = p.scrimIconPath ? `${API_BASE_URL.replace(/\/$/, "")}${p.scrimIconPath}` : "";
    const scrimIcon = scrimIconUrl
      ? `<img class="summoner-profile-icon" src="${escapeHtml(scrimIconUrl)}" alt="내전 레벨 아이콘">`
      : `<span class="summoner-profile-icon fallback" aria-label="내전 레벨 아이콘">${escapeHtml(p.scrimIconEmoji || "🎮")}</span>`;
    const profileIcon = titleProfileIcon(p.equippedTitle, scrimIcon);
    if ($("playerSearchInput")) $("playerSearchInput").value = p.name || "";
    const aliases=(p.aliases || []).filter(Boolean);

    window.dispatchEvent(new CustomEvent("lucid:player-opened", { detail: { name:p.name || "", userId:String(userId), guildId:String(guildId) } }));
    target.innerHTML=`<section class="profile-dashboard-grid">
      <div class="profile-summary-panel">
        <div class="profile-title-row"><div class="profile-name profile-name-with-icon"><span class="summoner-profile-stack" title="${p.equippedTitle?.displayTitle?`장착 칭호 · ${escapeHtml(p.equippedTitle.displayTitle)}`:`내전 ${Number(p.scrimGames || 0)}경기 · 다음 레벨 ${Number(p.scrimNextLevelAt || 5)}경기`}"><span class="summoner-level-text">Lv ${Number(p.scrimLevel || 1)}</span>${profileIcon}</span><div class="profile-identity-copy"><div class="profile-name-main"><span class="tier-badge ${tierClass(p.tier)}">${escapeHtml(p.tier || "-")}</span><h1 title="${escapeHtml(p.name)}">${escapeHtml(p.name)}</h1></div>${equippedTitleBadge(p.equippedTitle)}${roleBadges(p.roleBadges || [])}</div></div><div class="profile-refresh-wrap profile-refresh-above-name"><button class="profile-favorite-button${isFavoriteLocal(userId,guildId) ? " active" : ""}" type="button" data-profile-favorite aria-label="즐겨찾기" title="즐겨찾기">${isFavoriteLocal(userId,guildId) ? "★" : "☆"}</button><button class="profile-refresh-button" type="button" data-profile-refresh>전적 갱신</button></div></div>
        <div class="profile-overview profile-overview-compact">
          <div class="profile-record"><span>전적</span><strong>${Number(p.games || 0)}전 <em>${Number(p.wins || 0)}승</em> <b>${Number(p.losses || 0)}패</b></strong><small>승률 <b class="${winRateClass(p.winRate)}">${Number(p.winRate || 0).toFixed(1)}%</b></small></div>
          <div class="profile-record"><span>평균 KDA</span><strong class="${kdaClass(p.averageKda)}">${Number(p.averageKda || 0).toFixed(2)}</strong></div>
        </div>
        ${profileRanksPanel(p.roleTiers || [],data.publicRanks || [])}
      </div>
      <div class="profile-champion-panel">
        ${championStatsPanel(p.championStats || {})}
        ${associatesPanel(p.recentAssociates || {})}
      </div>
    </section>
    ${serverStats ? serverStatsPanel(serverStats) : ""}
    ${personalHistoryFilters(matches, userId, guildId, p.name || "")}
    <div class="match-feed personal-feed" data-personal-match-feed>${matches.map((m)=>playerMatchCard(m,userId)).join("") || `<div class="empty-state"><strong>상세 스탯이 있는 경기 기록이 없습니다.</strong></div>`}</div>`;

    bindChampionStats(target, p.championStats || {});
    bindRankSwitch(target);
    bindAssociates(target, p.recentAssociates || {});
    bindPersonalHistoryFilters(target, matches, userId);
    target.querySelector("[data-admin-analyze-player]")?.addEventListener("click", (event) => {
      const button = event.currentTarget;
      const requestedUserId = button.dataset.userId || String(userId);
      const requestedGuildId = button.dataset.guildId || String(guildId);
      const access = canAnalyzeSearchedPlayer(requestedUserId, requestedGuildId);
      if (!access.ok) {
        window.alert(access.message || "분석 권한이 필요합니다.");
        return;
      }
      const url = new URL(window.location.href);
      url.search = "";
      url.searchParams.set("view", "analysis");
      url.searchParams.set("userId", requestedUserId);
      url.searchParams.set("guildId", requestedGuildId);
      if(button.dataset.riotId)url.searchParams.set("riotId",button.dataset.riotId);
      window.location.assign(`${url.pathname}${url.search}`);
    });
    bindExpanders(target);
    bindReplayDownloads(target);
    target.querySelector("[data-profile-favorite]")?.addEventListener("click", (event) => {
      window.dispatchEvent(new CustomEvent("lucid:favorite-toggle", { detail: { name:p.name || "", userId:String(userId), guildId:String(guildId) } }));
      const nowFavorite = !event.currentTarget.classList.contains("active");
      event.currentTarget.classList.toggle("active", nowFavorite);
      event.currentTarget.textContent = nowFavorite ? "★" : "☆";
    });
    const refreshButton = target.querySelector("[data-profile-refresh]");
    refreshButton?.addEventListener("click", async () => {
      if (refreshButton.disabled) return;
      refreshButton.disabled = true;
      refreshButton.textContent = "갱신 중...";
      try {
        const response = await fetch(`${API_BASE_URL.replace(/\/$/, "")}/api/community/players/${encodeURIComponent(userId)}/public-sync?guildId=${encodeURIComponent(guildId)}`, {method:"POST", credentials:"include"});
        const result = await response.json().catch(() => ({}));
        if (!response.ok || !result.ok) {
          if (result.error === "sync_cooldown") throw new Error(`${result.retryAfter || 0}초 후 다시 갱신할 수 있습니다.`);
          throw new Error(result.message || result.error || "갱신 요청에 실패했습니다.");
        }
        refreshButton.textContent = "갱신 예약됨";
        setTimeout(() => { refreshButton.disabled = false; refreshButton.textContent = "전적 갱신"; }, 3000);
      } catch (error) {
        refreshButton.disabled = false;
        refreshButton.textContent = "전적 갱신";
        window.alert(error.message || "갱신 요청에 실패했습니다.");
      }
    });
  } catch(error) {
    target.innerHTML=`<div class="empty-state"><strong>개인 전적을 불러오지 못했습니다.</strong><span>${escapeHtml(error.message)}</span></div>`;
  }
}

export async function searchPlayers(query,{historyMode="push"}={}) {
  updateUrl({ q: query }, historyMode);
  switchView("search");
  const target=$("searchResults");
  renderLoading(target,2);
  try {
    const data=await apiGet(`/api/community/search?q=${encodeURIComponent(query)}&limit=12`);
    const players=data.players || [];
    if(players.length===1){
      await openPlayer(players[0].userId,players[0].guildId,{historyMode:"replace"});
      return;
    }
    target.innerHTML=`<h1 class="search-title">검색 결과</h1><div class="search-results-block">${players.map(candidate).join("") || `<div class="empty-state"><strong>검색 결과가 없습니다.</strong><span>등록된 본계정 또는 부계정 Riot ID를 확인해주세요.</span></div>`}</div>`;
    target.querySelectorAll(".search-candidate").forEach((b)=>b.addEventListener("click",()=>openPlayer(b.dataset.userId,b.dataset.guildId,{historyMode:"push"})));
  } catch(error) {
    const notConfigured = error.code === "community_guild_not_configured";
    target.innerHTML = notConfigured
      ? `<div class="empty-state"><strong>커뮤니티 전적 연결을 기다리고 있습니다.</strong><span>공개 서버 연결 후 닉네임 검색을 사용할 수 있습니다.</span></div>`
      : `<div class="empty-state"><strong>검색하지 못했습니다.</strong><span>${escapeHtml(error.message)}</span></div>`;
  }
}
