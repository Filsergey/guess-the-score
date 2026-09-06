(()=>{
function decorateExistingLogos(){
  const box=document.getElementById('leagueSelect'),headerIcon=box?.querySelector('.selector-icon');
  const headerImg=headerIcon?.querySelector('img');
  if(box&&headerIcon){
    const has=Boolean(headerImg);
    box.classList.toggle('has-tournament-brand',has);
    headerIcon.classList.toggle('has-tournament-logo',has);
  }
  document.querySelectorAll('#leaguesView .league-emblem').forEach(emblem=>{
    emblem.classList.toggle('has-tournament-logo',Boolean(emblem.querySelector('img')));
  });
}
function applyTournamentBranding(){decorateExistingLogos()}
const style=document.createElement('style');
style.textContent=`
#leagueSelect.has-tournament-brand{padding-left:58px}
#leagueSelect .selector-icon.has-tournament-logo{left:12px;width:38px;height:38px;border-radius:10px;display:grid;place-items:center;overflow:hidden;background:#fff;border:1px solid rgba(255,255,255,.9);box-shadow:0 2px 10px rgba(0,0,0,.18)}
#leagueSelect .selector-icon.has-tournament-logo img{width:34px;height:34px;object-fit:contain;display:block;padding:3px}
#leaguesView .league-emblem.has-tournament-logo{background:#fff!important;border-color:rgba(255,255,255,.88)!important;box-shadow:0 2px 9px rgba(0,0,0,.16)}
#leaguesView .league-emblem.has-tournament-logo img{width:100%;height:100%;object-fit:contain;padding:7px}
@media(max-width:430px){
  #leagueSelect.has-tournament-brand{padding-left:48px}
  #leagueSelect .selector-icon.has-tournament-logo{left:7px;width:34px;height:34px}
  #leagueSelect .selector-icon.has-tournament-logo img{width:30px;height:30px;padding:3px}
}`;
document.head.appendChild(style);
let scheduled=false;
function schedule(){
  if(scheduled)return;
  scheduled=true;
  requestAnimationFrame(()=>{scheduled=false;applyTournamentBranding()});
}
document.addEventListener('gts:ready',schedule);
document.addEventListener('gts:league-change',schedule);
const startObserver=()=>{
  const root=document.getElementById('leaguesView');
  if(!root)return;
  new MutationObserver(schedule).observe(root,{childList:true,subtree:true});
};
setTimeout(()=>{startObserver();schedule()},500);
window.applyTournamentBranding=applyTournamentBranding;
})();