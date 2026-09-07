(()=>{
const esc=s=>String(s??'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[m]));
const n=v=>v==null?'—':esc(v);
const style=document.createElement('style');
style.textContent=`
.ranking-tabs{display:flex;gap:6px;align-items:center}.ranking-tabs button{flex:1;min-width:0;padding:10px 2px;background:none;border:0;border-bottom:2px solid transparent;color:var(--gts-muted,#93a8bd);font-size:clamp(11px,3.4vw,16px);font-weight:800}.ranking-tabs button.active{color:var(--gts-text,#fff);border-bottom-color:var(--gts-accent,#55aaff)}
.club-table-card{overflow:hidden;margin-bottom:12px;background:var(--gts-panel,#0d1c2e);border:1px solid rgba(var(--gts-accent-rgb,36,164,255),.25);border-radius:16px}
.club-table-scroll{overflow-x:auto}.club-table{width:100%;border-collapse:collapse;font-size:11px;font-variant-numeric:tabular-nums}
.club-table th,.club-table td{padding:10px 3px;text-align:center;border-bottom:1px solid rgba(128,150,180,.15);white-space:nowrap}
.club-table th{font-size:10px;color:var(--gts-muted,#93a8bd)}.club-table .club-name{text-align:left;white-space:normal;min-width:100px}
.club-name>div{display:flex;align-items:center;gap:6px}.club-name span{overflow-wrap:anywhere;font-weight:650;font-size:11px;line-height:1.3}
.club-name img{width:22px;height:22px;object-fit:contain;flex-shrink:0}.club-table td:last-child{font-weight:900}
.club-table .zone-direct td:first-child{box-shadow:inset 3px 0 #55aaff;color:#74b8ff}
.club-table .zone-playoff td:first-child{box-shadow:inset 3px 0 #e8b75b;color:#e8b75b}
.club-table .zone-out td:first-child{box-shadow:inset 3px 0 #d47c89;color:#d47c89}
.club-table .zone-boundary td{border-top:2px solid rgba(150,175,210,.4)}
.club-legend{display:flex;flex-wrap:wrap;gap:4px 12px;padding:0 13px 10px;font-size:10px;line-height:1.4;color:var(--gts-muted,#93a8bd)}.club-legend span{display:inline-flex;align-items:center}
.club-legend i{display:inline-block;width:7px;height:7px;border-radius:2px;margin-right:5px;flex-shrink:0}
.club-heading{padding:13px;font-weight:800;font-size:15px}.club-heading small{display:block;margin-top:4px;font-size:11px;font-weight:400;color:var(--gts-muted,#93a8bd)}
.player-ranking-cell{display:flex!important;align-items:center!important;gap:9px!important;min-width:0}.player-ranking-photo{width:34px;height:34px;flex:0 0 34px;border-radius:50%;overflow:hidden;display:grid;place-items:center;background:color-mix(in srgb,var(--gts-panel,#10263b) 76%,var(--gts-accent,#55aaff) 24%);border:1px solid rgba(var(--gts-accent-rgb,36,164,255),.34)}.player-ranking-photo img{width:100%!important;height:100%!important;object-fit:cover!important;display:block}.player-ranking-photo span{display:grid;place-items:center;width:100%;height:100%;font-size:16px;line-height:1}.player-ranking-copy{min-width:0}.player-ranking-copy .player-ranking-name{display:block;font-size:11px;font-weight:800;line-height:1.25;white-space:normal;overflow-wrap:anywhere}.player-ranking-copy .player-ranking-club{font-size:10px;opacity:.7;margin-top:3px;white-space:normal;line-height:1.2}
`;
document.head.appendChild(style);
function groupHtml(g){
 return `<section class="club-table-card"><div class="club-heading">${esc(g.name)}</div>${g.ucl_zones?'<div class="club-legend"><span><i style="background:#55aaff"></i>1–8 — прямой выход в 1/8 финала</span><span><i style="background:#e8b75b"></i>9–24 — стыковые матчи</span><span><i style="background:#d47c89"></i>25–36 — вылет</span></div>':''}<div class="club-table-scroll"><table class="club-table"><thead><tr><th>#</th><th class="club-name">Клуб</th><th title="Игры">И</th><th title="Победы">В</th><th title="Ничьи">Н</th><th title="Поражения">П</th><th title="Забитые и пропущенные мячи">М</th><th title="Разница мячей">±</th><th title="Очки">О</th></tr></thead><tbody>${g.rows.map(r=>`<tr class="${r.zone?'zone-'+r.zone:''} ${g.ucl_zones&&[9,25].includes(r.rank)?'zone-boundary':''}"><td>${n(r.rank)}</td><td class="club-name"><div>${r.logo?`<img src="${esc(r.logo)}" alt="" loading="lazy" onerror="this.style.display='none'">`:''}<span>${esc(r.name)}</span></div></td><td>${n(r.played)}</td><td>${n(r.wins)}</td><td>${n(r.draws)}</td><td>${n(r.losses)}</td><td>${n(r.goals_for)}:${n(r.goals_against)}</td><td>${r.difference>0?'+':''}${n(r.difference)}</td><td>${n(r.points)}</td></tr>`).join('')}</tbody></table></div></section>`;
}
let request=0,tab='standings';
const finishedByLeague=new Map();
window.setRankingTab=function(next){
 if(!['standings','goals','assists'].includes(next))return;
 tab=next;
 document.querySelectorAll('[data-ranking]').forEach(b=>{b.classList.toggle('active',b.dataset.ranking===tab);b.setAttribute('aria-selected',String(b.dataset.ranking===tab))});
 window.loadTournamentStandings();
};
function playerPhoto(r){const src=`/api/players/provider/sstats/${encodeURIComponent(r.id)}/photo`;return `<span class="player-ranking-photo"><img src="${src}" alt="${esc(r.name)}" loading="lazy" onerror="this.style.display='none';this.nextElementSibling.style.display='grid'"><span style="display:none" aria-hidden="true">👤</span></span>`}
function playersHtml(d){
 const rows=d.rows.filter(r=>r[tab]>0).sort((a,b)=>b[tab]-a[tab]||a.name.localeCompare(b.name));
 let place=0,last=null;
 return `<div class="club-table-card"><div class="club-heading">${tab==='goals'?'Бомбардиры':'Плеймейкеры'}<small>По голам и голевым передачам в завершённых матчах</small></div><div class="club-legend">Учтено матчей: ${d.covered} из ${d.total}${d.covered<d.total?' · Данные неполные':''}</div><div class="club-table-scroll"><table class="club-table"><thead><tr><th>#</th><th class="club-name">Игрок / Клуб</th><th>Голы</th><th>Пасы</th><th>Г+П</th></tr></thead><tbody>${rows.map((r,i)=>{if(r[tab]!==last){place=i+1;last=r[tab]}return `<tr><td>${place}</td><td class="club-name"><div class="player-ranking-cell">${playerPhoto(r)}<div class="player-ranking-copy"><span class="player-ranking-name">${esc(r.name)}</span><div class="player-ranking-club">${esc(r.club)}</div></div></div></td><td>${r.goals}</td><td>${r.assists}</td><td>${r.goals+r.assists}</td></tr>`}).join('')}</tbody></table></div>${rows.length?'':`<div class="empty">Нет данных для рейтинга</div>`}</div>`;
}
window.loadTournamentStandings=async function(options={}){
 const seq=++request,id=window.GTS?.leagueId,silent=Boolean(options?.silent);
 const old=document.getElementById('leaderboard');old.hidden=true;
 let root=document.getElementById('tournamentStandings');
 if(!root){root=document.createElement('div');root.id='tournamentStandings';old.after(root)}
 if(!id){root.innerHTML='<div class="empty">Сначала выбери лигу</div>';return}
 if(!silent||!root.innerHTML)root.innerHTML='<div class="loading">Загружаем таблицу турнира…</div>';
 try{
  const d=await GTS.api(`/api/leagues/${id}/${tab==='standings'?'tournament-standings':'player-rankings'}`);
  if(seq!==request||id!==window.GTS?.leagueId)return;
  if(tab!=='standings'){
   root.innerHTML=playersHtml(d);
   return;
  }
  root.innerHTML=(d.groups.length?d.groups.map(groupHtml).join(''):'<div class="empty">Таблица турнира пока не опубликована</div>');
 }catch(e){if(seq===request&&!silent)root.innerHTML=`<div class="empty error">${esc(e.message)}</div><button class="save secondary" onclick="loadTournamentStandings()">Повторить</button>`}
};
document.addEventListener('gts:matches-updated',event=>{
 const id=Number(window.GTS?.leagueId||0);
 if(!id)return;
 const finished=new Set((event.detail?.matches||[]).filter(m=>m.status_group==='finished').map(m=>Number(m.id)).filter(Boolean));
 const previous=finishedByLeague.get(id);
 finishedByLeague.set(id,finished);
 if(!previous)return;
 let completed=false;
 for(const matchId of finished){if(!previous.has(matchId)){completed=true;break}}
 if(!completed||tab==='standings')return;
 if(document.getElementById('tableView')?.classList.contains('active'))window.loadTournamentStandings({silent:true});
});
})();
