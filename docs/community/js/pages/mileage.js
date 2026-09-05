import { API_BASE_URL } from "../config.js?v=20260904d";
import { getCurrentUser } from "../auth.js?v=20260905admin2";

const esc=(value)=>String(value??"").replace(/[&<>"']/g,(ch)=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[ch]));
const apiUrl=(path)=>`${API_BASE_URL.replace(/\/$/,"")}${path}`;
const labels={MATCH_COMPLETE:"내전 완료",MATCH_WIN:"승리 보너스",VOICE_ACTIVITY:"음성 활동",WEEKLY_QUEST:"주간 퀘스트",INVITE_REWARD:"친구 초대",EVENT_PARTICIPATION:"이벤트 참가",SHOP_PURCHASE:"상점 구매",SHOP_REFUND:"상점 환불",ADMIN_GRANT:"운영진 지급",ADMIN_DEDUCT:"운영진 차감",MATCH_REVERT:"경기 취소"};
let selectedGuild="";
let availableGuilds=[];

async function request(path,{method="GET",body}={}){
  const response=await fetch(apiUrl(path),{method,credentials:"include",headers:body?{"Content-Type":"application/json"}:{},body:body?JSON.stringify(body):undefined});
  const data=await response.json().catch(()=>({}));
  if(!response.ok||!data.ok) throw new Error(data.error||"요청에 실패했습니다.");
  return data;
}

function rows(items,empty,render){return items?.length?items.map(render).join(""):`<p class="mileage-muted">${empty}</p>`;}
function numberInput(name,label,value,min=0){return `<label>${label}<input name="${name}" type="number" min="${min}" value="${Number(value||0)}"></label>`;}

function settingsCard(settings){
  const r=settings.rules||{};
  return `<section class="mileage-card mileage-admin"><h2>서버 적립 규칙</h2><p class="mileage-muted">초기 권장: 내전 완료 20P · 승리 5P · 음성 30분당 5P. 승리 보너스는 완료 보상의 20~30%가 안정적입니다.</p><form id="mileageSettingsForm" class="mileage-form">
    <label><span>마일리지 기능</span><select name="enabled"><option value="1" ${settings.enabled?"selected":""}>사용</option><option value="0" ${!settings.enabled?"selected":""}>중지</option></select></label>
    <label><span>상점</span><select name="shopEnabled"><option value="1" ${settings.shopEnabled?"selected":""}>사용</option><option value="0" ${!settings.shopEnabled?"selected":""}>중지</option></select></label>
    ${numberInput("daily_earn_cap","일일 자동 획득 상한 (0=무제한)",r.daily_earn_cap)}${numberInput("weekly_earn_cap","주간 자동 획득 상한 (0=무제한)",r.weekly_earn_cap)}
    ${numberInput("match_complete","내전 완료",r.match_complete)}${numberInput("match_win","승리 보너스",r.match_win)}
    ${numberInput("event_participation","이벤트 참가",r.event_participation)}${numberInput("voice_daily_cap","음성 일일 상한",r.voice_daily_cap)}
    ${numberInput("voice_minutes_per_unit","음성 지급 단위(분)",r.voice_minutes_per_unit,1)}${numberInput("voice_points_per_unit","음성 단위 포인트",r.voice_points_per_unit)}
    ${numberInput("voice_min_humans","최소 동시 인원",r.voice_min_humans,2)}${numberInput("voice_min_session_minutes","최소 연속 활동(분)",r.voice_min_session_minutes,1)}
    <label><span>음성 적립</span><select name="voice_enabled"><option value="1" ${r.voice_enabled?"selected":""}>사용</option><option value="0" ${!r.voice_enabled?"selected":""}>중지</option></select></label>
    <label><span>잠수 제외</span><select name="voice_exclude_self_deaf"><option value="1" ${r.voice_exclude_self_deaf?"selected":""}>제외</option><option value="0" ${!r.voice_exclude_self_deaf?"selected":""}>포함</option></select></label>
    <label><span>주간 퀘스트</span><select name="weekly_quests_enabled"><option value="1" ${r.weekly_quests_enabled?"selected":""}>사용</option><option value="0" ${!r.weekly_quests_enabled?"selected":""}>중지</option></select></label>
    <label><span>친구 초대 보상</span><select name="invite_enabled"><option value="1" ${r.invite_enabled?"selected":""}>사용</option><option value="0" ${!r.invite_enabled?"selected":""}>중지</option></select></label>
    ${numberInput("invite_match_target","초대 활동 조건(경기)",r.invite_match_target)}${numberInput("invite_voice_minutes_target","초대 활동 조건(음성 분)",r.invite_voice_minutes_target)}
    ${numberInput("invite_reward","초대 보상",r.invite_reward)}
    <label class="wide"><span>적립 음성 채널 ID (쉼표, 비우면 전체)</span><input name="voice_channel_ids" value="${esc((r.voice_channel_ids||[]).join(","))}"></label>
    <button class="wide" type="submit">규칙 저장</button></form></section>`;
}

function adminCards(data){
  const e=data.economy||{};
  return `<section class="mileage-card mileage-admin"><h2>경제 현황</h2><div class="mileage-list">
    <div class="mileage-row"><span>최근 7일 발행 / 소비</span><b>${Number(e.issued7d||0).toLocaleString()}P / ${Number(e.spent7d||0).toLocaleString()}P</b></div>
    <div class="mileage-row"><span>총 유통 / 1인 평균</span><b>${Number(e.circulation||0).toLocaleString()}P / ${Number(e.averageBalance||0).toLocaleString()}P</b></div>
    <div class="mileage-row"><span>예상 주간 획득<br><small>${esc(e.estimateBasis||"")}</small></span><b>${Number(e.estimatedWeekly||0).toLocaleString()}P</b></div>
    <div class="mileage-row"><span>최다 지급 / 인기 상품</span><b>${esc(labels[e.topRewardType]||e.topRewardType||"-")} / ${esc(e.topShopItem||"-")}</b></div>
  </div></section><section class="mileage-card mileage-admin"><h2>수동 지급·차감</h2><form id="mileageAdjustForm" class="mileage-form">
    <label>Discord 사용자 ID<input name="userId" required inputmode="numeric"></label><label>포인트 (+지급 / -차감)<input name="amount" type="number" required></label>
    <label class="wide">사유<input name="reason" required maxlength="500"></label><button class="wide" type="submit">반영</button></form></section>
  <section class="mileage-card mileage-admin"><h2>상품 등록</h2><form id="mileageItemForm" class="mileage-form">
    <label>상품명<input name="name" required maxlength="100"></label>${numberInput("price","가격",0)}
    <label>재고 (비우면 무제한)<input name="stock" type="number" min="0"></label><label>1인 구매 제한<input name="perUserLimit" type="number" min="1"></label>
    <label>지급 방식<select name="fulfillmentType"><option value="manual">수동 지급</option><option value="auto_role">역할 자동 지급</option><option value="game_analysis">경기 분석</option><option value="coaching">코칭</option><option value="coupon">쿠폰</option><option value="digital">디지털</option></select></label>
    <label>판매 상태<select name="active"><option value="1">판매</option><option value="0">중지</option></select></label>
    <label class="wide">설명<input name="description" maxlength="2000"></label><button class="wide" type="submit">상품 저장</button></form></section>
  <section class="mileage-card mileage-admin"><h2>주간 퀘스트 등록</h2><form id="mileageQuestForm" class="mileage-form">
    <label>퀘스트명<input name="name" required maxlength="100"></label>${numberInput("reward","완료 보상",100)}
    ${numberInput("match_count","내전 횟수",0)}${numberInput("voice_minutes","음성 활동(분)",0)}${numberInput("event_count","이벤트 참가 횟수",0)}
    <label class="wide">설명<input name="description" maxlength="1000"></label><button class="wide" type="submit">퀘스트 저장</button></form></section>
  <section class="mileage-card mileage-admin"><h2>구매 처리</h2><div class="mileage-list">${rows(data.adminPurchases,"처리할 구매가 없습니다.",(p)=>`<div class="mileage-row"><span><strong>${esc(p.itemName)}</strong><br><small>${esc(p.userId)} · ${esc(p.status)}</small></span><span><select data-purchase-status="${esc(p.id)}"><option value="processing">처리중</option><option value="fulfilled">지급완료</option><option value="cancelled">취소·환불</option><option value="refunded">환불완료</option></select> <button class="mileage-action" data-update-purchase="${esc(p.id)}">변경</button></span></div>`)}</div></section>
  <section class="mileage-card mileage-admin"><h2>관리자 지급 감사로그</h2><div class="mileage-list">${rows(data.transactions,"수동 지급 내역이 없습니다.",(t)=>`<div class="mileage-row"><span><strong>${esc(t.userId)}</strong><br><small>${esc(t.reason)} · 관리자 ${esc(t.administratorId)}</small></span><b class="${t.amount>0?"mileage-positive":"mileage-negative"}">${t.amount>0?"+":""}${Number(t.amount).toLocaleString()}P</b></div>`)}</div></section>`;
}

async function loadGuild(root,guild){
  root.innerHTML=`<div class="mileage-page"><section class="mileage-card">불러오는 중...</section></div>`;
  const base=`/api/mileage/guilds/${encodeURIComponent(guild.guildId)}`;
  try{
    const calls=[request(`${base}/wallet`),request(`${base}/shop`),request(`${base}/purchases`),request(`${base}/quests`)];
    if(guild.canManage) calls.push(request(`${base}/settings`),request(`${base}/admin/purchases`),request(`${base}/admin/transactions?type=ADMIN`),request(`${base}/admin/economy`));
    const [walletData,shopData,purchaseData,questData,settingsData,adminPurchaseData,transactionData,economyData]=await Promise.all(calls);
    const wallet=walletData.wallet;
    root.innerHTML=`<div class="mileage-page"><section class="mileage-head"><div><p class="section-kicker">SERVER MILEAGE</p><h1>${esc(guild.guildName)}</h1></div><label>서버 선택<select id="mileageGuildSelect">${availableGuilds.map(g=>`<option value="${esc(g.guildId)}" ${g.guildId===guild.guildId?"selected":""}>${esc(g.guildName)}${g.canManage?" · 관리":""}</option>`).join("")}</select></label><div><small>현재 잔액</small><div class="mileage-balance">${Number(wallet.balance).toLocaleString()}P</div></div></section>
      <div class="mileage-grid"><section class="mileage-card"><h2>서버 상점</h2><div class="mileage-list">${rows(shopData.items,"판매 중인 상품이 없습니다.",(item)=>`<div class="mileage-row"><span><strong>${esc(item.name)}</strong><br><small>${esc(item.description)} · 재고 ${item.stock??"무제한"}</small></span><span><b>${Number(item.price).toLocaleString()}P</b> <button class="mileage-buy" data-buy="${esc(item.id)}">구매</button></span></div>`)}</div></section>
      <section class="mileage-card"><h2>최근 거래</h2><div class="mileage-list">${rows(wallet.transactions,"거래내역이 없습니다.",(t)=>`<div class="mileage-row"><span>${esc(labels[t.type]||t.type)}<br><small>${esc(t.reason)}</small></span><b class="${t.amount>0?"mileage-positive":"mileage-negative"}">${t.amount>0?"+":""}${Number(t.amount).toLocaleString()}P</b></div>`)}</div></section>
      <section class="mileage-card"><h2>내 구매내역</h2><div class="mileage-list">${rows(purchaseData.purchases,"구매내역이 없습니다.",(p)=>`<div class="mileage-row"><span>${esc(p.itemName)}<br><small>${esc(p.status)}${p.cancellationReason?` · ${esc(p.cancellationReason)}`:""}</small></span><b>${Number(p.price).toLocaleString()}P</b></div>`)}</div></section>
      <section class="mileage-card"><h2>주간 퀘스트</h2><div class="mileage-list">${rows(questData.quests,"진행 중인 퀘스트가 없습니다.",(q)=>`<div class="mileage-row"><span>${esc(q.name)}<br><small>${esc(q.description)}</small></span><b>${Number(q.reward).toLocaleString()}P</b></div>`)}</div></section></div>
      ${guild.canManage?`<div class="mileage-grid">${settingsCard(settingsData.settings)}${adminCards({adminPurchases:adminPurchaseData.purchases,transactions:transactionData.transactions,economy:economyData.summary})}</div>`:""}<div id="mileageStatus" class="mileage-status"></div></div>`;
    bindGuild(root,guild);
  }catch(error){root.innerHTML=`<section class="mileage-card"><h2>마일리지를 불러오지 못했습니다.</h2><p>${esc(error.message)}</p></section>`;}
}

function bindGuild(root,guild){
  const base=`/api/mileage/guilds/${encodeURIComponent(guild.guildId)}`;
  const status=root.querySelector("#mileageStatus");
  const run=async(task)=>{try{if(status)status.textContent="처리 중...";await task();await loadGuild(root,guild);}catch(error){if(status)status.textContent=error.message;}};
  root.querySelector("#mileageGuildSelect")?.addEventListener("change",(event)=>{selectedGuild=event.currentTarget.value;loadGuild(root,availableGuilds.find(g=>g.guildId===selectedGuild));});
  root.querySelectorAll("[data-buy]").forEach((button)=>{const requestKey=crypto.randomUUID();button.addEventListener("click",()=>{if(button.disabled||!confirm("이 상품을 구매할까요?"))return;button.disabled=true;run(()=>request(`${base}/purchases`,{method:"POST",body:{itemId:button.dataset.buy,requestKey}}));});});
  root.querySelector("#mileageSettingsForm")?.addEventListener("submit",(event)=>{event.preventDefault();const form=new FormData(event.currentTarget);const rules={};for(const key of ["daily_earn_cap","weekly_earn_cap","match_complete","match_win","event_participation","voice_daily_cap","voice_minutes_per_unit","voice_points_per_unit","voice_min_humans","voice_min_session_minutes","invite_match_target","invite_voice_minutes_target","invite_reward"])rules[key]=Number(form.get(key)||0);for(const key of ["voice_enabled","voice_exclude_self_deaf","weekly_quests_enabled","invite_enabled"])rules[key]=form.get(key)==="1";rules.voice_channel_ids=String(form.get("voice_channel_ids")||"").split(",").map(x=>x.trim()).filter(Boolean);run(()=>request(`${base}/settings`,{method:"PATCH",body:{enabled:form.get("enabled")==="1",shopEnabled:form.get("shopEnabled")==="1",rules}}));});
  root.querySelector("#mileageAdjustForm")?.addEventListener("submit",(event)=>{event.preventDefault();const form=new FormData(event.currentTarget),amount=Number(form.get("amount")||0);if(Math.abs(amount)>=10000&&!confirm(`${amount.toLocaleString()}P를 반영합니다. 계속할까요?`))return;run(()=>request(`${base}/admin/adjustments`,{method:"POST",body:{userId:form.get("userId"),amount,reason:form.get("reason"),requestKey:crypto.randomUUID()}}));});
  root.querySelector("#mileageItemForm")?.addEventListener("submit",(event)=>{event.preventDefault();const form=new FormData(event.currentTarget);run(()=>request(`${base}/shop/items`,{method:"POST",body:{name:form.get("name"),description:form.get("description"),price:Number(form.get("price")||0),stock:form.get("stock"),perUserLimit:form.get("perUserLimit"),fulfillmentType:form.get("fulfillmentType"),active:form.get("active")==="1"}}));});
  root.querySelector("#mileageQuestForm")?.addEventListener("submit",(event)=>{event.preventDefault();const form=new FormData(event.currentTarget);run(()=>request(`${base}/quests`,{method:"POST",body:{name:form.get("name"),description:form.get("description"),reward:Number(form.get("reward")||0),conditions:{match_count:Number(form.get("match_count")||0),voice_seconds:Number(form.get("voice_minutes")||0)*60,event_count:Number(form.get("event_count")||0)},active:true}}));});
  root.querySelectorAll("[data-update-purchase]").forEach((button)=>button.addEventListener("click",()=>{const purchaseId=button.dataset.updatePurchase,target=root.querySelector(`[data-purchase-status="${CSS.escape(purchaseId)}"]`),next=target?.value||"";const reason=["cancelled","refunded"].includes(next)?prompt("취소/환불 사유를 입력해주세요.",""):"";if(["cancelled","refunded"].includes(next)&&!reason)return;run(()=>request(`${base}/admin/purchases/${encodeURIComponent(purchaseId)}`,{method:"PATCH",body:{status:next,reason}}));}));
}

export async function renderMileage(){
  const root=document.getElementById("mileageRoot");if(!root)return;
  const user=getCurrentUser();
  if(!user){root.innerHTML=`<section class="mileage-card">로그인이 필요합니다.</section>`;return;}
  try{
    const data=await request("/api/mileage/guilds"),guilds=data.guilds||[];availableGuilds=guilds;
    if(!guilds.length){root.innerHTML=`<section class="mileage-card"><h2>사용 가능한 서버가 없습니다.</h2><p class="mileage-muted">Discord 계정을 연결하고, 해당 서버에서 마일리지를 한 번 이상 받거나 서버 관리자로 등록되어야 합니다.</p></section>`;return;}
    if(!guilds.some(g=>g.guildId===selectedGuild))selectedGuild=guilds[0].guildId;
    await loadGuild(root,guilds.find(g=>g.guildId===selectedGuild));
  }catch(error){root.innerHTML=`<section class="mileage-card"><h2>Discord 연결을 확인해주세요.</h2><p>${esc(error.message)}</p></section>`;}
}
