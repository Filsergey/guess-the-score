(()=>{
const HD={
 'Снайпер':['sniper-hd',4],
 'Серия точных':['exact-streak-hd',5],
 'На серии':['hot-streak-hd',3],
 'Охотник на Оракула':['oracle-hunter-hd',2],
 'Один такой':['unique-hd',4],
 'Король тура':['round-king-hd',4],
 'Лучший прогнозист тура':['round-king-hd',4],
 'Идеальный тур':['ideal-round-hd',3]
};
const cache=new Map();
function hdUrl(title){
 title=String(title||'').trim();
 const spec=HD[title];
 if(!spec)return Promise.resolve('');
 const [key,count]=spec;
 if(cache.has(key))return cache.get(key);
 const p=Promise.all(Array.from({length:count},(_,i)=>fetch(`/static/achievements/hd384/${key}.${i}.b64?v=1`,{cache:'force-cache'}).then(r=>{if(!r.ok)throw new Error(`${key}.${i}`);return r.text()}))).then(parts=>{
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
  const title=titleFor(el),img=imageFor(el);if(!title||!img||!HD[title]||img.dataset.hdPending||img.dataset.hdReady)return;
  img.dataset.hdPending='1';hdUrl(title).then(src=>{delete img.dataset.hdPending;if(src&&img.isConnected){img.src=src;img.dataset.hdReady='1'}})
 })
}
new MutationObserver(decorate).observe(document.body,{childList:true,subtree:true});
document.addEventListener('gts:ready',decorate);document.addEventListener('gts:league-change',()=>setTimeout(decorate,120));
setTimeout(decorate,80);setTimeout(decorate,500);setTimeout(decorate,1500);
window.gtsAchievementHdUrl=hdUrl;
})();
