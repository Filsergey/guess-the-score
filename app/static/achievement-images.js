(()=>{
const ART={
 'Снайпер':'/static/achievements/fireball.webp?v=1',
 'Серия точных':'/static/achievements/emerald-shield.webp?v=1',
 'На серии':'/static/achievements/crystal-space.webp?v=1',
 'Охотник на Оракула':'/static/achievements/champion-crown.webp?v=1',
 'Один такой':'/static/achievements/crystal-space.webp?v=1',
 'Король тура':'/static/achievements/gold-trophy.webp?v=1',
 'Лучший прогнозист тура':'/static/achievements/gold-trophy.webp?v=1',
 'Идеальный тур':'/static/achievements/champion-crown.webp?v=1'
};
const css=document.createElement('style');css.textContent=`
.ach-goal-icon{width:38px!important;height:38px!important;flex:0 0 38px!important;padding:0!important;overflow:hidden!important;position:relative!important;background:#10263b!important;border:1px solid rgba(var(--gts-accent-rgb,36,164,255),.32)!important;box-shadow:0 4px 12px rgba(0,0,0,.18)}
.ach-goal-icon .gts-ach-art,.ach-icon .gts-ach-art,.gts-award-icon .gts-ach-art{display:block;width:100%;height:100%;object-fit:cover;border-radius:inherit}
.ach-goal.locked .ach-goal-icon{filter:none!important;opacity:1!important}.ach-goal.locked .ach-goal-icon .gts-ach-art{filter:grayscale(1) brightness(.48);opacity:.72}.ach-goal.locked .ach-goal-icon::after{content:'🔒';position:absolute;right:-2px;bottom:-2px;width:17px;height:17px;border-radius:50%;display:grid;place-items:center;background:#101a26;border:1px solid #607184;font-size:9px;line-height:1;filter:none!important;opacity:1!important}
.ach-icon{width:38px;height:38px;flex:0 0 38px;border-radius:10px;overflow:hidden;font-size:0!important;background:#10263b;border:1px solid rgba(var(--gts-accent-rgb,36,164,255),.28)}
.gts-award-icon{width:48px;height:48px;flex:0 0 48px;border-radius:13px;overflow:hidden;font-size:0!important;background:#10263b}
@media(max-width:360px){.ach-goal-icon{width:34px!important;height:34px!important;flex-basis:34px!important}}
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