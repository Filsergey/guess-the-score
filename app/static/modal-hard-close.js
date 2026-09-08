(()=>{
const modal=document.getElementById('modal');
const box=document.getElementById('sheetContent');
const sheet=modal?.querySelector('.sheet');
const handle=modal?.querySelector('.handle');
if(!modal||!box)return;
let restoring=false,swallowUntil=0,shieldTimer=null;
function abortMatch(){
  try{document.dispatchEvent(new CustomEvent('gts:force-close-sheet'))}catch{}
  try{if(typeof window.openMatchDetail==='function')window.openMatchDetail(Number.NaN)}catch{}
}
function swallowActive(){return performance.now()<swallowUntil}
function armSwallow(ms=420){swallowUntil=Math.max(swallowUntil,performance.now()+ms)}
function resetSheetMotion(){
  if(!sheet)return;
  sheet.style.removeProperty('transform');
  sheet.style.removeProperty('transition');
}
function finishClose(){
  clearTimeout(shieldTimer);shieldTimer=null;
  box.innerHTML='';
  resetSheetMotion();
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
  resetSheetMotion();
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

/* The visible grabber is a real drag handle now. Dragging it down moves the
   entire bottom sheet; a short/slow drag springs back, a decisive swipe closes. */
if(sheet&&handle){
  handle.setAttribute('role','button');
  handle.setAttribute('aria-label','Потянуть вниз, чтобы закрыть');
  handle.style.setProperty('touch-action','none');
  handle.style.setProperty('cursor','grab');
  /* Keep the same 42x4 visual line but make its touch target comfortably large. */
  handle.style.setProperty('padding','12px 34px');
  handle.style.setProperty('margin','-8px auto 6px');
  handle.style.setProperty('box-sizing','content-box');
  handle.style.setProperty('background-clip','content-box');

  let dragging=false,startY=0,lastY=0,startAt=0,lastAt=0,distance=0;
  function springBack(){
    sheet.style.transition='transform .22s cubic-bezier(.2,.8,.2,1)';
    sheet.style.transform='translateY(0)';
    handle.style.cursor='grab';
    setTimeout(()=>{if(!dragging)sheet.style.removeProperty('transition')},230);
  }
  function begin(e){
    if(!modal.classList.contains('open')||restoring)return;
    dragging=true;distance=0;startY=lastY=e.clientY;startAt=lastAt=performance.now();
    sheet.style.transition='none';handle.style.cursor='grabbing';
    try{handle.setPointerCapture(e.pointerId)}catch{}
    e.preventDefault();e.stopPropagation();
  }
  function move(e){
    if(!dragging)return;
    const y=e.clientY,now=performance.now();
    distance=Math.max(0,y-startY);lastY=y;lastAt=now;
    const translated=distance<=50?distance:50+(distance-50)*.88;
    sheet.style.transform=`translateY(${translated}px)`;
    e.preventDefault();e.stopPropagation();
  }
  function end(e){
    if(!dragging)return;
    const elapsed=Math.max(1,performance.now()-startAt);
    const velocity=distance/elapsed;
    dragging=false;handle.style.cursor='grab';
    try{handle.releasePointerCapture(e.pointerId)}catch{}
    if(distance>=85||velocity>=0.55){
      armSwallow();hardClose();
    }else springBack();
    e.preventDefault();e.stopPropagation();
  }
  handle.addEventListener('pointerdown',begin);
  handle.addEventListener('pointermove',move);
  handle.addEventListener('pointerup',end);
  handle.addEventListener('pointercancel',end);
}

new MutationObserver(()=>{if(modal.classList.contains('open'))reopenReady()}).observe(modal,{attributes:true,attributeFilter:['class']});
})();