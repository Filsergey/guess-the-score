(()=>{
const tg=window.Telegram?.WebApp;
let handling=false,handled=false;
const esc=s=>String(s??'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[m]));
const seasonLabel=s=>{s=Number(s)||2026;return `${s}/${String(s+1).slice(-2)}`};

const style=document.createElement('style');
style.textContent=`
.gts-invite-confirm{text-align:center;color:var(--gts-text,#fff)}
.gts-invite-confirm-icon{width:58px;height:58px;border-radius:50%;margin:2px auto 12px;display:flex;align-items:center;justify-content:center;font-size:28px;background:color-mix(in srgb,var(--gts-panel,#10263b) 84%,var(--gts-accent,#24a4ff) 16%);border:1px solid rgba(var(--gts-accent-rgb,36,164,255),.36)}
.gts-invite-confirm-name{font-size:21px;font-weight:900;line-height:1.2;margin:5px 0 7px}
.gts-invite-confirm-meta{font-size:11px;color:var(--gts-muted,#8da1b6);margin-bottom:18px}
.gts-invite-confirm .save{background:var(--gts-accent,#268fff)!important;color:#fff!important}
`;
document.head.appendChild(style);

function startParam(){
 const fromTelegram=String(tg?.initDataUnsafe?.start_param||'').trim();
 if(fromTelegram)return fromTelegram;
 try{return String(new URLSearchParams(location.search).get('tgWebAppStartParam')||'').trim()}catch{return ''}
}
function inviteCode(){const m=startParam().match(/^league_([A-Z0-9]{4,12})$/i);return m?m[1].toUpperCase():''}
function leagues(){return window.getLeagues?.()||window.GTS?.leagues||[]}

async function focusLeague(id){
 await window.loadLeagues?.();
 const found=leagues().find(x=>Number(x.id)===Number(id));
 if(found)window.chooseLeague?.(found.id);
 if(typeof window.showLeagues==='function')window.showLeagues();else window.showView?.('leagues');
}

async function acceptInvite(code){
 const btn=document.getElementById('gtsAcceptInviteBtn');
 if(btn){btn.disabled=true;btn.textContent='Подключаем…'}
 try{
  const league=await window.GTS.api('/api/leagues/join',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({invite_code:code})});
  await focusLeague(league.id);
  window.closeSheet?.();
  window.toast?.(`Ты в лиге «${league.name}»`);
 }catch(e){
  window.toast?.(e.message||'Не удалось вступить в лигу');
  if(btn){btn.disabled=false;btn.textContent='Вступить в лигу'}
 }
}
window.gtsAcceptLeagueInvite=acceptInvite;

async function handleStartInvite(){
 if(handling||handled)return;
 const code=inviteCode();
 if(!code||!window.GTS?.api||!window.GTS?.me)return;
 handling=true;
 try{
  const data=await window.GTS.api(`/api/auth/league-invite/${encodeURIComponent(code)}`);
  handled=true;
  const league=data?.league||{};
  if(data?.already_member){
   await focusLeague(league.id);
   window.toast?.(`Ты уже в лиге «${league.name||''}»`);
   return;
  }
  const count=Number(league.member_count)||0;
  const memberWord=count%10===1&&count%100!==11?'участник':count%10>=2&&count%10<=4&&(count%100<12||count%100>14)?'участника':'участников';
  window.openSheet?.(`<div class="gts-invite-confirm"><div class="gts-invite-confirm-icon">👥</div><div class="sheet-title">Вступить в лигу?</div><div class="gts-invite-confirm-name">${esc(league.name||'Лига')}</div><div class="gts-invite-confirm-meta">${esc(league.tournament_name||'SStats')} · ${seasonLabel(league.tournament_season)} · ${count} ${memberWord}</div><button id="gtsAcceptInviteBtn" class="save" onclick="gtsAcceptLeagueInvite('${esc(code)}')">Вступить в лигу</button><button class="close" onclick="closeSheet()">Не сейчас</button></div>`);
 }catch(e){
  handled=true;
  window.toast?.(e.message||'Приглашение недействительно');
 }finally{handling=false}
}

async function copyText(text){
 if(navigator.clipboard?.writeText){await navigator.clipboard.writeText(text);return}
 const ta=document.createElement('textarea');ta.value=text;ta.style.position='fixed';ta.style.opacity='0';document.body.appendChild(ta);ta.select();try{document.execCommand('copy')}finally{ta.remove()}
}

async function shareLeagueInvite(id){
 const league=leagues().find(x=>Number(x.id)===Number(id));
 if(!league)return window.toast?.('Лига не найдена');
 try{
  const data=await window.GTS.api(`/api/auth/league-invite-link/${Number(id)}`);
  const url=String(data?.url||'');
  if(!url)throw new Error('Не удалось сформировать ссылку приглашения');
  const text=`Вступай в мою лигу «${league.name}» в «Угадай счёт».`;
  if(tg?.openTelegramLink){
   tg.openTelegramLink(`https://t.me/share/url?url=${encodeURIComponent(url)}&text=${encodeURIComponent(text)}`);
   return;
  }
  if(navigator.share){await navigator.share({title:`Лига «${league.name}»`,text,url});return}
  await copyText(`${text}\n${url}`);
  window.toast?.('Ссылка-приглашение скопирована');
 }catch(e){
  if(e?.name==='AbortError')return;
  window.toast?.(e.message||'Не удалось поделиться приглашением');
 }
}

function installShareOverride(){window.gtsShareLeagueInvite=shareLeagueInvite}
window.gtsShareLeagueInvite=shareLeagueInvite;
document.addEventListener('gts:ready',()=>setTimeout(handleStartInvite,80));
document.addEventListener('DOMContentLoaded',()=>{installShareOverride();setTimeout(installShareOverride,250);setTimeout(handleStartInvite,700)});
setTimeout(()=>{installShareOverride();handleStartInvite()},1200);
})();