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

export function normalizeMode(match) {
  const mode = String(match?.mode || "classic").toLowerCase();
  if (mode.includes("low")) return "저티어 내전";
  if (mode.includes("aram")) return "칼바람 내전";
  if (mode.includes("league")) return "리그전";
  return "자유랭크";
}

export const teamLabel = (team) => team === "blue" ? "블루팀" : "레드팀";
export const isWinner = (match, team) => String(match?.winner || "").toLowerCase().includes(team);
export const focusKda = (player) => player ? `${player.kills || 0} / ${player.deaths || 0} / ${player.assists || 0}` : "-";
export const scoreClass = (score) => Number(score || 0) < 45 ? "low" : (Number(score || 0) < 58 ? "mid" : "");
