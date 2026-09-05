(()=>{
const quality={high:'Высокое',medium:'Среднее',low:'Низкое'},outcome={home:'Победа хозяев',draw:'Ничья',away:'Победа гостей'};
function e(s=''){return String(s).replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[m]))}
function findMatch(id){return (window.allMatchesData||[]).find(x=>x.id===id)}
window.openOracle=async function(id){
  const modal=document.getElementById('modal'),box=document.getElementById('sheetContent');
  box.innerHTML='<div class="loading">Оракул считает прогноз…</div>';modal.classList.add('open');
  try{
    const r=await fetch(`/api/oracle/matches/${id}`),d=await r.json();if(!r.ok)throw new Error(d.detail||`HTTP ${r.status}`);
    const m=findMatch(id),p=d.probabilities,x=d.xg;
    const factors=(d.key_factors||[]).map(x=>`<div style="padding:7px 0;border-bottom:1px solid #172b40">• ${e(x)}</div>`).join('');
    const risks=(d.failure_risks||[]).map(x=>`<div style="padding:5px 0;color:#93a8bd">• ${e(x)}</div>`).join('');
    box.innerHTML=`<div class="sheet-round">✦ ОРАКУЛ · ${quality[d.data_quality]||d.data_quality}</div><div class="sheet-title" style="text-align:center">Прогноз ИИ</div>${m?`<div style="text-align:center;color:#93a8bd;font-size:13px">${e(m.home.name)} — ${e(m.away.name)}</div>`:''}<div style="text-align:center;font-size:42px;font-weight:900;margin:15px 0 2px">${d.home_score}:${d.away_score}</div><div style="text-align:center;color:#70e5ae;font-weight:800">${outcome[d.outcome]||d.outcome}</div><div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin:18px 0"><div class="card" style="padding:12px;text-align:center"><div class="meta">Уверенность</div><strong style="font-size:20px">${d.confidence}%</strong></div><div class="card" style="padding:12px;text-align:center"><div class="meta">Качество данных</div><strong>${quality[d.data_quality]||d.data_quality}</strong></div></div>${p?`<div class="card" style="padding:13px;margin-bottom:10px"><div class="meta">Вероятности 1 / X / 2</div><div style="display:flex;justify-content:space-between;margin-top:7px;font-weight:800"><span>${p.home}%</span><span>${p.draw}%</span><span>${p.away}%</span></div></div>`:''}${x?`<div class="card" style="padding:13px;margin-bottom:10px"><div class="meta">Ожидаемые голы xG</div><div style="font-size:18px;font-weight:850;margin-top:5px">${x.home} — ${x.away}</div></div>`:''}<div style="margin:15px 0 7px;font-weight:850">Почему такой прогноз</div><div style="font-size:13px;color:#b8c9d8;line-height:1.45">${e(d.reasoning)}</div><div style="margin:15px 0 5px;font-weight:850">Ключевые факторы</div><div style="font-size:13px">${factors}</div><div style="margin:15px 0 5px;font-weight:850">Что может сломать прогноз</div><div style="font-size:12px">${risks}</div><button class="close" onclick="closeSheet()">Закрыть</button>`;
  }catch(err){box.innerHTML=`<div class="sheet-title">Оракул недоступен</div><div class="error">${e(err.message)}</div><button class="close" onclick="closeSheet()">Закрыть</button>`}
};
// Intercept the existing Oracle placeholder buttons without rewriting the match renderer.
document.addEventListener('click',ev=>{const b=ev.target.closest?.('.action.ai');if(!b)return;const card=b.closest('.match');if(!card)return;const raw=card.getAttribute('onclick')||'',m=raw.match(/openPrediction\((\d+)\)/);if(!m)return;ev.preventDefault();ev.stopImmediatePropagation();window.openOracle(Number(m[1]));},true);
// Existing app keeps match data in a top-level lexical variable; expose it lazily from card ids when possible.
Object.defineProperty(window,'allMatchesData',{configurable:true,get(){try{return eval('allMatchesData')}catch{return[]}}});
})();
