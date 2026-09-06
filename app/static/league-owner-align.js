(()=>{
const style=document.createElement('style');
style.textContent=`
#leaguesView .league-card.gts-owner-stack{min-height:82px!important;padding-right:122px!important}
#leaguesView .league-card .league-owner.gts-owner-above-manage{position:absolute!important;right:11px!important;top:11px!important;width:98px!important;height:16px!important;margin:0!important;padding:0 6px!important;display:flex!important;align-items:center!important;justify-content:center!important;border-radius:6px!important;font-size:6.5px!important;line-height:1!important;letter-spacing:.05em!important;text-align:center!important;z-index:4!important;white-space:nowrap!important}
#leaguesView .league-card.gts-owner-stack .league-edit.gts-league-manage{right:11px!important;top:auto!important;bottom:11px!important;width:98px!important;min-width:98px!important;height:29px!important;transform:none!important}
#leaguesView .league-card.gts-owner-stack .league-edit.gts-league-manage:active{transform:scale(.97)!important}
@media(max-width:430px){
 #leaguesView .league-card.gts-owner-stack{min-height:78px!important;padding-right:114px!important}
 #leaguesView .league-card .league-owner.gts-owner-above-manage{right:10px!important;top:10px!important;width:92px!important;height:15px!important;font-size:6.2px!important}
 #leaguesView .league-card.gts-owner-stack .league-edit.gts-league-manage{right:10px!important;bottom:10px!important;width:92px!important;min-width:92px!important;height:27px!important}
}
`;
document.head.appendChild(style);

let scheduled=false;
function alignOwnerBadges(){
 const cards=[...document.querySelectorAll('#leaguesView .league-card')];
 for(const card of cards){
  const owner=card.querySelector('.league-owner');
  const manage=card.querySelector('.gts-league-manage');
  const stacked=!!owner&&!!manage;
  if(card.classList.contains('gts-owner-stack')!==stacked)card.classList.toggle('gts-owner-stack',stacked);
  if(!stacked)continue;
  if(!owner.classList.contains('gts-owner-above-manage'))owner.classList.add('gts-owner-above-manage');
  if(owner.parentElement!==card)card.appendChild(owner);
 }
}
function schedule(){if(scheduled)return;scheduled=true;requestAnimationFrame(()=>{scheduled=false;alignOwnerBadges()})}
const root=document.getElementById('leaguesView');
if(root)new MutationObserver(schedule).observe(root,{childList:true,subtree:true});
document.addEventListener('gts:ready',schedule);
document.addEventListener('gts:league-change',schedule);
setTimeout(schedule,250);
setTimeout(schedule,900);
})();