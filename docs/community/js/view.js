import { $ } from "./utils.js?v=20260904d";

export function showStatus(message = "") {
  const banner = $("statusBanner");
  banner.textContent = message;
  banner.hidden = !message;
}

export function switchView(view) {
  $("recentView")?.classList.toggle("active", view === "recent");
  $("searchView")?.classList.toggle("active", view === "search");
  $("analysisView")?.classList.toggle("active", view === "analysis");
  $("rankingView")?.classList.toggle("active", view === "ranking");
  $("accountView")?.classList.toggle("active", view === "account");
  if ($("clearSearchBtn")) $("clearSearchBtn").hidden = view !== "search";
  document.querySelectorAll(".nav-tab[data-view]").forEach((button) => {
    button.classList.toggle("active", button.dataset.view === view);
  });
}

export function renderLoading(target, count = 3) {
  target.innerHTML = "";
  for (let i = 0; i < count; i += 1) target.append($("loadingTemplate").content.cloneNode(true));
}
