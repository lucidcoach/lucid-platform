export const $ = (id) => document.getElementById(id);

export function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>'"]/g, (ch) => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"}[ch]));
}

export function formatDuration(seconds) {
  const value = Number(seconds || 0);
  if (!value) return "";
  const min = Math.floor(value / 60);
  const sec = Math.floor(value % 60);
  return `${min}:${String(sec).padStart(2,"0")}`;
}

export function relativeTime(text) {
  const raw = String(text || "");
  const normalized = raw.replace(" ", "T") + (raw.includes("+") ? "" : "+09:00");
  const time = new Date(normalized).getTime();
  if (!Number.isFinite(time)) return raw;
  const diff = Math.max(0, Date.now() - time);
  const min = Math.floor(diff / 60000);
  if (min < 1) return "방금 전";
  if (min < 60) return `${min}분 전`;
  const hour = Math.floor(min / 60);
  if (hour < 24) return `${hour}시간 전`;
  const day = Math.floor(hour / 24);
  if (day < 7) return `${day}일 전`;
  return raw.slice(0,10);
}

export function matchCategory(match) {
  const mode = String(match?.mode || "classic").toLowerCase();
  const queue = String(match?.queue || "").toLowerCase();
  if (mode.includes("aram") || queue.includes("aram")) return "aram";
  if (mode.includes("league") || queue.includes("league")) return "league";
  return "scrim";
}

export function normalizeMode(match) {
  const category = matchCategory(match);
  if (category === "aram") return "칼바람";
  if (category === "league") return "리그전";
  return "내전";
}

export const teamLabel = (team) => team === "blue" ? "블루팀" : "레드팀";

export function normalizeRoleKey(value = "") {
  const raw = String(value || "").trim().toUpperCase().replace(/[\s_-]+/g, "");
  const aliases = {
    "탑":"탑", TOP:"탑", TOPLANE:"탑",
    "정글":"정글", JUNGLE:"정글", JG:"정글",
    "미드":"미드", MID:"미드", MIDDLE:"미드", MIDLANE:"미드",
    "원딜":"원딜", ADC:"원딜", BOTTOM:"원딜", BOT:"원딜", CARRY:"원딜",
    "서폿":"서폿", SUPPORT:"서폿", SUP:"서폿", UTILITY:"서폿",
  };
  return aliases[raw] || String(value || "").trim();
}

export function tierClass(value = "") {
  const raw = String(value || "").trim().toUpperCase();
  const compact = raw.replace(/[\s_-]+/g, "");
  if (!raw || ["-","미배치","언랭","UNRANKED","UNPLACED"].includes(compact)) return "tier-unranked";
  if (compact.startsWith("CHALLENGER") || compact.startsWith("C")) return "tier-challenger";
  if (compact.startsWith("GRANDMASTER") || compact.startsWith("GM")) return "tier-grandmaster";
  if (compact.startsWith("MASTER") || (compact.startsWith("M") && !compact.startsWith("MASTER"))) return "tier-master";
  if (compact.startsWith("DIAMOND") || compact.startsWith("D")) return "tier-diamond";
  if (compact.startsWith("EMERALD") || compact.startsWith("E")) return "tier-emerald";
  if (compact.startsWith("PLATINUM") || compact.startsWith("P")) return "tier-platinum";
  if (compact.startsWith("GOLD") || compact.startsWith("G")) return "tier-gold";
  if (compact.startsWith("SILVER") || compact.startsWith("S")) return "tier-silver";
  if (compact.startsWith("BRONZE") || compact.startsWith("B")) return "tier-bronze";
  if (compact.startsWith("IRON") || compact.startsWith("I")) return "tier-iron";
  return "tier-unranked";
}

export function tierLeaguePoints(tier = "", rawScore = 0) {
  const score = Math.max(0, Math.round(Number(rawScore || 0)));
  const compact = String(tier || "").trim().toUpperCase().replace(/[\s_-]+/g, "");
  if (!score) return 0;
  if (["C", "GM", "M"].some((key) => compact === key) || /^(CHALLENGER|GRANDMASTER|MASTER)/.test(compact)) {
    return Math.max(0, score - 2800);
  }
  const division = Number((compact.match(/([1-4])$/) || [])[1] || 4);
  const majorBase = compact.startsWith("DIAMOND") || compact.startsWith("D") ? 2400
    : compact.startsWith("EMERALD") || compact.startsWith("E") ? 2000
    : compact.startsWith("PLATINUM") || compact.startsWith("P") ? 1600
    : compact.startsWith("GOLD") || compact.startsWith("G") ? 1200
    : compact.startsWith("SILVER") || compact.startsWith("S") ? 800
    : compact.startsWith("BRONZE") || compact.startsWith("B") ? 400
    : 0;
  return Math.max(0, score - (majorBase + (4 - Math.max(1, Math.min(4, division))) * 100));
}

export function winRateClass(value) {
  const n = Number(value || 0);
  if (!Number.isFinite(n) || n < 50) return "winrate-low";
  if (n < 55) return "winrate-blue";
  return "winrate-red";
}

export function kdaClass(value) {
  const n = Number(value || 0);
  if (!Number.isFinite(n) || n < 2) return "kda-low";
  if (n < 3) return "kda-green";
  if (n < 4) return "kda-blue";
  return "kda-red";
}

export function isWinner(match, team) {
  const side = String(team || "").toLowerCase();
  const rawWinner = String(match?.winner ?? match?.winnerSide ?? match?.winningTeam ?? "").trim().toLowerCase();
  if (rawWinner.includes("blue") || rawWinner.includes("블루")) return side === "blue";
  if (rawWinner.includes("red") || rawWinner.includes("레드")) return side === "red";

  const sidePlayers = (match?.players || []).filter((player) => String(player?.team || "").toLowerCase() === side);
  const wins = sidePlayers.filter((player) => String(player?.result || "").toLowerCase() === "win").length;
  const losses = sidePlayers.filter((player) => String(player?.result || "").toLowerCase() === "loss").length;
  if (wins || losses) return wins > losses;
  return false;
}

export const focusKda = (player) => player ? `${player.kills || 0} / ${player.deaths || 0} / ${player.assists || 0}` : "-";
export const scoreClass = (score) => Number(score || 0) < 45 ? "low" : (Number(score || 0) < 58 ? "mid" : "");
