import { ADMIN_TOKEN_KEY } from "./config.js";

export function apiFetch(input, init) {
  return globalThis.fetch(input, init);
}

export function getAdminHeaders(includeJson = false) {
  const adminToken = globalThis.sessionStorage?.getItem(ADMIN_TOKEN_KEY);
  return {
    ...(includeJson ? { "Content-Type": "application/json" } : {}),
    ...(adminToken ? { Authorization: `Bearer ${adminToken}` } : {}),
  };
}
