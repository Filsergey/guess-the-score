(()=>{
const modal=document.getElementById('modal');
const box=document.getElementById('sheetContent');
if(!modal||!box)return;
let restoring=false;
function hardClose(){
  if(restoring)return;
  restoring=true;
  try{document.dispatchEvent(new CustomEvent('gts:force-close-sheet'))}catch{}
  modal.classList.remove('open');
  modal.setAttribute('aria-hidden','true');
  modal.style.setProperty('display','none','important');
  modal.style.pointerEvents='none';
  document.body.style.removeProperty('overflow');
  setTimeout(()=>{
    box.innerHTML='';
    modal.style.removeProperty('display');
    modal.style.removeProperty('pointer-events');
    modal.removeAttribute('aria-hidden');
    restoring=false;
  },80);
}
function reopenReady(){
  modal.style.removeProperty('display');
  modal.style.removeProperty('pointer-events');
  modal.removeAttribute('aria-hidden');
}
const oldOpen=window.openSheet;
window.openSheet=function(html){reopenReady();return oldOpen?oldOpen(html):(box.innerHTML=html,modal.classList.add('open'))};
window.closeSheet=hardClose;
window.forceCloseSheet=hardClose;
for(const ev of ['pointerdown','touchstart','touchend','click']){
  document.addEventListener(ev,e=>{
    const close=e.target?.closest?.('#modal .close');
    if(!close)return;
    e.preventDefault();
    e.stopPropagation();
    e.stopImmediatePropagation?.();
    hardClose();
  },true);
}
for(const ev of ['pointerdown','click']){
  modal.addEventListener(ev,e=>{
    if(e.target!==modal)return;
    e.preventDefault();
    e.stopPropagation();
    hardClose();
  },true);
}
new MutationObserver(()=>{
  if(modal.classList.contains('open'))reopenReady();
}).observe(modal,{attributes:true,attributeFilter:['class']});
})();