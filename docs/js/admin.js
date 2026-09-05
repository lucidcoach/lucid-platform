import { API_BASE_URL } from "./config.js";
import { apiFetch, getAdminHeaders } from "./api.js";

const apiUrl = (path) => `${API_BASE_URL.replace(/\/$/, "")}${path}`;

async function requestJson(path, init = {}) {
  const response = await apiFetch(apiUrl(path), { credentials: "include", ...init });
  const result = await response.json().catch(() => ({}));
  if (!response.ok || !result.ok) {
    const error = new Error(result.error || `HTTP ${response.status}`);
    error.status = response.status;
    throw error;
  }
  return result;
}

export async function loginAdmin(password) {
  return requestJson("/api/admin/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ password }),
  });
}

export function normalizeAdminCoachSetting(item = {}, coaches = []) {
  const coachKey = String(item.coachKey || item.coach_key || "").trim();
  const publicLessons = coaches.filter((coach) => String(coach.coachKey || coach.coach_key || coach.id || "") === coachKey);
  const first = publicLessons[0] || {};
  const rate = Number(item.commissionRate ?? item.commission_rate ?? 0);
  return {
    coachKey,
    name: String(item.name || item.coachProfileName || item.coach_name || first.coachProfileName || first.name || coachKey || "이름 없음"),
    lessonCount: Number(item.lessonCount ?? item.lesson_count ?? publicLessons.length ?? 0),
    badges: Array.isArray(item.badges) ? item.badges.filter(Boolean) : [],
    commissionRate: Number.isFinite(rate) ? rate : 0,
    saleType: String(item.saleType || item.sale_type || "brokerage"),
    adminNote: String(item.adminNote ?? item.admin_note ?? ""),
  };
}

export async function fetchAdminSettlements(status = "") {
  const query = status ? `?status=${encodeURIComponent(status)}` : "";
  return requestJson(`/api/admin/settlements${query}`, { headers: getAdminHeaders() });
}

export async function updateAdminSettlement(id, status, note = "") {
  return requestJson(`/api/admin/settlements/${encodeURIComponent(id)}`, {
    method: "PATCH", headers: getAdminHeaders(true), body: JSON.stringify({ status, note }),
  });
}

export function reconcileAdminPayment(orderId) {
  return requestJson(`/api/admin/payments/${encodeURIComponent(orderId)}/reconcile`, { method: "POST", headers: getAdminHeaders(true) });
}

export async function fetchAdminCoachSettings(coaches = []) {
  const result = await requestJson("/api/admin/coach-settings", { headers: getAdminHeaders() });
  return (result.coaches || []).map((item) => normalizeAdminCoachSetting(item, coaches)).filter((item) => item.coachKey);
}

export async function saveAdminCoachSettings(coachKey, payload, coaches = []) {
  const result = await requestJson(`/api/admin/coach-settings/${encodeURIComponent(coachKey)}`, {
    method: "PATCH",
    headers: getAdminHeaders(true),
    body: JSON.stringify(payload),
  });
  return normalizeAdminCoachSetting(result.coach || { coachKey, ...payload }, coaches);
}

export async function saveCoachToApi(coach, sortOrder) {
  const result = await requestJson(`/api/coaches/${encodeURIComponent(coach.id)}`, {
    method: "PATCH",
    headers: getAdminHeaders(true),
    body: JSON.stringify({ ...coach, sortOrder }),
  });
  return result.coach || coach;
}

export async function deleteCoachFromApi(id) {
  await requestJson(`/api/coaches/${encodeURIComponent(id)}`, {
    method: "DELETE",
    headers: getAdminHeaders(),
  });
}

export function resetCoachesInApi(coaches) {
  return requestJson("/api/coaches/reset", {
    method: "POST",
    headers: getAdminHeaders(true),
    body: JSON.stringify({ coaches }),
  });
}

export async function fetchUsers() {
  const result = await requestJson("/api/users", { headers: getAdminHeaders() });
  return result.users || [];
}

export async function updateUserRole(id, payload) {
  const result = await requestJson(`/api/users/${encodeURIComponent(id)}`, {
    method: "PATCH",
    headers: getAdminHeaders(true),
    body: JSON.stringify(payload),
  });
  return result.user;
}

export async function createCoachRequest(payload) {
  const result = await requestJson("/api/coach-requests", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return result.request;
}

export async function fetchCoachRequests() {
  const result = await requestJson("/api/coach-requests", { headers: getAdminHeaders() });
  return result.requests || [];
}

export function decideCoachRequest(id, action) {
  return requestJson(`/api/coach-requests/${encodeURIComponent(id)}/${action}`, {
    method: "POST",
    headers: getAdminHeaders(true),
    body: JSON.stringify({}),
  });
}
