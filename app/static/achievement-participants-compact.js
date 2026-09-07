(()=>{
const css=document.createElement('style');
css.textContent=`
.ach-participant-compact{padding:7px 9px!important;margin:5px 0!important;border-radius:13px!important;background:rgba(13,29,46,.9)!important}
.ach-participant-compact .ach-user{gap:7px!important;min-height:28px!important;position:relative!important;padding-right:48px!important}
.ach-participant-compact .ach-user img,.ach-participant-compact .ach-avatar{width:27px!important;height:27px!important;flex:0 0 27px!important}
.ach-participant-compact .ach-user b{font-size:10px!important;line-height:1.15!important}
.ach-participant-compact .ach-user small{font-size:7px!important;line-height:1.2!important;margin-top:1px!important;color:#8ba1b4!important}
.ach-achievement-rank{position:absolute;right:0;top:50%;transform:translateY(-50%);display:flex;align-items:center;justify-content:center;min-width:38px;height:23px;padding:0 7px;box-sizing:border-box;border-radius:999px;background:#142b3d;border:1px solid #31516a;color:#9fb5c7;font-size:8px;font-weight:950;letter-spacing:.02em;box-shadow:0 3px 9px rgba(0,0,0,.17)}
.ach-achievement-rank.rank-1{background:linear-gradient(135deg,#695019,#352a13);border-color:#c99c3f;color:#ffe08a;box-shadow:0 3px 12px rgba(201,156,63,.18)}
.ach-achievement-rank.rank-2{background:linear-gradient(135deg,#3c4852,#242f38);border-color:#8496a7;color:#e1e9ef}
.ach-achievement-rank.rank-3{background:linear-gradient(135deg,#493326,#2d241e);border-color:#9a6f50;color:#e8b68e}
.ach-participant-compact .ach-badges{gap:5px!important;margin-top:5px!important;padding:0 0 1px!important;scrollbar-width:none!important}
.ach-participant-compact .ach-badges::-webkit-scrollbar{display:none!important}
.ach-participant-compact .ach-badge{min-width:84px!important;padding:5px 6px!important;border-radius:9px!important}
.ach-participant-compact .ach-badge-top{gap:5px!important}
.ach-participant-compact .ach-icon{width:30px!important;height:30px!important;flex:0 0 30px!important;border-radius:8px!important}
.ach-participant-compact .ach-title{font-size:8px!important;line-height:1.12!important}
.ach-participant-compact .ach-mini-tier{font-size:6px!important;padding:1px 4px!important;margin-top:2px!important}
.ach-participant-compact .ach-value{font-size:7px!important;margin-top:3px!important;white-space:nowrap!important}
.ach-participant-compact .ach-empty{font-size:8px!important;margin-top:4px!important}
.ach-participants-title{display:flex!important;align-items:center!important;justify-content:space-between!important;margin:12px 2px 6px!important}
.ach-participants-title::after{content:'I = 1 · II = 2 · MAX = 3';font-size:7px;font-weight:600;color:#6f879a}
`;
document.head.appendChild(css);
function stats(card){
 const badges=[...card.querySelectorAll('.ach-badge')];
 let score=0,maxed=0;
 badges.forEach(b=>{
  if(b.classList.contains('level-3')){score+=3;maxed++}
  else if(b.classList.contains('level-2'))score+=2;
  else if(b.classList.contains('level-1'))score+=1;
 });
 return {score,opened:badges.length,maxed};
}
function clean(){
 document.querySelectorAll('.round-awards').forEach(el=>el.remove());
 document.querySelectorAll('.ach-card').forEach(card=>{
  const heading=[...card.children].find(el=>el.tagName==='B');
  if(heading?.textContent?.trim()==='Твои награды за туры'){card.remove();return}
  if(card.querySelector('.ach-user'))card.classList.add('ach-participant-compact');
 });
 const title=[...document.querySelectorAll('.round-title')].find(el=>['Участники','Рейтинг достижений'].includes(el.textContent.trim()));
 if(!title)return;
 title.textContent='Рейтинг достижений';title.classList.add('ach-participants-title');
 const wrap=title.parentElement;if(!wrap)return;
 const cards=[...wrap.querySelectorAll(':scope > .ach-participant-compact')];
 const ranked=cards.map((card,index)=>({card,index,...stats(card),name:card.querySelector('.ach-user b')?.textContent?.trim()||''})).sort((a,b)=>b.score-a.score||b.maxed-a.maxed||b.opened-a.opened||a.index-b.index);
 let lastScore=null,lastMax=null,lastOpened=null,place=0;
 ranked.forEach((r,i)=>{
  if(r.score!==lastScore||r.maxed!==lastMax||r.opened!==lastOpened)place=i+1;
  lastScore=r.score;lastMax=r.maxed;lastOpened=r.opened;
  const user=r.card.querySelector('.ach-user'),small=user?.querySelector('small');
  if(small)small.textContent=`${r.opened} открыто · ${r.maxed} MAX · ${r.score} очк.`;
  let chip=user?.querySelector('.ach-achievement-rank');
  if(user&&!chip){chip=document.createElement('span');chip.className='ach-achievement-rank';user.appendChild(chip)}
  if(chip){chip.className=`ach-achievement-rank ${place<=3?`rank-${place}`:''}`;chip.textContent=`#${place}`;chip.title=`${r.score} очков достижений`}
 });
 const current=[...wrap.querySelectorAll(':scope > .ach-participant-compact')];
 if(ranked.some((r,i)=>current[i]!==r.card))ranked.forEach(r=>wrap.insertBefore(r.card,wrap.querySelector('.close')));
}
let queued=false;function schedule(){if(queued)return;queued=true;requestAnimationFrame(()=>{queued=false;clean()})}
new MutationObserver(schedule).observe(document.body,{childList:true,subtree:true});
document.addEventListener('gts:ready',schedule);
document.addEventListener('gts:league-change',()=>setTimeout(schedule,50));
setTimeout(schedule,0);setTimeout(schedule,150);setTimeout(schedule,600);
})();
