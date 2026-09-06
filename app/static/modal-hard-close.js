(()=>{
const modal=document.getElementById('modal');
const box=document.getElementById('sheetContent');
if(!modal||!box)return;
let restoring=false,swallowUntil=0,shieldTimer=null;
function abortMatch(){
  try{document.dispatchEvent(new CustomEvent('gts:force-close-sheet'))}catch{}
  try{if(typeof window.openMatchDetail==='function')window.openMatchDetail(Number.NaN)}catch{}
}
function swallowActive(){return performance.now()<swallowUntil}
function armSwallow(ms=420){swallowUntil=Math.max(swallowUntil,performance.now()+ms)}
function finishClose(){
  clearTimeout(shieldTimer);shieldTimer=null;
  box.innerHTML='';
  modal.style.removeProperty('display');
  modal.style.removeProperty('pointer-events');
  modal.style.removeProperty('opacity');
  modal.style.removeProperty('background');
  modal.removeAttribute('aria-hidden');
  restoring=false;
}
function hardClose(){
  if(restoring){armSwallow();return}
  restoring=true;armSwallow();abortMatch();
  /* Keep an invisible full-screen shield for the rest of this touch/click gesture.
     If the backdrop disappears on pointerdown, Telegram/iOS can deliver the
     following click to the match/card/navigation underneath it. */
  modal.classList.remove('open');
  modal.setAttribute('aria-hidden','true');
  modal.style.setProperty('display','flex','important');
  modal.style.setProperty('pointer-events','auto','important');
  modal.style.setProperty('opacity','0','important');
  modal.style.setProperty('background','transparent','important');
  document.body.style.removeProperty('overflow');
  shieldTimer=setTimeout(finishClose,430);
}
function reopenReady(){
  clearTimeout(shieldTimer);shieldTimer=null;restoring=false;swallowUntil=0;
  modal.style.removeProperty('display');
  modal.style.removeProperty('pointer-events');
  modal.style.removeProperty('opacity');
  modal.style.removeProperty('background');
  modal.removeAttribute('aria-hidden');
}
const oldOpen=window.openSheet;
window.openSheet=function(html){reopenReady();return oldOpen?oldOpen(html):(box.innerHTML=html,modal.classList.add('open'))};
window.closeSheet=hardClose;
window.forceCloseSheet=hardClose;
function consume(e){
  if(!swallowActive())return;
  e.preventDefault();e.stopPropagation();e.stopImmediatePropagation?.();
}
/* Capture the tail of a mobile gesture after the modal has started closing. */
for(const ev of ['pointerup','mouseup','touchend','click'])document.addEventListener(ev,consume,true);
for(const ev of ['pointerdown','touchstart','touchend','click']){
  document.addEventListener(ev,e=>{
    const close=e.target?.closest?.('#modal .close');
    if(!close)return;
    e.preventDefault();e.stopPropagation();e.stopImmediatePropagation?.();
    armSwallow();hardClose();
  },true);
}
/* A tap outside the sheet only closes the sheet. It must never activate whatever
   happened to be under the finger in the main interface. */
for(const ev of ['pointerdown','touchstart','click']){
  modal.addEventListener(ev,e=>{
    if(e.target!==modal)return;
    e.preventDefault();e.stopPropagation();e.stopImmediatePropagation?.();
    armSwallow();hardClose();
  },true);
}
new MutationObserver(()=>{if(modal.classList.contains('open'))reopenReady()}).observe(modal,{attributes:true,attributeFilter:['class']});
})();