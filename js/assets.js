import { DDRAGON_VERSION } from "./config.js?v=20260904b";
import { state } from "./state.js?v=20260904b";

async function fetchJson(url) {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`asset HTTP ${response.status}`);
  return response.json();
}

export async function loadGameAssets() {
  try {
    const [champions, spells, runes] = await Promise.all([
      fetchJson(`https://ddragon.leagueoflegends.com/cdn/${DDRAGON_VERSION}/data/ko_KR/champion.json`),
      fetchJson(`https://ddragon.leagueoflegends.com/cdn/${DDRAGON_VERSION}/data/ko_KR/summoner.json`),
      fetchJson(`https://ddragon.leagueoflegends.com/cdn/${DDRAGON_VERSION}/data/ko_KR/runesReforged.json`),
    ]);
    Object.values(champions?.data || {}).forEach((champion) => {
      state.championMap.set(String(champion.name || "").toLowerCase(), champion.id);
      state.championMap.set(String(champion.id || "").toLowerCase(), champion.id);
    });
    Object.values(spells?.data || {}).forEach((spell) => state.spellMap.set(Number(spell.key), spell.id));
    (runes || []).forEach((tree) => (tree.slots || []).forEach((slot) => (slot.runes || []).forEach((rune) => state.perkMap.set(Number(rune.id), rune.icon))));
  } catch (_) {
    // Text-only fallback keeps records readable if Riot static assets are temporarily unavailable.
  }
}

export function championIcon(champion) {
  const raw = String(champion || "").trim();
  const slug = state.championMap.get(raw.toLowerCase());
  return slug ? `https://ddragon.leagueoflegends.com/cdn/${DDRAGON_VERSION}/img/champion/${encodeURIComponent(slug)}.png` : "";
}
export const itemIcon = (itemId) => `https://ddragon.leagueoflegends.com/cdn/${DDRAGON_VERSION}/img/item/${Number(itemId)}.png`;
export function spellIcon(spellId) { const slug=state.spellMap.get(Number(spellId)); return slug ? `https://ddragon.leagueoflegends.com/cdn/${DDRAGON_VERSION}/img/spell/${slug}.png` : ""; }
export function perkIcon(perkId) { const path=state.perkMap.get(Number(perkId)); return path ? `https://ddragon.leagueoflegends.com/cdn/img/${path}` : ""; }
