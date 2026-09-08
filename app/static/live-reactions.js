(()=>{
let previous=new Map();
function snap(m){return {id:Number(m?.id),status_group:m?.status_group||null}}
function finished(oldM,newM){return oldM&&oldM.status_group!=='finished'&&newM.status_group==='finished'}
async function refreshCompetitionViews(){try{if(document.getElementById('tableView')?.classList.contains('active'))await window.loadLeaderboard?.();document.dispatchEvent(new CustomEvent('gts:competition-updated'))}catch(e){console.error('competition refresh',e)}}
document.addEventListener('gts:matches-updated',ev=>{const matches=ev.detail?.matches||[];if(!previous.size){previous=new Map(matches.map(m=>[Number(m.id),snap(m)]));return}let anyFinished=false;for(const m of matches){const id=Number(m.id),old=previous.get(id);if(old&&finished(old,m)){anyFinished=true;document.dispatchEvent(new CustomEvent('gts:match-finished',{detail:{before:old,match:m}}))}previous.set(id,snap(m))}if(anyFinished)refreshCompetitionViews()});
})();
