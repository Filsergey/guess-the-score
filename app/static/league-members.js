(()=>{
const esc=s=>String(s??'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot',"'":'&#039;'}[m]));

const style=document.createElement('style');
style.textContent=`
.gts-manage-members-head{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-bottom:8px}
.gts-manage-members-count,.gts-header-members-count{flex:0 0 auto;font-size:9px;font-weight:850;color:var(--gts-accent,#24a4ff);border:1px solid rgba(var(--gts-accent-rgb,36,164,255),.30);background:rgba(var(--gts-accent-rgb,36,164,255),.08);padding:5px 8px;border-radius:999px}
.gts-manage-members-list,.gts-header-members-list{display:flex;flex-direction:column}
.gts-manage-member,.gts-header-member{display:flex;align-items:center;gap:10px;padding:9px 0;border-bottom:1px solid rgba(var(--gts-accent-rgb,36,164,255),.13)}
.gts-manage-member:last-child,.gts-header-member:last-child{border-bottom:0}
.gts-manage-member-avatar,.gts-header-member-avatar{width:38px;height:38px;flex:0 0 38px;border-radius:50%;overflow:hidden;display:flex;align-items:center;justify-content:center;background:rgba(var(--gts-accent-rgb,36,164,255),.10);border:1px solid rgba(var(--gts-accent-rgb,36,164,255),.28);font-size:15px;font-weight:900;color:var(--gts-accent,#24a4ff)}
.gts-manage-member-avatar img,.gts-header-member-avatar img{width:100%;height:100%;object-fit:cover}
.gts-manage-member-copy,.gts-header-member-copy{min-width:0;flex:1}
.gts-manage-member-name,.gts-header-member-name{font-size:12px;font-weight:900;color:var(--gts-text,#f5f9ff);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.gts-manage-member-user,.gts-header-member-user{font-size:9px;color:var(--gts-muted,#8da1b6);margin-top:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.gts-manage-member-role,.gts-header-member-role{flex:0 0 auto;font-size:6.5px;font-weight:900;letter-spacing:.04em;color:var(--gts-accent,#24a4ff);border:1px solid rgba(var(--gts-accent-rgb,36,164,255),.32);background:rgba(var(--gts-accent-rgb,36,164,255),.08);padding:4px 6px;border-radius:6px}
.gts-manage-members-loading,.gts-header-members-loading{padding:10px 0;color:var(--gts-muted,#8da1b6);font-size:10px}
.gts-header-members-head{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-bottom:4px}
.gts-header-members-title{font-size:20px;font-weight:900;color:var(--gts-text,#f5f9ff);min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.gts-header-members-sub{font-size:10px;color:var(--gts-muted,#8da1b6);margin-bottom:12px}
#leagueSelect{cursor:pointer}
`;
document.head.appendChild(style);

function initials(name){const parts=String(name||'?').trim().split(/\s+/).filter(Boolean);return (parts.slice(0,2).map(x=>x[0]).join('')||'?').toUpperCase()}
function roleLabel(role){return role==='owner'?'ВЛАДЕЛЕЦ':role==='admin'?'АДМИН':''}
function selectedLeague(){return window.getSelectedLeague?.()||null}
function selectedLeagueId(){return Number(selectedLeague()?.id||window.GTS?.leagueId||0)}
function memberHtml(m,prefix='gts-manage'){const role=roleLabel(m.role);return `<div class="${prefix}-member"><div class="${prefix}-member-avatar">${m.avatar_url?`<img src="${esc(m.avatar_url)}" alt="">`:esc(initials(m.display_name))}</div><div class="${prefix}-member-copy"><div class="${prefix}-member-name">${esc(m.display_name||'Участник')}</div><div class="${prefix}-member-user">${m.username?'@'+esc(m.username):'Telegram-пользователь'}</div></div>${role?`<div class="${prefix}-member-role">${role}</div>`:''}</div>`}
function sortMembers(rows){return rows.slice().sort((a,b)=>Number(b.role==='owner')-Number(a.role==='owner'))}

async function openHeaderMembers(){
 const league=selectedLeague(),id=selectedLeagueId();
 if(!league||!id){window.openLeagues?.();return}
 window.openSheet?.(`<div class="gts-header-members"><div class="gts-header-members-head"><div class="gts-header-members-title">${esc(league.name)}</div><div class="gts-header-members-count">${Number(league.member_count)||'…'}</div></div><div class="gts-header-members-sub">Участники лиги</div><div class="gts-header-members-list"><div class="gts-header-members-loading">Загружаем участников…</div></div><button class="close" onclick="closeSheet()">Закрыть</button></div>`);
 try{
  const data=await window.GTS.api(`/api/leagues/${id}/members`);
  const rows=sortMembers(data.response||[]),count=Number(data.count)||rows.length;
  const content=document.getElementById('sheetContent');
  if(!content?.querySelector('.gts-header-members'))return;
  const countEl=content.querySelector('.gts-header-members-count');if(countEl)countEl.textContent=String(count);
  const list=content.querySelector('.gts-header-members-list');if(list)list.innerHTML=rows.length?rows.map(m=>memberHtml(m,'gts-header')).join(''):'<div class="gts-header-members-loading">В лиге пока нет участников</div>';
 }catch(e){
  const list=document.querySelector('#sheetContent .gts-header-members-list');if(list)list.innerHTML=`<div class="gts-header-members-loading">${esc(e.message||'Не удалось загрузить участников')}</div>`;
 }
}
window.openLeagueHeaderMembers=openHeaderMembers;

async function hydrateMembers(section,id){
 if(!section||section.dataset.loading==='1')return;
 section.dataset.loading='1';
 try{
  const data=await window.GTS.api(`/api/leagues/${id}/members`);
  if(!section.isConnected||selectedLeagueId()!==Number(id))return;
  const rows=sortMembers(data.response||[]);
  const count=Number(data.count)||rows.length;
  const countEl=section.querySelector('.gts-manage-members-count');if(countEl)countEl.textContent=String(count);
  const list=section.querySelector('.gts-manage-members-list');if(list)list.innerHTML=rows.length?rows.map(m=>memberHtml(m,'gts-manage')).join(''):'<div class="gts-manage-members-loading">В лиге пока нет участников</div>';
 }catch(e){
  const list=section.querySelector('.gts-manage-members-list');if(list)list.innerHTML=`<div class="gts-manage-members-loading">${esc(e.message||'Не удалось загрузить участников')}</div>`;
 }finally{section.dataset.loading='0'}
}

function installIntoManagement(){
 const content=document.getElementById('sheetContent');
 const head=content?.querySelector('.gts-manage-head');
 if(!head)return;
 const id=selectedLeagueId();if(!id)return;
 let section=content.querySelector('.gts-manage-members-section');
 if(!section){
  section=document.createElement('div');
  section.className='gts-manage-section gts-manage-members-section';
  section.innerHTML='<div class="gts-manage-members-head"><div class="gts-manage-section-title" style="margin:0">Участники</div><div class="gts-manage-members-count">…</div></div><div class="gts-manage-members-list"><div class="gts-manage-members-loading">Загружаем участников…</div></div>';
  const sections=[...content.querySelectorAll('.gts-manage-section')];
  const appearance=sections.find(x=>x.querySelector('.gts-manage-section-title')?.textContent.trim()==='Оформление');
  if(appearance)content.insertBefore(section,appearance);else content.appendChild(section);
 }
 if(Number(section.dataset.leagueId)!==id){section.dataset.leagueId=String(id);section.dataset.loading='0';section.querySelector('.gts-manage-members-count').textContent='…';section.querySelector('.gts-manage-members-list').innerHTML='<div class="gts-manage-members-loading">Загружаем участников…</div>'}
 hydrateMembers(section,id);
}
window.gtsRefreshLeagueMembers=installIntoManagement;

function installHeaderClick(){
 const header=document.getElementById('leagueSelect');
 if(!header||header.dataset.gtsMembersHeader==='1')return;
 header.dataset.gtsMembersHeader='1';
 header.setAttribute('aria-label','Показать участников текущей лиги');
 header.addEventListener('click',e=>{if(!selectedLeagueId())return;e.preventDefault();e.stopImmediatePropagation();openHeaderMembers()},true);
}

let scheduled=false;function schedule(){if(scheduled)return;scheduled=true;requestAnimationFrame(()=>{scheduled=false;installIntoManagement();installHeaderClick()})}
const target=document.getElementById('sheetContent');if(target)new MutationObserver(schedule).observe(target,{childList:true,subtree:true});
document.addEventListener('gts:ready',schedule);document.addEventListener('gts:league-change',schedule);document.addEventListener('DOMContentLoaded',schedule);setTimeout(schedule,300);
})();