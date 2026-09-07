(()=>{
const esc=s=>String(s??'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[m]));
const n=v=>v==null?'—':esc(v);
const style=document.createElement('style');
style.textContent=`
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
.club-legend{padding:12px;font-size:11px;line-height:1.7;color:var(--gts-muted,#93a8bd)}.club-legend span{display:block}
.club-legend i{display:inline-block;width:7px;height:7px;border-radius:2px;margin-right:7px}
.club-heading{padding:13px;font-weight:800;font-size:15px}.club-heading small{display:block;margin-top:4px;font-size:11px;font-weight:400;color:var(--gts-muted,#93a8bd)}
`;
document.head.appendChild(style);
function groupHtml(g){
 return `<section class="club-table-card"><div class="club-heading">${esc(g.name)}</div><div class="club-table-scroll"><table class="club-table"><thead><tr><th>#</th><th class="club-name">Клуб</th><th title="Игры">И</th><th title="Победы">В</th><th title="Ничьи">Н</th><th title="Поражения">П</th><th title="Забитые и пропущенные мячи">М</th><th title="Разница мячей">±</th><th title="Очки">О</th></tr></thead><tbody>${g.rows.map(r=>`<tr class="${r.zone?'zone-'+r.zone:''} ${g.ucl_zones&&[9,25].includes(r.rank)?'zone-boundary':''}"><td>${n(r.rank)}</td><td class="club-name"><div>${r.logo?`<img src="${esc(r.logo)}" alt="" loading="lazy" onerror="this.style.display='none'">`:''}<span>${esc(r.name)}</span></div></td><td>${n(r.played)}</td><td>${n(r.wins)}</td><td>${n(r.draws)}</td><td>${n(r.losses)}</td><td>${n(r.goals_for)}:${n(r.goals_against)}</td><td>${r.difference>0?'+':''}${n(r.difference)}</td><td>${n(r.points)}</td></tr>`).join('')}</tbody></table></div>${g.ucl_zones?'<div class="club-legend"><span><i style="background:#55aaff"></i>1–8 — прямой выход в 1/8 финала</span><span><i style="background:#e8b75b"></i>9–24 — стыковые матчи</span><span><i style="background:#d47c89"></i>25–36 — вылет</span>Зоны по текущему положению в таблице.</div>':''}</section>`;
}
let request=0;
window.loadTournamentStandings=async function(){
 const seq=++request,id=window.GTS?.leagueId;
 const old=document.getElementById('leaderboard');old.hidden=true;
 let root=document.getElementById('tournamentStandings');
 if(!root){root=document.createElement('div');root.id='tournamentStandings';old.after(root)}
 if(!id){root.innerHTML='<div class="empty">Сначала выбери лигу</div>';return}
 root.innerHTML='<div class="loading">Загружаем таблицу турнира…</div>';
 try{
  const d=await GTS.api(`/api/leagues/${id}/tournament-standings`);
  if(seq!==request||id!==window.GTS?.leagueId)return;
  root.innerHTML=`<div class="club-heading">${esc(d.name)}<small>Сезон ${esc(d.season)}</small></div>`+(d.groups.length?d.groups.map(groupHtml).join(''):'<div class="empty">Таблица турнира пока не опубликована</div>');
 }catch(e){if(seq===request)root.innerHTML=`<div class="empty error">${esc(e.message)}</div><button class="save secondary" onclick="loadTournamentStandings()">Повторить</button>`}
};
})();
