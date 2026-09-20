import { API_BASE_URL } from "./config.js";
import { apiFetch, getAdminHeaders } from "./api.js?v=20260906c";

const apiUrl = (path) => `${API_BASE_URL.replace(/\/$/, "")}${path}`;

async function requestJson(path, init = {}) {
  const response = await apiFetch(apiUrl(path), { credentials: "include", ...init, headers: { ...getAdminHeaders(), ...(init.headers || {}) } });
  const result = await response.json().catch(() => ({}));
  if (!response.ok || !result.ok) {
    const error = new Error(result.error || `HTTP ${response.status}`);
    error.status = response.status;
    throw error;
  }
  return result;
}

export async function fetchCoachCatalog(init) {
  const result = await requestJson("/api/coaches", init);
  return result.coaches || [];
}

export async function fetchCoachAvailability(coachId, range) {
  const query = new URLSearchParams(range || {}).toString();
  const result = await requestJson(`/api/coaches/${encodeURIComponent(coachId)}/availability${query ? `?${query}` : ""}`);
  return result.availability || result.slots || result.items || [];
}

export async function fetchCoachReviews(coachId) {
  const result = await requestJson(`/api/coaches/${encodeURIComponent(coachId)}/reviews`);
  return result.reviews || result.items || [];
}

export const fetchCoachProfile = () => requestJson("/api/coach/profile").then((result) => result.profile || null);

export const fetchCoachLessons = () => requestJson("/api/coach/lessons").then((result) => result.coaches || []);

export const saveCoachProfile = (payload) => requestJson("/api/coach/profile", {
  method: "PATCH",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(payload),
}).then((result) => result.profile || payload);

export const saveCoachLesson = (lesson) => requestJson(`/api/coach/lessons/${encodeURIComponent(lesson.id)}`, {
  method: "PATCH",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(lesson),
}).then((result) => result.lesson || result.coach || lesson);

export const createCoachLesson = (name) => requestJson("/api/coach/lessons", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ name }),
}).then((result) => result.coach);

export const deleteCoachLesson = (id) => requestJson(`/api/coach/lessons/${encodeURIComponent(id)}`, { method: "DELETE" });

export const fetchCoachSchedule = (query) => requestJson(`/api/coach/schedule?${new URLSearchParams(query).toString()}`);

export const saveCoachSchedule = (query, payload) => requestJson(`/api/coach/schedule?${new URLSearchParams(query).toString()}`, {
  method: "PUT",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(payload),
});

export const fetchCoachCalendar = (query) => requestJson(`/api/coach/calendar?${new URLSearchParams(query).toString()}`).then((result) => result.events || []);

export const createCoachCalendarEvent = (payload) => requestJson("/api/coach/calendar", {
  method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload),
}).then((result) => result.event);

export const updateCoachCalendarEvent = (id, payload) => requestJson(`/api/coach/calendar/${encodeURIComponent(id)}`, {
  method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload),
}).then((result) => result.event);

export const deleteCoachCalendarEvent = (id) => requestJson(`/api/coach/calendar/${encodeURIComponent(id)}`, { method: "DELETE" });

export const uploadLegacyImport = (file) => {
  const body = new FormData();
  body.append("file", file);
  return requestJson("/api/admin/legacy-imports", { method: "POST", body });
};

export const fetchLegacyImports = (batchId = "", status = "") => requestJson(`/api/admin/legacy-imports?${new URLSearchParams({ batchId, status }).toString()}`);

export const updateLegacyCandidate = (id, payload) => requestJson(`/api/admin/legacy-imports/candidates/${encodeURIComponent(id)}`, {
  method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload),
});

export const bulkUpdateLegacyCandidates = (batchId, payload) => requestJson(`/api/admin/legacy-imports/${encodeURIComponent(batchId)}/candidates/bulk`, {
  method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload),
});

export const approveSafeLegacyCandidates = (batchId) => requestJson(`/api/admin/legacy-imports/${encodeURIComponent(batchId)}/approve-safe`, { method: "POST" });

export const previewLegacyImport = (batchId, scope = "") => requestJson(`/api/admin/legacy-imports/${encodeURIComponent(batchId)}/preview?${new URLSearchParams({ scope }).toString()}`);

export const applyLegacyImport = (batchId) => requestJson(`/api/admin/legacy-imports/${encodeURIComponent(batchId)}/apply`, {
  method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ confirmBatchId: batchId }),
});

export const rollbackLegacyImport = (batchId) => requestJson(`/api/admin/legacy-imports/${encodeURIComponent(batchId)}/rollback`, {
  method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ confirmBatchId: batchId }),
});
