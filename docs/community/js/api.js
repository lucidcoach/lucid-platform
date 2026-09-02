import { API_BASE_URL } from "./config.js";

const apiUrl = (path) => `${API_BASE_URL.replace(/\/$/, "")}${path}`;

export async function apiGet(path) {
  const response = await fetch(apiUrl(path), { credentials: "include" });
  const data = await response.json().catch(() => ({}));
  if (!response.ok || !data.ok) {
    const error = new Error(data.message || data.error || `HTTP ${response.status}`);
    error.status = response.status;
    throw error;
  }
  return data;
}
