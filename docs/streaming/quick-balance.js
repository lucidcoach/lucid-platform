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
export const QUICK_ROLES = ["탑", "정글", "미드", "원딜", "서폿"];

export function balanceQuickPlayers(players) {
  if (players.length !== 10 || players.some((player) => !Number.isFinite(player.score))) throw new Error("ten_players_required");
  const pairs = QUICK_ROLES.map((role) => players.filter((player) => player.role === role));
  if (pairs.some((pair) => pair.length !== 2)) throw new Error("two_per_role_required");
  const total = players.reduce((sum, player) => sum + player.score, 0);
  let best = null;
  // ponytail: fixed five-role exhaustive search; revisit only if multi-role preferences are added.
  for (let mask = 0; mask < 1 << QUICK_ROLES.length; mask += 1) {
    const blue = pairs.map((pair, index) => pair[(mask >> index) & 1]);
    const difference = Math.abs(total - 2 * blue.reduce((sum, player) => sum + player.score, 0));
    const orderDifference = Math.abs(45 - 2 * blue.reduce((sum, player) => sum + players.indexOf(player), 0));
    if (!best || difference < best.difference || (difference === best.difference && orderDifference < best.orderDifference)) best = { blue, red: pairs.map((pair, index) => pair[1 - ((mask >> index) & 1)]), difference, orderDifference };
  }
  return best;
}

function permutations(values) {
  if (values.length < 2) return [values];
  return values.flatMap((value, index) => permutations(values.filter((_, itemIndex) => itemIndex !== index)).map((rest) => [value, ...rest]));
}

function teamAssignments(team) {
  return permutations(team).flatMap((ordered) => {
    let preference = 0, score = 0;
    const players = [];
    for (let index = 0; index < QUICK_ROLES.length; index += 1) {
      const player = ordered[index], choiceIndex = player.choices.findIndex((choice) => choice.role === QUICK_ROLES[index]);
      if (choiceIndex < 0) return [];
      const choice = player.choices[choiceIndex];
      preference += choice.preference ?? choiceIndex; score += choice.score;
      players.push({ ...player, ...choice });
    }
    return [{ players, preference, score }];
  });
}

export function balanceRolePlayers(players) {
  if (players.length !== 10 || players.some((player) => !player.choices?.length || player.choices.length > 3 || new Set(player.choices.map((choice) => choice.role)).size !== player.choices.length || player.choices.some((choice) => !QUICK_ROLES.includes(choice.role) || !Number.isFinite(choice.score)))) throw new Error("invalid_role_preferences");
  let best = null;
  // ponytail: mirrors the production five-role exhaustive matcher; 10 fixed players keep it bounded.
  for (let mask = 0; mask < 1 << 10; mask += 1) {
    if (mask.toString(2).replaceAll("0", "").length !== 5) continue;
    const blueOptions = teamAssignments(players.filter((_, index) => mask & (1 << index)));
    const redOptions = teamAssignments(players.filter((_, index) => !(mask & (1 << index))));
    for (const blue of blueOptions) for (const red of redOptions) {
      const preference = blue.preference + red.preference, difference = Math.abs(blue.score - red.score);
      if (!best || preference < best.preference || (preference === best.preference && difference < best.difference)) best = { blue: blue.players, red: red.players, preference, difference };
    }
  }
  if (!best) throw new Error("roles_unavailable");
  return best;
}
