(()=>{
const LOGOS={
  2:'/api/leagues/tournament-logo/2',
  39:'/api/leagues/tournament-logo/39',
  140:'/api/leagues/tournament-logo/140',
  135:'/api/leagues/tournament-logo/135',
  78:'/api/leagues/tournament-logo/78'
};
function tournamentForLeague(league){
  const tournaments=window.getTournaments?.()||[];
  if(!league)return null;
  return tournaments.find(t=>Number(t.id)===Number(league.tournament_id)&&Number(t.season)===Number(league.tournament_season))||tournaments.find(t=>Number(t.id)===Number(league.tournament_id))||null;
}
function img(logo){return `<img src="${logo}" alt="" loading="eager">`}
function applyHeader(){
  const box=document.getElementById('leagueSelect'),icon=box?.querySelector('.selector-icon');
  if(!box||!icon)return;
  const tournament=tournamentForLeague(window.getSelectedLeague?.());
  const logo=LOGOS[Number(tournament?.provider_id)];
  if(!logo){box.classList.remove('has-tournament-brand');return}
  icon.innerHTML=img(logo);
  icon.classList.add('has-tournament-logo');
  box.classList.add('has-tournament-brand');
}
function applyCards(){
  const leagues=window.getLeagues?.()||[];
  const cards=[...document.querySelectorAll('#leaguesView .league-card')];
  cards.forEach((card,i)=>{
    const league=leagues[i],emblem=card.querySelector('.league-emblem');
    if(!league||!emblem)return;
    const tournament=tournamentForLeague(league),logo=LOGOS[Number(tournament?.provider_id)];
    if(!logo)return;
    const existing=emblem.querySelector('img');
    if(existing?.src?.startsWith('data:'))return;
    emblem.innerHTML=img(logo);
    emblem.classList.add('has-tournament-logo');
  });
}
function applyTournamentBranding(){applyHeader();applyCards()}
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
document.addEventListener('gts:ready',()=>setTimeout(applyTournamentBranding,120));
document.addEventListener('gts:league-change',()=>setTimeout(applyTournamentBranding,120));
const obs=new MutationObserver(()=>setTimeout(applyTournamentBranding,0));
const startObserver=()=>{const root=document.getElementById('leaguesView');if(root)obs.observe(root,{childList:true,subtree:true})};
setTimeout(()=>{startObserver();applyTournamentBranding()},900);
setTimeout(applyTournamentBranding,1800);
window.applyTournamentBranding=applyTournamentBranding;
})();