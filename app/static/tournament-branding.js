(()=>{
const FALLBACK={
  2:['UCL','#07182e','#20a7ff'],
  39:['PL','#37003c','#04f5ff'],
  140:['LL','#171717','#ff4655'],
  78:['BL','#ffffff','#d20515'],
  135:['A','#ffffff','#0068ff'],
  61:['L1','#071a38','#ee1747'],
  88:['ERE','#ffffff','#e31b23'],
  71:['BR','#0b6b3a','#ffd400'],
  94:['PT','#0b6b3a','#d71920'],
  262:['MX','#0b6b3a','#d71920'],
  235:['RPL','#143d8d','#e53935']
};
function tournamentForLeague(league){
  const tournaments=window.getTournaments?.()||[];
  if(!league)return null;
  return tournaments.find(t=>Number(t.id)===Number(league.tournament_id)&&Number(t.season)===Number(league.tournament_season))||tournaments.find(t=>Number(t.id)===Number(league.tournament_id))||null;
}
function fallbackMarkup(league){
  const tournament=tournamentForLeague(league),spec=FALLBACK[Number(tournament?.provider_id)]||['T','#10263b','#24a4ff'];
  return `<span class="gts-tournament-fallback" style="--gts-logo-bg:${spec[1]};--gts-logo-accent:${spec[2]}">${spec[0]}</span>`;
}
function decorateExistingLogos(){
  const box=document.getElementById('leagueSelect'),headerIcon=box?.querySelector('.selector-icon');
  if(box&&headerIcon){
    let headerImg=headerIcon.querySelector('img');
    if(!headerImg&&headerIcon.textContent.trim()==='⚽'){
      headerIcon.innerHTML=fallbackMarkup(window.getSelectedLeague?.());
      headerImg=null;
    }
    const has=Boolean(headerImg||headerIcon.querySelector('.gts-tournament-fallback'));
    box.classList.toggle('has-tournament-brand',has);
    headerIcon.classList.toggle('has-tournament-logo',has);
  }
  const leagues=window.getLeagues?.()||[];
  document.querySelectorAll('#leaguesView .league-emblem').forEach((emblem,index)=>{
    let image=emblem.querySelector('img');
    if(!image&&emblem.textContent.trim()==='⚽'){
      emblem.innerHTML=fallbackMarkup(leagues[index]);
      image=null;
    }
    emblem.classList.toggle('has-tournament-logo',Boolean(image||emblem.querySelector('.gts-tournament-fallback')));
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
.gts-tournament-fallback{width:100%;height:100%;display:flex;align-items:center;justify-content:center;border-radius:inherit;background:var(--gts-logo-bg,#10263b);color:var(--gts-logo-accent,#24a4ff);border:2px solid var(--gts-logo-accent,#24a4ff);font:900 10px/1 Arial,Helvetica,sans-serif;letter-spacing:-.02em}
#leagueSelect .gts-tournament-fallback{font-size:9px}
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