(function(){
var style=document.createElement('style');
style.textContent=`
.sheet-match-head{margin-top:14px;display:grid;grid-template-columns:minmax(0,1fr) 48px minmax(0,1fr);align-items:center;gap:8px}
.sheet-club{min-width:0;text-align:center;display:flex;flex-direction:column;align-items:center}
.sheet-logo-box{width:76px;height:76px;display:flex;align-items:center;justify-content:center;margin-bottom:8px}
.sheet-logo-box img{display:block;max-width:68px;max-height:68px;width:auto!important;height:auto!important;object-fit:contain;margin:0!important}
.sheet-logo-box .crest{width:64px!important;height:64px!important;margin:0!important}
.sheet-club-name{font-size:16px;font-weight:850;line-height:1.15;min-height:38px;display:flex;align-items:flex-start;justify-content:center;text-align:center;word-break:normal;overflow-wrap:anywhere}
.sheet-vs{align-self:center;text-align:center;color:#8ba1b6;font-size:15px;font-weight:900;padding-bottom:28px}
.sheet .score-row{margin:18px 0 10px}
.sheet .score{width:84px;height:68px;font-size:30px}
@media(max-width:390px){
 .sheet-match-head{grid-template-columns:minmax(0,1fr) 42px minmax(0,1fr);gap:4px}
 .sheet-logo-box{width:68px;height:68px}
 .sheet-logo-box img{max-width:60px;max-height:60px}
 .sheet-club-name{font-size:15px;min-height:36px}
}
`;
document.head.appendChild(style);
function esc(s){return String(s==null?'':s).replace(/[&<>"']/g,function(m){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[m]})}
function clubLogo(t){return t&&t.logo?'<img src="'+esc(t.logo)+'" alt="">':'<div class="crest"></div>'}
function getFmt(dt){var d=new Date(dt);return d.toLocaleTimeString('ru-RU',{hour:'2-digit',minute:'2-digit'})}
function openPredictionFixed(id){
 var data=window.allMatchesData||[];
 var m=data.find?data.find(function(x){return x.id===id}):null;
 if(!m)return;
 window.activeMatch=m;
 var preds=window.myPredictions||{};
 var p=preds[id];
 var locked=new Date(m.kickoff_at)<=new Date();
 var sheet=document.getElementById('sheetContent'),modal=document.getElementById('modal');
 if(!sheet||!modal)return;
 var hs=p&&p.home_score!=null?p.home_score:'';
 var as=p&&p.away_score!=null?p.away_score:'';
 sheet.innerHTML='<div class="sheet-round">'+esc(m.round||'Лига чемпионов')+' · '+esc(getFmt(m.kickoff_at))+'</div>'+
 '<div class="sheet-match-head">'+
  '<div class="sheet-club"><div class="sheet-logo-box">'+clubLogo(m.home)+'</div><div class="sheet-club-name">'+esc(m.home.name)+'</div></div>'+
  '<div class="sheet-vs">VS</div>'+
  '<div class="sheet-club"><div class="sheet-logo-box">'+clubLogo(m.away)+'</div><div class="sheet-club-name">'+esc(m.away.name)+'</div></div>'+
 '</div>'+
 '<div class="score-row"><input id="modalHome" class="score" type="number" min="0" max="30" value="'+hs+'" placeholder="0" '+(locked?'disabled':'')+'><span class="colon">:</span><input id="modalAway" class="score" type="number" min="0" max="30" value="'+as+'" placeholder="0" '+(locked?'disabled':'')+'></div>'+
 '<div id="modalNote" class="sheet-note">'+(locked?'Матч начался — прогноз закрыт':p?'Можно изменить прогноз до начала матча':'Прогноз скрыт от других до начала матча')+'</div>'+
 (locked?'':'<button id="modalSave" type="button" class="save" onclick="savePrediction()">'+(p?'Изменить прогноз':'Сохранить прогноз')+'</button>')+
 '<button type="button" class="close" onclick="closeSheet()">Закрыть</button>';
 modal.classList.add('open');
}
function apply(){
 if(window.openPrediction){window.openPrediction=openPredictionFixed;}
}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',apply);else apply();
setTimeout(apply,0);
})();