(()=>{
const HD={
 'Снайпер':['sniper-hd',4],
 'Серия точных':['exact-streak-hd',5],
 'На серии':['hot-streak-hd',3],
 'Охотник на Оракула':['oracle-hunter-hd',2],
 'Один такой':['unique-one-direct',1],
 'Король тура':['round-king-hd',4],
 'Лучший прогнозист тура':['round-king-hd',4],
 'Идеальный тур':['ideal-round-hd',3]
};
const cache=new Map();
function sourceUrl(key,i){return key==='unique-one-direct'?`/static/achievements/unique-one-320.b64?v=4`:`/static/achievements/hd384/${key}.${i}.b64?v=4`}
function hdUrl(title){
 title=String(title||'').trim();
 const spec=HD[title];
 if(!spec)return Promise.resolve('');
 const [key,count]=spec;
 if(cache.has(key))return cache.get(key);
 const p=Promise.all(Array.from({length:count},(_,i)=>fetch(sourceUrl(key,i),{cache:'reload'}).then(r=>{if(!r.ok)throw new Error(`${key}.${i}`);return r.text()}))).then(parts=>{
  const b64=parts.join('').replace(/\s+/g,'');
  const raw=atob(b64),bytes=new Uint8Array(raw.length);
  for(let i=0;i<raw.length;i++)bytes[i]=raw.charCodeAt(i);
  return URL.createObjectURL(new Blob([bytes],{type:'image/webp'}));
 }).catch(e=>{console.warn('achievement HD',e);return''});
 cache.set(key,p);return p;
}
function titleFor(el){return el.querySelector('.ach-showcase-title,.ach-goal-title,.ach-title,.gts-award-title')?.textContent?.trim()||''}
function imageFor(el){return el.querySelector('.ach-showcase-art,.ach-goal-icon .gts-ach-art,.ach-icon .gts-ach-art,.gts-award-icon .gts-ach-art')}
function decorate(){
 document.querySelectorAll('.ach-showcase,.ach-goal,.ach-badge,.gts-award-pop').forEach(el=>{
  const title=titleFor(el),img=imageFor(el);if(!title||!img||!HD[title]||img.dataset.hdPending)return;
  if(img.dataset.hdTitle===title)return;
  img.dataset.hdPending='1';
  hdUrl(title).then(src=>{delete img.dataset.hdPending;if(!src||!img.isConnected)return;const probe=new Image();probe.onload=()=>{if(img.isConnected){img.src=src;img.dataset.hdReady='1';img.dataset.hdTitle=title}};probe.onerror=()=>console.warn('achievement HD image decode',title);probe.src=src})
 })
}
function preload(){Object.keys(HD).forEach(title=>hdUrl(title))}
new MutationObserver(decorate).observe(document.body,{childList:true,subtree:true});
document.addEventListener('gts:ready',()=>{decorate();setTimeout(preload,500)});document.addEventListener('gts:league-change',()=>setTimeout(decorate,80));
setInterval(decorate,700);
setTimeout(decorate,50);setTimeout(decorate,250);setTimeout(decorate,900);
window.gtsAchievementHdUrl=hdUrl;
})();