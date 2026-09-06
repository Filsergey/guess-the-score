(()=>{
let editLeagueSettings=null;
const style=document.createElement('style');
style.textContent=`
#leaguesView .league-card.has-delete{padding-right:20px;padding-bottom:38px;min-height:76px}
#leaguesView .league-card.has-delete .league-main{min-width:0;width:100%}
#leaguesView .league-card.has-delete .league-name-row{padding-right:0}
#leaguesView .league-card.has-delete .league-meta{padding-right:0}
#leaguesView .league-card .league-arrow{display:none!important}
#leaguesView .league-edit{position:absolute;right:54px;bottom:7px;height:25px;padding:0 8px;border-radius:9px;display:flex;align-items:center;justify-content:center;color:#9fd3ff;background:rgba(25,88,137,.16);border:1px solid rgba(63,143,203,.32);font-size:8px;font-weight:850;z-index:3;white-space:nowrap}
#leaguesView .league-edit:active{background:rgba(35,111,171,.26)}
#leaguesView .league-card.has-delete .league-delete{right:14px;top:auto;bottom:7px;transform:none;width:29px;height:25px;border-radius:9px;font-size:12px}
#leaguesView .league-card.selected{border-color:#24a4ff!important;box-shadow:inset 3px 0 #24a4ff,0 0 0 1px rgba(42,157,255,.18),0 0 14px rgba(24,145,255,.30)!important}
@media(max-width:430px){
  #leaguesView .league-card.has-delete{padding-right:18px;padding-bottom:37px;min-height:74px}
  #leaguesView .league-edit{right:52px;bottom:6px;height:24px;padding:0 7px;font-size:7.8px}
  #leaguesView .league-card.has-delete .league-delete{right:13px;bottom:6px;height:24px;width:28px}
}
`;
document.head.appendChild(style);

function leagueIdFromCard(card,index){
  const leagues=window.getLeagues?.()||[];
  const league=leagues[index];
  if(league?.id!=null){card.dataset.leagueId=String(league.id);return Number(league.id)}
  const m=String(card.getAttribute('onclick')||'').match(/openLeagueSettings\((\d+)\)/);
  return m?Number(m[1]):0;
}
function canManage(league){return league?.member_role==='owner'||window.GTS?.me?.role==='superadmin'}
function applyThemeDirect(id){
  if(!window.GTS?.api||!id)return;
  window.GTS.api(`/api/leagues/${id}/theme`).then(t=>{
    if(t.background){
      document.body.style.backgroundImage=`linear-gradient(rgba(3,12,22,.74),rgba(3,12,22,.88)),url("${t.background}")`;
      document.body.style.backgroundSize='cover';document.body.style.backgroundPosition='center top';document.body.style.backgroundAttachment='fixed';document.body.style.backgroundRepeat='no-repeat';
    }else{
      for(const p of ['background-image','background-size','background-position','background-attachment','background-repeat'])document.body.style.removeProperty(p);
    }
    if(t.tournament_background)document.documentElement.style.setProperty('--tournament-card-image',`url("${t.tournament_background}")`);
    else document.documentElement.style.removeProperty('--tournament-card-image');
  }).catch(()=>{});
}
function markSelected(id){
  document.querySelectorAll('#leaguesView .league-card').forEach(card=>card.classList.toggle('selected',Number(card.dataset.leagueId)===Number(id)));
}
function selectLeagueOnly(id){
  id=Number(id);if(!id)return;
  window.chooseLeague?.(id);
  markSelected(id);
  applyThemeDirect(id);
  setTimeout(()=>window.applyTournamentBranding?.(),50);
}
window.selectLeagueOnly=selectLeagueOnly;

function decorate(){
  const cards=[...document.querySelectorAll('#leaguesView .league-card')],leagues=window.getLeagues?.()||[];
  cards.forEach((card,index)=>{
    const id=leagueIdFromCard(card,index),league=leagues.find(x=>Number(x.id)===id)||leagues[index];
    if(!id)return;
    card.dataset.leagueId=String(id);
    if(canManage(league)&&!card.querySelector('.league-edit')){
      const btn=document.createElement('span');
      btn.className='league-edit';btn.setAttribute('role','button');btn.textContent='Изменить';
      btn.onclick=e=>{e.preventDefault();e.stopPropagation();editLeagueSettings?.(id)};
      const del=card.querySelector('.league-delete');
      if(del)card.insertBefore(btn,del);else card.appendChild(btn);
    }
  });
  const selected=Number(window.GTS?.leagueId||0);if(selected)markSelected(selected);
}
function install(){
  if(!editLeagueSettings&&typeof window.openLeagueSettings==='function'){
    editLeagueSettings=window.openLeagueSettings.bind(window);
    window.editLeagueSettings=id=>editLeagueSettings?.(Number(id));
    window.openLeagueSettings=id=>selectLeagueOnly(Number(id));
  }
  decorate();
}
const observer=new MutationObserver(()=>install());
setTimeout(()=>{const root=document.getElementById('leaguesView');if(root)observer.observe(root,{childList:true,subtree:true});install()},200);
document.addEventListener('gts:ready',()=>setTimeout(install,100));
document.addEventListener('gts:league-change',()=>setTimeout(decorate,50));
setInterval(()=>{if(!editLeagueSettings)install()},500);
})();