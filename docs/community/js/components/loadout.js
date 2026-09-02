import { itemIcon, perkIcon, spellIcon } from "../assets.js";
import { escapeHtml } from "../utils.js";

function image(src, alt = "", className = "") {
  return src ? `<img class="${className}" src="${escapeHtml(src)}" alt="${escapeHtml(alt)}" loading="lazy">` : `<span class="loadout-placeholder ${className}" aria-hidden="true"></span>`;
}

export function renderItems(player, max = 7) {
  const items = Array.isArray(player?.items) ? player.items.slice(0,max) : [];
  if (!items.length) return `<span class="numeric">-</span>`;
  return `<div class="loadout">${items.map((id) => image(itemIcon(id), `아이템 ${id}`)).join("")}</div>`;
}

export function renderRuneSpells(player) {
  const spells = Array.isArray(player?.spells) ? player.spells.slice(0,2) : [];
  const keystone = Array.isArray(player?.perks) ? player.perks.find((id) => perkIcon(id)) : null;
  if (!spells.length && !keystone) return `<div class="rune-spells muted-loadout">-</div>`;
  return `<div class="rune-spells">${keystone ? image(perkIcon(keystone), `룬 ${keystone}`, "rune-icon") : ""}${spells.map((id) => image(spellIcon(id), `소환사 주문 ${id}`, "spell-icon")).join("")}</div>`;
}

export const renderLoadout = renderItems;
