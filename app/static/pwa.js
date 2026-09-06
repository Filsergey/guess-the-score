(()=>{
const inTelegram=Boolean(window.Telegram?.WebApp?.initData);
if(inTelegram)return;

function ensureLink(rel,href,attrs={}){
  let el=document.querySelector(`link[rel="${rel}"]`);
  if(!el){el=document.createElement('link');el.rel=rel;document.head.appendChild(el)}
  el.href=href;Object.entries(attrs).forEach(([k,v])=>el.setAttribute(k,v));return el;
}
function ensureMeta(name,content){
  let el=document.querySelector(`meta[name="${name}"]`);
  if(!el){el=document.createElement('meta');el.name=name;document.head.appendChild(el)}
  el.content=content;return el;
}

ensureLink('manifest','/static/manifest.webmanifest?v=2');
ensureMeta('apple-mobile-web-app-capable','yes');
ensureMeta('apple-mobile-web-app-status-bar-style','black-translucent');
ensureMeta('apple-mobile-web-app-title','Угадай счёт');
ensureMeta('mobile-web-app-capable','yes');

const style=document.createElement('style');
style.textContent=`
html{-webkit-text-size-adjust:100%;text-size-adjust:100%}
html[data-gts-pwa] body{width:100%;min-width:0;overflow-x:hidden}
html[data-gts-pwa] .app{width:100%;max-width:560px;min-height:100dvh}
html[data-gts-pwa] .top{margin-top:-14px!important;top:env(safe-area-inset-top)!important}
@media(max-width:390px){html[data-gts-pwa] .top{margin-left:-10px!important;margin-right:-10px!important}}
.gts-pwa-nudge{position:fixed;left:50%;bottom:calc(78px + env(safe-area-inset-bottom));transform:translateX(-50%);width:min(520px,calc(100% - 24px));z-index:18;display:flex;align-items:center;gap:10px;padding:11px 12px;border-radius:16px;background:color-mix(in srgb,var(--gts-panel,#10263b) 94%,#000 6%);border:1px solid rgba(var(--gts-accent-rgb,36,164,255),.34);box-shadow:0 14px 36px rgba(0,0,0,.28);color:var(--gts-text,#f5f9ff)}
.gts-pwa-nudge-copy{min-width:0;flex:1}.gts-pwa-nudge-copy strong{display:block;font-size:12px;font-weight:900}.gts-pwa-nudge-copy span{display:block;margin-top:2px;font-size:9px;line-height:1.35;color:var(--gts-muted,#a9c3da)}
.gts-pwa-nudge button{flex:0 0 auto;border:1px solid var(--gts-accent,#24a4ff);background:var(--gts-accent,#24a4ff);color:#fff;border-radius:11px;padding:9px 11px;font-size:10px;font-weight:900}.gts-pwa-nudge .gts-pwa-x{border:0;background:transparent;color:var(--gts-muted,#a9c3da);padding:6px;font-size:16px}
`;
document.head.appendChild(style);

let standalone=window.matchMedia?.('(display-mode: standalone)')?.matches||window.navigator.standalone===true;
document.documentElement.dataset.gtsPwa=standalone?'standalone':'browser';
const isIOS=/iPhone|iPad|iPod/i.test(navigator.userAgent)||(/Macintosh/i.test(navigator.userAgent)&&navigator.maxTouchPoints>1);

const api={standalone,registration:null,ready:null};
window.GTSPWA=api;
if('serviceWorker' in navigator){
  api.ready=navigator.serviceWorker.register('/static/service-worker.js?v=3').then(reg=>{
    api.registration=reg;
    return reg;
  }).catch(()=>null);
}

function authHeaders(){const token=localStorage.getItem('access_token')||'';return token?{Authorization:`Bearer ${token}`}:{}}
async function apiFetch(url,opts={}){
  if(window.GTS?.api)return window.GTS.api(url,opts);
  const r=await fetch(url,{...opts,headers:{...(opts.headers||{}),...authHeaders()}});let d={};try{d=await r.json()}catch{}
  if(!r.ok)throw new Error(d.detail||`HTTP ${r.status}`);return d;
}
function urlBase64ToUint8Array(value){
  const padding='='.repeat((4-value.length%4)%4),base64=(value+padding).replace(/-/g,'+').replace(/_/g,'/'),raw=atob(base64),out=new Uint8Array(raw.length);for(let i=0;i<raw.length;i++)out[i]=raw.charCodeAt(i);return out;
}
function dismissNudge(){document.querySelector('.gts-pwa-nudge')?.remove()}
function showNudge(title,text,buttonLabel,onClick){
  dismissNudge();const el=document.createElement('div');el.className='gts-pwa-nudge';el.innerHTML=`<div class="gts-pwa-nudge-copy"><strong>${title}</strong><span>${text}</span></div><button class="gts-pwa-action">${buttonLabel}</button><button class="gts-pwa-x" aria-label="Закрыть">×</button>`;el.querySelector('.gts-pwa-action').onclick=onClick;el.querySelector('.gts-pwa-x').onclick=dismissNudge;document.body.appendChild(el);
}
function installHelp(){
  dismissNudge();
  if(window.openSheet)window.openSheet(`<div class="sheet-title">Установить «Угадай счёт»</div><div class="sheet-note" style="text-align:left;line-height:1.65">1. Открой эту страницу в Safari.<br>2. Нажми «Поделиться».<br>3. Выбери «На экран Домой».<br>4. Оставь включённым «Открыть как веб-приложение» и нажми «Добавить».</div><button class="save secondary" onclick="closeSheet()">Понятно</button>`);
  else alert('Safari → Поделиться → На экран Домой → Добавить');
}
async function enableNotifications(){
  try{
    const reg=await api.ready;if(!reg||!('PushManager' in window)||!('Notification' in window))throw new Error('Push-уведомления не поддерживаются на этом устройстве');
    const cfg=await apiFetch('/api/auth/push/config');if(!cfg.configured||!cfg.public_key)throw new Error('Push-уведомления ещё не настроены на сервере');
    const permission=await Notification.requestPermission();if(permission!=='granted')throw new Error('Разрешение на уведомления не выдано');
    let sub=await reg.pushManager.getSubscription();
    if(!sub)sub=await reg.pushManager.subscribe({userVisibleOnly:true,applicationServerKey:urlBase64ToUint8Array(cfg.public_key)});
    const json=sub.toJSON();await apiFetch('/api/auth/push/subscribe',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({endpoint:json.endpoint,keys:json.keys})});
    dismissNudge();window.toast?.('Уведомления включены');
    try{await apiFetch('/api/auth/push/test',{method:'POST'})}catch{}
    return true;
  }catch(e){window.toast?.(e.message||'Не удалось включить уведомления');return false}
}
api.enableNotifications=enableNotifications;window.gtsEnableNotifications=enableNotifications;window.gtsPwaInstallHelp=installHelp;

async function refreshNudge(){
  if(!localStorage.getItem('access_token'))return;
  standalone=window.matchMedia?.('(display-mode: standalone)')?.matches||window.navigator.standalone===true;api.standalone=standalone;
  if(!standalone){if(isIOS)showNudge('Установить как приложение','Будет открываться отдельно от Safari и сможет получать уведомления.','Как установить',installHelp);return}
  if(!('Notification' in window)||!('PushManager' in window)||Notification.permission==='denied')return;
  try{
    const cfg=await apiFetch('/api/auth/push/config');if(!cfg.configured)return;
    const reg=await api.ready;if(!reg)return;const sub=await reg.pushManager.getSubscription();
    if(Notification.permission!=='granted'||!sub)showNudge('Включить уведомления','Напомним о матчах и важных событиях лиги.','Включить',enableNotifications);
  }catch{}
}

document.addEventListener('gts:ready',()=>setTimeout(refreshNudge,350));
window.addEventListener('appinstalled',()=>{standalone=true;api.standalone=true;document.documentElement.dataset.gtsPwa='standalone';dismissNudge();setTimeout(refreshNudge,500);window.dispatchEvent(new CustomEvent('gts:pwa-installed'))});
})();
