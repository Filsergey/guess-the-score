(()=>{
const esc=s=>String(s??'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[m]));
const leagues=()=>window.getLeagues?.()||window.GTS?.leagues||[];
const getLeague=id=>leagues().find(x=>Number(x.id)===Number(id));

const style=document.createElement('style');
style.textContent=`
#modal .sheet:has(.gts-league-members){background:var(--gts-panel,#10263b)!important;color:var(--gts-text,#f5f9ff)!important;border-color:rgba(var(--gts-accent-rgb,36,164,255),.28)!important}
.gts-league-members-head{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:6px}
.gts-league-members-title{font-size:20px;font-weight:900;color:var(--gts-text,#f5f9ff);min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.gts-league-members-count{flex:0 0 auto;font-size:10px;font-weight:850;color:var(--gts-accent,#24a4ff);border:1px solid rgba(var(--gts-accent-rgb,36,164,255),.30);background:rgba(var(--gts-accent-rgb,36,164,255),.08);padding:6px 9px;border-radius:999px}
.gts-league-members-sub{font-size:10px;color:var(--gts-muted,#8da1b6);margin-bottom:13px}
.gts-league-member-list{display:flex;flex-direction:column}
.gts-league-member{display:flex;align-items:center;gap:11px;padding:11px 0;border-bottom:1px solid rgba(var(--gts-accent-rgb,36,164,255),.13)}
.gts-league-member:last-child{border-bottom:0}
.gts-league-member-avatar{width:42px;height:42px;flex:0 0 42px;border-radius:50%;overflow:hidden;display:flex;align-items:center;justify-content:center;background:rgba(var(--gts-accent-rgb,36,164,255),.10);border:1px solid rgba(var(--gts-accent-rgb,36,164,255),.28);font-size:18px;font-weight:900;color:var(--gts-accent,#24a4ff)}
.gts-league-member-avatar img{width:100%;height:100%;object-fit:cover}
.gts-league-member-copy{min-width:0;flex:1}
.gts-league-member-name{font-size:13px;font-weight:900;color:var(--gts-text,#f5f9ff);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.gts-league-member-user{font-size:10px;color:var(--gts-muted,#8da1b6);margin-top:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.gts-league-member-role{flex:0 0 auto;font-size:7px;font-weight:900;letter-spacing:.04em;color:var(--gts-accent,#24a4ff);border:1px solid rgba(var(--gts-accent-rgb,36,164,255),.32);background:rgba(var(--gts-accent-rgb,36,164,255),.08);padding:4px 6px;border-radius:6px}
.gts-league-members-loading{padding:24px 0;text-align:center;color:var(--gts-muted,#8da1b6);font-size:12px}
`;
document.head.appendChild(style);

function initials(name){const parts=String(name||'?').trim().split(/\s+/).filter(Boolean);return (parts.slice(0,2).map(x=>x[0]).join('')||'?').toUpperCase()}
function roleLabel(role){return role==='owner'?'ВЛАДЕЛЕЦ':role==='admin'?'АДМИН':''}
function selectLeague(id){if(typeof window.selectLeagueOnly==='function')window.selectLeagueOnly(id);else window.chooseLeague?.(id)}

async function openLeagueMembers(id){
 id=Number(id);const league=getLeague(id);if(!id||!league)return;
 selectLeague(id);
 window.openSheet?.(`<div class="gts-league-members"><div class="gts-league-members-head"><div class="gts-league-members-title">${esc(league.name)}</div><div class="gts-league-members-count">${Number(league.member_count)||0} участн.</div></div><div class="gts-league-members-sub">Участники лиги</div><div class="gts-league-members-loading">Загружаем участников…</div><button class="close" onclick="closeSheet()">Закрыть</button></div>`);
 try{
  const data=await window.GTS.api(`/api/leagues/${id}/members`);
  const rows=(data.response||[]).slice().sort((a,b)=>(a.role==='owner'?-1:0)-(b.role==='owner'?-1:0));
  const count=Number(data.count)||rows.length;
  const list=rows.length?rows.map(m=>{const role=roleLabel(m.role);return `<div class="gts-league-member"><div class="gts-league-member-avatar">${m.avatar_url?`<img src="${esc(m.avatar_url)}" alt="">`:esc(initials(m.display_name))}</div><div class="gts-league-member-copy"><div class="gts-league-member-name">${esc(m.display_name||'Участник')}</div><div class="gts-league-member-user">${m.username?'@'+esc(m.username):'Telegram-пользователь'}</div></div>${role?`<div class="gts-league-member-role">${role}</div>`:''}</div>`}).join(''):'<div class="gts-league-members-loading">В лиге пока нет участников</div>';
  window.openSheet?.(`<div class="gts-league-members"><div class="gts-league-members-head"><div class="gts-league-members-title">${esc(league.name)}</div><div class="gts-league-members-count">${count} участн.</div></div><div class="gts-league-members-sub">Участники лиги</div><div class="gts-league-member-list">${list}</div><button class="close" onclick="closeSheet()">Закрыть</button></div>`);
 }catch(e){
  window.openSheet?.(`<div class="gts-league-members"><div class="gts-league-members-head"><div class="gts-league-members-title">${esc(league.name)}</div></div><div class="gts-league-members-loading">${esc(e.message||'Не удалось загрузить участников')}</div><button class="close" onclick="closeSheet()">Закрыть</button></div>`);
 }
}
window.openLeagueMembers=openLeagueMembers;

function install(){
 const root=document.getElementById('leaguesView');
 if(!root||root.dataset.gtsMembersClick==='1')return;
 root.dataset.gtsMembersClick='1';
 root.addEventListener('click',e=>{
  const card=e.target.closest('.league-card');
  if(!card||!root.contains(card))return;
  if(e.target.closest('.gts-league-manage,.league-edit,.league-delete'))return;
  const id=Number(card.dataset.leagueId||0);
  if(!id)return;
  e.preventDefault();e.stopImmediatePropagation();
  openLeagueMembers(id);
 },true);
}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',install);else install();
document.addEventListener('gts:ready',install);
})();