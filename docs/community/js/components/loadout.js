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

function minuteLabel(value) {
  const seconds = Number(value || 0);
  if (!Number.isFinite(seconds) || seconds <= 0) return "";
  const minute = Math.floor(seconds / 60);
  const second = Math.floor(seconds % 60);
  return second ? `${minute}:${String(second).padStart(2,"0")}` : `${minute}분`;
}

function itemTimeline(player) {
  const rows = Array.isArray(player?.itemTimeline) ? player.itemTimeline : [];
  if (rows.length) {
    return `<div class="item-build-track timeline-mode">${rows.map((row) => {
      const itemId = Number(row?.item || row?.itemId || 0);
      const action = String(row?.action || "BUY").toUpperCase();
      const time = minuteLabel(row?.time ?? row?.timestamp);
      const actionLabel = action === "SELL" ? "판매" : action === "UNDO" ? "되돌림" : "";
      return `<div class="item-build-step ${action.toLowerCase()}">
        <div class="item-build-icon">${itemId > 0 ? image(itemIcon(itemId), `아이템 ${itemId}`) : ""}</div>
        <span>${time || "-"}</span>
        ${actionLabel ? `<small>${actionLabel}</small>` : ""}
      </div>`;
    }).join(`<i class="build-arrow" aria-hidden="true">›</i>`)}</div>`;
  }

  const items = Array.isArray(player?.items) ? player.items.filter((id) => Number(id) > 0) : [];
  if (!items.length) {
    return `<div class="build-empty-line">저장된 아이템 정보가 없습니다.</div>`;
  }
  return `<div class="final-build-row">
    <span class="build-sub-label">최종 빌드</span>
    <div class="item-build-track final-mode">${items.map((id) =>
      `<div class="item-build-step"><div class="item-build-icon">${image(itemIcon(id), `아이템 ${id}`)}</div></div>`
    ).join(`<i class="build-arrow" aria-hidden="true">›</i>`)}</div>
  </div>`;
}

function skillBuild(player) {
  const rows = Array.isArray(player?.skillBuild) ? player.skillBuild : [];
  if (!rows.length) {
    return `<div class="build-empty-line">
      스킬 순서 데이터가 저장되지 않은 경기입니다.
    </div>`;
  }

  const clean = rows
    .map((row) => ({
      level: Number(row?.level || 0),
      skill: String(row?.skill || "").toUpperCase(),
    }))
    .filter((row) => row.level > 0 && ["Q","W","E","R"].includes(row.skill))
    .sort((a,b) => a.level - b.level);

  if (!clean.length) {
    return `<div class="build-empty-line">스킬 순서 데이터가 없습니다.</div>`;
  }

  const skills = ["Q","W","E","R"];
  const maxLevel = Math.max(18, ...clean.map((row) => row.level));
  const byLevel = new Map();
  for (const row of clean) {
    const picked = byLevel.get(row.level) || new Set();
    picked.add(row.skill);
    byLevel.set(row.level, picked);
  }

  return `<div class="skill-build-wrap">
    <div class="skill-sequence">${clean.slice(0,18).map((row) =>
      `<span class="skill-seq-chip skill-${row.skill.toLowerCase()}"><b>${row.skill}</b><small>Lv.${row.level}</small></span>`
    ).join(`<i>›</i>`)}</div>
    <div class="skill-grid" style="--skill-cols:${maxLevel}">
      ${skills.map((skill) => `<div class="skill-grid-row">
        <strong>${skill}</strong>
        ${Array.from({length:maxLevel},(_,index)=>{
          const level=index+1;
          const picked=byLevel.get(level);
          const isPicked=Boolean(picked?.has(skill));
          return `<span class="${isPicked ? `picked skill-${skill.toLowerCase()}` : ""}">${isPicked ? level : ""}</span>`;
        }).join("")}
      </div>`).join("")}
    </div>
  </div>`;
}

export function renderBuildSummary(player) {
  return `<div class="match-analysis-panel">
    <section class="analysis-build-section">
      <div class="analysis-build-title">아이템 빌드</div>
      ${itemTimeline(player)}
    </section>
    <section class="analysis-build-section">
      <div class="analysis-build-title">스킬 빌드</div>
      ${skillBuild(player)}
    </section>
  </div>`;
}

export const renderLoadout = renderItems;
