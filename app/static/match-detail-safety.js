(()=>{
const modal=document.getElementById('modal');
const box=document.getElementById('sheetContent');
if(!modal||!box)return;
let closing=false;
function isMatchSheet(){return !!box.querySelector('[data-match-detail-id]')}
function abortMatchLoad(){
  if(typeof window.openMatchDetail!=='function')return;
  try{window.openMatchDetail(Number.NaN)}catch{}
}
function closeMatchSheet(){
  if(closing)return;
  closing=true;
  abortMatchLoad();
  modal.classList.remove('open');
  setTimeout(()=>{
    if(!modal.classList.contains('open')&&isMatchSheet())box.innerHTML='';
    closing=false;
  },0);
}
function closeHandler(e){
  const btn=e.target?.closest?.('#sheetContent .close');
  if(!btn||!isMatchSheet())return;
  e.preventDefault();
  e.stopPropagation();
  e.stopImmediatePropagation?.();
  closeMatchSheet();
}
for(const eventName of ['pointerdown','touchend','click'])document.addEventListener(eventName,closeHandler,true);
modal.addEventListener('pointerdown',e=>{if(e.target===modal&&isMatchSheet()){e.preventDefault();closeMatchSheet()}},true);

/* If another sheet is opened from match details, stop the slow SStats request first
   so it cannot overwrite Participants / Oracle / Prediction afterwards. */
document.addEventListener('pointerdown',e=>{
  const action=e.target?.closest?.('#sheetContent [data-match-detail-id] .match-detail-actions button');
  if(action)abortMatchLoad();
},true);

/* Never leave an endless-looking spinner on screen. The client request has its own
   timeout, but this visual watchdog also works with a cached older match-detail script. */
const started=new WeakMap();
function watchLoading(){
  const el=box.querySelector('[data-match-detail-id] .match-detail-loading');
  if(!el)return;
  if(!started.has(el)){started.set(el,Date.now());return}
  if(Date.now()-started.get(el)<6000)return;
  el.className='match-detail-note';
  el.textContent='Подробности SStats отвечают слишком долго. Основные данные матча уже доступны.';
}
setInterval(watchLoading,500);
window.closeMatchDetail=closeMatchSheet;
})();