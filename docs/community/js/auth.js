import { API_BASE_URL } from "./config.js";
import { apiGet } from "./api.js";

const LINK_KEY = "lucid-community-analysis-link-v1";
let currentUser = null;

function apiUrl(path){ return `${API_BASE_URL.replace(/\/$/, "")}${path}`; }
function accountKey(user=currentUser){ return String(user?.id || user?.email || user?.displayName || "").trim(); }
function readLinks(){ try { const v=JSON.parse(localStorage.getItem(LINK_KEY)||"{}"); return v&&typeof v==="object"?v:{}; } catch(_){ return {}; } }
function writeLinks(v){ localStorage.setItem(LINK_KEY, JSON.stringify(v)); }

export function getCurrentUser(){ return currentUser; }
export function isCommunityAdmin(){ return String(currentUser?.role||"").toLowerCase()==="admin" || Boolean(currentUser?.isAdmin || currentUser?.is_admin); }
export function getAnalysisIdentity(){
  const key=accountKey(); if(!key) return null;
  const row=readLinks()[key];
  return row?.userId && row?.guildId ? row : null;
}
export function canAnalyzePlayer(userId,guildId){
  if(isCommunityAdmin()) return true;
  if(!currentUser) return false;
  const own=getAnalysisIdentity();
  return Boolean(own && String(own.userId)===String(userId) && String(own.guildId)===String(guildId));
}

function renderAuthActions(){
  const login=document.getElementById("communityLoginBtn");
  const discord=document.getElementById("communityLinkBtn");
  const reg=document.getElementById("communityRegisterIdBtn");
  if(!login||!discord) return;
  if(currentUser){
    login.textContent=currentUser.displayName || currentUser.email || "내 계정";
    login.classList.add("active-user");
    const connected=Boolean(currentUser.discordConnected||currentUser.discord_connected||currentUser.discordDisplayName||currentUser.discord_display_name);
    discord.textContent=connected?`Discord · ${currentUser.discordDisplayName||currentUser.discord_display_name||"연결됨"}`:"Discord 연결";
    discord.classList.toggle("active-user",connected);
    if(reg){
      reg.hidden=isCommunityAdmin();
      const own=getAnalysisIdentity();
      reg.textContent=own?`내 ID · ${own.name}`:"내 ID 등록";
      reg.classList.toggle("active-user",Boolean(own));
    }
  }else{
    login.textContent="로그인"; login.classList.remove("active-user");
    discord.textContent="Discord로 연결"; discord.classList.remove("active-user");
    if(reg) reg.hidden=true;
  }
  window.dispatchEvent(new CustomEvent("lucid:auth-changed",{detail:{user:currentUser,admin:isCommunityAdmin(),identity:getAnalysisIdentity()}}));
}

async function loadCurrentUser(){
  try{
    const res=await fetch(apiUrl("/api/auth/me"),{credentials:"include"});
    const data=await res.json().catch(()=>({}));
    currentUser=res.ok&&data.ok?data.user:null;
  }catch(_){ currentUser=null; }
  renderAuthActions();
  return currentUser;
}

function openModal(){ document.getElementById("communityAuthModal")?.removeAttribute("hidden"); }
function closeModal(){ document.getElementById("communityAuthModal")?.setAttribute("hidden",""); }

async function login(email,password){
  const res=await fetch(apiUrl("/api/auth/login"),{method:"POST",credentials:"include",headers:{"Content-Type":"application/json"},body:JSON.stringify({email,password})});
  const data=await res.json().catch(()=>({}));
  if(!res.ok||!data.ok) throw new Error(data.error||"로그인에 실패했습니다.");
  currentUser=data.user||null; renderAuthActions(); return currentUser;
}

async function logout(){
  try{ await fetch(apiUrl("/api/auth/logout"),{method:"POST",credentials:"include"}); }catch(_){ }
  currentUser=null; renderAuthActions();
}

async function registerOwnId(){
  if(!currentUser){ openModal(); return; }
  const input=window.prompt("내전에서 사용하는 Riot ID를 입력하세요. 예: its not you#shst");
  const q=String(input||"").trim(); if(!q) return;
  try{
    const data=await apiGet(`/api/community/search?q=${encodeURIComponent(q)}&limit=12`);
    const rows=data.players||[];
    const exact=rows.find(r=>String(r.name||"").toLowerCase()===q.toLowerCase() || String(r.matchedName||"").toLowerCase()===q.toLowerCase());
    const picked=exact || (rows.length===1?rows[0]:null);
    if(!picked){ window.alert("정확히 한 명을 찾지 못했습니다. Riot ID를 태그까지 입력해주세요."); return; }
    const key=accountKey(); const links=readLinks();
    links[key]={userId:String(picked.userId),guildId:String(picked.guildId),name:String(picked.name||q)};
    writeLinks(links); renderAuthActions();
    window.alert(`${picked.name} 계정을 내 분석 ID로 등록했습니다.`);
  }catch(e){ window.alert(e.message||"ID 등록에 실패했습니다."); }
}

export async function initCommunityAuth(){
  const loginBtn=document.getElementById("communityLoginBtn");
  const discordBtn=document.getElementById("communityLinkBtn");
  const registerBtn=document.getElementById("communityRegisterIdBtn");
  const form=document.getElementById("communityAuthForm");
  document.getElementById("communityAuthClose")?.addEventListener("click",closeModal);
  document.getElementById("communityAuthModal")?.addEventListener("click",e=>{ if(e.target?.id==="communityAuthModal") closeModal(); });
  loginBtn?.addEventListener("click",()=>{ if(currentUser){ if(window.confirm("로그아웃할까요?")) logout(); } else openModal(); });
  discordBtn?.addEventListener("click",()=>window.location.assign(apiUrl("/api/auth/oauth/discord/start")));
  registerBtn?.addEventListener("click",registerOwnId);
  form?.addEventListener("submit",async e=>{
    e.preventDefault(); const status=document.getElementById("communityAuthStatus");
    const data=new FormData(form); const btn=form.querySelector("button[type=submit]");
    try{ btn.disabled=true; if(status) status.textContent=""; await login(data.get("email"),data.get("password")); closeModal(); }
    catch(err){ if(status) status.textContent=err.message||"로그인에 실패했습니다."; }
    finally{ btn.disabled=false; }
  });
  return loadCurrentUser();
}
