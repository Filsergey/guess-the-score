(()=>{
const esc=s=>String(s??'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot',"'":'&#039;'}[m]));
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
.club-open{cursor:pointer}.club-open:active{opacity:.72}.club-open .club-name span{text-decoration:underline;text-decoration-color:rgba(var(--gts-accent-rgb,36,164,255),.3);text-underline-offset:2px}
.player-ranking-cell{display:flex!important;align-items:center!important;gap:9px!important;min-width:0}.player-ranking-photo{width:34px;height:34px;flex:0 0 34px;border-radius:50%;overflow:hidden;display:grid;place-items:center;background:color-mix(in srgb,var(--gts-panel,#10263b) 76%,var(--gts-accent,#55aaff) 24%);border:1px solid rgba(var(--gts-accent-rgb,36,164,255),.34)}.player-ranking-photo img{width:100%!important;height:100%!important;object-fit:cover!important;display:block}.player-ranking-photo span{display:grid;place-items:center;width:100%;height:100%;font-size:16px;line-height:1}.player-ranking-copy{min-width:0}.player-ranking-copy .player-ranking-name{display:block;font-size:11px;font-weight:800;line-height:1.25;white-space:normal;overflow-wrap:anywhere}.player-ranking-copy .player-ranking-club{font-size:10px;opacity:.7;margin-top:3px;white-space:normal;line-height:1.2}
.club-sheet-head{text-align:center;padding:4px 0 14px}.club-sheet-logo{width:74px;height:74px;object-fit:contain;margin:0 auto 8px;display:block}.club-sheet-name{font-size:22px;font-weight:950;line-height:1.1}.club-sheet-meta{margin-top:5px;color:var(--gts-muted,#93a8bd);font-size:11px}.club-sheet-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:7px;margin:0 0 13px}.club-sheet-stat{padding:10px 4px;border-radius:12px;background:rgba(255,255,255,.04);border:1px solid rgba(255,255,255,.06);text-align:center}.club-sheet-stat strong{display:block;font-size:15px}.club-sheet-stat span{display:block;margin-top:3px;font-size:8px;color:var(--gts-muted,#93a8bd)}.club-sheet-section{margin:15px 0 7px;font-size:12px;font-weight:900}.club-form{display:flex;gap:6px;margin-bottom:12px}.club-form i{width:30px;height:30px;border-radius:50%;display:grid;place-items:center;font-style:normal;font-weight:950;font-size:10px}.club-form .W{background:rgba(71,196,126,.18);color:#70e5ae;border:1px solid rgba(71,196,126,.32)}.club-form .D{background:rgba(232,183,91,.14);color:#e8b75b;border:1px solid rgba(232,183,91,.28)}.club-form .L{background:rgba(212,124,137,.14);color:#e68b99;border:1px solid rgba(212,124,137,.28)}.club-match{display:flex;align-items:center;gap:9px;padding:9px 0;border-bottom:1px solid rgba(128,150,180,.12)}.club-match img{width:28px;height:28px;object-fit:contain;flex:0 0 28px}.club-match-copy{min-width:0;flex:1}.club-match-copy strong{display:block;font-size:11px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.club-match-copy span{display:block;margin-top:2px;color:var(--gts-muted,#93a8bd);font-size:8.5px}.club-match-score{font-size:13px;font-weight:950}.club-squad{display:grid;grid-template-columns:1fr;gap:7px}.club-player{display:flex;align-items:center;gap:9px;padding:8px;border-radius:12px;background:rgba(255,255,255,.03);border:1px solid rgba(255,255,255,.055)}.club-player img,.club-player-fallback{width:38px;height:38px;border-radius:50%;object-fit:cover;flex:0 0 38px;background:#173653;display:grid;place-items:center}.club-player-copy{min-width:0;flex:1}.club-player-copy strong{font-size:11px;display:block;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.club-player-copy span{font-size:8.5px;color:var(--gts-muted,#93a8bd);display:block;margin-top:3px}.club-player-number{font-size:12px;font-weight:900;color:var(--gts-muted,#93a8bd)}
`;
document.head.appendChild(style);
function groupHtml(g){
 return `<section class="club-table-card"><div class="club-heading">${esc(g.name)}</div>${g.ucl_zones?'<div class="club-legend"><span><i style="background:#55aaff"></i>1–8 — прямой выход в 1/8 финала</span><span><i style="background:#e8b75b"></i>9–24 — стыковые матчи</span><span><i style="background:#d47c89"></i>25–36 — вылет</span></div>':''}<div class="club-table-scroll"><table class="club-table"><thead><tr><th>#</th><th class="club-name">Клуб</th><th title="Игры">И</th><th title="Победы">В</th><th title="Ничьи">Н</th><th title="Поражения">П</th><th title="Забитые и пропущенные мячи">М</th><th title="Разница мячей">±</th><th title="Очки">О</th></tr></thead><tbody>${g.rows.map(r=>`<tr class="${r.zone?'zone-'+r.zone:''} ${g.ucl_zones&&[9,25].includes(r.rank)?'zone-boundary':''} ${r.team_id?'club-open':''}" ${r.team_id?`data-team-id="${r.team_id}"`:''}><td>${n(r.rank)}</td><td class="club-name"><div>${r.logo?`<img src="${esc(r.logo)}" alt="" loading="lazy" onerror="this.style.display='none'">`:''}<span>${esc(r.name)}</span></div></td><td>${n(r.played)}</td><td>${n(r.wins)}</td><td>${n(r.draws)}</td><td>${n(r.losses)}</td><td>${n(r.goals_for)}:${n(r.goals_against)}</td><td>${r.difference>0?'+':''}${n(r.difference)}</td><td>${n(r.points)}</td></tr>`).join('')}</tbody></table></div></section>`;
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
function fmtDate(v){return new Date(v).toLocaleString('ru-RU',{day:'numeric',month:'short',hour:'2-digit',minute:'2-digit'})}
function clubMatch(m){const live=m.status_group==='live',score=(m.own_goals!=null&&m.opponent_goals!=null)?`${m.own_goals}:${m.opponent_goals}`:(live?'LIVE':'—');return `<div class="club-match">${m.opponent?.logo?`<img src="${esc(m.opponent.logo)}" alt="" onerror="this.style.visibility='hidden'">`:''}<div class="club-match-copy"><strong>${esc(m.opponent?.name||'Соперник')}</strong><span>${esc(m.is_home?'Дома':'В гостях')} · ${esc(fmtDate(m.kickoff_at))}${m.round?` · ${esc(m.round)}`:''}</span></div><div class="club-match-score">${esc(score)}</div></div>`}
function squadPlayer(p){return `<div class="club-player">${p.photo?`<img src="${esc(p.photo)}" alt="" loading="lazy" onerror="this.outerHTML='<span class=&quot;club-player-fallback&quot;>👤</span>'">`:'<span class="club-player-fallback">👤</span>'}<div class="club-player-copy"><strong>${esc(p.name)}</strong><span>${esc([p.position,p.nationality].filter(Boolean).join(' · ')||'Игрок')}</span></div><div class="club-player-number">${p.number!=null?'№'+esc(p.number):''}</div></div>`}
async function openClub(teamId){const leagueId=window.GTS?.leagueId,modal=document.getElementById('modal'),box=document.getElementById('sheetContent');if(!leagueId||!modal||!box)return;modal.classList.add('open');box.innerHTML='<div class="loading">Загружаем клуб…</div>';try{const d=await GTS.api(`/api/leagues/${leagueId}/teams/${teamId}/overview`),t=d.team,s=d.standing||{};const form=(d.form||[]).map(x=>`<i class="${esc(x)}">${x==='W'?'В':x==='D'?'Н':'П'}</i>`).join('');box.innerHTML=`<div class="club-sheet-head"><img class="club-sheet-logo" src="${esc(t.logo)}" alt="" onerror="this.style.display='none'"><div class="club-sheet-name">${esc(t.name)}</div><div class="club-sheet-meta">${esc([t.country_code,t.code,d.tournament?.name].filter(Boolean).join(' · '))}</div></div>${d.standing?`<div class="club-sheet-grid"><div class="club-sheet-stat"><strong>${n(s.rank)}</strong><span>место</span></div><div class="club-sheet-stat"><strong>${n(s.points)}</strong><span>очки</span></div><div class="club-sheet-stat"><strong>${n(s.played)}</strong><span>матчи</span></div><div class="club-sheet-stat"><strong>${n(s.goals_for)}:${n(s.goals_against)}</strong><span>мячи</span></div><div class="club-sheet-stat"><strong>${n(s.wins)}</strong><span>победы</span></div><div class="club-sheet-stat"><strong>${n(s.draws)}</strong><span>ничьи</span></div><div class="club-sheet-stat"><strong>${n(s.losses)}</strong><span>поражения</span></div><div class="club-sheet-stat"><strong>${s.difference>0?'+':''}${n(s.difference)}</strong><span>разница</span></div></div>`:''}<div class="club-sheet-section">Форма</div>${form?`<div class="club-form">${form}</div>`:'<div class="empty">Пока нет завершённых матчей</div>'}<div class="club-sheet-section">Последние матчи</div>${(d.recent_matches||[]).map(clubMatch).join('')||'<div class="empty">Матчей пока нет</div>'}<div class="club-sheet-section">Ближайшие матчи</div>${(d.next_matches||[]).map(clubMatch).join('')||'<div class="empty">Ближайших матчей нет</div>'}<div class="club-sheet-section">Состав</div><div class="club-squad">${(d.squad||[]).map(squadPlayer).join('')||'<div class="empty">Состав пока недоступен</div>'}</div><button class="close" id="clubClose">Закрыть</button>`;document.getElementById('clubClose').onclick=()=>modal.classList.remove('open')}catch(e){box.innerHTML=`<div class="sheet-title">Клуб недоступен</div><div class="empty error">${esc(e.message)}</div><button class="close" id="clubClose">Закрыть</button>`;document.getElementById('clubClose').onclick=()=>modal.classList.remove('open')}}
function bindClubs(root){root.querySelectorAll('.club-open[data-team-id]').forEach(row=>{row.onclick=()=>openClub(Number(row.dataset.teamId))})}
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
  root.innerHTML=(d.groups.length?d.groups.map(groupHtml).join(''):'<div class="empty">Таблица турнира пока не опубликована</div>');bindClubs(root);
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
