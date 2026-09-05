(function(){
var resolving={};
function auth(){var t=localStorage.getItem('access_token')||'';return t?{Authorization:'Bearer '+t}:{}}
function readCache(key){try{var raw=localStorage.getItem(key);if(raw){var d=JSON.parse(raw);if(d&&(d.photo||d.team||d.position))return d}}catch(e){}return null}
function writeCache(key,d){if(!d||( !d.photo&&!d.team&&!d.position))return;try{localStorage.setItem(key,JSON.stringify(d))}catch(e){}}
function photoFor(name,team){
 var nk=String(name||'').trim().toLowerCase(),tk=String(team||'').trim().toLowerCase();if(!nk)return Promise.resolve(null);
 var key=nk+'|'+tk,cacheKey='player_profile_v5:'+key,cached=readCache(cacheKey)||readCache('popular_profile_v2:'+key);if(cached)return Promise.resolve(cached);
 if(resolving[key])return resolving[key];var url='/api/player-photo/resolve?name='+encodeURIComponent(name);if(team)url+='&team='+encodeURIComponent(team);
 resolving[key]=fetch(url,{headers:auth()}).then(function(r){return r.json().then(function(d){return r.ok?d:null})}).catch(function(){return null}).then(function(d){writeCache(cacheKey,d);if(team)writeCache('popular_profile_v2:'+key,d);delete resolving[key];return d});return resolving[key]
}
function currentMeta(control){var meta=control.querySelector('.tp-player-meta');return meta?String(meta.textContent||'').trim():''}
function expectedTeam(control){return String(control.getAttribute('data-player-team')||'').trim()}
function ensureMeta(control,d){var main=control.querySelector('.tp-player-main');if(!main)return;var meta=control.querySelector('.tp-player-meta');if(!meta){meta=document.createElement('div');meta.className='tp-player-meta';main.appendChild(meta)}var existing=currentMeta(control),trusted=control.getAttribute('data-player-meta-trusted')==='1';if(trusted&&existing&&existing!=='Загружаем данные игрока…')return;var bits=[];if(d&&d.team)bits.push(d.team);if(d&&d.position)bits.push(d.position);meta.textContent=bits.length?bits.join(' · '):(existing||'Нажми, чтобы изменить')}
function ensureFallback(control){if(control.querySelector('.tp-photo,.tp-crest-fallback'))return;var span=document.createElement('span');span.className='tp-crest-fallback';span.textContent='👤';control.insertBefore(span,control.firstChild)}
function setPhoto(control,url){if(!url){ensureFallback(control);return}var old=control.querySelector('.tp-photo');if(old&&old.src===url)return;var img=new Image();img.className='tp-photo';img.alt='';img.onload=function(){if(!document.body.contains(control))return;var cur=control.querySelector('.tp-photo,.tp-crest-fallback');if(cur)cur.replaceWith(img);else control.insertBefore(img,control.firstChild)};img.onerror=function(){ensureFallback(control)};img.src=url}
function decorateControl(control){if(!control||control.getAttribute('data-profile-loading')==='1')return;var wrap=control.closest('.tp-player-wrap');if(!wrap)return;var hidden=wrap.querySelector('input[type="hidden"]'),name=hidden&&hidden.value?hidden.value.trim():'';if(!name)return;ensureFallback(control);var team=expectedTeam(control),cached=readCache('player_profile_v5:'+name.toLowerCase()+'|'+team.toLowerCase())||readCache('popular_profile_v2:'+name.toLowerCase()+'|'+team.toLowerCase());if(cached){ensureMeta(control,cached);if(cached.photo)setPhoto(control,cached.photo);return}control.setAttribute('data-profile-loading','1');photoFor(name,team).then(function(d){control.removeAttribute('data-profile-loading');if(!document.body.contains(control))return;ensureMeta(control,d||{});if(d&&d.photo)setPhoto(control,d.photo)})}
function scan(){var controls=document.querySelectorAll('.tp-player-control');for(var i=0;i<controls.length;i++)decorateControl(controls[i])}
var observer=new MutationObserver(function(){setTimeout(scan,0)});
function loadPopularPicker(){if(document.getElementById('popularPlayerPicker'))return;var s=document.createElement('script');s.id='popularPlayerPicker';s.src='/static/popular-player-picker.js?v=4';document.body.appendChild(s)}
function init(){observer.observe(document.body,{childList:true,subtree:true});scan();loadPopularPicker();window.addEventListener('player-picked',function(){setTimeout(scan,0)})}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init);else init();
})();
