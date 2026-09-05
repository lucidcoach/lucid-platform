import { API_BASE_URL } from "./config.js";
import { apiFetch } from "./api.js";

export function userRoles(user) {
  const roles = Array.isArray(user?.roles)
    ? user.roles
    : String(user?.roles || "").split(/[\s,]+/).filter(Boolean);
  return new Set([...(user?.role ? [user.role] : []), ...roles.map((role) => String(role).toLowerCase())]);
}

export function userIsAdmin(user) {
  const roles = userRoles(user);
  return Boolean(user?.isAdmin || user?.is_admin || roles.has("admin") || roles.has("관리자"));
}

export function userIsCoach(user) {
  const roles = userRoles(user);
  return Boolean(user?.isCoach || user?.is_coach || user?.coachKey || user?.coach_key || roles.has("coach") || roles.has("코치"));
}

export async function fetchCurrentUser() {
  const response = await apiFetch(`${API_BASE_URL.replace(/\/$/, "")}/api/auth/me`, {
    method: "GET",
    credentials: "include",
  });
  const result = await response.json().catch(() => ({}));
  return response.ok && result.ok ? result.user : null;
}

async function requestAuth(path, payload) {
  const response = await apiFetch(`${API_BASE_URL.replace(/\/$/, "")}${path}`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const result = await response.json().catch(() => ({}));
  if (!response.ok || !result.ok || !result.user) throw new Error(result.error || `HTTP ${response.status}`);
  return result.user;
}

export const signupUser = (payload) => requestAuth("/api/auth/signup", payload);
export const loginUser = (payload) => requestAuth("/api/auth/login", payload);

export async function updateCurrentUser(payload) {
  const response = await apiFetch(`${API_BASE_URL.replace(/\/$/, "")}/api/auth/me`, {
    method: "PATCH",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const result = await response.json().catch(() => ({}));
  if (!response.ok || !result.ok || !result.user) {
    const error = new Error(result.error || `HTTP ${response.status}`);
    error.retryAt = result.retryAt || result.retry_at || "";
    throw error;
  }
  return result.user;
}

export async function updateRiotAccounts(accounts) {
  const response = await apiFetch(`${API_BASE_URL.replace(/\/$/, "")}/api/auth/riot-accounts`, {
    method: "PUT",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ accounts }),
  });
  const result = await response.json().catch(() => ({}));
  if (!response.ok || !result.ok || !result.user) throw new Error(result.error || `HTTP ${response.status}`);
  return result.user;
}

export async function deleteCurrentUser() {
  const response = await apiFetch(`${API_BASE_URL.replace(/\/$/, "")}/api/auth/me`, { method: "DELETE", credentials: "include" });
  const result = await response.json().catch(() => ({}));
  if (!response.ok || !result.ok) throw new Error(result.error || `HTTP ${response.status}`);
}

async function requestAccountAction(path, payload, method = "POST") {
  const response = await apiFetch(`${API_BASE_URL.replace(/\/$/, "")}${path}`, {
    method,
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const result = await response.json().catch(() => ({}));
  if (!response.ok || !result.ok) throw new Error(result.error || `HTTP ${response.status}`);
  return result;
}

export const requestPasswordReset = (email) => requestAccountAction("/api/auth/password/forgot", { email });
export const resetPassword = (token, password) => requestAccountAction("/api/auth/password/reset", { token, password });
export const updateAccountPassword = (currentPassword, password) => requestAccountAction(
  "/api/account/password",
  { currentPassword, password },
  "PATCH",
);

export async function fetchAccountOverview() {
  const response = await apiFetch(`${API_BASE_URL.replace(/\/$/, "")}/api/account/overview`, {
    method: "GET",
    credentials: "include",
  });
  const result = await response.json().catch(() => ({}));
  if (!response.ok || !result.ok) throw new Error(result.error || `HTTP ${response.status}`);
  return result;
}

export async function updatePayoutProfile(payload) {
  const result = await requestAccountAction("/api/account/payout", payload, "PATCH");
  return result.payout;
}

export function logoutAuthSessions() {
  return Promise.allSettled(["auth", "admin"].map((scope) => apiFetch(`${API_BASE_URL.replace(/\/$/, "")}/api/${scope}/logout`, {
    method: "POST",
    credentials: "include",
  })));
}
