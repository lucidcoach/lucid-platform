export const VIEW_ROUTES = {mine:"",quick:"team",auction:"auction",records:"history",admin:"admin"};

export function viewFromSearch(search) {
  const params = new URLSearchParams(search), value = params.get("view") || "";
  if (params.get("player")) return "records";
  if (params.get("channel") && value !== "auction") return "workspace";
  return ({team:"quick",quick:"quick",auction:"auction",history:"records",records:"records",admin:"admin",mine:"mine"})[value] || "mine";
}

export function viewUrlFor(href, name, slug = "") {
  const url = new URL(href);
  ["view","channel","team","preview","player","mode"].forEach((key) => url.searchParams.delete(key));
  if (name === "workspace" && slug) url.searchParams.set("channel", slug);
  else {
    if (VIEW_ROUTES[name]) url.searchParams.set("view", VIEW_ROUTES[name]);
    if (name === "auction" && slug) url.searchParams.set("channel", slug);
  }
  return `${url.pathname}${url.search}${url.hash}`;
}
