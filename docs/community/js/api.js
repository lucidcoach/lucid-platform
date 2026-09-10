import { API_BASE_URL } from "./config.js?v=20260904d";

const apiUrl = (path) => `${API_BASE_URL.replace(/\/$/, "")}${path}`;

async function apiRequest(path, options = {}) {
  const response = await fetch(apiUrl(path), { credentials: "include", ...options });
  const data = await response.json().catch(() => ({}));
  if (!response.ok || !data.ok) {
    const publicMessages = {
      community_guild_not_configured: "커뮤니티 공개 서버가 아직 연결되지 않았습니다.",
      player_not_found: "해당 닉네임의 내전 기록을 찾지 못했습니다.",
      match_not_found: "해당 내전 기록을 찾지 못했습니다.",
      discord_link_required: "Discord 연동 후 본인이 등록한 계정만 분석할 수 있습니다.",
      analysis_forbidden: "본인이 등록한 계정만 볼 수 있습니다. 다른 회원 분석은 관리자 권한이 필요합니다.",
      admin_required: "랭킹 관리 권한이 필요합니다.",
      ranking_refresh_cooldown: "잠시 후 다시 갱신해주세요.",
      ranking_refresh_failed: "랭킹 갱신에 실패했습니다.",
    };
    const code = data.error || "";
    const error = new Error(publicMessages[code] || data.message || code || `HTTP ${response.status}`);
    error.status = response.status;
    error.code = code;
    throw error;
  }
  return data;
}

export function apiGet(path) { return apiRequest(path); }
export function apiPost(path) { return apiRequest(path, { method: "POST" }); }
