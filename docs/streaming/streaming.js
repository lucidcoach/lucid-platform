import { API_BASE_URL } from "../js/config.js";
import { fetchCurrentUser, loginUser, updateRiotAccounts, userIsAdmin } from "../js/auth.js";

const apiBase = API_BASE_URL.replace(/\/$/, "");
const roles = ["탑", "정글", "미드", "원딜", "서폿"];
const tiers = ["미평가","아이언 IV","아이언 III","아이언 II","아이언 I","브론즈 IV","브론즈 III","브론즈 II","브론즈 I","실버 IV","실버 III","실버 II","실버 I","골드 IV","골드 III","골드 II","골드 I","플래티넘 IV","플래티넘 III","플래티넘 II","플래티넘 I","에메랄드 IV","에메랄드 III","에메랄드 II","에메랄드 I","다이아 IV","다이아 III","다이아 II","다이아 I","마스터","그랜드마스터","챌린저"];
const $ = (selector) => document.querySelector(selector);
let user = null;
let currentSlug = new URLSearchParams(location.search).get("channel") || "";
let state = null;

async function request(path, options = {}) {
  const response = await fetch(`${apiBase}${path}`, { credentials: "include", ...options, headers: { "Content-Type": "application/json", ...(options.headers || {}) } });
  const result = await response.json().catch(() => ({}));
  if (!response.ok || !result.ok) throw new Error(result.error || `요청 실패 (${response.status})`);
  return result;
}

function notice(message = "") { $("#notice").hidden = !message; $("#notice").textContent = message; }
function errorText(error) {
  return ({ login_required:"로그인이 필요합니다.", workspace_not_found:"방송 공간을 찾지 못했습니다.", invalid_workspace:"방송 이름과 주소를 확인해주세요.", workspace_already_exists:"이미 사용 중인 주소나 채팅 연결 키입니다.", not_enough_players:"참가자가 10명 이상 필요합니다.", result_already_recorded:"이미 결과를 기록한 경기입니다." })[error.message] || error.message;
}
function profileCard(player, example = false) {
  const total = player.wins + player.losses;
  return `<article class="profile-card"><strong>${escapeHtml(player.name)}</strong><span>${escapeHtml(player.riotId || "Riot ID 미등록")}</span><span>${escapeHtml(player.tier)} · ${player.wins}승 ${player.losses}패${total ? ` · 승률 ${Math.round(player.wins / total * 100)}%` : ""}</span>${player.workspaceName ? `<small>${escapeHtml(player.workspaceName)}</small>` : ""}${player.publicSlug && !example ? `<a href="?player=${encodeURIComponent(player.publicSlug)}">전적 보기</a>` : ""}</article>`;
}
function escapeHtml(value) { const div = document.createElement("div"); div.textContent = String(value ?? ""); return div.innerHTML; }
function options(values, selected) { return values.map((value) => `<option${value === selected ? " selected" : ""}>${value}</option>`).join(""); }

async function loadAccount() {
  user = await fetchCurrentUser().catch(() => null);
  $("#loginOpen").textContent = user ? user.displayName || user.display_name || "내 계정" : "로그인";
  $("#accountSection").hidden = !user;
  if (!user) return;
  const { workspaces } = await request("/api/streaming/workspaces");
  $("#workspaceList").innerHTML = workspaces.length ? workspaces.map((item) => `<button class="workspace-card quiet" data-open="${item.slug}"><strong>${escapeHtml(item.name)}</strong><br><small>${item.queueCount}명 대기 · ${item.matchCount}경기</small></button>`).join("") : '<p class="empty">아직 만든 방송 공간이 없습니다.</p>';
  if (userIsAdmin(user)) { $("#adminSection").hidden = false; await loadAdmin(); }
}

async function openWorkspace(slug) {
  try {
    const result = await request(`/api/streaming/workspaces/${encodeURIComponent(slug)}`);
    currentSlug = slug; state = result.data;
    history.replaceState(null, "", `?channel=${encodeURIComponent(slug)}`);
    renderWorkspace(); notice();
  } catch (error) { notice(errorText(error)); }
}

function renderWorkspace() {
  const { workspace, me, queue, matches } = state;
  $("#workspaceSection").hidden = false;
  $("#workspaceLabel").textContent = workspace.canManage ? "스트리머 화면" : "시청자 화면";
  $("#workspaceName").textContent = workspace.name;
  $("#chzzkConnect").hidden = !workspace.canManage || !workspace.chatKey;
  $("#chzzkConnect").href = `${apiBase}/chzzk/auth-url?guild_id=${encodeURIComponent(workspace.chatKey)}&redirect=1`;
  $("#queueCount").textContent = `${queue.length}명 대기 중`;
  const joined = me && queue.some((player) => player.id === me.id);
  $("#joinBtn").disabled = !user || joined; $("#leaveBtn").disabled = !user || !joined;
  $("#balanceBtn").hidden = !workspace.canManage; $("#balanceBtn").disabled = queue.length < 10;
  $("#queueList").innerHTML = queue.length ? queue.map((player, index) => `<div class="queue-row"><strong>${index + 1}</strong><div><b>${escapeHtml(player.name)}</b><br><small>${escapeHtml(player.riotId || "Riot ID 미등록")}</small></div>${workspace.canManage ? `<select data-tier="${player.id}">${options(tiers, player.tier)}</select><select data-role="${player.id}">${options(["라인 미정",...roles], player.roles[0] || "라인 미정")}</select><button class="quiet" data-save-player="${player.id}">저장</button>` : `<span>${escapeHtml(player.tier)}</span>`}</div>`).join("") : '<p class="empty">아직 참가자가 없습니다. 채팅에서 !참가를 입력하거나 웹에서 참가할 수 있습니다.</p>';
  $("#matchList").innerHTML = matches.length ? matches.map((match) => `<article class="match-card"><div class="teams"><div class="team blue"><strong>파랑 팀</strong><ul>${match.blue.map((p) => `<li>${escapeHtml(p.name)} · ${escapeHtml(p.tier)}</li>`).join("")}</ul></div><div class="team red"><strong>빨강 팀</strong><ul>${match.red.map((p) => `<li>${escapeHtml(p.name)} · ${escapeHtml(p.tier)}</li>`).join("")}</ul></div></div>${workspace.canManage && match.status === "pending" ? `<div class="result-actions"><button data-result="${match.id}:blue">파랑 팀 승리</button><button data-result="${match.id}:red">빨강 팀 승리</button></div>` : `<p>${match.status === "completed" ? `${match.winner === "blue" ? "파랑" : "빨강"} 팀 승리` : "경기 진행 중"}</p>`}</article>`).join("") : '<p class="empty">편성된 경기가 없습니다.</p>';
  $("#profileForm").hidden = !user; $("#discordLink").hidden = !user;
  if (me) {
    $("#profileForm").riotId.value = me.riotId; $("#profileForm").profileEnabled.checked = me.profileEnabled;
    document.querySelectorAll('#roleChecks input').forEach((input) => { input.checked = me.roles.includes(input.value); });
    $("#publicProfileLink").hidden = !me.publicSlug; $("#publicProfileLink").href = `?player=${encodeURIComponent(me.publicSlug)}`;
  } else { $("#profileForm").reset(); $("#publicProfileLink").hidden = true; }
}

async function reload() { if (currentSlug) await openWorkspace(currentSlug); }
async function loadAdmin() {
  const { workspaces } = await request("/api/streaming/workspaces?scope=all");
  $("#adminRows").innerHTML = workspaces.length ? workspaces.map((w) => `<tr><td><a href="?channel=${encodeURIComponent(w.slug)}">${escapeHtml(w.name)}</a></td><td>${escapeHtml(w.ownerName)}</td><td>${escapeHtml(w.chatKey || "-")}</td><td>${w.usageCount}</td><td>${w.playerCount}</td><td>${w.matchCount}</td><td>${w.recentMatchCount}</td><td>${w.queueCount}</td><td>${w.lastUsedAt ? new Date(w.lastUsedAt).toLocaleString("ko-KR") : "-"}</td></tr>`).join("") : '<tr><td colspan="9">사용 중인 방송이 없습니다.</td></tr>';
}

$("#roleChecks").innerHTML = roles.map((role) => `<label><input type="checkbox" name="roles" value="${role}"> ${role}</label>`).join("");
$("#openForm").addEventListener("submit", (event) => { event.preventDefault(); openWorkspace($("#openSlug").value.trim().toLowerCase()); });
$("#workspaceList").addEventListener("click", (event) => { const button = event.target.closest("[data-open]"); if (button) openWorkspace(button.dataset.open); });
$("#createWorkspaceForm").addEventListener("submit", async (event) => { event.preventDefault(); const data = Object.fromEntries(new FormData(event.currentTarget)); try { const result = await request("/api/streaming/workspaces", { method:"POST", body:JSON.stringify(data) }); event.currentTarget.reset(); await loadAccount(); await openWorkspace(result.slug); } catch (error) { notice(errorText(error)); } });
$("#joinBtn").addEventListener("click", async () => { try { await request(`/api/streaming/workspaces/${currentSlug}/queue`, { method:"POST", body:"{}" }); await reload(); } catch(error) { notice(errorText(error)); } });
$("#leaveBtn").addEventListener("click", async () => { try { await request(`/api/streaming/workspaces/${currentSlug}/queue`, { method:"DELETE" }); await reload(); } catch(error) { notice(errorText(error)); } });
$("#profileForm").addEventListener("submit", async (event) => { event.preventDefault(); const data = new FormData(event.currentTarget); const payload = { riotId:data.get("riotId").trim(), roles:data.getAll("roles"), profileEnabled:data.get("profileEnabled") === "on" }; try { if (payload.riotId) await updateRiotAccounts([payload.riotId]); await request(`/api/streaming/workspaces/${currentSlug}/me`, { method:"PUT", body:JSON.stringify(payload) }); await reload(); notice("참가 정보를 저장했습니다."); } catch(error) { notice(errorText(error)); } });
$("#queueList").addEventListener("click", async (event) => { const button = event.target.closest("[data-save-player]"); if (!button) return; const id = button.dataset.savePlayer; const tier = document.querySelector(`[data-tier="${id}"]`).value; const role = document.querySelector(`[data-role="${id}"]`).value; try { await request(`/api/streaming/workspaces/${currentSlug}/players/${id}`, { method:"PATCH", body:JSON.stringify({ tier, roles:role === "라인 미정" ? [] : [role] }) }); await reload(); } catch(error) { notice(errorText(error)); } });
$("#balanceBtn").addEventListener("click", async () => { try { await request(`/api/streaming/workspaces/${currentSlug}/balance`, { method:"POST", body:"{}" }); await reload(); } catch(error) { notice(errorText(error)); } });
$("#matchList").addEventListener("click", async (event) => { const button = event.target.closest("[data-result]"); if (!button) return; const [id,winner] = button.dataset.result.split(":"); try { await request(`/api/streaming/workspaces/${currentSlug}/matches/${id}/result`, { method:"POST", body:JSON.stringify({winner}) }); await reload(); } catch(error) { notice(errorText(error)); } });
$("#copyLink").addEventListener("click", async () => { await navigator.clipboard.writeText(location.href); notice("참가 링크를 복사했습니다."); });
$("#playerSearchForm").addEventListener("submit", async (event) => { event.preventDefault(); try { const { players } = await request(`/api/streaming/players?q=${encodeURIComponent($("#playerSearch").value)}`); $("#playerResults").innerHTML = players.length ? players.map((p) => profileCard(p)).join("") : '<p class="empty">검색 결과가 없습니다.</p>'; } catch(error) { notice(errorText(error)); } });
$("#exampleBtn").addEventListener("click", () => { $("#playerResults").innerHTML = profileCard({name:"예시 참가자",riotId:"Lucid#KR1",tier:"플래티넘 II",wins:18,losses:12,workspaceName:"예시 방송"}, true); });
$("#loginOpen").addEventListener("click", () => { if (!user) $("#loginDialog").showModal(); else $("#accountSection").scrollIntoView({behavior:"smooth"}); });
$("#loginForm").addEventListener("submit", async (event) => { event.preventDefault(); const data = Object.fromEntries(new FormData(event.currentTarget)); try { user = await loginUser(data); $("#loginDialog").close(); await loadAccount(); await reload(); } catch(error) { notice("이메일 또는 비밀번호를 확인해주세요."); } });
$("#adminRefresh").addEventListener("click", loadAdmin);
$("#discordLogin").href = `${apiBase}/api/auth/oauth/discord/start?returnTo=${encodeURIComponent(location.href)}`;
$("#discordLink").href = $("#discordLogin").href;
$("#roleChecks").addEventListener("change", (event) => { const checked = [...document.querySelectorAll('#roleChecks input:checked')]; if (checked.length > 2) { event.target.checked = false; notice("선호 라인은 두 개까지 선택할 수 있습니다."); } });

await loadAccount();
const publicSlug = new URLSearchParams(location.search).get("player");
if (publicSlug) { try { const { player } = await request(`/api/streaming/players/${encodeURIComponent(publicSlug)}`); $("#playerResults").innerHTML = profileCard(player); $("#playerResults").scrollIntoView(); } catch(error) { notice(errorText(error)); } }
else if (currentSlug) await openWorkspace(currentSlug);
