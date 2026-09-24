import { API_BASE_URL } from "../js/config.js";
import { fetchCurrentUser, loginUser, updateRiotAccounts, userIsAdmin } from "../js/auth.js";

const apiBase = API_BASE_URL.replace(/\/$/, "");
const roles = ["탑", "정글", "미드", "원딜", "서폿"];
const tiers = ["평가 대기","미평가","아이언 IV","아이언 III","아이언 II","아이언 I","브론즈 IV","브론즈 III","브론즈 II","브론즈 I","실버 IV","실버 III","실버 II","실버 I","골드 IV","골드 III","골드 II","골드 I","플래티넘 IV","플래티넘 III","플래티넘 II","플래티넘 I","에메랄드 IV","에메랄드 III","에메랄드 II","에메랄드 I","다이아 IV","다이아 III","다이아 II","다이아 I","마스터","그랜드마스터","챌린저"];
const $ = (selector) => document.querySelector(selector);
let user = null;
let currentSlug = new URLSearchParams(location.search).get("channel") || "";
let state = null;

async function request(path, options = {}) {
  const response = await fetch(`${apiBase}${path}`, { credentials:"include", ...options, headers:{ "Content-Type":"application/json", ...(options.headers || {}) } });
  const result = await response.json().catch(() => ({}));
  if (!response.ok || !result.ok) throw new Error(result.error || `요청 실패 (${response.status})`);
  return result;
}

function escapeHtml(value) { const div = document.createElement("div"); div.textContent = String(value ?? ""); return div.innerHTML; }
function notice(message = "") { $("#notice").hidden = !message; $("#notice").textContent = message; }
function errorText(error) { return ({login_required:"로그인이 필요합니다.",workspace_not_found:"방송을 찾지 못했습니다.",invalid_workspace:"방송 이름과 주소를 확인해주세요.",workspace_already_exists:"이미 사용 중인 방송 주소입니다.",not_enough_players:"참가자가 10명 이상 필요합니다.",result_already_recorded:"이미 기록한 경기입니다.",invalid_riot_accounts:"Riot ID를 게임이름#태그 형식으로 입력해주세요."})[error.message] || error.message; }
function options(values, selected) { return values.map((value) => `<option${value === selected ? " selected" : ""}>${value}</option>`).join(""); }

function showView(name) {
  document.querySelectorAll(".content-view").forEach((view) => view.classList.toggle("active", view.id === `${name}View`));
  document.querySelectorAll(".stream-nav [data-view]").forEach((button) => button.classList.toggle("active", button.dataset.view === name));
  scrollTo({top:0,behavior:"smooth"});
}

function profileCard(player) {
  const total = player.wins + player.losses;
  return `<article class="profile-card"><strong>${escapeHtml(player.name)}</strong><span>${escapeHtml(player.riotId || "Riot ID 미등록")}</span><span>${escapeHtml(player.tier)} · ${player.wins}승 ${player.losses}패${total ? ` · ${Math.round(player.wins / total * 100)}%` : ""}</span>${player.workspaceName ? `<small>${escapeHtml(player.workspaceName)}</small>` : ""}${player.publicSlug ? `<a href="?player=${encodeURIComponent(player.publicSlug)}">전적 보기</a>` : ""}</article>`;
}

function playerEditor(player, index = "") {
  const role1 = player.roles?.[0] || "라인 미정", role2 = player.roles?.[1] || "라인 미정";
  return `<div class="queue-row"><strong>${index}</strong><div><b>${escapeHtml(player.name)}</b><br><small>${escapeHtml(player.riotId || player.tier)}</small></div><select data-tier>${options(tiers, player.tier)}</select><select data-role1>${options(["라인 미정",...roles], role1)}</select><select data-role2>${options(["라인 미정",...roles], role2)}</select><button class="quiet" data-save-player="${player.id}">저장</button></div>`;
}

async function loadAccount() {
  user = await fetchCurrentUser().catch(() => null);
  $("#loginOpen").textContent = user ? user.displayName || "내 계정" : "로그인";
  $("#mineLogin").hidden = Boolean(user); $("#accountSection").hidden = !user;
  $("#adminNav").hidden = !userIsAdmin(user);
  if (!user) return;
  const { workspaces } = await request("/api/streaming/workspaces");
  $("#workspaceList").innerHTML = workspaces.length ? workspaces.map((item) => `<button class="workspace-card" data-open="${item.slug}"><strong>${escapeHtml(item.name)}</strong><br><small>${item.queueCount}명 · ${item.matchCount}경기${item.channelName ? ` · ${escapeHtml(item.channelName)}` : ""}</small></button>`).join("") : '<p class="empty">방송이 없습니다.</p>';
  if (userIsAdmin(user)) await loadAdmin();
}

async function openWorkspace(slug) {
  try {
    state = (await request(`/api/streaming/workspaces/${encodeURIComponent(slug)}`)).data;
    currentSlug = slug; history.replaceState(null,"",`?channel=${encodeURIComponent(slug)}`);
    $("#workspaceNav").hidden = false; renderWorkspace(); showView("workspace"); notice();
  } catch (error) { notice(errorText(error)); }
}

function renderWorkspace() {
  const {workspace,me,queue,applications = [],matches} = state;
  $("#workspaceLabel").textContent = workspace.canManage ? "스트리머" : "참가자";
  $("#workspaceName").textContent = workspace.name;
  $("#tierPanel").hidden = !workspace.canManage; $("#applicationCount").textContent = `${applications.length}명`;
  $("#applicationList").innerHTML = applications.length ? applications.map((player) => playerEditor(player)).join("") : '<p class="empty">신청 없음</p>';
  $("#chzzkConnect").hidden = !workspace.canManage; $("#chzzkConnect").href = `${apiBase}/chzzk/auth-url?guild_id=${encodeURIComponent(workspace.chatKey)}&redirect=1`;
  $("#connectSection").hidden = !workspace.canManage; $("#queueCount").textContent = `${queue.length}명`;
  const joined = me && queue.some((player) => player.id === me.id);
  $("#joinBtn").disabled = !user || joined; $("#leaveBtn").disabled = !user || !joined;
  $("#balanceBtn").hidden = !workspace.canManage; $("#balanceBtn").disabled = queue.length < 10;
  $("#queueList").innerHTML = queue.length ? queue.map((player,index) => workspace.canManage ? playerEditor(player,index + 1) : `<div class="queue-row"><strong>${index + 1}</strong><div><b>${escapeHtml(player.name)}</b><br><small>${escapeHtml(player.riotId || "Riot ID 미등록")}</small></div><span>${escapeHtml(player.tier)}</span><span>${escapeHtml((player.roles || []).join(" / ") || "라인 미정")}</span></div>`).join("") : '<p class="empty">대기 없음</p>';
  $("#matchList").innerHTML = matches.length ? matches.map((match) => `<article class="match-card"><div class="teams"><div class="team blue"><strong>파랑 팀</strong><ul>${match.blue.map((p) => `<li>${escapeHtml(p.name)} · ${escapeHtml(p.tier)}</li>`).join("")}</ul></div><div class="team red"><strong>빨강 팀</strong><ul>${match.red.map((p) => `<li>${escapeHtml(p.name)} · ${escapeHtml(p.tier)}</li>`).join("")}</ul></div></div>${workspace.canManage && match.status === "pending" ? `<div class="result-actions"><button data-result="${match.id}:blue">파랑 승리</button><button data-result="${match.id}:red">빨강 승리</button></div>` : `<p>${match.status === "completed" ? `${match.winner === "blue" ? "파랑" : "빨강"} 승리` : "진행 중"}</p>`}</article>`).join("") : '<p class="empty">경기 없음</p>';
  $("#profileForm").hidden = !user;
  if (me) { $("#profileForm").riotId.value = me.riotId; $("#profileForm").profileEnabled.checked = me.profileEnabled; document.querySelectorAll('#roleChecks input').forEach((input) => input.checked = me.roles.includes(input.value)); $("#publicProfileLink").hidden = !me.publicSlug; $("#publicProfileLink").href = `?player=${encodeURIComponent(me.publicSlug)}`; }
  else { $("#profileForm").reset(); $("#publicProfileLink").hidden = true; }
}

async function reload() { if (currentSlug) await openWorkspace(currentSlug); }
function adminRows(workspaces) { return workspaces.map((w) => `<tr><td>${w.slug ? `<a href="?channel=${encodeURIComponent(w.slug)}">${escapeHtml(w.name)}</a>` : escapeHtml(w.name)}</td><td>${escapeHtml(w.ownerName)}</td><td>${escapeHtml(w.channelName || "미연결")}</td><td>${w.usageCount}</td><td>${w.playerCount}</td><td>${w.matchCount}</td><td>${w.recentMatchCount}</td><td>${w.queueCount}</td><td>${escapeHtml(w.lastUsedAt || "-")}</td></tr>`).join(""); }
async function loadAdmin() { const {workspaces} = await request("/api/streaming/workspaces?scope=all"); $("#adminRows").innerHTML = workspaces.length ? adminRows(workspaces.map((w) => ({...w,lastUsedAt:w.lastUsedAt ? new Date(w.lastUsedAt).toLocaleString("ko-KR") : "-"}))) : '<tr><td colspan="9">사용 중인 방송 없음</td></tr>'; }

const samplePlayers = ["여유","초롱","루나","하늘","도담","모카","유자","라온","해든","윤슬"].map((name,index) => ({id:`sample-${index}`,name,riotId:`${name}#KR1`,tier:["다이아 IV","에메랄드 II","플래티넘 I","플래티넘 III","골드 I"][index%5],roles:[["탑","미드"],["정글","서폿"],["미드","탑"],["원딜","미드"],["서폿","정글"]][index%5]}));
function renderExample(type) {
  document.querySelectorAll("[data-example]").forEach((button) => { button.classList.toggle("active",button.dataset.example === type); button.classList.toggle("quiet",button.dataset.example !== type); });
  if (type === "admin") { const rows = [{name:"여유 방송",ownerName:"여유",channelName:"여유FPS",usageCount:284,playerCount:67,matchCount:31,recentMatchCount:12,queueCount:8,lastUsedAt:"방금 전"},{name:"주말 내전",ownerName:"루시드",channelName:"Lucid",usageCount:146,playerCount:42,matchCount:18,recentMatchCount:7,queueCount:0,lastUsedAt:"어제"}]; $("#exampleRoot").innerHTML = `<div class="table-wrap example-admin"><table><thead><tr><th>방송</th><th>운영자</th><th>치지직 채널</th><th>누적 참가</th><th>참가자</th><th>전체 경기</th><th>최근 30일</th><th>현재 대기</th><th>최근 사용</th></tr></thead><tbody>${adminRows(rows)}</tbody></table></div>`; return; }
  $("#exampleRoot").innerHTML = `<div class="example-shell"><section class="panel"><div class="example-title"><h2>티어 신청</h2><span>2명</span></div>${samplePlayers.slice(0,2).map((p) => playerEditor({...p,tier:"평가 대기"})).join("")}</section><section class="panel"><div class="example-title"><h2>참가 대기열</h2><span>10명</span></div><div class="queue-list">${samplePlayers.map((p,i) => playerEditor(p,i+1)).join("")}</div><button class="wide">팀 편성</button></section><section class="panel"><h2>경기</h2><div class="teams"><div class="team blue"><strong>파랑 팀</strong><ul>${samplePlayers.slice(0,5).map((p) => `<li>${p.name} · ${p.tier}</li>`).join("")}</ul></div><div class="team red"><strong>빨강 팀</strong><ul>${samplePlayers.slice(5).map((p) => `<li>${p.name} · ${p.tier}</li>`).join("")}</ul></div></div></section></div>`;
}

$("#roleChecks").innerHTML = roles.map((role) => `<label><input type="checkbox" name="roles" value="${role}"> ${role}</label>`).join("");
document.querySelectorAll(".stream-nav [data-view]").forEach((button) => button.addEventListener("click",() => showView(button.dataset.view)));
$("#openForm").addEventListener("submit",(event) => { event.preventDefault(); openWorkspace($("#openSlug").value.trim().toLowerCase()); });
$("#workspaceList").addEventListener("click",(event) => { const button=event.target.closest("[data-open]"); if(button) openWorkspace(button.dataset.open); });
$("#createWorkspaceForm").addEventListener("submit",async(event) => { event.preventDefault(); try { const result=await request("/api/streaming/workspaces",{method:"POST",body:JSON.stringify(Object.fromEntries(new FormData(event.currentTarget)))}); event.currentTarget.reset(); await loadAccount(); await openWorkspace(result.slug); } catch(error){ notice(errorText(error)); } });
$("#joinBtn").addEventListener("click",async()=>{try{await request(`/api/streaming/workspaces/${currentSlug}/queue`,{method:"POST",body:"{}"});await reload();}catch(error){notice(errorText(error));}});
$("#leaveBtn").addEventListener("click",async()=>{try{await request(`/api/streaming/workspaces/${currentSlug}/queue`,{method:"DELETE"});await reload();}catch(error){notice(errorText(error));}});
$("#profileForm").addEventListener("submit",async(event)=>{event.preventDefault();const data=new FormData(event.currentTarget);const payload={riotId:data.get("riotId").trim(),roles:data.getAll("roles"),profileEnabled:data.get("profileEnabled")==="on"};try{if(payload.riotId)await updateRiotAccounts([payload.riotId]);await request(`/api/streaming/workspaces/${currentSlug}/me`,{method:"PUT",body:JSON.stringify(payload)});await reload();notice("저장했습니다.");}catch(error){notice(errorText(error));}});
document.addEventListener("click",async(event)=>{const save=event.target.closest("[data-save-player]");if(save&&!save.closest("#exampleRoot")){const id=save.dataset.savePlayer,row=save.closest(".queue-row"),tier=row.querySelector("[data-tier]").value;const selected=[row.querySelector("[data-role1]").value,row.querySelector("[data-role2]").value].filter((role,index,array)=>role!=="라인 미정"&&array.indexOf(role)===index);try{await request(`/api/streaming/workspaces/${currentSlug}/players/${id}`,{method:"PATCH",body:JSON.stringify({tier,roles:selected})});await reload();}catch(error){notice(errorText(error));}}const result=event.target.closest("[data-result]");if(result){const[id,winner]=result.dataset.result.split(":");try{await request(`/api/streaming/workspaces/${currentSlug}/matches/${id}/result`,{method:"POST",body:JSON.stringify({winner})});await reload();}catch(error){notice(errorText(error));}}});
$("#balanceBtn").addEventListener("click",async()=>{try{await request(`/api/streaming/workspaces/${currentSlug}/balance`,{method:"POST",body:"{}"});await reload();}catch(error){notice(errorText(error));}});
$("#copyLink").addEventListener("click",async()=>{await navigator.clipboard.writeText(location.href);notice("복사했습니다.");});
$("#playerSearchForm").addEventListener("submit",async(event)=>{event.preventDefault();try{const{players}=await request(`/api/streaming/players?q=${encodeURIComponent($("#playerSearch").value)}`);$("#playerResults").innerHTML=players.length?players.map(profileCard).join(""):'<p class="empty">검색 결과 없음</p>';$("#recordExample").hidden=true;}catch(error){notice(errorText(error));}});
document.querySelectorAll("[data-example]").forEach((button)=>button.addEventListener("click",()=>renderExample(button.dataset.example)));
$("#loginOpen").addEventListener("click",()=>user?showView("mine"):$("#loginDialog").showModal());$("#mineLogin").addEventListener("click",()=>$("#loginDialog").showModal());
$("#loginForm").addEventListener("submit",async(event)=>{event.preventDefault();try{user=await loginUser(Object.fromEntries(new FormData(event.currentTarget)));$("#loginDialog").close();await loadAccount();showView("mine");}catch{notice("이메일 또는 비밀번호를 확인해주세요.");}});
$("#adminRefresh").addEventListener("click",loadAdmin);$("#discordLogin").href=`${apiBase}/api/auth/oauth/discord/start?returnTo=${encodeURIComponent(location.href)}`;$("#discordLink").href=$("#discordLogin").href;
$("#roleChecks").addEventListener("change",(event)=>{if(document.querySelectorAll('#roleChecks input:checked').length>2){event.target.checked=false;notice("선호 라인은 두 개까지 선택할 수 있습니다.");}});

renderExample("streamer");
const pageParams=new URLSearchParams(location.search),initialView=pageParams.get("view");
if(!pageParams.get("player")&&!currentSlug&&["home","mine","records","examples"].includes(initialView))showView(initialView);
await loadAccount();
const publicSlug=pageParams.get("player");
if(publicSlug){try{const{player}=await request(`/api/streaming/players/${encodeURIComponent(publicSlug)}`);$("#playerResults").innerHTML=profileCard(player);$("#recordExample").hidden=true;showView("records");}catch(error){notice(errorText(error));}}
else if(currentSlug)await openWorkspace(currentSlug);
