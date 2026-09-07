(()=>{
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
function image(title){const src=ART[String(title||'').trim()];return src?`<img class="gts-ach-art" src="${src}" alt="${esc(title)}" loading="lazy">`:''}
function decorateGoals(){document.querySelectorAll('.ach-goal').forEach(card=>{const title=card.querySelector('.ach-goal-title')?.textContent?.trim(),icon=card.querySelector('.ach-goal-icon');if(!title||!icon||!ART[title]||icon.dataset.gtsArt===title)return;icon.innerHTML=image(title);icon.dataset.gtsArt=title})}
function decorateBadges(){document.querySelectorAll('.ach-badge').forEach(card=>{const title=card.querySelector('.ach-title')?.textContent?.trim(),icon=card.querySelector('.ach-icon');if(!title||!icon||!ART[title]||icon.dataset.gtsArt===title)return;icon.innerHTML=image(title);icon.dataset.gtsArt=title})}
function decoratePopup(){document.querySelectorAll('.gts-award-pop').forEach(pop=>{const title=pop.querySelector('.gts-award-title')?.textContent?.trim(),icon=pop.querySelector('.gts-award-icon');if(!title||!icon||!ART[title]||icon.dataset.gtsArt===title)return;icon.innerHTML=image(title);icon.dataset.gtsArt=title})}
function decorate(){decorateGoals();decorateBadges();decoratePopup()}
new MutationObserver(decorate).observe(document.body,{childList:true,subtree:true});
document.addEventListener('gts:ready',decorate);setTimeout(decorate,100);setTimeout(decorate,800);
})();
