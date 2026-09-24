import { API_BASE_URL } from "../js/config.js";
import { fetchCurrentUser, loginUser, updateRiotAccounts, userIsAdmin } from "../js/auth.js";

const apiBase = API_BASE_URL.replace(/\/$/, "");
const roles = ["탑", "정글", "미드", "원딜", "서폿"];
const tierCategories = ["티어 선택","아이언","브론즈","실버","골드","플래티넘","에메랄드","다이아몬드","마스터","그랜드마스터","챌린저"];
const $ = (selector) => document.querySelector(selector);
let user = null;
let currentSlug = new URLSearchParams(location.search).get("channel") || "";
let state = null;
let ownedWorkspaces = [];

async function request(path, options = {}) {
  const response = await fetch(`${apiBase}${path}`, { credentials:"include", ...options, headers:{ "Content-Type":"application/json", ...(options.headers || {}) } });
  const result = await response.json().catch(() => ({}));
  if (!response.ok || !result.ok) throw new Error(result.error || `요청 실패 (${response.status})`);
  return result;
}

function escapeHtml(value) { const div = document.createElement("div"); div.textContent = String(value ?? ""); return div.innerHTML; }
function notice(message = "") { $("#notice").hidden = !message; $("#notice").textContent = message; }
function errorText(error) { return ({login_required:"로그인이 필요합니다.",workspace_not_found:"방송을 찾지 못했습니다.",invalid_workspace:"방송 정보를 확인해주세요.",workspace_already_exists:"이미 사용 중인 방송입니다.",invalid_placement:"라인과 세부 티어를 모두 선택해주세요.",not_enough_players:"참가자가 10명 이상 필요합니다.",unrated_players:"모든 참가자의 라인별 티어를 먼저 배치해주세요.",result_already_recorded:"이미 기록한 경기입니다.",invalid_riot_accounts:"Riot ID를 게임이름#태그 형식으로 입력해주세요."})[error.message] || error.message; }
function options(values, selected) { return values.map((value) => `<option${value === selected ? " selected" : ""}>${value}</option>`).join(""); }
function tierParts(value = "") { const match=String(value).match(/^(아이언|브론즈|실버|골드|플래티넘|에메랄드|다이아(?:몬드)?)\s+(IV|III|II|I|[1-4])$/);if(match){const roman={IV:"4",III:"3",II:"2",I:"1"};return [match[1].startsWith("다이아")?"다이아몬드":match[1],roman[match[2]]||match[2]];}for(const category of ["그랜드마스터","마스터"]){if(String(value).startsWith(category))return[category,String(value).split(" ")[1]||"중"];}return value==="챌린저"?["챌린저","없음"]:["티어 선택","세부 등급"]; }
function tierDetails(category, selected = "") { const values=category==="챌린저"?["없음"]:["마스터","그랜드마스터"].includes(category)?["하","중","상"]:tierCategories.includes(category)&&category!=="티어 선택"?["4","3","2","1"]:["세부 등급"];return options(values,selected||values[0]); }

function showView(name) {
  document.querySelectorAll(".content-view").forEach((view) => view.classList.toggle("active", view.id === `${name}View`));
  document.querySelectorAll(".stream-nav [data-view]").forEach((button) => button.classList.toggle("active", button.dataset.view === name));
  scrollTo({top:0,behavior:"smooth"});
}

function profileCard(player) {
  const total = player.wins + player.losses;
  const placements = Object.entries(player.roleTiers || {}).map(([role,tier]) => `${role} ${tier}`).join(" · ") || player.tier;
  return `<article class="profile-card"><strong>${escapeHtml(player.name)}</strong><span>${escapeHtml(player.riotId || "Riot ID 미등록")}</span><span>${escapeHtml(placements)} · ${player.wins}승 ${player.losses}패${total ? ` · ${Math.round(player.wins / total * 100)}%` : ""}</span>${player.workspaceName ? `<small>${escapeHtml(player.workspaceName)}</small>` : ""}${player.publicSlug ? `<a href="?player=${encodeURIComponent(player.publicSlug)}">전적 보기</a>` : ""}</article>`;
}

function playerEditor(player, index = "") {
  const role = player.roles?.find((item) => !player.roleTiers?.[item]) || player.roles?.[0] || "라인 선택";
  const [category,detail] = tierParts(player.roleTiers?.[role]);
  return `<div class="queue-row"><strong>${index}</strong><div><b>${escapeHtml(player.chzzkNickname || player.name)}</b><br><small>${escapeHtml(player.riotId || "게임이름#태그 미입력")}</small></div><select data-placement-role>${options(["라인 선택",...roles], role)}</select><select data-tier-category>${options(tierCategories, category)}</select><select data-tier-detail>${tierDetails(category,detail)}</select><button class="quiet" data-save-player="${player.id}">저장</button><button class="quiet" data-cancel-player="${player.id}">취소</button></div>`;
}

async function loadAccount() {
  user = await fetchCurrentUser().catch(() => null);
  $("#loginOpen").textContent = user ? user.displayName || "내 계정" : "로그인";
  $("#mineLogin").hidden = Boolean(user); $("#accountSection").hidden = !user;
  $("#adminNav").hidden = !userIsAdmin(user);
  if (!user) return;
  const { workspaces } = await request("/api/streaming/workspaces");
  ownedWorkspaces = workspaces;
  $("#workspaceList").innerHTML = workspaces.length ? workspaces.map((item) => `<button class="workspace-card" data-open="${item.slug}"><strong>${escapeHtml(item.channelName || item.name)}</strong><br><small>${item.channelName ? `${item.queueCount}명 · ${item.matchCount}경기` : "치지직 연결 필요"}</small></button>`).join("") : "";
  $("#connectBroadcast").textContent = workspaces.some((item) => item.channelName) ? "방송 추가" : "치지직 방송 연결";
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
  $("#chzzkConnect").hidden = !workspace.canManage; $("#chzzkConnect").href = `${apiBase}/chzzk/auth-url?guild_id=${encodeURIComponent(workspace.chatKey)}&redirect=1`; $("#chzzkConnect").target = "_blank"; $("#chzzkConnect").rel = "noopener";
  $("#connectSection").hidden = !workspace.canManage; $("#queueCount").textContent = `${queue.length}명`;
  const joined = me && queue.some((player) => player.id === me.id);
  $("#joinBtn").disabled = !user || joined; $("#leaveBtn").disabled = !user || !joined;
  $("#balanceBtn").hidden = !workspace.canManage; $("#balanceBtn").disabled = queue.length < 10 || queue.some((player) => !player.roles?.length || player.roles.some((role) => !player.roleTiers?.[role]));
  $("#queueList").innerHTML = queue.length ? queue.map((player,index) => workspace.canManage ? playerEditor(player,index + 1) : `<div class="queue-row"><strong>${index + 1}</strong><div><b>${escapeHtml(player.name)}</b><br><small>${escapeHtml(player.riotId || "Riot ID 미등록")}</small></div><span>${escapeHtml(player.tier)}</span><span>${escapeHtml((player.roles || []).join(" / ") || "라인 미정")}</span></div>`).join("") : '<p class="empty">대기 없음</p>';
  $("#matchList").innerHTML = matches.length ? matches.map((match) => `<article class="match-card"><div class="teams"><div class="team blue"><strong>파랑 팀</strong><ul>${match.blue.map((p) => `<li>${escapeHtml(p.assignedRole || "")} · ${escapeHtml(p.name)} · ${escapeHtml(p.tier)}</li>`).join("")}</ul></div><div class="team red"><strong>빨강 팀</strong><ul>${match.red.map((p) => `<li>${escapeHtml(p.assignedRole || "")} · ${escapeHtml(p.name)} · ${escapeHtml(p.tier)}</li>`).join("")}</ul></div></div>${workspace.canManage && match.status === "pending" ? `<div class="result-actions"><button data-result="${match.id}:blue">파랑 승리</button><button data-result="${match.id}:red">빨강 승리</button></div>` : `<p>${match.status === "completed" ? `${match.winner === "blue" ? "파랑" : "빨강"} 승리` : "진행 중"}</p>`}</article>`).join("") : '<p class="empty">경기 없음</p>';
  $("#profileForm").hidden = !user;
  if (me) { $("#profileForm").riotId.value = me.riotId; $("#profileForm").profileEnabled.checked = me.profileEnabled; document.querySelectorAll('#roleChecks input').forEach((input) => input.checked = me.roles.includes(input.value)); $("#publicProfileLink").hidden = !me.publicSlug; $("#publicProfileLink").href = `?player=${encodeURIComponent(me.publicSlug)}`; }
  else { $("#profileForm").reset(); $("#publicProfileLink").hidden = true; }
}

async function reload() { if (currentSlug) await openWorkspace(currentSlug); }
function adminRows(workspaces) { return workspaces.map((w) => `<tr><td>${w.slug ? `<a href="?channel=${encodeURIComponent(w.slug)}">${escapeHtml(w.name)}</a>` : escapeHtml(w.name)}</td><td>${escapeHtml(w.ownerName)}</td><td>${escapeHtml(w.channelName || "미연결")}</td><td>${w.usageCount}</td><td>${w.playerCount}</td><td>${w.matchCount}</td><td>${w.recentMatchCount}</td><td>${w.queueCount}</td><td>${escapeHtml(w.lastUsedAt || "-")}</td></tr>`).join(""); }
async function loadAdmin() { const {workspaces} = await request("/api/streaming/workspaces?scope=all"); $("#adminRows").innerHTML = workspaces.length ? adminRows(workspaces.map((w) => ({...w,lastUsedAt:w.lastUsedAt ? new Date(w.lastUsedAt).toLocaleString("ko-KR") : "-"}))) : '<tr><td colspan="9">사용 중인 방송 없음</td></tr>'; }

const samplePlayers = ["여유","초롱","루나","하늘","도담","모카","유자","라온","해든","윤슬"].map((name,index) => {const tier=["다이아몬드 4","에메랄드 2","플래티넘 1","플래티넘 3","골드 1"][index%5],playerRoles=[["탑","미드"],["정글","서폿"],["미드","탑"],["원딜","미드"],["서폿","정글"]][index%5];return {id:`sample-${index}`,name,chzzkNickname:`치지직_${name}`,riotId:`${name}#KR1`,tier,roles:playerRoles,roleTiers:Object.fromEntries(playerRoles.map((role)=>[role,tier]))};});
function renderExample(type) {
  document.querySelectorAll("[data-example]").forEach((button) => { button.classList.toggle("active",button.dataset.example === type); button.classList.toggle("quiet",button.dataset.example !== type); });
  if (type === "admin") { const rows = [{name:"여유 방송",ownerName:"여유",channelName:"여유FPS",usageCount:284,playerCount:67,matchCount:31,recentMatchCount:12,queueCount:8,lastUsedAt:"방금 전"},{name:"주말 내전",ownerName:"루시드",channelName:"Lucid",usageCount:146,playerCount:42,matchCount:18,recentMatchCount:7,queueCount:0,lastUsedAt:"어제"}]; $("#exampleRoot").innerHTML = `<div class="table-wrap example-admin"><table><thead><tr><th>방송</th><th>운영자</th><th>치지직 채널</th><th>누적 참가</th><th>참가자</th><th>전체 경기</th><th>최근 30일</th><th>현재 대기</th><th>최근 사용</th></tr></thead><tbody>${adminRows(rows)}</tbody></table></div>`; return; }
  $("#exampleRoot").innerHTML = `<div class="example-shell"><section class="panel"><div class="example-title"><h2>티어 신청</h2><span>2명</span></div>${samplePlayers.slice(0,2).map((p) => playerEditor({...p,tier:"평가 대기",roleTiers:{}})).join("")}</section><section class="panel"><div class="example-title"><h2>참가 대기열</h2><span>10명</span></div><div class="queue-list">${samplePlayers.map((p,i) => playerEditor(p,i+1)).join("")}</div><button class="wide">팀 편성</button></section><section class="panel"><h2>경기</h2><div class="teams"><div class="team blue"><strong>파랑 팀</strong><ul>${samplePlayers.slice(0,5).map((p) => `<li>${p.name} · ${p.tier}</li>`).join("")}</ul></div><div class="team red"><strong>빨강 팀</strong><ul>${samplePlayers.slice(5).map((p) => `<li>${p.name} · ${p.tier}</li>`).join("")}</ul></div></div></section></div>`;
}

$("#roleChecks").innerHTML = roles.map((role) => `<label><input type="checkbox" name="roles" value="${role}"> ${role}</label>`).join("");
document.querySelectorAll(".stream-nav [data-view]").forEach((button) => button.addEventListener("click",() => showView(button.dataset.view)));
$("#workspaceList").addEventListener("click",(event) => { const button=event.target.closest("[data-open]"); if(button) openWorkspace(button.dataset.open); });
$("#connectBroadcast").addEventListener("click",async()=>{const authTab=window.open("about:blank","_blank");if(!authTab){notice("팝업을 허용한 뒤 다시 눌러주세요.");return;}authTab.document.body.textContent="치지직 연결 화면을 여는 중입니다.";try{const pending=ownedWorkspaces.find((item)=>!item.channelName);let chatKey=pending?.chatKey;if(!chatKey){const slug=`broadcast-${crypto.randomUUID().slice(0,8)}`;await request("/api/streaming/workspaces",{method:"POST",body:JSON.stringify({name:`${user.displayName || "내"} 방송`,slug})});chatKey=`web-${slug}`;}authTab.location.replace(`${apiBase}/chzzk/auth-url?guild_id=${encodeURIComponent(chatKey)}&redirect=1`);authTab.opener=null;}catch(error){authTab.close();notice(errorText(error));}});
$("#joinBtn").addEventListener("click",async()=>{try{await request(`/api/streaming/workspaces/${currentSlug}/queue`,{method:"POST",body:"{}"});await reload();}catch(error){notice(errorText(error));}});
$("#leaveBtn").addEventListener("click",async()=>{try{await request(`/api/streaming/workspaces/${currentSlug}/queue`,{method:"DELETE"});await reload();}catch(error){notice(errorText(error));}});
$("#profileForm").addEventListener("submit",async(event)=>{event.preventDefault();const data=new FormData(event.currentTarget);const payload={riotId:data.get("riotId").trim(),roles:data.getAll("roles"),profileEnabled:data.get("profileEnabled")==="on"};try{if(payload.riotId)await updateRiotAccounts([payload.riotId]);await request(`/api/streaming/workspaces/${currentSlug}/me`,{method:"PUT",body:JSON.stringify(payload)});await reload();notice("저장했습니다.");}catch(error){notice(errorText(error));}});
document.addEventListener("change",(event)=>{const category=event.target.closest("[data-tier-category]");if(category){const detail=category.closest(".queue-row").querySelector("[data-tier-detail]");detail.innerHTML=tierDetails(category.value);detail.disabled=category.value==="챌린저";}});
document.addEventListener("click",async(event)=>{const save=event.target.closest("[data-save-player]"),cancel=event.target.closest("[data-cancel-player]"),example=(save||cancel)?.closest("#exampleRoot");if(example){if(save){const row=save.closest(".queue-row"),category=row.querySelector("[data-tier-category]").value,detail=row.querySelector("[data-tier-detail]").value;if(category!=="티어 선택"&&detail!=="세부 등급")save.textContent="저장됨";}else cancel.closest(".queue-row").remove();return;}if(save){const id=save.dataset.savePlayer,row=save.closest(".queue-row"),role=row.querySelector("[data-placement-role]").value,category=row.querySelector("[data-tier-category]").value,detail=row.querySelector("[data-tier-detail]").value,tier=category==="챌린저"?category:`${category} ${detail}`;try{await request(`/api/streaming/workspaces/${currentSlug}/players/${id}`,{method:"PATCH",body:JSON.stringify({role,tier})});await reload();}catch(error){notice(errorText(error));}}if(cancel){try{await request(`/api/streaming/workspaces/${currentSlug}/players/${cancel.dataset.cancelPlayer}`,{method:"DELETE"});await reload();}catch(error){notice(errorText(error));}}const result=event.target.closest("[data-result]");if(result){const[id,winner]=result.dataset.result.split(":");try{await request(`/api/streaming/workspaces/${currentSlug}/matches/${id}/result`,{method:"POST",body:JSON.stringify({winner})});await reload();}catch(error){notice(errorText(error));}}const demoBalance=event.target.closest("#exampleRoot .wide");if(demoBalance)demoBalance.textContent="팀 편성 완료";});
$("#balanceBtn").addEventListener("click",async()=>{try{await request(`/api/streaming/workspaces/${currentSlug}/balance`,{method:"POST",body:"{}"});await reload();}catch(error){notice(errorText(error));}});
$("#copyLink").addEventListener("click",async()=>{await navigator.clipboard.writeText(location.href);notice("복사했습니다.");});
$("#playerSearchForm").addEventListener("submit",async(event)=>{event.preventDefault();try{const{players}=await request(`/api/streaming/players?q=${encodeURIComponent($("#playerSearch").value)}`);$("#playerResults").innerHTML=players.length?players.map(profileCard).join(""):'<p class="empty">검색 결과 없음</p>';$("#recordExample").hidden=true;}catch(error){notice(errorText(error));}});
document.querySelectorAll("[data-example]").forEach((button)=>button.addEventListener("click",()=>renderExample(button.dataset.example)));
$("#loginOpen").addEventListener("click",()=>user?showView("mine"):$("#loginDialog").showModal());$("#mineLogin").addEventListener("click",()=>$("#loginDialog").showModal());
$("#loginForm").addEventListener("submit",async(event)=>{event.preventDefault();try{user=await loginUser(Object.fromEntries(new FormData(event.currentTarget)));$("#loginDialog").close();await loadAccount();showView("mine");}catch{notice("이메일 또는 비밀번호를 확인해주세요.");}});
$("#adminRefresh").addEventListener("click",loadAdmin);$("#discordLogin").href=`${apiBase}/api/auth/oauth/discord/start?returnTo=${encodeURIComponent(location.href)}`;
$("#roleChecks").addEventListener("change",(event)=>{if(document.querySelectorAll('#roleChecks input:checked').length>2){event.target.checked=false;notice("선호 라인은 두 개까지 선택할 수 있습니다.");}});

renderExample("streamer");
const pageParams=new URLSearchParams(location.search),initialView=pageParams.get("view");
if(!pageParams.get("player")&&!currentSlug&&["mine","records","examples"].includes(initialView))showView(initialView);
await loadAccount();
const publicSlug=pageParams.get("player");
if(publicSlug){try{const{player}=await request(`/api/streaming/players/${encodeURIComponent(publicSlug)}`);$("#playerResults").innerHTML=profileCard(player);$("#recordExample").hidden=true;showView("records");}catch(error){notice(errorText(error));}}
else if(currentSlug)await openWorkspace(currentSlug);
