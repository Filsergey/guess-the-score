(function(){
var resolving={};
var KNOWN={
 'kylian mbappe':['Real Madrid','Нападающий'],'harry kane':['Бавария','Нападающий'],'erling haaland':['Манчестер Сити','Нападающий'],
 'lamine yamal':['Барселона','Нападающий'],'vinicius junior':['Real Madrid','Нападающий'],'ousmane dembele':['ПСЖ','Нападающий'],
 'bukayo saka':['Арсенал','Нападающий'],'raphinha':['Барселона','Нападающий'],'julian alvarez':['Атлетико','Нападающий'],
 'jude bellingham':['Real Madrid','Полузащитник'],'pedri':['Барселона','Полузащитник'],'florian wirtz':['Ливерпуль','Полузащитник'],
 'jamal musiala':['Бавария','Полузащитник'],'lautaro martinez':['Интер','Нападающий']
};
function auth(){var t=localStorage.getItem('access_token')||'';return t?{Authorization:'Bearer '+t}:{}}
function norm(s){return String(s||'').trim().toLowerCase()}
function known(name){return KNOWN[norm(name)]||null}
function readCache(key){try{var raw=localStorage.getItem(key);if(raw){var d=JSON.parse(raw);if(d&&(d.photo||d.team||d.position))return d}}catch(e){}return null}
function writeCache(key,d){if(!d||(!d.photo&&!d.team&&!d.position))return;try{localStorage.setItem(key,JSON.stringify(d))}catch(e){}}
function photoFor(name,team){var nk=norm(name),tk=norm(team);if(!nk)return Promise.resolve(null);var key=nk+'|'+tk,cacheKey='player_profile_v7:'+key,cached=readCache(cacheKey);if(cached)return Promise.resolve(cached);if(resolving[key])return resolving[key];var url='/api/player-photo/resolve?name='+encodeURIComponent(name);if(team)url+='&team='+encodeURIComponent(team);resolving[key]=fetch(url,{headers:auth(),cache:'no-store'}).then(function(r){return r.json().then(function(d){return r.ok?d:null})}).catch(function(){return null}).then(function(d){writeCache(cacheKey,d);delete resolving[key];return d});return resolving[key]}
function currentMeta(control){var meta=control.querySelector('.tp-player-meta');return meta?String(meta.textContent||'').trim():''}
function expectedTeam(control,name){var attr=String(control.getAttribute('data-player-team')||'').trim();if(attr)return attr;var k=known(name);return k?k[0]:''}
function primeKnownMeta(control,name){var k=known(name);if(!k)return;control.setAttribute('data-player-team',k[0]);control.setAttribute('data-player-meta-trusted','1');var main=control.querySelector('.tp-player-main');if(!main)return;var meta=control.querySelector('.tp-player-meta');if(!meta){meta=document.createElement('div');meta.className='tp-player-meta';main.appendChild(meta)}meta.textContent=k[0]+' · '+k[1]}
function ensureMeta(control,d){var main=control.querySelector('.tp-player-main');if(!main)return;var meta=control.querySelector('.tp-player-meta');if(!meta){meta=document.createElement('div');meta.className='tp-player-meta';main.appendChild(meta)}var existing=currentMeta(control),trusted=control.getAttribute('data-player-meta-trusted')==='1';if(trusted&&existing&&existing!=='Загружаем данные игрока…'&&existing!=='Нажми, чтобы изменить')return;var bits=[];if(d&&d.team)bits.push(d.team);if(d&&d.position)bits.push(d.position);meta.textContent=bits.length?bits.join(' · '):(existing||'Нажми, чтобы изменить')}
function fallbackNode(){var span=document.createElement('span');span.className='tp-crest-fallback';span.textContent='👤';return span}
function ensureFallback(control){if(control.querySelector('.tp-photo,.tp-crest-fallback'))return;control.insertBefore(fallbackNode(),control.firstChild)}
function setPhoto(control,url){if(!url){ensureFallback(control);return}var old=control.querySelector('.tp-photo');if(old&&old.getAttribute('src')===url)return;var img=new Image();img.className='tp-photo';img.alt='';img.onload=function(){if(!document.body.contains(control))return;var cur=control.querySelector('.tp-photo,.tp-crest-fallback');if(cur)cur.replaceWith(img);else control.insertBefore(img,control.firstChild)};img.onerror=function(){var cur=control.querySelector('.tp-photo');if(cur)cur.replaceWith(fallbackNode())};img.src=url}
function decorateControl(control){if(!control||control.getAttribute('data-profile-loading')==='1')return;var wrap=control.closest('.tp-player-wrap');if(!wrap)return;var hidden=wrap.querySelector('input[type="hidden"]'),name=hidden&&hidden.value?hidden.value.trim():'';if(!name)return;primeKnownMeta(control,name);ensureFallback(control);var team=expectedTeam(control,name),key=norm(name)+'|'+norm(team),cached=readCache('player_profile_v7:'+key);if(cached){ensureMeta(control,cached);if(cached.photo)setPhoto(control,cached.photo);return}control.setAttribute('data-profile-loading','1');photoFor(name,team).then(function(d){control.removeAttribute('data-profile-loading');if(!document.body.contains(control))return;ensureMeta(control,d||{});if(d&&d.photo)setPhoto(control,d.photo)})}
function scan(){var controls=document.querySelectorAll('.tp-player-control');for(var i=0;i<controls.length;i++)decorateControl(controls[i])}
var observer=new MutationObserver(function(){setTimeout(scan,0)});
function loadPopularPicker(){if(document.getElementById('popularPlayerPicker'))return;var s=document.createElement('script');s.id='popularPlayerPicker';s.src='/static/popular-player-picker.js?v=6';document.body.appendChild(s)}
function init(){observer.observe(document.body,{childList:true,subtree:true});scan();loadPopularPicker();window.addEventListener('player-picked',function(){setTimeout(scan,0)})}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init);else init();
})();
