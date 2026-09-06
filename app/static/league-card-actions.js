(()=>{
let editLeagueSettings=null;
const style=document.createElement('style');
style.textContent=`
#leaguesView .league-card{--accent:#24a4ff;--accent-rgb:36,164,255;--accent-soft:#9fd3ff;--card-bg1:rgba(18,43,73,.96);--card-bg2:rgba(8,20,34,.96);background:linear-gradient(145deg,var(--card-bg1),var(--card-bg2))!important}
#leaguesView .league-card[data-tournament='2']{--accent:#27b7ff;--accent-rgb:39,183,255;--accent-soft:#d8f3ff;--card-bg1:rgba(15,39,82,.98);--card-bg2:rgba(5,15,42,.98)}
#leaguesView .league-card[data-tournament='39']{--accent:#9b5cff;--accent-rgb:155,92,255;--accent-soft:#eadfff;--card-bg1:rgba(42,24,68,.97);--card-bg2:rgba(19,12,34,.98)}
#leaguesView .league-card[data-tournament='140']{--accent:#ff4f5e;--accent-rgb:255,79,94;--accent-soft:#ffd9dd;--card-bg1:rgba(63,24,36,.97);--card-bg2:rgba(25,12,20,.98)}
#leaguesView .league-card[data-tournament='135']{--accent:#49a7ff;--accent-rgb:73,167,255;--accent-soft:#d9efff;--card-bg1:rgba(18,52,86,.97);--card-bg2:rgba(8,23,40,.98)}
#leaguesView .league-card[data-tournament='78']{--accent:#ff4d4d;--accent-rgb:255,77,77;--accent-soft:#ffe0e0;--card-bg1:rgba(63,26,30,.97);--card-bg2:rgba(28,12,15,.98)}
#leaguesView .league-card.has-delete{min-height:72px;padding:9px 126px 9px 10px!important;display:flex;align-items:center}
#leaguesView .league-card.has-delete .league-emblem{flex:0 0 48px;width:48px;height:48px;margin-right:10px;border-color:rgba(var(--accent-rgb),.38);background:rgba(var(--accent-rgb),.08)}
#leaguesView .league-card.has-delete .league-main{min-width:0;width:100%;display:flex;flex-direction:column;justify-content:center;gap:2px}
#leaguesView .league-card.has-delete .league-name-row{display:flex;min-width:0;padding:0!important;line-height:1.1}
#leaguesView .league-card.has-delete .league-name{display:block;max-width:100%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:14px;line-height:17px;color:#fff}
#leaguesView .league-card.has-delete .league-role,#leaguesView .league-card .league-owner{margin-left:5px;flex:0 0 auto;color:var(--accent-soft)!important;background:rgba(var(--accent-rgb),.13)!important;border-color:rgba(var(--accent-rgb),.35)!important}
#leaguesView .league-card.has-delete .league-meta{padding:0!important;margin:0!important;display:flex!important;flex-direction:column!important;align-items:flex-start!important;gap:1px!important;line-height:1.15}
#leaguesView .league-card.has-delete .league-meta>*{margin:0!important}
#leaguesView .league-card .league-arrow{display:none!important}
#leaguesView .league-edit{position:absolute;right:49px;top:50%;transform:translateY(-50%);height:27px;padding:0 7px;border-radius:8px;display:flex;align-items:center;justify-content:center;color:var(--accent-soft);background:rgba(var(--accent-rgb),.12);border:1px solid rgba(var(--accent-rgb),.34);font-size:8px;font-weight:850;z-index:3;white-space:nowrap}
#leaguesView .league-edit:active{background:rgba(var(--accent-rgb),.22)}
#leaguesView .league-card.has-delete .league-delete{right:11px;top:50%;bottom:auto;transform:translateY(-50%);width:29px;height:27px;border-radius:8px;font-size:12px}
#leaguesView .league-card.selected{border-color:var(--accent)!important;box-shadow:inset 3px 0 var(--accent),0 0 0 1px rgba(var(--accent-rgb),.18),0 0 14px rgba(var(--accent-rgb),.30)!important}
#leaguesView .gts-tournament-line{font-size:9px;color:#b7c8dc;max-width:100%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
#leaguesView .gts-members-line{font-size:10px;font-weight:850;color:var(--accent-soft);max-width:100%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
@media(max-width:430px){
 #leaguesView .league-card.has-delete{min-height:68px;padding:8px 116px 8px 9px!important}
 #leaguesView .league-card.has-delete .league-emblem{flex-basis:44px;width:44px;height:44px;margin-right:9px}
 #leaguesView .league-card.has-delete .league-name{font-size:13px;line-height:16px}
 #leaguesView .league-edit{right:47px;height:25px;padding:0 6px;font-size:7.6px}
 #leaguesView .league-card.has-delete .league-delete{right:10px;width:27px;height:25px}
}
`;
document.head.appendChild(style);
function leagueIdFromCard(card,index){const leagues=window.getLeagues?.()||[],league=leagues[index];if(league?.id!=null){card.dataset.leagueId=String(league.id);return Number(league.id)}const m=String(card.getAttribute('onclick')||'').match(/openLeagueSettings\((\d+)\)/);return m?Number(m[1]):0}
function tournamentFor(league){const tournaments=window.getTournaments?.()||[];return tournaments.find(t=>Number(t.id)===Number(league?.tournament_id)&&Number(t.season)===Number(league?.tournament_season))||tournaments.find(t=>Number(t.id)===Number(league?.tournament_id))||null}
function canManage(league){return league?.member_role==='owner'||window.GTS?.me?.role==='superadmin'}
function applyThemeDirect(id){if(!window.GTS?.api||!id)return;window.GTS.api(`/api/leagues/${id}/theme`).then(t=>{if(t.background){document.body.style.backgroundImage=`linear-gradient(rgba(3,12,22,.74),rgba(3,12,22,.88)),url("${t.background}")`;document.body.style.backgroundSize='cover';document.body.style.backgroundPosition='center top';document.body.style.backgroundAttachment='fixed';document.body.style.backgroundRepeat='no-repeat'}else for(const p of ['background-image','background-size','background-position','background-attachment','background-repeat'])document.body.style.removeProperty(p);if(t.tournament_background)document.documentElement.style.setProperty('--tournament-card-image',`url("${t.tournament_background}")`);else document.documentElement.style.removeProperty('--tournament-card-image')}).catch(()=>{})}
function markSelected(id){document.querySelectorAll('#leaguesView .league-card').forEach(card=>card.classList.toggle('selected',Number(card.dataset.leagueId)===Number(id)))}
function selectLeagueOnly(id){id=Number(id);if(!id)return;window.chooseLeague?.(id);markSelected(id);applyThemeDirect(id);setTimeout(()=>window.applyTournamentBranding?.(),50)}
window.selectLeagueOnly=selectLeagueOnly;
function splitMeta(card){const meta=card.querySelector('.league-meta');if(!meta||meta.dataset.threeRows==='1')return;const text=(meta.textContent||'').trim();const parts=text.split('·').map(x=>x.trim()).filter(Boolean);let members=parts.find(x=>/участник/i.test(x))||'';let tournament=parts.filter(x=>x!==members).join(' · ');if(!members){const m=text.match(/\d+\s*участник\S*/i);members=m?.[0]||'';tournament=m?text.replace(m[0],'').replace(/^\s*[·•-]\s*|\s*[·•-]\s*$/g,'').trim():text}meta.innerHTML=`<div class="gts-tournament-line">${tournament}</div><div class="gts-members-line">${members}</div>`;meta.dataset.threeRows='1'}
function decorate(){const cards=[...document.querySelectorAll('#leaguesView .league-card')],leagues=window.getLeagues?.()||[];cards.forEach((card,index)=>{const id=leagueIdFromCard(card,index),league=leagues.find(x=>Number(x.id)===id)||leagues[index];if(!id)return;card.dataset.leagueId=String(id);const tournament=tournamentFor(league);card.dataset.tournament=String(tournament?.provider_id||'');splitMeta(card);if(canManage(league)&&!card.querySelector('.league-edit')){const btn=document.createElement('span');btn.className='league-edit';btn.setAttribute('role','button');btn.textContent='Изменить';btn.onclick=e=>{e.preventDefault();e.stopPropagation();editLeagueSettings?.(id)};const del=card.querySelector('.league-delete');if(del)card.insertBefore(btn,del);else card.appendChild(btn)}});const selected=Number(window.GTS?.leagueId||0);if(selected)markSelected(selected)}
function install(){if(!editLeagueSettings&&typeof window.openLeagueSettings==='function'){editLeagueSettings=window.openLeagueSettings.bind(window);window.editLeagueSettings=id=>editLeagueSettings?.(Number(id));window.openLeagueSettings=id=>selectLeagueOnly(Number(id))}decorate()}
const observer=new MutationObserver(()=>install());setTimeout(()=>{const root=document.getElementById('leaguesView');if(root)observer.observe(root,{childList:true,subtree:true});install()},200);document.addEventListener('gts:ready',()=>setTimeout(install,100));document.addEventListener('gts:league-change',()=>setTimeout(decorate,50));setInterval(()=>{if(!editLeagueSettings)install()},500);
})();