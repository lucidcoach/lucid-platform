const divisions = [4, 3, 2, 1];
const ranks = [
  ["아이언", 0], ["브론즈", 400], ["실버", 800], ["골드", 1200],
  ["플래티넘", 1600], ["에메랄드", 2000], ["다이아몬드", 2400],
];

export const QUICK_TIERS = [
  ...ranks.flatMap(([rank, base]) => divisions.map((division) => ({ label: `${rank} ${division}`, score: base + (4 - division) * 100 + 50 }))),
  { label: "마스터 하", score: 2900 }, { label: "마스터 중", score: 3000 }, { label: "마스터 상", score: 3100 },
  { label: "그랜드마스터 하", score: 3300 }, { label: "그랜드마스터 중", score: 3400 }, { label: "그랜드마스터 상", score: 3500 },
  { label: "챌린저", score: 3800 },
];

export function balanceQuickPlayers(players) {
  if (players.length !== 10 || players.some((player) => !Number.isFinite(player.score))) throw new Error("ten_players_required");
  const total = players.reduce((sum, player) => sum + player.score, 0);
  let best = null;
  // ponytail: fixed 10-player exhaustive search; revisit only if party size becomes configurable.
  for (let mask = 0; mask < 1 << 10; mask += 1) {
    if (mask.toString(2).replaceAll("0", "").length !== 5) continue;
    const blue = players.filter((_, index) => mask & (1 << index));
    const difference = Math.abs(total - 2 * blue.reduce((sum, player) => sum + player.score, 0));
    const orderDifference = Math.abs(45 - 2 * blue.reduce((sum, player) => sum + players.indexOf(player), 0));
    if (!best || difference < best.difference || (difference === best.difference && orderDifference < best.orderDifference)) best = { blue, red: players.filter((_, index) => !(mask & (1 << index))), difference, orderDifference };
  }
  return best;
}
