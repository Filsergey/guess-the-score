(()=>{
const modal=document.getElementById('modal');
const box=document.getElementById('sheetContent');
const sheet=modal?.querySelector('.sheet');
const handle=modal?.querySelector('.handle');
if(!modal||!box)return;
let restoring=false,swallowUntil=0,shieldTimer=null;
let navIntent=false,navIntentTimer=null,suppressHistory=false;
let wasOpen=modal.classList.contains('open');
const history=[];
const htmlDescriptor=Object.getOwnPropertyDescriptor(Element.prototype,'innerHTML');

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
function clearNavIntent(){
  navIntent=false;
  clearTimeout(navIntentTimer);navIntentTimer=null;
}
function armNavIntent(){
  if(!modal.classList.contains('open')||restoring)return;
  navIntent=true;
  clearTimeout(navIntentTimer);
  navIntentTimer=setTimeout(()=>{navIntent=false;navIntentTimer=null},1400);
}
function clearHistory(){
  history.length=0;
  clearNavIntent();
  document.dispatchEvent(new CustomEvent('gts:sheet-depth',{detail:{depth:0}}));
}
function pushCurrentSheet(){
  if(!box.childNodes.length)return false;
  const fragment=document.createDocumentFragment();
  [...box.childNodes].forEach(node=>fragment.appendChild(node));
  history.push({
    fragment,
    sheetScroll:Number(sheet?.scrollTop)||0,
    boxScroll:Number(box.scrollTop)||0
  });
  if(history.length>20)history.shift();
  document.dispatchEvent(new CustomEvent('gts:sheet-depth',{detail:{depth:history.length}}));
  return true;
}
function restorePreviousSheet(){
  if(!history.length||restoring)return false;
  const frame=history.pop();
  clearNavIntent();
  suppressHistory=true;
  try{
    if(htmlDescriptor?.set)htmlDescriptor.set.call(box,'');
    else box.replaceChildren();
    box.appendChild(frame.fragment);
  }finally{suppressHistory=false}
  resetSheetMotion();
  requestAnimationFrame(()=>{
    if(sheet)sheet.scrollTop=frame.sheetScroll||0;
    box.scrollTop=frame.boxScroll||0;
    document.dispatchEvent(new CustomEvent('gts:sheet-restored',{detail:{depth:history.length}}));
    document.dispatchEvent(new CustomEvent('gts:sheet-depth',{detail:{depth:history.length}}));
  });
  return true;
}

// Preserve the actual DOM nodes before a user-triggered nested transition replaces
// #sheetContent. Moving the nodes into a detached fragment keeps their listeners,
// form state and scroll position intact, so Back restores the real previous screen.
if(htmlDescriptor?.get&&htmlDescriptor?.set){
  try{
    Object.defineProperty(box,'innerHTML',{
      configurable:true,
      enumerable:htmlDescriptor.enumerable,
      get(){return htmlDescriptor.get.call(box)},
      set(value){
        if(!suppressHistory&&navIntent&&modal.classList.contains('open')&&box.childNodes.length){
          pushCurrentSheet();
          clearNavIntent();
        }
        htmlDescriptor.set.call(box,value);
      }
    });
  }catch{}
}

function finishClose(){
  clearTimeout(shieldTimer);shieldTimer=null;
  suppressHistory=true;
  try{box.innerHTML=''}finally{suppressHistory=false}
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
  restoring=true;armSwallow();clearHistory();abortMatch();
  modal.classList.remove('open');
  modal.setAttribute('aria-hidden','true');
  modal.style.setProperty('display','flex','important');
  modal.style.setProperty('pointer-events','auto','important');
  modal.style.setProperty('opacity','0','important');
  modal.style.setProperty('background','transparent','important');
  document.body.style.removeProperty('overflow');
  shieldTimer=setTimeout(finishClose,430);
}
function requestClose(){
  if(restorePreviousSheet()){armSwallow(180);return true}
  hardClose();return true;
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
window.openSheet=function(html){
  const alreadyOpen=modal.classList.contains('open');
  reopenReady();
  if(!alreadyOpen)clearHistory();
  return oldOpen?oldOpen(html):(box.innerHTML=html,modal.classList.add('open'));
};
window.closeSheet=requestClose;
window.forceCloseSheet=hardClose;
window.gtsSheetBack=restorePreviousSheet;
window.gtsSheetCanBack=()=>history.length>0;
window.gtsSheetDepth=()=>history.length;
window.gtsResetSheetHistory=clearHistory;

// Existing feature screens already contain buttons such as “← Назад к профилю”.
// When universal history is available, consume those controls here so they pop the
// same stack as the floating X instead of rebuilding an older screen independently.
document.addEventListener('click',e=>{
  if(!history.length||!modal.classList.contains('open')||!box.contains(e.target))return;
  const control=e.target?.closest?.('button,a,[role="button"]');
  if(!control)return;
  const text=(control.textContent||'').trim();
  const explicit=control.matches?.('[data-gts-sheet-back],.social-back');
  if(!explicit&&!/^←\s*Назад/i.test(text))return;
  e.preventDefault();e.stopPropagation();e.stopImmediatePropagation?.();
  armSwallow(180);restorePreviousSheet();
},true);

// Any click inside an already open sheet can start a nested view. We only consume
// the intent when the top-level sheetContent is actually replaced, so ordinary
// accordions, filters and controls that update their own child nodes do not create
// fake history entries.
document.addEventListener('click',e=>{
  if(!modal.classList.contains('open')||!box.contains(e.target))return;
  if(e.target?.closest?.('.close,.gts-sheet-close-float,[data-gts-sheet-back]'))return;
  armNavIntent();
},true);

function consume(e){
  if(!swallowActive())return;
  e.preventDefault();e.stopPropagation();e.stopImmediatePropagation?.();
}
for(const ev of ['pointerup','mouseup','touchend','click'])document.addEventListener(ev,consume,true);
for(const ev of ['pointerdown','touchstart','touchend','click']){
  document.addEventListener(ev,e=>{
    const close=e.target?.closest?.('#modal .close');
    if(!close)return;
    e.preventDefault();e.stopPropagation();e.stopImmediatePropagation?.();
    armSwallow();requestClose();
  },true);
}
for(const ev of ['pointerdown','touchstart','click']){
  modal.addEventListener(ev,e=>{
    if(e.target!==modal)return;
    e.preventDefault();e.stopPropagation();e.stopImmediatePropagation?.();
    armSwallow();requestClose();
  },true);
}
if(sheet&&handle){
  handle.setAttribute('role','button');
  handle.setAttribute('aria-label','Потянуть вниз, чтобы вернуться или закрыть');
  handle.style.setProperty('touch-action','none');
  handle.style.setProperty('cursor','grab');
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
    if(distance>=85||velocity>=0.55){armSwallow();requestClose()}else springBack();
    e.preventDefault();e.stopPropagation();
  }
  handle.addEventListener('pointerdown',begin);
  handle.addEventListener('pointermove',move);
  handle.addEventListener('pointerup',end);
  handle.addEventListener('pointercancel',end);
}
new MutationObserver(()=>{
  const open=modal.classList.contains('open');
  if(open&&!wasOpen){reopenReady();clearHistory()}
  if(!open&&wasOpen&&!restoring)clearHistory();
  wasOpen=open;
}).observe(modal,{attributes:true,attributeFilter:['class']});
})();
(()=>{if(document.querySelector('script[data-gts-club-player-details]'))return;const s=document.createElement('script');s.src='/static/club-player-details.js?v=1';s.defer=true;s.dataset.gtsClubPlayerDetails='1';document.head.appendChild(s)})();
