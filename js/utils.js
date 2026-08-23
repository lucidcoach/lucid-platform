export function byId(id) {
  return document.getElementById(id);
}

export function parseReservationPrice(value) {
  const textValue = String(value || "");
  const amount = Number((textValue.match(/[\d,]+/)?.[0] || "").replace(/,/g, "")) || 0;
  const unitMatch = textValue.match(/(\d+(?:\.\d+)?)\s*(시간|hour|hours|게임)/i);
  const unit = unitMatch?.[2] || "";
  const units = Number(unitMatch?.[1] || 1) || 1;
  return { amount, hours: /시간|hour/i.test(unit) ? units : 0 };
}

export function formatWon(value) {
  return `${Math.round(Number(value) || 0).toLocaleString("ko-KR")}원`;
}

export function formatDateTime(value) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("ko-KR", { dateStyle: "short", timeStyle: "short" });
}

export function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

export function localDateOnly(value) {
  const date = value instanceof Date ? new Date(value) : new Date(`${String(value || "").slice(0, 10)}T00:00:00`);
  return Number.isNaN(date.getTime()) ? new Date() : date;
}

export function isoDateOnly(value) {
  const date = localDateOnly(value);
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
}

export function addLocalDays(value, count) {
  const date = localDateOnly(value);
  date.setDate(date.getDate() + count);
  return date;
}

export function getIsoWeekday(value) {
  const day = localDateOnly(value).getDay();
  return day === 0 ? 7 : day;
}

export function splitCsv(value) {
  return value.split(",").map((item) => item.trim()).filter(Boolean);
}
