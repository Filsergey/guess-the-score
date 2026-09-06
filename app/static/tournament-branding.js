(()=>{
const LOGOS={
  2:'https://media.api-sports.io/football/leagues/2.png',
  39:'https://media.api-sports.io/football/leagues/39.png',
  140:'https://media.api-sports.io/football/leagues/140.png',
  135:'https://media.api-sports.io/football/leagues/135.png',
  78:'https://media.api-sports.io/football/leagues/78.png'
};
function selectedTournament(){
  const league=window.getSelectedLeague?.();
  const tournaments=window.getTournaments?.()||[];
  if(!league)return null;
  return tournaments.find(t=>Number(t.id)===Number(league.tournament_id))||null;
}
function applyTournamentBranding(){
  const icon=document.querySelector('#leagueSelect .selector-icon');
  if(!icon)return;
  const tournament=selectedTournament();
  const logo=LOGOS[Number(tournament?.provider_id)];
  if(!logo){icon.innerHTML='👥';icon.classList.remove('has-tournament-logo');return}
  icon.innerHTML=`<img src="${logo}" alt="" loading="eager">`;
  icon.classList.add('has-tournament-logo');
}
const style=document.createElement('style');
style.textContent=`#leagueSelect .selector-icon.has-tournament-logo{width:34px;height:34px;border-radius:10px;display:grid;place-items:center;overflow:hidden;background:rgba(255,255,255,.08);flex:0 0 34px}#leagueSelect .selector-icon.has-tournament-logo img{width:30px;height:30px;object-fit:contain;display:block}`;
document.head.appendChild(style);
document.addEventListener('gts:ready',()=>setTimeout(applyTournamentBranding,100));
document.addEventListener('gts:league-change',()=>setTimeout(applyTournamentBranding,50));
setTimeout(applyTournamentBranding,1200);
window.applyTournamentBranding=applyTournamentBranding;
})();