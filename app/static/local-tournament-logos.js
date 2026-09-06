(()=>{
const LOGOS={
  2:'/static/tournament-logos/2.svg?v=1',39:'/static/tournament-logos/39.svg?v=1',140:'/static/tournament-logos/140.svg?v=1',78:'/static/tournament-logos/78.svg?v=1',135:'/static/tournament-logos/135.svg?v=1',61:'/static/tournament-logos/61.svg?v=1',88:'/static/tournament-logos/88.svg?v=1',71:'/static/tournament-logos/71.svg?v=1',94:'/static/tournament-logos/94.svg?v=1',262:'/static/tournament-logos/262.svg?v=1',235:'/static/tournament-logos/235.svg?v=1'
};
window.GTS_LOCAL_TOURNAMENT_LOGOS=LOGOS;
function tournamentFor(league){
  const ts=window.getTournaments?.()||[];
  if(!league)return null;
  return ts.find(t=>Number(t.id)===Number(league.tournament_id)&&Number(t.season)===Number(league.tournament_season))||ts.find(t=>Number(t.id)===Number(league.tournament_id))||null;
}
function logoFor(league){return LOGOS[Number(tournamentFor(league)?.provider_id)]||null}
function setLocal(container,src,cls){
  if(!container||!src)return;
  const current=container.querySelector('img');
  if(current?.src?.startsWith('data:'))return; // owner-uploaded league icon wins
  if(current){
    const wanted=new URL(src,location.origin).href;
    if(current.src!==wanted)current.src=src;
    if(cls&&!current.classList.contains(cls))current.classList.add(cls);
    return;
  }
  const img=document.createElement('img');img.src=src;img.alt='';if(cls)img.className=cls;
  container.replaceChildren(img);
}
function apply(){
  const leagues=window.getLeagues?.()||[];
  document.querySelectorAll('#leaguesView .league-card').forEach((card,index)=>{
    const emblem=card.querySelector('.league-emblem'),src=logoFor(leagues[index]);
    setLocal(emblem,src,'gts-local-tournament-logo');
  });
  const selected=window.getSelectedLeague?.()||leagues.find(l=>Number(l.id)===Number(window.GTS?.leagueId));
  const box=document.getElementById('leagueSelect'),icon=box?.querySelector('.selector-icon'),src=logoFor(selected);
  setLocal(icon,src,'selector-custom-icon');
  window.applyTournamentBranding?.();
}
let scheduled=false;
function schedule(){if(scheduled)return;scheduled=true;requestAnimationFrame(()=>{scheduled=false;apply()})}
document.addEventListener('gts:ready',schedule);
document.addEventListener('gts:league-change',schedule);
const start=()=>{const root=document.getElementById('leaguesView');if(root)new MutationObserver(schedule).observe(root,{childList:true,subtree:true});schedule()};
setTimeout(start,350);setTimeout(schedule,1000);
window.applyLocalTournamentLogos=schedule;
})();