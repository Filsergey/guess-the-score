(()=>{
const style=document.createElement('style');
style.textContent=`
#leaguesView .league-card.has-delete{padding-right:108px!important}
#leaguesView .league-delete{display:none!important}
#leaguesView .league-edit.gts-league-manage{right:11px!important;min-width:84px;height:29px;padding:0 9px!important;font-size:8.5px!important;border-radius:9px!important}
#leaguesView .league-edit.gts-league-manage:active{transform:translateY(-50%) scale(.97)}
.gts-manage-head{display:flex;align-items:center;gap:11px;margin-bottom:15px}.gts-manage-head .gts-manage-emblem{width:46px;height:46px;flex:0 0 46px;border-radius:50%;display:flex;align-items:center;justify-content:center;background:#10263a;border:1px solid #365772;overflow:hidden;font-size:23px}.gts-manage-head .gts-manage-emblem img{width:100%;height:100%;object-fit:contain;padding:7px}.gts-manage-head strong{display:block;font-size:18px}.gts-manage-sub{font-size:11px;color:#87a1b8;margin-top:3px}
.gts-manage-section{padding:14px 0;border-top:1px solid #172b40}.gts-manage-section:first-of-type{border-top:0}.gts-manage-section-title{font-size:12px;font-weight:900;color:#dcecff;margin-bottom:9px}.gts-manage-section-note{font-size:10px;line-height:1.45;color:#8298ae;margin:-3px 0 10px}
.gts-manage-name-row{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:8px}.gts-manage-input{min-width:0;width:100%;border:1px solid #294963;background:#06121e;color:#fff;border-radius:12px;padding:11px 12px;font-size:14px}.gts-manage-small-btn{border:1px solid #2a5980;background:#102c45;color:#dcedfb;border-radius:11px;padding:0 12px;font-size:10px;font-weight:850;white-space:nowrap}.gts-manage-small-btn:disabled{opacity:.55}
.gts-invite-box{display:grid;grid-template-columns:minmax(0,1fr) auto auto;gap:7px;align-items:stretch}.gts-invite-code{display:flex;align-items:center;justify-content:center;min-height:42px;border:1px solid #294963;background:#06121e;border-radius:12px;color:#70e5ae;font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:16px;font-weight:900;letter-spacing:2px;padding:8px 10px;user-select:all}.gts-invite-action{border:1px solid #294963;background:#10263b;color:#dcecff;border-radius:11px;padding:0 10px;font-size:10px;font-weight:850}
.gts-theme-asset{display:grid;grid-template-columns:68px minmax(0,1fr);gap:11px;align-items:center;padding:10px 0;border-bottom:1px solid #132a40}.gts-theme-asset:last-child{border-bottom:0}.gts-theme-preview{width:68px;height:54px;border:1px solid #294963;border-radius:11px;background:#06121e;display:flex;align-items:center;justify-content:center;overflow:hidden;color:#7890a7;font-size:9px;text-align:center}.gts-theme-preview.icon{height:68px}.gts-theme-preview img{width:100%;height:100%;object-fit:cover}.gts-theme-preview.icon img{object-fit:contain;padding:7px}.gts-theme-title{font-size:12px;font-weight:850;margin-bottom:6px}.gts-theme-file{display:inline-block;border:1px solid #2a5980;background:#102c45;color:#dcedfb;border-radius:10px;padding:8px 10px;font-size:10px;font-weight:800;cursor:pointer}.gts-theme-file input{display:none}.gts-theme-reset{border:0;background:transparent;color:#78a9d4;font-size:9px;padding:7px 5px}
.gts-manage-danger{width:100%;border:1px solid rgba(222,73,91,.48);background:rgba(126,31,43,.22);color:#ff9aa3;border-radius:13px;padding:12px;font-size:11px;font-weight:900}.gts-manage-close{margin-top:4px}
@media(max-width:390px){#leaguesView .league-card.has-delete{padding-right:101px!important}#leaguesView .league-edit.gts-league-manage{min-width:78px;padding:0 7px!important;font-size:8px!important}.gts-invite-box{grid-template-columns:1fr 1fr}.gts-invite-code{grid-column:1/-1}.gts-manage-name-row{grid-template-columns:1fr}.gts-manage-small-btn{min-height:40px}}
`;
document.head.appendChild(style);

const esc=s=>String(s??'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[m]));
const seasonLabel=s=>{s=Number(s)||2026;return `${s}/${String(s+1).slice(-2)}`};
const leagues=()=>window.getLeagues?.()||[];
const getLeague=id=>leagues().find(x=>Number(x.id)===Number(id));
const canManage=l=>l?.member_role==='owner'||window.GTS?.me?.role==='superadmin';
function tournamentFor(l){const ts=window.getTournaments?.()||[];return ts.find(t=>Number(t.id)===Number(l?.tournament_id)&&Number(t.season)===Number(l?.tournament_season))||ts.find(t=>Number(t.id)===Number(l?.tournament_id))||null}
function cardLeagueId(card,index){const direct=Number(card.dataset.leagueId||0);if(direct)return direct;const l=leagues()[index];return Number(l?.id||0)}
function selectLeague(id){id=Number(id);if(!id)return;if(typeof window.selectLeagueOnly==='function')window.selectLeagueOnly(id);else window.chooseLeague?.(id)}
function fixLegacyTournamentLogo(img,l){if(!img||!String(img.src||'').includes('media.api-sports.io'))return;const t=tournamentFor(l);if(t?.logo_url)img.src=t.logo_url}
function decorate(){
 const cards=[...document.querySelectorAll('#leaguesView .league-card')];
 cards.forEach((card,index)=>{
  const id=cardLeagueId(card,index),l=getLeague(id)||leagues()[index];if(!id||!l)return;
  card.dataset.leagueId=String(id);
  card.onclick=e=>{if(e.target.closest('.league-edit,.gts-league-manage'))return;e.preventDefault();selectLeague(id)};
  const del=card.querySelector('.league-delete');if(del)del.remove();
  const edit=card.querySelector('.league-edit');
  if(canManage(l)){
   const btn=edit||document.createElement('span');
   if(!edit)card.appendChild(btn);
   btn.className='league-edit gts-league-manage';btn.setAttribute('role','button');btn.setAttribute('aria-label','Управление лигой');
   if(btn.textContent!=='Управление')btn.textContent='Управление';
   btn.onclick=e=>{e.preventDefault();e.stopPropagation();openLeagueManagement(id)};
  }else if(edit){edit.remove()}
  fixLegacyTournamentLogo(card.querySelector('.league-emblem img'),l);
 });
 const selected=getLeague(window.GTS?.leagueId),headerImg=document.querySelector('.top #leagueSelect img');
 if(selected)fixLegacyTournamentLogo(headerImg,selected);
}

async function loadTheme(id){try{return await window.GTS.api(`/api/leagues/${id}/theme`)}catch{return {icon:null,background:null,tournament_background:null}}}
function defaultLeagueLogo(l){const t=tournamentFor(l);return t?.logo_url||null}
function emblem(l,theme){const src=theme?.icon||defaultLeagueLogo(l);return src?`<img src="${esc(src)}" alt="">`:'⚽'}
function themeAsset(kind,label,id,theme){const data=theme?.[kind];return `<div class="gts-theme-asset"><div class="gts-theme-preview ${kind==='icon'?'icon':''}">${data?`<img src="${data}" alt="">`:'Стандартный'}</div><div><div class="gts-theme-title">${label}</div><label class="gts-theme-file">Выбрать файл<input type="file" accept="image/png,image/jpeg,image/webp" onchange="gtsLeagueManagementThemeFile('${kind}',this,${Number(id)})"></label>${data?`<button class="gts-theme-reset" onclick="gtsLeagueManagementThemeReset('${kind}',${Number(id)})">Вернуть стандартный</button>`:''}</div></div>`}

async function openLeagueManagement(id){
 const l=getLeague(id);if(!l)return;if(!canManage(l))return window.toast?.('Управление доступно владельцу лиги');
 const t=tournamentFor(l),theme=await loadTheme(id),code=String(l.invite_code||'').trim().toUpperCase();
 window.openSheet?.(`<div class="gts-manage-head"><div class="gts-manage-emblem">${emblem(l,theme)}</div><div><strong>Управление лигой</strong><div class="gts-manage-sub">${esc(l.name)} · ${esc(t?.name||'SStats')} ${seasonLabel(l.tournament_season)}</div></div></div>
 <div class="gts-manage-section"><div class="gts-manage-section-title">Название лиги</div><div class="gts-manage-name-row"><input id="gtsLeagueManageName" class="gts-manage-input" maxlength="120" value="${esc(l.name)}"><button id="gtsLeagueManageNameBtn" class="gts-manage-small-btn" onclick="gtsSaveLeagueName(${Number(id)})">Сохранить</button></div></div>
 <div class="gts-manage-section"><div class="gts-manage-section-title">Код приглашения</div><div class="gts-manage-section-note">Отправь этот код другу. Он сможет подключиться через «Вступить по коду».</div><div class="gts-invite-box"><div class="gts-invite-code">${esc(code||'—')}</div><button class="gts-invite-action" onclick="gtsCopyLeagueInvite(${Number(id)})">Копировать</button><button class="gts-invite-action" onclick="gtsShareLeagueInvite(${Number(id)})">Поделиться</button></div></div>
 <div class="gts-manage-section"><div class="gts-manage-section-title">Оформление</div><div class="gts-manage-section-note">Иконка, общий фон и фон блока прогноза будут одинаковыми для всех участников этой лиги.</div>${themeAsset('icon','Иконка лиги',id,theme)}${themeAsset('background','Фон интерфейса',id,theme)}${themeAsset('tournament_background','Фон «Прогноза на турнир»',id,theme)}</div>
 <div class="gts-manage-section"><div class="gts-manage-section-title">Удаление</div><button class="gts-manage-danger" onclick="openDeleteLeague(${Number(id)})">Удалить лигу</button></div>
 <button class="close gts-manage-close" onclick="closeSheet()">Готово</button>`);
}

async function saveLeagueName(id){
 const l=getLeague(id),input=document.getElementById('gtsLeagueManageName'),btn=document.getElementById('gtsLeagueManageNameBtn'),name=String(input?.value||'').trim();
 if(!l||!canManage(l))return;if(name.length<2)return window.toast?.('Название должно быть не короче 2 символов');
 if(btn){btn.disabled=true;btn.textContent='Сохраняем…'}
 try{await window.GTS.api(`/api/leagues/${id}`,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({name})});await window.loadLeagues?.();window.renderLeagues?.();window.toast?.('Название лиги изменено');await openLeagueManagement(id)}catch(e){window.toast?.(e.message||'Не удалось изменить название');if(btn){btn.disabled=false;btn.textContent='Сохранить'}}
}
function fallbackCopy(text){const ta=document.createElement('textarea');ta.value=text;ta.style.position='fixed';ta.style.opacity='0';document.body.appendChild(ta);ta.select();try{document.execCommand('copy')}finally{ta.remove()}}
async function copyLeagueInvite(id){const l=getLeague(id),code=String(l?.invite_code||'').trim().toUpperCase();if(!code)return window.toast?.('Код приглашения не найден');try{if(navigator.clipboard?.writeText)await navigator.clipboard.writeText(code);else fallbackCopy(code);window.toast?.('Код скопирован')}catch{fallbackCopy(code);window.toast?.('Код скопирован')}}
async function shareLeagueInvite(id){const l=getLeague(id),code=String(l?.invite_code||'').trim().toUpperCase();if(!l||!code)return window.toast?.('Код приглашения не найден');const text=`Вступай в мою лигу «${l.name}» в «Угадай счёт». Код лиги: ${code}`;try{if(navigator.share){await navigator.share({title:`Лига «${l.name}»`,text});return}const tg=window.Telegram?.WebApp;if(tg?.openTelegramLink){tg.openTelegramLink(`https://t.me/share/url?url=&text=${encodeURIComponent(text)}`);return}if(navigator.clipboard?.writeText)await navigator.clipboard.writeText(text);else fallbackCopy(text);window.toast?.('Приглашение скопировано')}catch(e){if(e?.name!=='AbortError'){fallbackCopy(text);window.toast?.('Приглашение скопировано')}}}

function compressImage(file,maxW,maxH,quality){return new Promise((resolve,reject)=>{if(!file||!file.type.startsWith('image/'))return reject(new Error('Выбери изображение'));const reader=new FileReader();reader.onerror=()=>reject(new Error('Не удалось прочитать файл'));reader.onload=()=>{const img=new Image();img.onerror=()=>reject(new Error('Не удалось открыть изображение'));img.onload=()=>{let w=img.naturalWidth||img.width,h=img.naturalHeight||img.height;const k=Math.min(1,maxW/w,maxH/h);w=Math.max(1,Math.round(w*k));h=Math.max(1,Math.round(h*k));const c=document.createElement('canvas');c.width=w;c.height=h;c.getContext('2d').drawImage(img,0,0,w,h);resolve(c.toDataURL('image/webp',quality))};img.src=String(reader.result||'')};reader.readAsDataURL(file)})}
async function saveTheme(kind,input,id){const file=input?.files?.[0];if(!file)return;try{let maxW=1600,maxH=2200,quality=.82;if(kind==='icon'){maxW=320;maxH=320;quality=.92}else if(kind==='tournament_background'){maxW=1400;maxH=700;quality=.86}const data=await compressImage(file,maxW,maxH,quality),theme=await loadTheme(id),next={icon:theme.icon||null,background:theme.background||null,tournament_background:theme.tournament_background||null};next[kind]=data;await window.GTS.api(`/api/leagues/${id}/theme`,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(next)});selectLeague(id);window.toast?.('Оформление обновлено');setTimeout(()=>openLeagueManagement(id),80)}catch(e){window.toast?.(e.message||'Не удалось сохранить оформление')}}
async function resetTheme(kind,id){try{const theme=await loadTheme(id),next={icon:theme.icon||null,background:theme.background||null,tournament_background:theme.tournament_background||null};next[kind]=null;await window.GTS.api(`/api/leagues/${id}/theme`,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(next)});selectLeague(id);window.toast?.('Оформление сброшено');setTimeout(()=>openLeagueManagement(id),80)}catch(e){window.toast?.(e.message||'Не удалось сбросить оформление')}}

window.openLeagueManagement=openLeagueManagement;
window.gtsSaveLeagueName=saveLeagueName;
window.gtsCopyLeagueInvite=copyLeagueInvite;
window.gtsShareLeagueInvite=shareLeagueInvite;
window.gtsLeagueManagementThemeFile=saveTheme;
window.gtsLeagueManagementThemeReset=resetTheme;

const observer=new MutationObserver(()=>decorate());
function install(){const root=document.getElementById('leaguesView');if(root&&!root.dataset.gtsManagementObserved){root.dataset.gtsManagementObserved='1';observer.observe(root,{childList:true,subtree:true})}decorate()}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',()=>setTimeout(install,0));else setTimeout(install,0);
document.addEventListener('gts:ready',()=>setTimeout(install,150));document.addEventListener('gts:league-change',()=>setTimeout(decorate,80));
setInterval(install,700);
})();