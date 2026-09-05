(function(){
var resolving={};
function auth(){var t=localStorage.getItem('access_token')||'';return t?{Authorization:'Bearer '+t}:{}}
function photoFor(name){
 var key=String(name||'').trim().toLowerCase();
 if(!key)return Promise.resolve(null);
 var cacheKey='player_photo_v2:'+key;
 var cached=sessionStorage.getItem(cacheKey);
 if(cached){try{var parsed=JSON.parse(cached);if(parsed&&parsed.found&&parsed.photo)return Promise.resolve(parsed)}catch(e){}}
 if(resolving[key])return resolving[key];
 resolving[key]=fetch('/api/player-photo/resolve?name='+encodeURIComponent(name)+'&_='+Date.now(),{headers:auth(),cache:'no-store'})
  .then(function(r){return r.json().then(function(d){return r.ok?d:null})})
  .catch(function(){return null})
  .then(function(d){if(d&&d.found&&d.photo){try{sessionStorage.setItem(cacheKey,JSON.stringify(d))}catch(e){}}delete resolving[key];return d});
 return resolving[key];
}
function decorateControl(control){
 if(!control||control.getAttribute('data-photo-loading')==='1')return;
 var wrap=control.closest('.tp-player-wrap');if(!wrap)return;
 var hidden=wrap.querySelector('input[type="hidden"]');
 var name=hidden&&hidden.value?hidden.value.trim():'';
 if(!name)return;
 control.setAttribute('data-photo-loading','1');
 photoFor(name).then(function(d){
  control.removeAttribute('data-photo-loading');
  if(!d||!d.found||!d.photo||!document.body.contains(control))return;
  var old=control.querySelector('.tp-photo,.tp-crest-fallback');
  var img=document.createElement('img');img.className='tp-photo';img.src=d.photo;img.alt='';
  img.onerror=function(){this.remove()};
  if(old)old.replaceWith(img);else control.insertBefore(img,control.firstChild);
  var meta=control.querySelector('.tp-player-meta');
  if(meta){var bits=[];if(d.team)bits.push(d.team);if(d.position)bits.push(d.position);if(bits.length)meta.textContent=bits.join(' · ')}
 });
}
function scan(){var controls=document.querySelectorAll('.tp-player-control');for(var i=0;i<controls.length;i++)decorateControl(controls[i])}
var observer=new MutationObserver(function(){setTimeout(scan,0)});
function init(){observer.observe(document.body,{childList:true,subtree:true});scan()}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init);else init();
})();
