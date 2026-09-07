(()=>{
const css=document.createElement('style');
css.textContent=`
.ach-participant-compact{padding:10px!important;margin:7px 0!important;border-radius:14px!important;background:rgba(13,29,46,.94)!important}
.ach-participant-compact .ach-user{display:flex!important;gap:8px!important;min-height:36px!important;position:relative!important;padding-right:50px!important;align-items:center!important}
.ach-participant-compact .ach-user img,.ach-participant-compact .ach-avatar{width:34px!important;height:34px!important;flex:0 0 34px!important}
.ach-participant-compact .ach-user b{font-size:12px!important;line-height:1.15!important}
.ach-participant-compact .ach-user small{display:none!important}
.ach-achievement-rank{position:absolute;right:0;top:50%;transform:translateY(-50%);display:flex;align-items:center;justify-content:center;min-width:42px;height:26px;padding:0 8px;box-sizing:border-box;border-radius:999px;background:#142b3d;border:1px solid #31516a;color:#9fb5c7;font-size:10px;font-weight:950;box-shadow:0 3px 9px rgba(0,0,0,.17)}
.ach-achievement-rank.rank-1{background:linear-gradient(135deg,#735716,#3b2d10);border-color:#d3a332;color:#ffe18a}.ach-achievement-rank.rank-2{background:linear-gradient(135deg,#46525d,#28333d);border-color:#8ea1b3;color:#e6edf3}.ach-achievement-rank.rank-3{background:linear-gradient(135deg,#503728,#30231c);border-color:#a77955;color:#efbd96}
.ach-rank-stats{display:flex!important;align-items:center!important;gap:6px!important;flex-wrap:wrap!important;margin:7px 0 0 42px!important}.ach-rank-stat{display:inline-flex!important;align-items:center!important;height:21px!important;padding:0 7px!important;border-radius:999px!important;background:#13283a!important;border:1px solid #29465d!important;color:#9fb3c3!important;font-size:8px!important;font-weight:800!important;line-height:1!important;white-space:nowrap!important}.ach-rank-stat .ach-stat-num{font-size:9px!important;font-weight:950!important;line-height:1!important;color:#eef6fb!important;margin-right:3px!important}.ach-rank-stat.score{border-color:rgba(var(--gts-accent-rgb,36,164,255),.48)!important;color:#a8cae3!important;background:rgba(var(--gts-accent-rgb,36,164,255),.09)!important}.ach-rank-stat.max{border-color:#80682f!important;color:#e7ca75!important;background:#2a2518!important}
.ach-participant-compact .ach-badges{display:grid!important;grid-template-columns:repeat(2,minmax(0,1fr))!important;gap:6px!important;margin-top:9px!important;padding:0!important;overflow:visible!important;scroll-snap-type:none!important}
.ach-participant-compact .ach-badge{box-sizing:border-box!important;min-width:0!important;width:auto!important;padding:7px!important;border-radius:11px!important;overflow:hidden!important}.ach-participant-compact .ach-badge-top{display:flex!important;gap:7px!important;align-items:center!important}.ach-participant-compact .ach-icon{width:38px!important;height:38px!important;flex:0 0 38px!important;border-radius:9px!important}.ach-participant-compact .ach-badge-copy{min-width:0!important}.ach-participant-compact .ach-title{font-size:9px!important;line-height:1.15!important;min-height:20px!important;display:-webkit-box!important;-webkit-line-clamp:2!important;-webkit-box-orient:vertical!important;overflow:hidden!important}.ach-participant-compact .ach-mini-tier{display:inline-flex!important;align-items:center!important;font-size:7px!important;line-height:1!important;padding:3px 5px!important;margin-top:3px!important;white-space:nowrap!important}.ach-participant-compact .ach-value{font-size:7px!important;line-height:1.2!important;margin-top:5px!important;color:#91a7b9!important;white-space:nowrap!important;overflow:hidden!important;text-overflow:ellipsis!important}.ach-participant-compact .ach-empty{font-size:8px!important;margin:7px 0 1px 42px!important}
.ach-participants-title{display:block!important;margin:14px 2px 8px!important}.ach-participants-title::after{display:block;content:'За каждый уровень начисляются очки: I — 1 · II — 2 · MAX — 3';font-size:8px;font-weight:600;line-height:1.35;color:#71899d;margin-top:3px}
@media(max-width:360px){.ach-participant-compact .ach-badges{grid-template-columns:1fr!important}}
`;
document.head.appendChild(css);
function stats(card){const badges=[...card.querySelectorAll('.ach-badge')];let score=0,maxed=0;badges.forEach(b=>{if(b.classList.contains('level-3')){score+=3;maxed++}else if(b.classList.contains('level-2'))score+=2;else if(b.classList.contains('level-1'))score+=1});return {score,opened:badges.length,maxed}}
function explainBadge(b){
 const level=b.classList.contains('level-3')?3:b.classList.contains('level-2')?2:1;
 const tier=b.querySelector('.ach-mini-tier');if(tier)tier.textContent=level===3?'MAX · +3':level===2?'II уровень · +2':'I уровень · +1';
 const value=b.querySelector('.ach-value');if(value&&!value.dataset.clearLabel){const raw=value.textContent.trim();value.textContent=`Результат: ${raw}`;value.dataset.clearLabel='1'}
}
function clean(){
 document.querySelectorAll('.round-awards').forEach(el=>el.remove());
 document.querySelectorAll('.ach-card').forEach(card=>{const heading=[...card.children].find(el=>el.tagName==='B');if(heading?.textContent?.trim()==='Твои награды за туры'){card.remove();return}if(card.querySelector('.ach-user'))card.classList.add('ach-participant-compact')});
 const title=[...document.querySelectorAll('.round-title')].find(el=>['Участники','Рейтинг достижений'].includes(el.textContent.trim()));if(!title)return;
 title.textContent='Рейтинг достижений';title.classList.add('ach-participants-title');const wrap=title.parentElement;if(!wrap)return;
 const cards=[...wrap.querySelectorAll(':scope > .ach-participant-compact')];cards.forEach(card=>card.querySelectorAll('.ach-badge').forEach(explainBadge));
 const ranked=cards.map((card,index)=>({card,index,...stats(card)})).sort((a,b)=>b.score-a.score||b.maxed-a.maxed||b.opened-a.opened||a.index-b.index);
 let lastScore=null,lastMax=null,lastOpened=null,place=0;
 ranked.forEach((r,i)=>{if(r.score!==lastScore||r.maxed!==lastMax||r.opened!==lastOpened)place=i+1;lastScore=r.score;lastMax=r.maxed;lastOpened=r.opened;
  const user=r.card.querySelector('.ach-user');let chip=user?.querySelector('.ach-achievement-rank');if(user&&!chip){chip=document.createElement('span');chip.className='ach-achievement-rank';user.appendChild(chip)}if(chip){chip.className=`ach-achievement-rank ${place<=3?`rank-${place}`:''}`;chip.textContent=`#${place}`;chip.title=`${r.score} очков достижений`}
  let row=r.card.querySelector('.ach-rank-stats');if(!row){row=document.createElement('div');row.className='ach-rank-stats';user?.after(row)}if(row)row.innerHTML=`<span class="ach-rank-stat score"><span class="ach-stat-num">${r.score}</span> очков</span><span class="ach-rank-stat"><span class="ach-stat-num">${r.opened}</span> открыто</span><span class="ach-rank-stat max"><span class="ach-stat-num">${r.maxed}</span> MAX</span>`;
 });
 const current=[...wrap.querySelectorAll(':scope > .ach-participant-compact')];if(ranked.some((r,i)=>current[i]!==r.card))ranked.forEach(r=>wrap.insertBefore(r.card,wrap.querySelector('.close')))
}
let queued=false;function schedule(){if(queued)return;queued=true;requestAnimationFrame(()=>{queued=false;clean()})}
new MutationObserver(schedule).observe(document.body,{childList:true,subtree:true});document.addEventListener('gts:ready',schedule);document.addEventListener('gts:league-change',()=>setTimeout(schedule,50));setTimeout(schedule,0);setTimeout(schedule,150);setTimeout(schedule,600);
})();
