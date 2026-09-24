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
  const response = await fetch(`${apiBase}${path}`, { credentials:"include", ...options, headers:{ ...(options.body ? {"Content-Type":"application/json"} : {}), ...(options.headers || {}) } });
  const result = await response.json().catch(() => ({}));
  if (!response.ok || !result.ok) throw new Error(result.error || `요청 실패 (${response.status})`);
  return result;
}

function escapeHtml(value) { const div = document.createElement("div"); div.textContent = String(value ?? ""); return div.innerHTML; }
function notice(message = "") { $("#notice").hidden = !message; $("#notice").textContent = message; }
function errorText(error) { return ({"Failed to fetch":"서버 연결에 실패했습니다. 다시 시도해주세요.",login_required:"로그인이 필요합니다.",workspace_not_found:"방송을 찾지 못했습니다.",invalid_workspace:"방송 정보를 확인해주세요.",workspace_already_exists:"이미 사용 중인 방송입니다.",invalid_placement:"라인과 세부 티어를 모두 선택해주세요.",not_enough_players:"참가자가 10명 이상 필요합니다.",unrated_players:"모든 참가자의 라인별 티어를 먼저 배치해주세요.",result_already_recorded:"이미 기록한 경기입니다.",invalid_riot_accounts:"Riot ID를 게임이름#태그 형식으로 입력해주세요.",manager_required:"방송 운영자만 사용할 수 있습니다.",invalid_auction_team:"팀 이름과 팀장을 입력해주세요.",invalid_auction_player:"참가자 이름과 사진 주소를 확인해주세요.",auction_in_progress:"현재 선수를 먼저 낙찰 또는 유찰 처리해주세요.",auction_no_players:"대기 중인 참가자가 없습니다.",auction_no_current_player:"진행 중인 참가자가 없습니다.",auction_no_bid:"입찰한 팀이 없습니다.",auction_bid_unavailable:"현재 입찰할 수 없습니다.",auction_not_enough_points:"남은 포인트가 부족합니다."})[error.message] || error.message; }
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
  const visibleWorkspaces = workspaces.filter((item) => item.channelId), pending = workspaces.find((item) => !item.channelId);
  if (!visibleWorkspaces.length && pending) visibleWorkspaces.push(pending);
  $("#workspaceList").innerHTML = visibleWorkspaces.map((item) => `<button class="workspace-card" data-open="${item.slug}"><strong>${escapeHtml(item.channelName || item.name)}</strong><br><small>${item.channelId ? `연결됨 · ${item.queueCount}명 · ${item.matchCount}경기` : "치지직 연결 필요"}</small></button>`).join("");
  $("#connectBroadcast").textContent = workspaces.some((item) => item.channelId) ? "방송 추가" : "치지직 방송 연결";
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
  $("#connectionState").textContent = workspace.connected ? `${workspace.channelName} 연결됨` : "연결되지 않음"; $("#chzzkConnect").textContent = workspace.connected ? "다시 연결" : "치지직 방송 연결";
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

let auctionState = null;
async function loadAuction(){if(!currentSlug){$("#auctionBroadcast").textContent="";$("#auctionRoot").innerHTML='<p class="empty">방송 관리에서 방송을 선택해주세요.</p>';return;}try{const token=new URLSearchParams(location.search).get("team")||"",result=await request(`/api/streaming/workspaces/${encodeURIComponent(currentSlug)}/auction${token?`?team=${encodeURIComponent(token)}`:""}`);auctionState=result.auction;renderAuction();}catch(error){notice(errorText(error));}}
async function auctionAction(action,payload={}){try{const teamToken=new URLSearchParams(location.search).get("team")||"",result=await request(`/api/streaming/workspaces/${encodeURIComponent(currentSlug)}/auction`,{method:"POST",body:JSON.stringify({action,teamToken,...payload})});auctionState=result.auction;renderAuction();notice();}catch(error){notice(errorText(error));}}
function renderAuction(){const a=auctionState,s=a.settings,current=a.current,player=a.players.find((item)=>item.id===current?.playerId),leader=a.teams.find((item)=>item.id===current?.teamId),nextBid=current?.teamId?current.amount+s.increment:s.minBid,seconds=current?Math.max(0,s.bidSeconds-Math.floor(Date.now()/1000-current.startedAt)):0;$("#auctionBroadcast").textContent=state?.workspace?.name||"";const manager=a.canManage?`<section class="panel auction-settings"><h2>경매 설정</h2><form data-auction-form="settings"><label>팀별 포인트<input name="points" type="number" min="1" value="${s.points}" required></label><label>최소 입찰가<input name="minBid" type="number" min="1" value="${s.minBid}" required></label><label>호가 단위<input name="increment" type="number" min="1" value="${s.increment}" required></label><label>입찰 시간<input name="bidSeconds" type="number" min="1" value="${s.bidSeconds}" required></label><button>저장</button></form><div class="auction-add"><form data-auction-form="addTeam"><input name="name" placeholder="팀 이름" required><input name="captain" placeholder="팀장" required><button>팀 추가</button></form><form data-auction-form="addPlayer"><input name="name" placeholder="참가자 이름" required><input name="riotId" placeholder="Riot ID"><select name="role"><option value="">라인</option>${options(roles)}</select><input name="tier" placeholder="티어"><input name="imageUrl" type="url" placeholder="프로필 사진 주소"><input name="note" placeholder="참가자 정보"><button>참가자 추가</button></form></div></section>`:"";const teams=a.teams.map((team)=>{const members=a.players.filter((item)=>item.teamId===team.id),canBid=Boolean(current&&(a.canManage||a.myTeamId===team.id));return `<article class="auction-team"><header><div><strong>${escapeHtml(team.name)}</strong><small>${escapeHtml(team.captain)}</small></div><b>${team.points}P</b></header><ul>${members.map((item)=>`<li>${escapeHtml(item.role)} ${escapeHtml(item.name)} · ${item.price}P</li>`).join("")||"<li>선수 없음</li>"}</ul>${canBid?`<button data-auction-action="bid" data-team-id="${team.id}">${nextBid}P 입찰</button>`:""}${a.canManage&&!members.length?`<button class="quiet" data-auction-action="removeTeam" data-id="${team.id}">삭제</button>`:""}${a.canManage?`<button class="quiet" data-copy-team="${team.id}">팀장 링크</button>`:""}</article>`}).join("");const waiting=a.players.filter((item)=>!['sold','current'].includes(item.status)).map((item)=>`<div class="auction-player"><img src="${escapeHtml(item.imageUrl||'../logo.png')}" alt=""><div><strong>${escapeHtml(item.name)}</strong><small>${escapeHtml([item.riotId,item.role,item.tier,item.note].filter(Boolean).join(' · '))}</small></div><span>${item.status==='unsold'?'유찰':'대기'}</span>${a.canManage?`<button class="quiet" data-auction-action="removePlayer" data-id="${item.id}">삭제</button>`:""}</div>`).join("");$("#auctionRoot").innerHTML=`${manager}<section class="auction-stage panel">${player?`<img src="${escapeHtml(player.imageUrl||'../logo.png')}" alt=""><div><span>${escapeHtml(player.role)} · ${escapeHtml(player.tier)}</span><h2>${escapeHtml(player.name)}</h2><p>${escapeHtml(player.riotId)} ${escapeHtml(player.note)}</p><strong>${current.amount||s.minBid}P ${leader?`· ${escapeHtml(leader.name)}`:""}</strong><b class="auction-timer">${seconds}초</b></div>`:'<p class="empty">진행 중인 선수가 없습니다.</p>'}${a.canManage?`<div class="auction-controls"><button data-auction-action="next" ${current?'disabled':''}>다음 선수</button><button data-auction-action="sold" ${!current?.teamId?'disabled':''}>낙찰</button><button class="quiet" data-auction-action="unsold" ${!current?'disabled':''}>유찰</button></div>`:""}</section><section><h2>팀</h2><div class="auction-teams">${teams||'<p class="empty">등록된 팀이 없습니다.</p>'}</div></section><section class="panel"><h2>대기 선수 ${waiting?`(${a.players.filter((item)=>!['sold','current'].includes(item.status)).length}명)`:''}</h2><div class="auction-players">${waiting||'<p class="empty">대기 선수가 없습니다.</p>'}</div></section>`;}

$("#roleChecks").innerHTML = roles.map((role) => `<label><input type="checkbox" name="roles" value="${role}"> ${role}</label>`).join("");
document.querySelectorAll(".stream-nav [data-view]").forEach((button) => button.addEventListener("click",async()=>{showView(button.dataset.view);if(button.dataset.view==="auction")await loadAuction();}));
async function connectBroadcast(chatKey=""){const authTab=window.open("about:blank","_blank");if(!authTab){notice("팝업을 허용한 뒤 다시 눌러주세요.");return;}authTab.document.body.textContent="치지직 연결 화면을 여는 중입니다.";try{if(!chatKey){const pending=ownedWorkspaces.find((item)=>!item.channelId);chatKey=pending?.chatKey;if(!chatKey){const slug=`broadcast-${crypto.randomUUID().slice(0,8)}`,created=await request("/api/streaming/workspaces",{method:"POST",body:JSON.stringify({name:`${user.displayName || "내"} 방송`,slug})});chatKey=created.chatKey;}}authTab.location.replace(`${apiBase}/chzzk/auth-url?guild_id=${encodeURIComponent(chatKey)}&redirect=1`);authTab.opener=null;notice("새 탭에서 치지직 연결을 완료해주세요.");}catch(error){authTab.close();notice(errorText(error));}}
$("#workspaceList").addEventListener("click",(event) => { const button=event.target.closest("[data-open]");if(!button)return;const workspace=ownedWorkspaces.find((item)=>item.slug===button.dataset.open);workspace?.channelId?openWorkspace(workspace.slug):connectBroadcast(workspace?.chatKey); });
$("#connectBroadcast").addEventListener("click",()=>connectBroadcast());
$("#joinBtn").addEventListener("click",async()=>{try{await request(`/api/streaming/workspaces/${currentSlug}/queue`,{method:"POST",body:"{}"});await reload();}catch(error){notice(errorText(error));}});
$("#leaveBtn").addEventListener("click",async()=>{try{await request(`/api/streaming/workspaces/${currentSlug}/queue`,{method:"DELETE"});await reload();}catch(error){notice(errorText(error));}});
$("#profileForm").addEventListener("submit",async(event)=>{event.preventDefault();const data=new FormData(event.currentTarget);const payload={riotId:data.get("riotId").trim(),roles:data.getAll("roles"),profileEnabled:data.get("profileEnabled")==="on"};try{if(payload.riotId)await updateRiotAccounts([payload.riotId]);await request(`/api/streaming/workspaces/${currentSlug}/me`,{method:"PUT",body:JSON.stringify(payload)});await reload();notice("저장했습니다.");}catch(error){notice(errorText(error));}});
document.addEventListener("change",(event)=>{const category=event.target.closest("[data-tier-category]");if(category){const detail=category.closest(".queue-row").querySelector("[data-tier-detail]");detail.innerHTML=tierDetails(category.value);detail.disabled=category.value==="챌린저";}});
document.addEventListener("click",async(event)=>{const save=event.target.closest("[data-save-player]"),cancel=event.target.closest("[data-cancel-player]");if(save){const id=save.dataset.savePlayer,row=save.closest(".queue-row"),role=row.querySelector("[data-placement-role]").value,category=row.querySelector("[data-tier-category]").value,detail=row.querySelector("[data-tier-detail]").value,tier=category==="챌린저"?category:`${category} ${detail}`;try{await request(`/api/streaming/workspaces/${currentSlug}/players/${id}`,{method:"PATCH",body:JSON.stringify({role,tier})});await reload();}catch(error){notice(errorText(error));}}if(cancel){try{await request(`/api/streaming/workspaces/${currentSlug}/players/${cancel.dataset.cancelPlayer}`,{method:"DELETE"});await reload();}catch(error){notice(errorText(error));}}const result=event.target.closest("[data-result]");if(result){const[id,winner]=result.dataset.result.split(":");try{await request(`/api/streaming/workspaces/${currentSlug}/matches/${id}/result`,{method:"POST",body:JSON.stringify({winner})});await reload();}catch(error){notice(errorText(error));}}});
$("#auctionRoot").addEventListener("submit",async(event)=>{const form=event.target.closest("[data-auction-form]");if(!form)return;event.preventDefault();await auctionAction(form.dataset.auctionForm,Object.fromEntries(new FormData(form)));});
$("#auctionRoot").addEventListener("click",async(event)=>{const action=event.target.closest("[data-auction-action]");if(action){await auctionAction(action.dataset.auctionAction,{id:action.dataset.id||"",teamId:action.dataset.teamId||""});return;}const copy=event.target.closest("[data-copy-team]");if(copy){const token=auctionState.teamTokens?.[copy.dataset.copyTeam],url=`${location.origin}${location.pathname}?channel=${encodeURIComponent(currentSlug)}&view=auction&team=${encodeURIComponent(token)}`;await navigator.clipboard.writeText(url);notice("팀장 링크를 복사했습니다.");}});
$("#balanceBtn").addEventListener("click",async()=>{try{await request(`/api/streaming/workspaces/${currentSlug}/balance`,{method:"POST",body:"{}"});await reload();}catch(error){notice(errorText(error));}});
$("#copyLink").addEventListener("click",async()=>{await navigator.clipboard.writeText(location.href);notice("복사했습니다.");});
$("#playerSearchForm").addEventListener("submit",async(event)=>{event.preventDefault();try{const{players}=await request(`/api/streaming/players?q=${encodeURIComponent($("#playerSearch").value)}`);$("#playerResults").innerHTML=players.length?players.map(profileCard).join(""):'<p class="empty">검색 결과 없음</p>';$("#recordExample").hidden=true;}catch(error){notice(errorText(error));}});
$("#loginOpen").addEventListener("click",()=>user?showView("mine"):$("#loginDialog").showModal());$("#mineLogin").addEventListener("click",()=>$("#loginDialog").showModal());
$("#loginForm").addEventListener("submit",async(event)=>{event.preventDefault();try{user=await loginUser(Object.fromEntries(new FormData(event.currentTarget)));$("#loginDialog").close();await loadAccount();showView("mine");}catch{notice("이메일 또는 비밀번호를 확인해주세요.");}});
$("#adminRefresh").addEventListener("click",loadAdmin);$("#discordLogin").href=`${apiBase}/api/auth/oauth/discord/start?returnTo=${encodeURIComponent(location.href)}`;
$("#roleChecks").addEventListener("change",(event)=>{if(document.querySelectorAll('#roleChecks input:checked').length>2){event.target.checked=false;notice("선호 라인은 두 개까지 선택할 수 있습니다.");}});

const pageParams=new URLSearchParams(location.search),initialView=pageParams.get("view");
if(!pageParams.get("player")&&!currentSlug&&["mine","records","auction"].includes(initialView))showView(initialView);
await loadAccount();
window.addEventListener("focus",()=>{if(user)loadAccount().catch(()=>{});});
setInterval(()=>{if(currentSlug&&$("#auctionView").classList.contains("active"))loadAuction();},2000);
const publicSlug=pageParams.get("player");
if(publicSlug){try{const{player}=await request(`/api/streaming/players/${encodeURIComponent(publicSlug)}`);$("#playerResults").innerHTML=profileCard(player);$("#recordExample").hidden=true;showView("records");}catch(error){notice(errorText(error));}}
else if(currentSlug){await openWorkspace(currentSlug);if(initialView==="auction"){showView("auction");await loadAuction();}}
