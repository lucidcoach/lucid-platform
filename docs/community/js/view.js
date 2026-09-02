import { $ } from "./utils.js";

export function showStatus(message = "") {
  const banner = $("statusBanner");
  banner.textContent = message;
  banner.hidden = !message;
}

export function switchView(view) {
  $("recentView").classList.toggle("active", view === "recent");
  $("searchView").classList.toggle("active", view === "search");
  $("clearSearchBtn").hidden = view !== "search";
}

export function renderLoading(target, count = 3) {
  target.innerHTML = "";
  for (let i = 0; i < count; i += 1) target.append($("loadingTemplate").content.cloneNode(true));
}
