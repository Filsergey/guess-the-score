(function(){
var resolving={};
function auth(){var t=localStorage.getItem('access_token')||'';return t?{Authorization:'Bearer '+t}:{}}
function photoFor(name){
 var key=String(name||'').trim().toLowerCase();
 if(!key)return Promise.resolve(null);
 var cacheKey='player_profile_v3:'+key;
 var cached=sessionStorage.getItem(cacheKey);
 if(cached){try{var parsed=JSON.parse(cached);if(parsed&&(parsed.photo||parsed.team||parsed.position))return Promise.resolve(parsed)}catch(e){}}
 if(resolving[key])return resolving[key];
 resolving[key]=fetch('/api/player-photo/resolve?name='+encodeURIComponent(name)+'&_='+Date.now(),{headers:auth(),cache:'no-store'})
  .then(function(r){return r.json().then(function(d){return r.ok?d:null})})
  .catch(function(){return null})
  .then(function(d){if(d&&(d.photo||d.team||d.position)){try{sessionStorage.setItem(cacheKey,JSON.stringify(d))}catch(e){}}delete resolving[key];return d});
 return resolving[key];
}
function ensureMeta(control,d){
 var main=control.querySelector('.tp-player-main');if(!main)return;
 var meta=control.querySelector('.tp-player-meta');
 if(!meta){meta=document.createElement('div');meta.className='tp-player-meta';main.appendChild(meta)}
 var bits=[];if(d&&d.team)bits.push(d.team);if(d&&d.position)bits.push(d.position);
 meta.textContent=bits.length?bits.join(' · '):'Нажми, чтобы изменить';
}
function ensureFallback(control){
 if(control.querySelector('.tp-photo,.tp-crest-fallback'))return;
 var span=document.createElement('span');span.className='tp-crest-fallback';span.textContent='👤';control.insertBefore(span,control.firstChild);
}
function setPhoto(control,url){
 if(!url){ensureFallback(control);return}
 var preload=new Image();
 preload.onload=function(){
  if(!document.body.contains(control))return;
  var old=control.querySelector('.tp-photo,.tp-crest-fallback');
  var img=document.createElement('img');img.className='tp-photo';img.src=url;img.alt='';
  if(old)old.replaceWith(img);else control.insertBefore(img,control.firstChild);
 };
 preload.onerror=function(){ensureFallback(control)};
 preload.src=url;
}
function decorateControl(control){
 if(!control||control.getAttribute('data-profile-loading')==='1')return;
 var wrap=control.closest('.tp-player-wrap');if(!wrap)return;
 var hidden=wrap.querySelector('input[type="hidden"]');
 var name=hidden&&hidden.value?hidden.value.trim():'';
 if(!name)return;
 ensureFallback(control);
 control.setAttribute('data-profile-loading','1');
 photoFor(name).then(function(d){
  control.removeAttribute('data-profile-loading');
  if(!document.body.contains(control))return;
  ensureMeta(control,d||{});
  if(d&&d.photo)setPhoto(control,d.photo);
 });
}
function scan(){var controls=document.querySelectorAll('.tp-player-control');for(var i=0;i<controls.length;i++)decorateControl(controls[i])}
var observer=new MutationObserver(function(){setTimeout(scan,0)});
function init(){observer.observe(document.body,{childList:true,subtree:true});scan()}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init);else init();
})();
