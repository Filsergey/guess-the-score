(()=>{
const css=document.createElement('style');css.textContent=`
.match-participant{display:flex;align-items:center;gap:10px;padding:12px 0;border-bottom:1px solid #172b40}.match-participant:last-child{border-bottom:0}.match-participant .avatar{width:38px;height:38px;flex:0 0 38px}.match-participant-main{min-width:0;flex:1}.match-participant-name{font-weight:800;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.match-participant-pred{font-size:17px;font-weight:900;min-width:58px;text-align:right}.match-participant-pred.hidden{font-size:12px;color:#70e5ae;font-weight:750}.match-participant-points{font-size:11px;color:#70e5ae;text-align:right;margin-top:2px}.privacy-note{padding:10px 12px;border-radius:13px;background:#0d2134;border:1px solid #1e405e;color:#91a9bf;font-size:12px;line-height:1.35;margin:10px 0}
`;document.head.appendChild(css);
const e=s=>String(s??'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[m]));
function matchById(id){return (window.allMatchesData||[]).find(x=>x.id===id)}
function avatar(x){return x.avatar_url?`<img class="avatar" src="${e(x.avatar_url)}" alt="">`:'<div class="avatar"></div>'}
window.openMatchParticipants=async function(id){
 const modal=document.getElementById('modal'),box=document.getElementById('sheetContent'),m=matchById(id);box.innerHTML='<div class="loading">Загружаем прогнозы…</div>';modal.classList.add('open');
 try{
  const d=await window.api(`/api/predictions/matches/${id}/participants`),rows=d.response||[];
  const list=rows.map(x=>{const p=x.prediction,score=p?`${p.home_score}:${p.away_score}`:'✓ прогноз есть',pts=p?.points;return `<div class="match-participant">${avatar(x)}<div class="match-participant-main"><div class="match-participant-name">${e(x.display_name||x.username||'Игрок')}${x.is_mine?' · ты':''}</div><div class="meta">${x.username?'@'+e(x.username):'участник'}</div></div><div><div class="match-participant-pred ${p?'':'hidden'}">${score}</div>${pts!=null?`<div class="match-participant-points">+${pts} очк.</div>`:''}</div></div>`}).join('');
  const privacy=d.predictions_visible?'Матч начался — прогнозы участников открыты.':'До начала матча чужие счета скрыты. Видно только, кто сделал прогноз.';
  box.innerHTML=`<div class="sheet-round">${e(m?.round||'Лига чемпионов')}</div><div class="sheet-title">Участники матча</div>${m?`<div style="text-align:center;color:#b7c9d9;font-weight:800;margin-bottom:10px">${e(m.home.name)} — ${e(m.away.name)}</div>`:''}<div class="privacy-note">${privacy}</div><div class="meta" style="margin:10px 0">Прогноз сделали: ${d.count}</div>${list||'<div class="empty">Пока никто не сделал прогноз</div>'}<button class="close" onclick="closeSheet()">Закрыть</button>`;
 }catch(err){box.innerHTML=`<div class="sheet-title">Не удалось загрузить прогнозы</div><div class="error">${e(err.message)}</div><button class="close" onclick="closeSheet()">Закрыть</button>`}
};
document.addEventListener('click',ev=>{const b=ev.target.closest?.('.match .action:not(.ai)');if(!b)return;const card=b.closest('.match'),raw=card?.getAttribute('onclick')||'',m=raw.match(/openPrediction\((\d+)\)/);if(!m)return;ev.preventDefault();ev.stopImmediatePropagation();window.openMatchParticipants(Number(m[1]));},true);
})();
