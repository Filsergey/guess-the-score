(()=>{
if(window.__gtsSheetDragCloseV1)return;window.__gtsSheetDragCloseV1=true;
const modal=document.getElementById('modal');
if(!modal)return;
const sheet=modal.querySelector('.sheet');
const handle=modal.querySelector('.handle');
if(!sheet||!handle)return;

handle.setAttribute('role','button');
handle.setAttribute('aria-label','Потянуть вниз, чтобы закрыть');
handle.style.touchAction='none';
handle.style.cursor='grab';
handle.style.padding='12px 34px';
handle.style.margin='-8px auto 6px';
handle.style.boxSizing='content-box';
handle.style.backgroundClip='content-box';

let active=false,startY=0,lastY=0,startTime=0,lastTime=0,dy=0;
const reset=()=>{
 sheet.style.transition='transform .22s cubic-bezier(.2,.8,.2,1)';
 sheet.style.transform='translateY(0)';
 handle.style.cursor='grab';
 setTimeout(()=>{if(!active)sheet.style.transition='';},230);
};
const close=()=>{
 active=false;
 handle.style.cursor='grab';
 sheet.style.transition='transform .2s ease-out';
 sheet.style.transform='translateY(105%)';
 setTimeout(()=>{
  modal.classList.remove('open');
  sheet.style.transition='';
  sheet.style.transform='';
 },190);
};

handle.addEventListener('pointerdown',e=>{
 if(!modal.classList.contains('open'))return;
 active=true;startY=lastY=e.clientY;startTime=lastTime=performance.now();dy=0;
 handle.style.cursor='grabbing';
 sheet.style.transition='none';
 try{handle.setPointerCapture(e.pointerId)}catch{}
 e.preventDefault();
});
handle.addEventListener('pointermove',e=>{
 if(!active)return;
 const y=e.clientY,now=performance.now();
 dy=Math.max(0,y-startY);lastY=y;lastTime=now;
 const eased=dy<50?dy:50+(dy-50)*.88;
 sheet.style.transform=`translateY(${eased}px)`;
 e.preventDefault();
});
const finish=e=>{
 if(!active)return;
 const now=performance.now();
 const totalMs=Math.max(1,now-startTime);
 const velocity=dy/totalMs;
 active=false;
 try{handle.releasePointerCapture(e.pointerId)}catch{}
 if(dy>=85||velocity>=0.55)close();else reset();
};
handle.addEventListener('pointerup',finish);
handle.addEventListener('pointercancel',finish);

modal.addEventListener('transitionend',()=>{
 if(!modal.classList.contains('open')){sheet.style.transform='';sheet.style.transition='';}
});
})();
