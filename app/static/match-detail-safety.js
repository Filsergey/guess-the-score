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

/* Hard watchdog: with either the current or a cached older match-detail script,
   kill a details request after 6 seconds and leave the already-rendered score sheet usable. */
const started=new WeakMap();
const stopped=new WeakSet();
function watchLoading(){
  const el=box.querySelector('[data-match-detail-id] .match-detail-loading');
  if(!el)return;
  if(!started.has(el)){started.set(el,Date.now());return}
  if(Date.now()-started.get(el)<6000||stopped.has(el))return;
  stopped.add(el);
  abortMatchLoad();
  if(!modal.classList.contains('open'))return;
  el.className='match-detail-note';
  el.textContent='Подробности SStats не ответили за 6 секунд. Основные данные матча доступны.';
}
setInterval(watchLoading,300);
window.closeMatchDetail=closeMatchSheet;
})();