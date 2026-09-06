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

ensureLink('manifest','/static/manifest.webmanifest?v=1');
ensureLink('apple-touch-icon','/static/pwa-icon.svg?v=1');
ensureMeta('apple-mobile-web-app-capable','yes');
ensureMeta('apple-mobile-web-app-status-bar-style','black-translucent');
ensureMeta('apple-mobile-web-app-title','Угадай счёт');
ensureMeta('mobile-web-app-capable','yes');

const standalone=window.matchMedia?.('(display-mode: standalone)')?.matches||window.navigator.standalone===true;
document.documentElement.dataset.gtsPwa=standalone?'standalone':'browser';

const api={standalone,registration:null,ready:null};
window.GTSPWA=api;
if('serviceWorker' in navigator){
  api.ready=navigator.serviceWorker.register('/static/service-worker.js?v=1').then(reg=>{
    api.registration=reg;
    return reg;
  }).catch(()=>null);
}

window.addEventListener('appinstalled',()=>{
  document.documentElement.dataset.gtsPwa='standalone';
  window.dispatchEvent(new CustomEvent('gts:pwa-installed'));
});
})();
