import { itemIcon, perkIcon, spellIcon } from "../assets.js";
import { escapeHtml } from "../utils.js";

function image(src, alt = "", className = "") {
  return src ? `<img class="${className}" src="${escapeHtml(src)}" alt="${escapeHtml(alt)}" loading="lazy">` : "";
}

export function renderItems(player, max = 7) {
  const items = Array.isArray(player?.items) ? player.items.slice(0,max) : [];
  if (!items.length) return "";
  return `<div class="loadout">${items.map((id) => image(itemIcon(id), `아이템 ${id}`)).join("")}</div>`;
}

export function renderSpells(player) {
  const spells = Array.isArray(player?.spells) ? player.spells.slice(0,2) : [];
  return spells.length ? `<div class="spell-list">${spells.map((id) => image(spellIcon(id), `소환사 주문 ${id}`, "spell-icon")).join("")}</div>` : "";
}

export function renderKeystone(player) {
  const perks = Array.isArray(player?.perks) ? player.perks : [];
  const keystone = perks.find((id) => perkIcon(id));
  return keystone ? image(perkIcon(keystone), `핵심 룬 ${keystone}`, "rune-icon") : "";
}

export function renderRunes(player) {
  const perks = Array.isArray(player?.perks) ? player.perks : [];
  const icons = perks.map((id) => image(perkIcon(id), `룬 ${id}`, "rune-icon")).filter(Boolean);
  return icons.length ? `<div class="rune-list">${icons.join("")}</div>` : "";
}

export function renderRuneSpells(player) {
  const keystone = renderKeystone(player);
  const spells = renderSpells(player);
  if (!keystone && !spells) return "";
  return `<div class="rune-spells">${keystone}${spells}</div>`;
}

export function renderBuildSummary(player) {
  const level = Number(player?.level || 0);
  return `<div class="build-detail-grid">
    <div><span>최종 레벨</span><strong>${level > 0 ? level : "-"}</strong></div>
    <div><span>소환사 주문</span>${renderSpells(player) || `<small>기록 없음</small>`}</div>
    <div><span>룬</span>${renderRunes(player) || `<small>기록 없음</small>`}</div>
    <div class="build-items-row"><span>최종 아이템</span>${renderItems(player,7) || `<small>기록 없음</small>`}</div>
  </div>`;
}

export const renderLoadout = renderItems;
