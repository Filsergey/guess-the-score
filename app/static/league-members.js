(()=>{
const esc=s=>String(s??'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[m]));

const style=document.createElement('style');
style.textContent=`
.gts-manage-members-head{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-bottom:8px}
.gts-manage-members-count{flex:0 0 auto;font-size:9px;font-weight:850;color:var(--gts-accent,#24a4ff);border:1px solid rgba(var(--gts-accent-rgb,36,164,255),.30);background:rgba(var(--gts-accent-rgb,36,164,255),.08);padding:5px 8px;border-radius:999px}
.gts-manage-members-list{display:flex;flex-direction:column}
.gts-manage-member{display:flex;align-items:center;gap:10px;padding:9px 0;border-bottom:1px solid rgba(var(--gts-accent-rgb,36,164,255),.13)}
.gts-manage-member:last-child{border-bottom:0}
.gts-manage-member-avatar{width:38px;height:38px;flex:0 0 38px;border-radius:50%;overflow:hidden;display:flex;align-items:center;justify-content:center;background:rgba(var(--gts-accent-rgb,36,164,255),.10);border:1px solid rgba(var(--gts-accent-rgb,36,164,255),.28);font-size:15px;font-weight:900;color:var(--gts-accent,#24a4ff)}
.gts-manage-member-avatar img{width:100%;height:100%;object-fit:cover}
.gts-manage-member-copy{min-width:0;flex:1}
.gts-manage-member-name{font-size:12px;font-weight:900;color:var(--gts-text,#f5f9ff);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.gts-manage-member-user{font-size:9px;color:var(--gts-muted,#8da1b6);margin-top:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.gts-manage-member-role{flex:0 0 auto;font-size:6.5px;font-weight:900;letter-spacing:.04em;color:var(--gts-accent,#24a4ff);border:1px solid rgba(var(--gts-accent-rgb,36,164,255),.32);background:rgba(var(--gts-accent-rgb,36,164,255),.08);padding:4px 6px;border-radius:6px}
.gts-manage-members-loading{padding:10px 0;color:var(--gts-muted,#8da1b6);font-size:10px}
`;
document.head.appendChild(style);

function initials(name){const parts=String(name||'?').trim().split(/\s+/).filter(Boolean);return (parts.slice(0,2).map(x=>x[0]).join('')||'?').toUpperCase()}
function roleLabel(role){return role==='owner'?'ВЛАДЕЛЕЦ':role==='admin'?'АДМИН':''}
function selectedLeagueId(){return Number(window.getSelectedLeague?.()?.id||window.GTS?.leagueId||0)}
function memberHtml(m){const role=roleLabel(m.role);return `<div class="gts-manage-member"><div class="gts-manage-member-avatar">${m.avatar_url?`<img src="${esc(m.avatar_url)}" alt="">`:esc(initials(m.display_name))}</div><div class="gts-manage-member-copy"><div class="gts-manage-member-name">${esc(m.display_name||'Участник')}</div><div class="gts-manage-member-user">${m.username?'@'+esc(m.username):'Telegram-пользователь'}</div></div>${role?`<div class="gts-manage-member-role">${role}</div>`:''}</div>`}

async function hydrateMembers(section,id){
 if(!section||section.dataset.loading==='1')return;
 section.dataset.loading='1';
 try{
  const data=await window.GTS.api(`/api/leagues/${id}/members`);
  if(!section.isConnected||selectedLeagueId()!==Number(id))return;
  const rows=(data.response||[]).slice().sort((a,b)=>Number(b.role==='owner')-Number(a.role==='owner'));
  const count=Number(data.count)||rows.length;
  const countEl=section.querySelector('.gts-manage-members-count');if(countEl)countEl.textContent=String(count);
  const list=section.querySelector('.gts-manage-members-list');if(list)list.innerHTML=rows.length?rows.map(memberHtml).join(''):'<div class="gts-manage-members-loading">В лиге пока нет участников</div>';
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

let scheduled=false;function schedule(){if(scheduled)return;scheduled=true;requestAnimationFrame(()=>{scheduled=false;installIntoManagement()})}
const target=document.getElementById('sheetContent');if(target)new MutationObserver(schedule).observe(target,{childList:true,subtree:true});
document.addEventListener('gts:ready',schedule);document.addEventListener('gts:league-change',schedule);setTimeout(schedule,300);
})();