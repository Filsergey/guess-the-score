(()=>{
const style=document.createElement('style');
style.textContent=`
:root{--md-stat-home:#2c8df4;--md-stat-away:#9b6cff}
.md-bar{height:6px!important;background:rgba(127,127,127,.12)!important}
.md-bar span:first-child{background:var(--md-stat-home)!important}
.md-bar span:last-child{background:var(--md-stat-away)!important}
.md-stat .n:first-child{color:var(--md-stat-home)!important}
.md-stat .n:last-child{color:var(--md-stat-away)!important}
.md-stat-legend{display:grid;grid-template-columns:1fr 1fr;gap:10px;align-items:center;margin:0 0 9px;padding:8px 10px;border-radius:11px;background:rgba(127,127,127,.07);font-size:9px;font-weight:800}
.md-stat-legend-side{display:flex;align-items:center;gap:6px;min-width:0}
.md-stat-legend-side:last-child{justify-content:flex-end;text-align:right}
.md-stat-legend-name{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.md-stat-dot{width:9px;height:9px;border-radius:50%;flex:0 0 9px}
.md-stat-dot.home{background:var(--md-stat-home)}
.md-stat-dot.away{background:var(--md-stat-away)}
.md-my-prediction{margin-top:5px;font-size:10px;line-height:1.2;font-weight:850;color:var(--md-stat-home);white-space:nowrap}
.md-my-prediction span{font-size:12px;font-weight:950}
html[data-gts-tournament-theme='ucl']{--md-stat-home:#20a7ff;--md-stat-away:#f5f9ff}
html[data-gts-tournament-theme='laliga']{--md-stat-home:#a965ff;--md-stat-away:#ff4655}
html[data-gts-tournament-theme='epl']{--md-stat-home:#37003c;--md-stat-away:#04f5ff}
html[data-gts-tournament-theme='seriea']{--md-stat-home:#071a38;--md-stat-away:#22b8ff}
html[data-gts-tournament-theme='bundesliga']{--md-stat-home:#111111;--md-stat-away:#d20515}
html[data-gts-tournament-theme='ucl'] .md-stat-legend{background:rgba(255,255,255,.05)}
html[data-gts-tournament-theme='laliga'] .md-stat-legend,html[data-gts-tournament-theme='epl'] .md-stat-legend,html[data-gts-tournament-theme='seriea'] .md-stat-legend,html[data-gts-tournament-theme='bundesliga'] .md-stat-legend{background:#f5f5f5;color:#111}
`;
document.head.appendChild(style);
const esc=s=>String(s??'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[m]));
function cleanupPredictionDuplicates(root){const all=[...(root?.querySelectorAll('.md-my-prediction')||[])];all.slice(1).forEach(x=>x.remove())}
function decorateStats(root){
 const body=root?.querySelector('[data-md-body="stats"]');
 if(!root||!body||body.dataset.loaded!=='1'||body.querySelector('.md-stat-legend'))return;
 const id=Number(root.dataset.matchDetailId),match=window.GTS?.match?.(id);
 if(!match)return;
 const legend=document.createElement('div');legend.className='md-stat-legend';
 legend.innerHTML=`<div class="md-stat-legend-side"><span class="md-stat-dot home"></span><span class="md-stat-legend-name">${esc(match.home?.name||'Хозяева')}</span></div><div class="md-stat-legend-side"><span class="md-stat-legend-name">${esc(match.away?.name||'Гости')}</span><span class="md-stat-dot away"></span></div>`;
 body.prepend(legend);
}
function decorate(){const root=document.querySelector('#sheetContent [data-match-detail-id]');if(!root)return;cleanupPredictionDuplicates(root);decorateStats(root)}
new MutationObserver(()=>queueMicrotask(decorate)).observe(document.getElementById('sheetContent')||document.body,{childList:true,subtree:true,attributes:true,attributeFilter:['data-loaded']});
document.addEventListener('click',e=>{if(e.target?.closest?.('[data-md-toggle="stats"]'))setTimeout(decorate,60)},true);
document.addEventListener('gts:matches-updated',()=>setTimeout(decorate,50));
setInterval(decorate,900);
})();