(function(){
function toastMsg(t){if(typeof window.toast==='function')window.toast(t)}
function watch(){
 var btn=document.getElementById('tpSave');
 if(!btn||btn.getAttribute('data-save-guard')==='1')return;
 btn.setAttribute('data-save-guard','1');
 var obs=new MutationObserver(function(){
  if(!btn.disabled)return;
  var started=Date.now();
  var timer=setInterval(function(){
   if(!document.body.contains(btn)||!btn.disabled){clearInterval(timer);return}
   if(Date.now()-started>10000){
    clearInterval(timer);btn.disabled=false;toastMsg('Сохранение заняло слишком много времени. Попробуй ещё раз.');
   }
  },500);
 });
 obs.observe(btn,{attributes:true,attributeFilter:['disabled']});
}
var mo=new MutationObserver(function(){watch()});
function init(){mo.observe(document.body,{childList:true,subtree:true});watch()}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init);else init();
})();
