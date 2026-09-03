import { itemIcon, perkIcon, perkStyleIcon, perkTreeInfo, spellIcon } from "../assets.js?v=20260904f";
import { escapeHtml } from "../utils.js?v=20260904f";

function image(src, alt = "", className = "") {
  return src ? `<img class="${className}" src="${escapeHtml(src)}" alt="${escapeHtml(alt)}" loading="lazy">` : "";
}

function numericList(...values) {
  for (const value of values) {
    if (Array.isArray(value)) {
      const rows = value.map((item) => Number(item?.id ?? item)).filter((item) => Number.isFinite(item) && item > 0);
      if (rows.length) return rows;
    }
  }
  return [];
}

function spellIds(player) {
  const stats = player?.stats || {};
  const direct = numericList(player?.spells, player?.summonerSpells);
  if (direct.length) return direct.slice(0,2);
  return [
    player?.spell1 ?? player?.summonerSpell1 ?? stats.SUMMON_SPELL1 ?? stats.SUMMON_SPELL_1 ?? stats.SUMMONER_SPELL1 ?? stats.SPELL1 ?? stats.SPELL1_ID,
    player?.spell2 ?? player?.summonerSpell2 ?? stats.SUMMON_SPELL2 ?? stats.SUMMON_SPELL_2 ?? stats.SUMMONER_SPELL2 ?? stats.SPELL2 ?? stats.SPELL2_ID,
  ].map(Number).filter((item) => Number.isFinite(item) && item > 0).slice(0,2);
}

function perkIds(player) {
  const stats = player?.stats || {};
  const direct = numericList(player?.perks, player?.runes);
  if (direct.length) return direct;
  return [0,1,2,3,4,5].map((index) => Number(stats[`PERK${index}`] ?? player?.[`perk${index}`] ?? 0)).filter((item) => item > 0);
}

function secondaryStyleId(player) {
  const stats = player?.stats || {};
  const directCandidates = [
    player?.subStyle,
    player?.secondaryStyle,
    player?.subPerkStyle,
    player?.perkSubStyle,
    player?.subRuneStyle,
    player?.secondaryRuneStyle,
    stats.PERK_SUB_STYLE,
    stats.PERK_SUBSTYLE,
    stats.SUB_STYLE,
    stats.SUBSTYLE,
    stats.PERK_STYLE_SUB,
    stats.PERK_SECONDARY_STYLE,
  ].map(Number).filter((value) => Number.isFinite(value) && value > 0);
  if (directCandidates.length) return directCandidates[0];

  const perks = perkIds(player).filter((id) => perkIcon(id));
  if (!perks.length) return 0;
  const primaryTree = perkTreeInfo(perks[0])?.treeId || 0;
  const secondaryPerk = perks.find((id) => {
    const treeId = perkTreeInfo(id)?.treeId || 0;
    return treeId > 0 && treeId !== primaryTree;
  });
  return perkTreeInfo(secondaryPerk)?.treeId || 0;
}


const TRINKET_ITEM_IDS = new Set([3330, 3340, 3348, 3363, 3364, 3513]);

function questItemId(player, normalItems = []) {
  const stats = player?.stats || {};
  const direct = [
    player?.questItem, player?.questItemId, player?.roleQuestItem, player?.roleQuestItemId,
    stats.QUEST_ITEM, stats.QUEST_ITEM_ID, stats.ROLE_QUEST_ITEM, stats.ROLE_QUEST_ITEM_ID,
  ].map(Number).find((value) => Number.isFinite(value) && value > 0);
  if (direct) return direct;
  // 2026 support quest slot can hold a control ward. If it is present in the
  // saved final inventory, render it in the dedicated quest slot instead.
  if (normalItems.includes(2055)) return 2055;
  return 0;
}

function inventoryParts(player) {
  const source = Array.isArray(player?.items)
    ? player.items.map(Number).filter((id) => Number.isFinite(id) && id > 0)
    : [];
  const trinket = source.find((id) => TRINKET_ITEM_IDS.has(id)) || 0;
  let normal = source.filter((id) => id !== trinket);
  const quest = questItemId(player, normal);
  if (quest) {
    const idx = normal.indexOf(quest);
    if (idx >= 0) normal.splice(idx, 1);
  }
  return { normal: normal.slice(0, 6), trinket, quest };
}

function inventorySlot(itemId, className = "", label = "") {
  if (Number(itemId) > 0) {
    return `<span class="inventory-slot ${className}" title="${escapeHtml(label)}">${image(itemIcon(itemId), label || `아이템 ${itemId}`, "inventory-item-icon")}</span>`;
  }
  return `<span class="inventory-slot empty ${className}" title="${escapeHtml(label)}"></span>`;
}

export function renderInventoryGrid(player) {
  const { normal, trinket, quest } = inventoryParts(player);
  const slots = Array.from({length:6}, (_, index) => normal[index] || 0);
  return `<div class="inventory-grid" aria-label="최종 아이템">
    ${inventorySlot(slots[0], "item-1")}${inventorySlot(slots[1], "item-2")}${inventorySlot(slots[2], "item-3")}${inventorySlot(trinket, "trinket-slot", "장신구")}
    ${inventorySlot(slots[3], "item-4")}${inventorySlot(slots[4], "item-5")}${inventorySlot(slots[5], "item-6")}${quest ? inventorySlot(quest, "quest-slot", "퀘스트 슬롯") : `<span class="inventory-slot empty quest-slot" title="퀘스트 슬롯"><i>✦</i></span>`}
  </div>`;
}

export function renderItems(player, max = 7) {
  const items = Array.isArray(player?.items) ? player.items.slice(0,max) : [];
  if (!items.length) return "";
  return `<div class="loadout">${items.map((id) => image(itemIcon(id), `아이템 ${id}`)).join("")}</div>`;
}

export function renderSpells(player) {
  const spells = spellIds(player);
  return spells.length ? `<div class="spell-list">${spells.map((id) => image(spellIcon(id), `소환사 주문 ${id}`, "spell-icon")).join("")}</div>` : "";
}

export function renderKeystone(player) {
  const perks = perkIds(player);
  const keystone = perks.find((id) => perkIcon(id));
  return keystone ? image(perkIcon(keystone), `핵심 룬 ${keystone}`, "rune-icon keystone-icon") : "";
}

export function renderSecondaryRune(player) {
  const styleId = secondaryStyleId(player);
  const icon = perkStyleIcon(styleId);
  return icon ? image(icon, `보조 룬 계열 ${styleId}`, "rune-icon secondary-rune-icon secondary-style-icon") : "";
}

export function renderRunes(player) {
  const perks = perkIds(player);
  const icons = perks.map((id) => image(perkIcon(id), `룬 ${id}`, "rune-icon")).filter(Boolean);
  return icons.length ? `<div class="rune-list">${icons.join("")}</div>` : "";
}

export function renderRuneSpells(player) {
  const keystone = renderKeystone(player);
  const secondaryRune = renderSecondaryRune(player);
  const spells = renderSpells(player);
  if (!keystone && !secondaryRune && !spells) return "";
  const runeBlock = keystone || secondaryRune
    ? `<div class="rune-stack">${keystone}${secondaryRune}</div>`
    : "";
  return `<div class="rune-spells">${runeBlock}${spells}</div>`;
}

export function renderProfileRuneSpells(player) {
  const spells = spellIds(player);
  const perks = perkIds(player).filter((id) => perkIcon(id));
  const mainRune = perks[0] || 0;
  const secondaryRune = renderSecondaryRune(player);
  if (!spells.length && !mainRune && !secondaryRune) return "";
  return `<div class="profile-rune-spells" aria-label="소환사 주문과 룬">
    <div class="profile-spell-stack">
      ${spells.slice(0,2).map((id) => image(spellIcon(id), `소환사 주문 ${id}`, "profile-spell-icon")).join("")}
    </div>
    <div class="profile-rune-stack">
      <div class="profile-main-rune">${mainRune ? image(perkIcon(mainRune), `메인 핵심 룬 ${mainRune}`, "profile-rune-icon profile-keystone-icon") : ""}</div>
      <div class="profile-secondary-rune">${secondaryRune || ""}</div>
    </div>
  </div>`;
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
  const byLevel = new Map(clean.map((row) => [row.level, row.skill]));

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
          return `<span class="${picked===skill ? `picked skill-${skill.toLowerCase()}` : ""}">${picked===skill ? level : ""}</span>`;
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
