import { API_BASE_URL } from "./config.js";
import { apiGet } from "./api.js";

let currentUser = null;
let riotAccounts = [];
let resolvedPlayers = [];

function apiUrl(path){ return `${API_BASE_URL.replace(/\/$/, "")}${path}`; }
function normalizeRiotId(value){ return String(value || "").trim().replace(/＃/g, "#"); }
function validRiotId(value){
  const text = normalizeRiotId(value);
  const split = text.lastIndexOf("#");
  if(split <= 0 || split >= text.length - 1) return false;
  const gameName = text.slice(0, split).trim();
  const tagLine = text.slice(split + 1).trim();
  return Boolean(gameName && tagLine && gameName.length <= 32 && tagLine.length <= 16);
}

export function getCurrentUser(){ return currentUser; }
export function isCommunityAdmin(){ return String(currentUser?.role||"").toLowerCase()==="admin" || Boolean(currentUser?.isAdmin || currentUser?.is_admin); }
export function isCommunityCoach(){ return String(currentUser?.role||"").toLowerCase()==="coach" || Boolean(currentUser?.isCoach || currentUser?.is_coach); }
export function canAnalyzeAllPlayers(){ return isCommunityAdmin() || isCommunityCoach(); }
export function getRiotAccounts(){ return [...riotAccounts]; }
export function getResolvedAnalysisPlayers(){ return [...resolvedPlayers]; }
export function getAnalysisIdentity(){ return resolvedPlayers[0] || null; }
export function canAnalyzePlayer(userId,guildId){
  if(canAnalyzeAllPlayers()) return true;
  if(!currentUser) return false;
  return resolvedPlayers.some(row => String(row.userId)===String(userId) && String(row.guildId)===String(guildId));
}

async function resolveRegisteredPlayers(){
  if(!currentUser || !riotAccounts.length){ resolvedPlayers=[]; return resolvedPlayers; }
  const found=[];
  const seen=new Set();
  await Promise.all(riotAccounts.map(async (riotId) => {
    try{
      const data=await apiGet(`/api/community/search?q=${encodeURIComponent(riotId)}&limit=20`);
      for(const row of (data.players||[])){
        const names=[row.name,row.matchedName].map(x=>normalizeRiotId(x).toLowerCase());
        if(!names.includes(normalizeRiotId(riotId).toLowerCase())) continue;
        const key=`${row.guildId}:${row.userId}`;
        if(seen.has(key)) continue;
        seen.add(key);
        found.push({userId:String(row.userId),guildId:String(row.guildId),name:String(row.name||riotId),riotId});
      }
    }catch(_){ }
  }));
  resolvedPlayers=found;
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
  riotAccounts=Array.isArray(currentUser?.riotAccounts) ? currentUser.riotAccounts.map(normalizeRiotId).filter(Boolean).slice(0,5) : [];
  await resolveRegisteredPlayers();
  renderAuthActions();
  return currentUser;
}

function openModal(){ document.getElementById("communityAuthModal")?.removeAttribute("hidden"); }
function closeModal(){ document.getElementById("communityAuthModal")?.setAttribute("hidden",""); }

async function login(email,password){
  const res=await fetch(apiUrl("/api/auth/login"),{method:"POST",credentials:"include",headers:{"Content-Type":"application/json"},body:JSON.stringify({email,password})});
  const data=await res.json().catch(()=>({}));
  if(!res.ok||!data.ok) throw new Error(data.error||"로그인에 실패했습니다.");
  currentUser=data.user||null;
  riotAccounts=Array.isArray(currentUser?.riotAccounts) ? currentUser.riotAccounts.map(normalizeRiotId).filter(Boolean).slice(0,5) : [];
  await resolveRegisteredPlayers();
  renderAuthActions();
  return currentUser;
}

export async function logoutCommunityUser(){
  try{ await fetch(apiUrl("/api/auth/logout"),{method:"POST",credentials:"include"}); }catch(_){ }
  currentUser=null; riotAccounts=[]; resolvedPlayers=[]; renderAuthActions();
}

export async function saveRiotAccounts(values=[]){
  if(!currentUser) throw new Error("로그인이 필요합니다.");
  const clean=[];
  for(const raw of values.slice(0,5)){
    const value=normalizeRiotId(raw);
    if(!value) continue;
    if(!validRiotId(value)) throw new Error(`Riot ID는 닉네임#태그 형식으로 입력해주세요: ${value}`);
    if(clean.some(x=>x.toLowerCase()===value.toLowerCase())) throw new Error("같은 Riot ID를 중복 등록할 수 없습니다.");
    clean.push(value);
  }
  const res=await fetch(apiUrl("/api/auth/riot-accounts"),{method:"PUT",credentials:"include",headers:{"Content-Type":"application/json"},body:JSON.stringify({accounts:clean})});
  const data=await res.json().catch(()=>({}));
  if(!res.ok||!data.ok) throw new Error(data.error==="invalid_riot_id"?"Riot ID 형식을 확인해주세요.":data.error||"Riot ID 저장에 실패했습니다.");
  currentUser=data.user||currentUser;
  riotAccounts=Array.isArray(currentUser?.riotAccounts)?currentUser.riotAccounts.map(normalizeRiotId).filter(Boolean).slice(0,5):clean;
  await resolveRegisteredPlayers();
  renderAuthActions();
  return getRiotAccounts();
}

export async function initCommunityAuth(){
  const loginBtn=document.getElementById("communityLoginBtn");
  const discordBtn=document.getElementById("communityLinkBtn");
  const logoutBtn=document.getElementById("communityLogoutBtn");
  const form=document.getElementById("communityAuthForm");
  document.getElementById("communityAuthClose")?.addEventListener("click",closeModal);
  document.getElementById("communityAuthModal")?.addEventListener("click",e=>{ if(e.target?.id==="communityAuthModal") closeModal(); });
  loginBtn?.addEventListener("click",()=>{ if(currentUser) window.dispatchEvent(new CustomEvent("lucid:open-account")); else openModal(); });
  discordBtn?.addEventListener("click",()=>window.location.assign(apiUrl("/api/auth/oauth/discord/start")));
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
