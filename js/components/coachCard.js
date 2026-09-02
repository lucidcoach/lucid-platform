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

export function getOriginalPrice(price) {
  const amount = Number(String(price || "").replace(/[^\d]/g, ""));
  if (!amount) return "";
  return `${Math.round(amount * 1.7).toLocaleString("ko-KR")}원`;
}

export function renderFeaturedCard(coach) {
  const originalPrice = getOriginalPrice(coach.price);
  const featuredImage = getFeaturedImage(coach);
  const purposeText = getPurposeLabels(coach.purpose).slice(0, 2).join(" · ");
  return `
    <article class="featured-card ${getTierClass(coach)}" data-coach-id="${escapeHtml(coach.id)}">
      <div class="featured-image">
        <img src="${escapeHtml(featuredImage)}" alt="" style="${escapeHtml(getWideImageStyle(coach, "featuredImagePosition"))}">
        <span class="ad-label">추천</span>
        <span class="tier-ribbon">${escapeHtml(coach.tier)}</span>
      </div>
      <div class="featured-body">
        <h3>${escapeHtml(coach.name)}</h3>
        <p class="coach-owner">${escapeHtml(coach.coachProfileName || coach.name)}</p>
        <p class="purpose-label">${escapeHtml(purposeText)}</p>
        <p class="featured-summary">${escapeHtml(coach.tagline)}</p>
        <div class="featured-rating">★ ${coach.rating.toFixed(1)} <span>(${coach.lessons || 0})</span></div>
        <div class="featured-price">
          <strong>${escapeHtml(coach.price)}</strong>
          ${originalPrice ? `<del>${escapeHtml(originalPrice)}</del>` : ""}
        </div>
        <button class="detail-link" type="button" data-detail-id="${escapeHtml(coach.id)}">상세보기</button>
      </div>
    </article>
  `;
}

export function renderCoachCard(coach, selectedCoachId) {
  const badges = getCoachBadges(coach);
  const imageStyle = getImageStyle(coach);
  const purposeText = getPurposeLabels(coach.purpose).slice(0, 2).join(" · ");
  return `
    <article class="coach-card ${coach.id === selectedCoachId ? "active" : ""} ${getTierClass(coach)}" data-coach-id="${escapeHtml(coach.id)}">
      <div class="avatar-frame"><img class="avatar" src="${escapeHtml(coach.image)}" alt="" style="${escapeHtml(imageStyle)}"></div>
      <div class="coach-main">
        ${badges.length ? `<div class="rank-badges">${badges.map(renderBadge).join("")}</div>` : ""}
        <h3>${escapeHtml(coach.name)}</h3>
        <span class="coach-owner">${escapeHtml(coach.coachProfileName || coach.name)}</span>
        <span class="purpose-label">${escapeHtml(purposeText)}</span>
        <p>${escapeHtml(coach.tagline)}</p>
        <div class="chips">${(coach.roles || []).map((role) => `<span class="chip">${escapeHtml(role)}</span>`).join("")}</div>
      </div>
      <div class="card-foot">
        <span>★ ${coach.rating.toFixed(1)} · 후기 ${coach.reviews?.length || 0}</span>
        <span class="price">${escapeHtml(coach.price)}</span>
      </div>
      <button class="detail-link card-detail-link" type="button" data-detail-id="${escapeHtml(coach.id)}">상세보기</button>
    </article>
  `;
}
