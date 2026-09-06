(()=>{
let previous=new Map();
const style=document.createElement('style');style.textContent=`
@keyframes gts-goal-flash{0%{box-shadow:0 0 0 rgba(71,225,141,0)}20%{box-shadow:0 0 0 3px rgba(71,225,141,.45),0 0 32px rgba(71,225,141,.26)}100%{box-shadow:0 14px 40px rgba(0,0,0,.24)}}
@keyframes gts-score-pop{0%{transform:scale(1)}35%{transform:scale(1.28)}100%{transform:scale(1)}}
.match.goal-flash{animation:gts-goal-flash 1.6s ease}.match.goal-flash .score-final{animation:gts-score-pop .65s ease;color:#70e5ae}.goal-toast{position:fixed;left:50%;top:calc(18px + env(safe-area-inset-top));transform:translateX(-50%) translateY(-20px);z-index:60;background:#0b2d25;border:1px solid #2f795d;color:#dfffee;border-radius:15px;padding:10px 14px;font-size:13px;font-weight:850;opacity:0;pointer-events:none;transition:.22s;max-width:min(92vw,520px);text-align:center}.goal-toast.show{opacity:1;transform:translateX(-50%) translateY(0)}
`;document.head.appendChild(style);
const toast=document.createElement('div');toast.className='goal-toast';document.body.appendChild(toast);let toastTimer=null;
function showGoal(text){toast.textContent=text;toast.classList.add('show');clearTimeout(toastTimer);toastTimer=setTimeout(()=>toast.classList.remove('show'),3200)}
function snap(m){return {id:Number(m?.id),status_group:m?.status_group||null,home:{name:m?.home?.name||'',goals:m?.home?.goals??null},away:{name:m?.away?.name||'',goals:m?.away?.goals??null}}}
function score(m){return [Number(m?.home?.goals??0),Number(m?.away?.goals??0)]}
function flash(id){document.querySelectorAll(`.match[data-match-id="${id}"]`).forEach(el=>{el.classList.remove('goal-flash');void el.offsetWidth;el.classList.add('goal-flash');setTimeout(()=>el.classList.remove('goal-flash'),1700)})}
function teamGoalText(oldM,newM){const [oh,oa]=score(oldM),[nh,na]=score(newM);if(nh>oh)return `⚽ ГОЛ! ${newM.home.name} · ${nh}:${na}`;if(na>oa)return `⚽ ГОЛ! ${newM.away.name} · ${nh}:${na}`;return null}
function finished(oldM,newM){return oldM&&oldM.status_group!=='finished'&&newM.status_group==='finished'}
async function refreshCompetitionViews(){try{if(document.getElementById('tableView')?.classList.contains('active'))await window.loadLeaderboard?.();document.dispatchEvent(new CustomEvent('gts:competition-updated'))}catch(e){console.error('competition refresh',e)}}
document.addEventListener('gts:matches-updated',ev=>{const matches=ev.detail?.matches||[];if(!previous.size){previous=new Map(matches.map(m=>[Number(m.id),snap(m)]));return}let anyFinished=false;for(const m of matches){const id=Number(m.id),old=previous.get(id);if(old){const text=teamGoalText(old,m);if(text){flash(id);showGoal(text);document.dispatchEvent(new CustomEvent('gts:goal',{detail:{before:old,match:m}}))}if(finished(old,m)){anyFinished=true;document.dispatchEvent(new CustomEvent('gts:match-finished',{detail:{before:old,match:m}}))}}previous.set(id,snap(m))}if(anyFinished)refreshCompetitionViews()});
})();