(function(){
var cache={};
function esc(s){return String(s==null?'':s).replace(/[&<>"']/g,function(m){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot',"'":'&#039;'}[m]})}
function auth(){var t=localStorage.getItem('access_token')||'';return t?{Authorization:'Bearer '+t}:{}}
function keyFromControl(c){return (c&&c.id||'').replace('tp_player_control_','')}
function closeOthers(except){var ms=document.querySelectorAll('.tp-menu.open');for(var i=0;i<ms.length;i++)if(ms[i]!==except)ms[i].classList.remove('open')}
function fetchPlayers(url){if(cache[url])return Promise.resolve(cache[url]);return fetch(url,{headers:auth(),cache:'no-store'}).then(function(r){return r.json().then(function(d){if(!r.ok)throw new Error(d.detail||'Ошибка');return d})}).then(function(d){cache[url]=d.response||[];return cache[url]})}
function photo(x){return x&&x.photo?'<img class="tp-photo" src="'+esc(x.photo)+'" alt="" loading="lazy">':'<span class="tp-crest-fallback">👤</span>'}
function setSelected(k,x){var h=document.getElementById('tp_'+k),c=document.getElementById('tp_player_control_'+k),m=document.getElementById('tp_results_'+k);if(!h||!c)return;h.value=x.name;h.setAttribute('data-selected','1');c.setAttribute('data-player-id',x.id||'');c.setAttribute('data-player-team',x.team_original||x.team||'');c.setAttribute('data-player-meta-trusted','1');var meta=[x.team,x.position].filter(Boolean).join(' · ');c.innerHTML=photo(x)+'<div class="tp-player-main"><div class="tp-player-name">'+esc(x.display_name||x.name)+'</div><div class="tp-player-meta">'+esc(meta)+'</div></div><button type="button" class="tp-clear" aria-label="Очистить">×</button>';if(m)m.classList.remove('open');var clear=c.querySelector('.tp-clear');if(clear)clear.onclick=function(e){e.stopPropagation();h.value='';h.setAttribute('data-selected','0');c.removeAttribute('data-player-id');c.innerHTML='<div class="tp-player-main"><div class="tp-player-name tp-placeholder">Выбрать игрока</div></div><span class="tp-chevron">⌄</span>'}}
function render(k,items,title){var list=document.getElementById('tp_list_'+k);if(!list)return;var html=title?'<div style="padding:10px 13px 6px;color:#7898b8;font-size:10px;text-transform:uppercase;letter-spacing:.08em">'+esc(title)+'</div>':'';if(!items.length)html+='<div class="empty" style="padding:13px">Игроки пока не загружены</div>';for(var i=0;i<items.length;i++){var x=items[i],meta=[x.team,x.position].filter(Boolean).join(' · ');html+='<button type="button" class="tp-item tp-player-item" data-db-player="'+i+'">'+photo(x)+'<div class="tp-player-main"><div class="tp-player-name">'+esc(x.display_name||x.name)+'</div><div class="tp-player-meta">'+esc(meta)+'</div></div></button>'}list.innerHTML=html;var bs=list.querySelectorAll('[data-db-player]');for(var j=0;j<bs.length;j++)bs[j].onclick=function(e){e.stopPropagation();setSelected(k,items[Number(this.getAttribute('data-db-player'))])}}
function openPicker(control){var k=keyFromControl(control),menu=document.getElementById('tp_results_'+k),search=document.getElementById('tp_search_'+k);if(!menu||!search)return;closeOthers(menu);var opening=!menu.classList.contains('open');menu.classList.toggle('open');if(!opening)return;search.value='';var list=document.getElementById('tp_list_'+k);if(list)list.innerHTML='<div class="loading" style="padding:13px">Загружаем игроков…</div>';fetchPlayers('/api/players?popular=true&limit=40').then(function(items){render(k,items,'Популярные игроки')}).catch(function(){render(k,[],'Популярные игроки')});var timer=null,controller=null;search.oninput=function(){clearTimeout(timer);if(controller)controller.abort();var q=search.value.trim();if(!q){fetchPlayers('/api/players?popular=true&limit=40').then(function(items){render(k,items,'Популярные игроки')});return}if(q.length<2)return;timer=setTimeout(function(){controller=new AbortController();fetch('/api/players?q='+encodeURIComponent(q)+'&limit=40',{headers:auth(),signal:controller.signal,cache:'no-store'}).then(function(r){return r.json()}).then(function(d){if(search.value.trim()===q)render(k,d.response||[],'Результаты поиска')}).catch(function(e){if(e&&e.name!=='AbortError')render(k,[],'Результаты поиска')})},120)};setTimeout(function(){search.focus()},30)}
function restoreControl(control){if(!control||control.getAttribute('data-db-restored')==='1')return;var wrap=control.closest('.tp-player-wrap'),h=wrap&&wrap.querySelector('input[type="hidden"]');var name=h&&h.value?h.value.trim():'';if(!name)return;control.setAttribute('data-db-restored','1');fetch('/api/players?q='+encodeURIComponent(name)+'&limit=10',{headers:auth(),cache:'no-store'}).then(function(r){return r.json()}).then(function(d){var xs=d.response||[],low=name.toLowerCase(),chosen=null;for(var i=0;i<xs.length;i++)if(String(xs[i].name||'').toLowerCase()===low){chosen=xs[i];break}if(chosen)setSelected(keyFromControl(control),chosen)}).catch(function(){})}
// Tournament-prediction.js historically submits player names. Keep that UI
// compatible while attaching our stable local Player IDs to the same PUT.
var nativeFetch=window.fetch.bind(window);
window.fetch=function(input,init){
 try{
  var url=typeof input==='string'?input:(input&&input.url)||'';
  if(init&&String(init.method||'GET').toUpperCase()==='PUT'&&url.indexOf('/api/tournament-predictions/mine')>=0&&typeof init.body==='string'){
   var body=JSON.parse(init.body),keys=['top_scorer','top_assistant','best_player'];
   for(var i=0;i<keys.length;i++){
    var c=document.getElementById('tp_player_control_'+keys[i]);
    var id=c&&Number(c.getAttribute('data-player-id'));
    body[keys[i]+'_player_id']=id||null;
   }
   init=Object.assign({},init,{body:JSON.stringify(body)});
  }
 }catch(e){}
 return nativeFetch(input,init);
};
document.addEventListener('click',function(e){var c=e.target.closest&&e.target.closest('.tp-player-control');if(!c)return;e.preventDefault();e.stopPropagation();e.stopImmediatePropagation();openPicker(c)},true);
var obs=new MutationObserver(function(){var cs=document.querySelectorAll('.tp-player-control');for(var i=0;i<cs.length;i++)restoreControl(cs[i])});
function init(){obs.observe(document.body,{childList:true,subtree:true});var cs=document.querySelectorAll('.tp-player-control');for(var i=0;i<cs.length;i++)restoreControl(cs[i])}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init);else init();
})();
