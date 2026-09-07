(()=>{
const css=document.createElement('style');
css.textContent=`
.ach-participant-compact{padding:7px 9px!important;margin:5px 0!important;border-radius:13px!important;background:rgba(13,29,46,.9)!important}
.ach-participant-compact .ach-user{gap:7px!important;min-height:28px!important}
.ach-participant-compact .ach-user img,.ach-participant-compact .ach-avatar{width:27px!important;height:27px!important;flex:0 0 27px!important}
.ach-participant-compact .ach-user b{font-size:10px!important;line-height:1.15!important}
.ach-participant-compact .ach-user small{font-size:7px!important;line-height:1.2!important;margin-top:1px!important}
.ach-participant-compact .ach-badges{gap:5px!important;margin-top:5px!important;padding:0 0 1px!important;scrollbar-width:none!important}
.ach-participant-compact .ach-badges::-webkit-scrollbar{display:none!important}
.ach-participant-compact .ach-badge{min-width:84px!important;padding:5px 6px!important;border-radius:9px!important}
.ach-participant-compact .ach-badge-top{gap:5px!important}
.ach-participant-compact .ach-icon{width:30px!important;height:30px!important;flex:0 0 30px!important;border-radius:8px!important}
.ach-participant-compact .ach-title{font-size:8px!important;line-height:1.12!important}
.ach-participant-compact .ach-mini-tier{font-size:6px!important;padding:1px 4px!important;margin-top:2px!important}
.ach-participant-compact .ach-value{font-size:7px!important;margin-top:3px!important;white-space:nowrap!important}
.ach-participant-compact .ach-empty{font-size:8px!important;margin-top:4px!important}
.ach-participants-title{margin:12px 2px 6px!important}
`;
document.head.appendChild(css);
function clean(){
 document.querySelectorAll('.round-awards').forEach(el=>el.remove());
 document.querySelectorAll('.ach-card').forEach(card=>{
  const heading=[...card.children].find(el=>el.tagName==='B');
  if(heading?.textContent?.trim()==='Твои награды за туры'){card.remove();return}
  if(card.querySelector('.ach-user'))card.classList.add('ach-participant-compact');
 });
 document.querySelectorAll('.round-title').forEach(el=>{if(el.textContent.trim()==='Участники')el.classList.add('ach-participants-title')});
}
new MutationObserver(clean).observe(document.body,{childList:true,subtree:true});
document.addEventListener('gts:ready',clean);
document.addEventListener('gts:league-change',()=>setTimeout(clean,50));
setTimeout(clean,0);setTimeout(clean,150);setTimeout(clean,600);
})();
