(()=>{
const UNIQUE='Один такой';
const ART={
 'Снайпер':'/static/achievements/fireball.webp?v=1',
 'Серия точных':'/static/achievements/emerald-shield.webp?v=1',
 'На серии':'/static/achievements/crystal-space.webp?v=1',
 'Охотник на Оракула':'/static/achievements/oracle-hunter.webp?v=2',
 'Один такой':'/static/achievements/champion-crown.webp?v=1',
 'Король тура':'/static/achievements/gold-trophy.webp?v=1',
 'Лучший прогнозист тура':'/static/achievements/gold-trophy.webp?v=1',
 'Идеальный тур':'/static/achievements/ideal-round.webp?v=2'
};
const css=document.createElement('style');css.textContent=`
.ach-goal-icon{width:46px!important;height:46px!important;flex:0 0 46px!important;padding:0!important;overflow:hidden!important;position:relative!important;background:#10263b!important;border:1px solid rgba(var(--gts-accent-rgb,36,164,255),.32)!important;box-shadow:0 5px 14px rgba(0,0,0,.24)}
.ach-goal-icon .gts-ach-art,.ach-icon .gts-ach-art,.gts-award-icon .gts-ach-art{display:block;width:100%;height:100%;object-fit:cover;border-radius:inherit}
.ach-goal.locked .ach-goal-icon{filter:none!important;opacity:1!important}.ach-goal.locked .ach-goal-icon .gts-ach-art{filter:grayscale(.65) brightness(.58);opacity:.82}.ach-goal.locked .ach-goal-icon::after{content:'🔒';position:absolute;right:-2px;bottom:-2px;width:18px;height:18px;border-radius:50%;display:grid;place-items:center;background:#101a26;border:1px solid #607184;font-size:9px;line-height:1;filter:none!important;opacity:1!important;box-shadow:0 2px 6px rgba(0,0,0,.35)}
.ach-icon{width:42px;height:42px;flex:0 0 42px;border-radius:11px;overflow:hidden;font-size:0!important;background:#10263b;border:1px solid rgba(var(--gts-accent-rgb,36,164,255),.28);box-shadow:0 4px 10px rgba(0,0,0,.18)}
.gts-award-icon{width:52px;height:52px;flex:0 0 52px;border-radius:14px;overflow:hidden;font-size:0!important;background:#10263b}
@media(max-width:360px){.ach-goal-icon{width:42px!important;height:42px!important;flex-basis:42px!important}.ach-icon{width:38px;height:38px;flex-basis:38px}}
`;document.head.appendChild(css);
const esc=s=>String(s??'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[m]));
let uniquePromise=null;
function uniqueUrl(){
 if(uniquePromise)return uniquePromise;
 uniquePromise=Promise.all([0,1,2].map(i=>fetch(`/static/achievements/unique-one-clean/part_0${i}.b64?v=1`,{cache:'no-store'}).then(r=>{if(!r.ok)throw new Error(`unique ${i}`);return r.text()}))).then(parts=>{
  const b64=parts.join('').replace(/\s+/g,'');
  const raw=atob(b64),bytes=new Uint8Array(raw.length);
  for(let i=0;i<raw.length;i++)bytes[i]=raw.charCodeAt(i);
  if(bytes.length<30000||String.fromCharCode(...bytes.slice(0,4))!=='RIFF'||String.fromCharCode(...bytes.slice(8,12))!=='WEBP')throw new Error('invalid unique WebP');
  return URL.createObjectURL(new Blob([bytes],{type:'image/webp'}));
 }).catch(e=>{console.warn('unique achievement image',e);return''});
 return uniquePromise;
}
function image(title){const src=ART[String(title||'').trim()];return src?`<img class="gts-ach-art" src="${src}" alt="${esc(title)}" loading="lazy">`:''}
function setUnique(img){if(!img||img.dataset.uniquePending==='1'||img.dataset.uniqueReady==='1')return;img.dataset.uniquePending='1';uniqueUrl().then(src=>{delete img.dataset.uniquePending;if(!src||!img.isConnected)return;const probe=new Image();probe.onload=()=>{if(!img.isConnected)return;img.src=src;img.dataset.uniqueReady='1';img.dataset.hdReady='1';img.dataset.hdTitle='skip';delete img.dataset.hdPending};probe.onerror=()=>console.warn('unique achievement decode failed');probe.src=src})}
function decorateGoals(){document.querySelectorAll('.ach-goal').forEach(card=>{const title=card.querySelector('.ach-goal-title')?.textContent?.trim(),icon=card.querySelector('.ach-goal-icon');if(!title||!icon||!ART[title])return;if(icon.dataset.gtsArt!==title){icon.innerHTML=image(title);icon.dataset.gtsArt=title}if(title===UNIQUE)setUnique(icon.querySelector('img'))})}
function decorateBadges(){document.querySelectorAll('.ach-badge').forEach(card=>{const title=card.querySelector('.ach-title')?.textContent?.trim(),icon=card.querySelector('.ach-icon');if(!title||!icon||!ART[title])return;if(icon.dataset.gtsArt!==title){icon.innerHTML=image(title);icon.dataset.gtsArt=title}if(title===UNIQUE)setUnique(icon.querySelector('img'))})}
function decoratePopup(){document.querySelectorAll('.gts-award-pop').forEach(pop=>{const title=pop.querySelector('.gts-award-title')?.textContent?.trim(),icon=pop.querySelector('.gts-award-icon');if(!title||!icon||!ART[title])return;if(icon.dataset.gtsArt!==title){icon.innerHTML=image(title);icon.dataset.gtsArt=title}if(title===UNIQUE)setUnique(icon.querySelector('img'))})}
function decorateShowcase(){document.querySelectorAll('.ach-showcase').forEach(card=>{const title=card.querySelector('.ach-showcase-title')?.textContent?.trim(),img=card.querySelector('.ach-showcase-art');if(!title||!img||img.tagName!=='IMG'||!ART[title])return;if(title===UNIQUE){setUnique(img);return}const src=ART[title];if(img.dataset.gtsDirectArt===src)return;img.src=src;img.dataset.gtsDirectArt=src})}
function decorate(){decorateGoals();decorateBadges();decoratePopup();decorateShowcase()}
new MutationObserver(decorate).observe(document.body,{childList:true,subtree:true});
document.addEventListener('gts:ready',decorate);document.addEventListener('gts:league-change',()=>setTimeout(decorate,50));setInterval(decorate,600);setTimeout(decorate,50);setTimeout(decorate,300);setTimeout(decorate,900);setTimeout(()=>uniqueUrl(),200);
})();
