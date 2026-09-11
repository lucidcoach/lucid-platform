import { API_BASE_URL } from "./config.js";

let currentUser = null;
let riotAccounts = [];
let resolvedPlayers = [];

function apiUrl(path){ return `${API_BASE_URL.replace(/\/$/, "")}${path}`; }
function normalizeRiotId(value){ return String(value || "").trim().replace(/＃/g, "#"); }

export function getCurrentUser(){ return currentUser; }
export function isCommunityAdmin(){
  const roles=Array.isArray(currentUser?.roles)?currentUser.roles.map(x=>String(x).toLowerCase()):[];
  return String(currentUser?.role||"").toLowerCase()==="admin"
    || roles.includes("admin") || roles.includes("관리자")
    || Boolean(currentUser?.isAdmin || currentUser?.is_admin);
}
export function isCommunityCoach(){
  const roles=Array.isArray(currentUser?.roles)?currentUser.roles.map(x=>String(x).toLowerCase()):[];
  return String(currentUser?.role||"").toLowerCase()==="coach"
    || roles.includes("coach") || roles.includes("코치")
    || Boolean(currentUser?.isCoach || currentUser?.is_coach);
}
export function isCommunityServerAdmin(guildId=""){
  if(!currentUser) return false;
  const roles=Array.isArray(currentUser?.roles)?currentUser.roles.map(x=>String(x).toLowerCase()):[];
  const role=String(currentUser?.role||"").toLowerCase();
  const hasServerAdminRole = role === "server_admin" || role === "server-admin" || role === "서버 관리자"
    || roles.includes("server_admin") || roles.includes("server-admin") || roles.includes("서버 관리자");
  const rawLists=[
    currentUser?.serverAdminGuildIds,currentUser?.server_admin_guild_ids,
    currentUser?.managedGuildIds,currentUser?.managed_guild_ids,currentUser?.serverGuildIds,
  ];
  const ids=[];
  for(const list of rawLists){ if(Array.isArray(list)) ids.push(...list.map(String)); }
  if(currentUser?.serverAdmins && typeof currentUser.serverAdmins === "object"){
    if(Array.isArray(currentUser.serverAdmins)) ids.push(...currentUser.serverAdmins.map(x=>String(x?.guildId ?? x)));
    else ids.push(...Object.keys(currentUser.serverAdmins).filter(key=>currentUser.serverAdmins[key]));
  }
  if(guildId) return ids.includes(String(guildId));
  return hasServerAdminRole && ids.length > 0;
}
export function canAnalyzeAllPlayers(guildId=""){ return isCommunityAdmin() || isCommunityCoach() || isCommunityServerAdmin(guildId); }
export function getRiotAccounts(){ return [...riotAccounts]; }
export function getResolvedAnalysisPlayers(){ return [...resolvedPlayers]; }
export function getAnalysisIdentity(){ return resolvedPlayers[0] || null; }
export function canAnalyzePlayer(userId,guildId){
  if(canAnalyzeAllPlayers(guildId)) return true;
  if(!currentUser) return false;
  return resolvedPlayers.some(row => String(row.userId)===String(userId) && String(row.guildId)===String(guildId));
}

async function resolveRegisteredPlayers(){
  const rows=Array.isArray(currentUser?.analysisPlayers)?currentUser.analysisPlayers:[];
  resolvedPlayers=rows.map(row=>({
    userId:String(row.userId||""), guildId:String(row.guildId||""),
    name:String(row.name||row.riotId||""), riotId:String(row.riotId||row.name||""),
  })).filter(row=>row.userId&&row.guildId);
  return resolvedPlayers;
}

function renderAuthActions(){
  const login=document.getElementById("communityLoginBtn");
  const discord=document.getElementById("communityLinkBtn");
  const logoutBtn=document.getElementById("communityLogoutBtn");
  if(!login||!discord) return;
  if(currentUser){
    login.textContent=currentUser.displayName || currentUser.email || "내 정보";
    login.classList.add("active-user");
    login.title="커뮤니티 내 정보";
    const connected=Boolean(currentUser.discordConnected||currentUser.discord_connected||currentUser.discordDisplayName||currentUser.discord_display_name);
    discord.textContent=connected?`Discord · ${currentUser.discordDisplayName||currentUser.discord_display_name||"연결됨"}`:"Discord 연결";
    discord.classList.toggle("active-user",connected);
    if(logoutBtn) logoutBtn.hidden=false;
  }else{
    login.textContent="로그인";
    login.classList.remove("active-user");
    login.title="로그인";
    discord.textContent="Discord로 연결";
    discord.classList.remove("active-user");
    if(logoutBtn) logoutBtn.hidden=true;
  }
  window.dispatchEvent(new CustomEvent("lucid:auth-changed",{detail:{user:currentUser,admin:isCommunityAdmin(),coach:isCommunityCoach(),analyzeAll:canAnalyzeAllPlayers(),riotAccounts:getRiotAccounts(),players:getResolvedAnalysisPlayers()}}));
}

async function loadCurrentUser(){
  try{
    const res=await fetch(apiUrl("/api/auth/me"),{credentials:"include"});
    const data=await res.json().catch(()=>({}));
    currentUser=res.ok&&data.ok?data.user:null;
  }catch(_){ currentUser=null; }
  const verified=Array.isArray(currentUser?.verifiedRiotAccounts)?currentUser.verifiedRiotAccounts:currentUser?.riotAccounts;
  riotAccounts=Array.isArray(verified) ? verified.map(normalizeRiotId).filter(Boolean) : [];
  await resolveRegisteredPlayers();
  renderAuthActions();
  return currentUser;
}

function openModal(){
  const modal=document.getElementById("communityAuthModal");
  modal?.removeAttribute("hidden");
  requestAnimationFrame(()=>modal?.querySelector('[data-community-oauth="discord"]')?.focus());
}
function closeModal(){ document.getElementById("communityAuthModal")?.setAttribute("hidden",""); }
function startOAuth(provider){
  const start=new URL(apiUrl(`/api/auth/oauth/${provider}/start`));
  start.searchParams.set("returnTo",window.location.href);
  window.location.assign(start.toString());
}

async function login(email,password){
  const res=await fetch(apiUrl("/api/auth/login"),{method:"POST",credentials:"include",headers:{"Content-Type":"application/json"},body:JSON.stringify({email,password})});
  const data=await res.json().catch(()=>({}));
  if(!res.ok||!data.ok) throw new Error(data.error||"로그인에 실패했습니다.");
  return loadCurrentUser();
}

export async function logoutCommunityUser(){
  try{ await fetch(apiUrl("/api/auth/logout"),{method:"POST",credentials:"include"}); }catch(_){ }
  currentUser=null; riotAccounts=[]; resolvedPlayers=[]; renderAuthActions();
}

export async function saveRiotAccounts(values=[]){
  void values;
  throw new Error("Riot ID는 Discord 봇의 소환사등록 정보에서 자동으로 가져옵니다.");
}

export async function initCommunityAuth(){
  const loginBtn=document.getElementById("communityLoginBtn");
  const discordBtn=document.getElementById("communityLinkBtn");
  const logoutBtn=document.getElementById("communityLogoutBtn");
  const form=document.getElementById("communityAuthForm");
  document.getElementById("communityAuthClose")?.addEventListener("click",closeModal);
  document.getElementById("communityAuthModal")?.addEventListener("click",e=>{ if(e.target?.id==="communityAuthModal") closeModal(); });
  document.addEventListener("keydown",e=>{ if(e.key==="Escape") closeModal(); });
  loginBtn?.addEventListener("click",()=>{ if(currentUser) window.dispatchEvent(new CustomEvent("lucid:open-account")); else openModal(); });
  discordBtn?.addEventListener("click",()=>{
    const connected=Boolean(currentUser?.discordConnected||currentUser?.discord_connected||currentUser?.discordDisplayName||currentUser?.discord_display_name);
    if(currentUser && connected){
      window.dispatchEvent(new CustomEvent("lucid:open-account"));
      return;
    }
    startOAuth("discord");
  });
  document.querySelectorAll("[data-community-oauth]").forEach(button=>button.addEventListener("click",()=>startOAuth(button.dataset.communityOauth)));
  logoutBtn?.addEventListener("click",async()=>{ await logoutCommunityUser(); window.dispatchEvent(new CustomEvent("lucid:logged-out")); });
  form?.addEventListener("submit",async e=>{
    e.preventDefault(); const status=document.getElementById("communityAuthStatus");
    const data=new FormData(form); const btn=form.querySelector("button[type=submit]");
    try{ btn.disabled=true; if(status) status.textContent=""; await login(data.get("email"),data.get("password")); closeModal(); }
    catch(err){ if(status) status.textContent=err.message||"로그인에 실패했습니다."; }
    finally{ btn.disabled=false; }
  });
  return loadCurrentUser();
}
