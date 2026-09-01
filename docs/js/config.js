const runtimeConfig = globalThis.LUCID_COACH_CONFIG || {};

export const API_BASE_URL = String(
  runtimeConfig.apiBaseUrl || "https://lucid-chzzk-auth-yhfg.onrender.com",
).replace(/\/$/, "");
export const ADMIN_TOKEN_KEY = "coach-admin-token";
export const THEME_KEY = "coach-theme";
export const EMAIL_MAX_LENGTH = 254;
export const PASSWORD_MIN_LENGTH = 8;
export const PASSWORD_MAX_LENGTH = 128;
export const RESERVATION_STATUSES = ["신규", "결제대기", "코치확정대기", "상담중", "예약확정", "완료", "취소"];
export const COACH_API_TIMEOUT_MS = 60000;
