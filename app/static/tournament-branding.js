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
  const icon=document.querySelector('#leagueSelect .selector-icon');
  if(!icon)return;
  const tournament=tournamentForLeague(window.getSelectedLeague?.());
  const logo=LOGOS[Number(tournament?.provider_id)];
  if(!logo)return;
  icon.innerHTML=img(logo);
  icon.classList.add('has-tournament-logo');
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
style.textContent=`#leagueSelect .selector-icon.has-tournament-logo{width:34px;height:34px;border-radius:10px;display:grid;place-items:center;overflow:hidden;background:rgba(255,255,255,.08);flex:0 0 34px}#leagueSelect .selector-icon.has-tournament-logo img{width:30px;height:30px;object-fit:contain;display:block}.league-emblem.has-tournament-logo img{width:100%;height:100%;object-fit:contain;padding:6px}`;
document.head.appendChild(style);
document.addEventListener('gts:ready',()=>setTimeout(applyTournamentBranding,120));
document.addEventListener('gts:league-change',()=>setTimeout(applyTournamentBranding,120));
const obs=new MutationObserver(()=>setTimeout(applyTournamentBranding,0));
const startObserver=()=>{const root=document.getElementById('leaguesView');if(root)obs.observe(root,{childList:true,subtree:true})};
setTimeout(()=>{startObserver();applyTournamentBranding()},900);
setTimeout(applyTournamentBranding,1800);
window.applyTournamentBranding=applyTournamentBranding;
})();