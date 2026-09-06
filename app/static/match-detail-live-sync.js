(()=>{
const box=document.getElementById('sheetContent');if(!box)return;
const style=document.createElement('style');style.textContent=`.md-my-prediction{margin-top:5px;font-size:10px;line-height:1.2;font-weight:850;color:var(--md-stat-home,var(--gts-accent,#8dbdff));white-space:nowrap}.md-my-prediction span{font-size:12px;font-weight:950}`;document.head.appendChild(style);
const esc=s=>String(s??'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[m]));
function canonicalLabel(m){const raw=String(m?.status??'').toUpperCase(),label=String(m?.status_label||'').toLowerCase();if(raw==='4'||raw==='HT'||/halftime|half time|перерыв/.test(label))return'Перерыв';if(raw==='3'||raw==='1H'||/first half|1-й тайм|первый тайм/.test(label))return'1-й тайм';if(raw==='5'||raw==='2H'||/second half|2-й тайм|второй тайм/.test(label))return'2-й тайм';if(raw==='6'||raw==='ET'||/extra time|доп/.test(label))return'Доп. время';if(raw==='7'||raw==='PEN'||/penalt|пенальти/.test(label))return'Пенальти';if(m?.status_group==='finished')return m.status_label||'Завершён';return m?.status_label||'LIVE'}
function setText(el,value){if(!el)return;const next=String(value??'');if(el.textContent!==next)el.textContent=next}
function prediction(root,id){
 const score=root.querySelector('.match-detail-score');if(!score)return;
 const all=[...score.querySelectorAll('.md-my-prediction')],existing=all[0]||null;
 for(let i=1;i<all.length;i++)all[i].remove();
 const p=window.getMatchPrediction?.(id);
 if(!p){if(existing)existing.remove();return}
 const key=`${p.home_score}:${p.away_score}`;
 if(existing?.dataset?.predictionScore===key)return;
 const el=existing||document.createElement('div');el.className='md-my-prediction';el.dataset.predictionScore=key;el.innerHTML=`Мой прогноз <span>${esc(p.home_score)}:${esc(p.away_score)}</span>`;if(!existing)score.appendChild(el)
}
function sync(){
 const root=box.querySelector('[data-match-detail-id]');if(!root)return;
 const id=Number(root.dataset.matchDetailId),m=window.GTS?.match?.(id);if(!m)return;
 const big=root.querySelector('.match-detail-score .big'),status=root.querySelector('.match-detail-score .status');
 if(m.status_group==='live'){
  setText(big,`${m.home?.goals??0}:${m.away?.goals??0}`);
  setText(status,`${canonicalLabel(m)}${m.elapsed!==null&&m.elapsed!==undefined&&m.elapsed!==''?` · ${m.elapsed}′`:''}`)
 }else if(m.status_group==='finished'){
  setText(big,`${m.home?.goals??'–'}:${m.away?.goals??'–'}`);
  setText(status,canonicalLabel(m))
 }
 prediction(root,id)
}
let queued=false;function queueSync(){if(queued)return;queued=true;requestAnimationFrame(()=>{queued=false;sync()})}
new MutationObserver(queueSync).observe(box,{childList:true,subtree:true});
document.addEventListener('gts:matches-updated',queueSync);document.addEventListener('gts:league-change',()=>setTimeout(queueSync,60));document.addEventListener('visibilitychange',()=>{if(!document.hidden)setTimeout(queueSync,50)});setInterval(sync,1200);
})();