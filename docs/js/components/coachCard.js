import { purposes } from "../catalog.js";
import { escapeHtml } from "../utils.js";

export function getCoachBadges(coach) {
  if (coach.tier === "엠버서더") return ["추천", "엠버서더"];
  if (coach.tier === "최우수") return ["추천", "최우수"];
  if (coach.tier === "우수") return ["추천", "우수"];
  return coach.badges || [];
}

export function renderBadge(label) {
  const className = label === "추천" ? "badge recommend" : ["최우수", "엠버서더"].includes(label) ? "badge best" : "badge good";
  return `<span class="${className}">${escapeHtml(label)}</span>`;
}

export function getTierClass(coach) {
  if (["최우수", "엠버서더"].includes(coach.tier)) return "tier-best";
  if (coach.tier === "우수") return "tier-good";
  return "tier-normal";
}

export function getImageStyle(coach) {
  return `object-position: ${coach.imagePosition || "center center"};`;
}

export function getFeaturedImage(coach) {
  return coach.featuredImage || coach.bannerImage || coach.heroImage || coach.image || "assets/logo.jpg";
}

export function getDetailImage(coach) {
  return coach.detailImage || coach.bannerImage || coach.heroImage || coach.featuredImage || coach.image || "assets/logo.jpg";
}

export function getWideImageStyle(coach, positionKey) {
  return `object-position: ${coach[positionKey] || coach.bannerImagePosition || "center center"};`;
}

export function getCoachPurposes(coach) {
  const raw = Array.isArray(coach?.purpose) ? coach.purpose : String(coach?.purpose || "").split(",");
  return raw.map((item) => String(item).trim()).filter(Boolean);
}

export function getPurposeLabels(value) {
  const ids = Array.isArray(value) ? value : String(value || "").split(",");
  const labels = ids
    .map((id) => purposes.find((purpose) => purpose.id === String(id).trim())?.label || String(id).trim())
    .filter(Boolean);
  return labels.length ? labels : ["분류 미지정"];
}
