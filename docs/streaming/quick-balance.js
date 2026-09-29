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
