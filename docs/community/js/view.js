import { $ } from "./utils.js?v=20260904d";

export function showStatus(message = "") {
  const banner = $("statusBanner");
  banner.textContent = message;
  banner.hidden = !message;
}

const PAGE_META = {
  home: ["Lucid Community | 내전 · 전적 · 게임 분석", "Lucid 서버의 실시간 내전, 소환사 전적 검색과 내전 기록을 한곳에서 확인합니다."],
  recent: ["Lucid | 롤 내전 · 전적 · 게임 분석 커뮤니티", "롤 내전, 전적 검색, 게임 분석, 랭킹, 포인트 시스템을 제공하는 Lucid 커뮤니티"],
  search: ["Lucid 전적검색 | 롤 내전 · 전적 분석", "Lucid 서버 내전과 소환사 전적을 검색하고 게임 기록을 분석합니다."],
  analysis: ["Lucid 게임 분석 | 내전 리포트", "Lucid 내전 경기의 플레이와 흐름을 분석한 게임 리포트를 확인합니다."],
  ranking: ["Lucid 랭킹 | 내전 · 포지션 랭킹", "Lucid 서버 내전과 포지션별 랭킹을 확인합니다."],
  mileage: ["Lucid 포인트 상점", "Lucid 활동 포인트와 퀘스트, 상점 상품을 확인합니다."],
  admin: ["Lucid 관리자 | 커뮤니티 운영", "Lucid 커뮤니티 운영 도구와 관리 기록을 확인합니다."],
  patchnotes: ["Lucid 패치노트", "Lucid 커뮤니티의 최근 변경사항을 확인합니다."],
  support: ["Lucid 문의", "Lucid 서비스 이용 문의를 접수합니다."],
  account: ["Lucid 내 정보", "Lucid 계정과 Riot 계정 연결 정보를 관리합니다."],
};

function updatePageMeta(view) {
  const [title, description] = PAGE_META[view] || PAGE_META.recent;
  document.title = title;
  for (const selector of ['meta[name="description"]', 'meta[property="og:description"]', 'meta[name="twitter:description"]']) {
    document.querySelector(selector)?.setAttribute("content", description);
  }
  for (const selector of ['meta[property="og:title"]', 'meta[name="twitter:title"]']) {
    document.querySelector(selector)?.setAttribute("content", title);
  }
}

const initialParams = new URLSearchParams(window.location.search);
updatePageMeta(initialParams.has("player") || initialParams.has("q") ? "search" : initialParams.get("view") || "home");

export function switchView(view) {
  $("homeView")?.classList.toggle("active", view === "home");
  $("recentView")?.classList.toggle("active", view === "recent");
  $("searchView")?.classList.toggle("active", view === "search");
  $("analysisView")?.classList.toggle("active", view === "analysis");
  $("rankingView")?.classList.toggle("active", view === "ranking");
  $("patchnotesView")?.classList.toggle("active", view === "patchnotes");
  $("mileageView")?.classList.toggle("active", view === "mileage");
  $("adminView")?.classList.toggle("active", view === "admin");
  $("supportView")?.classList.toggle("active", view === "support");
  $("accountView")?.classList.toggle("active", view === "account");
  document.body.classList.toggle("community-admin-mode", view === "admin");
  if ($("clearSearchBtn")) $("clearSearchBtn").hidden = view !== "search";
  document.querySelectorAll(".nav-tab[data-view]").forEach((button) => {
    button.classList.toggle("active", button.dataset.view === view);
  });
  updatePageMeta(view);
}

export function renderLoading(target, count = 3) {
  target.innerHTML = "";
  for (let i = 0; i < count; i += 1) target.append($("loadingTemplate").content.cloneNode(true));
}
