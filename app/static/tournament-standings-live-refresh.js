(()=>{
let lastSignature='';
let timer=null;
function signature(matches){
  return (matches||[])
    .filter(m=>m?.status_group==='finished')
    .map(m=>`${Number(m.id)||0}:${m.home?.goals??''}:${m.away?.goals??''}:${m.status||''}`)
    .sort()
    .join('|');
}
function standingsTabActive(){
  return !!document.querySelector('[data-ranking="standings"].active');
}
function tableVisible(){
  return !!document.getElementById('tableView')?.classList.contains('active');
}
document.addEventListener('gts:matches-updated',event=>{
  const next=signature(event.detail?.matches);
  if(!next){lastSignature='';return}
  if(!lastSignature){lastSignature=next;return}
  if(next===lastSignature)return;
  lastSignature=next;
  if(!tableVisible()||!standingsTabActive()||typeof window.loadTournamentStandings!=='function')return;
  clearTimeout(timer);
  timer=setTimeout(()=>window.loadTournamentStandings({silent:true}),250);
});
})();
