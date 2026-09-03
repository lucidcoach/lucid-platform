import { API_BASE_URL } from "./config.js?v=20260904d";

const apiUrl = (path) => `${API_BASE_URL.replace(/\/$/, "")}${path}`;

export async function apiGet(path) {
  const response = await fetch(apiUrl(path), { credentials: "include" });
  const data = await response.json().catch(() => ({}));
  if (!response.ok || !data.ok) {
    const publicMessages = {
      community_guild_not_configured: "커뮤니티 공개 서버가 아직 연결되지 않았습니다.",
      player_not_found: "해당 닉네임의 내전 기록을 찾지 못했습니다.",
      match_not_found: "해당 내전 기록을 찾지 못했습니다.",
    };
    const code = data.error || "";
    const error = new Error(publicMessages[code] || data.message || code || `HTTP ${response.status}`);
    error.status = response.status;
    error.code = code;
    throw error;
  }
  return data;
}
