(()=>{
function isCreateRequest(url){
 const s=String(url||'');
 return s==='/api/leagues/catalog/sync'||s==='/api/leagues'||s.startsWith('/api/leagues/catalog/sync?');
}
function compactMessage(value,status){
 let s=String(value||'Неизвестная ошибка').replace(/\s+/g,' ').trim();
 s=s.replace(/^Турнир пока не готов:\s*/i,'').replace(/\s*Лига не создана\.?$/i,'').trim();
 if(status===429||/\b429\b|too many requests|слишком много запросов/i.test(s))return 'SStats: слишком много запросов (HTTP 429)';
 if(status===401||status===403||/\b401\b|\b403\b/i.test(s))return `SStats: ошибка API-ключа${status?` (HTTP ${status})`:''}`;
 if(/timeout|timed out|слишком долго/i.test(s))return 'SStats слишком долго отвечает — запрос остановлен по таймауту';
 if(/не загрузились игроки/i.test(s))return s.length>145?s.slice(0,142)+'…':s;
 if(/не удалось загрузить данные команд/i.test(s))return s.length>145?s.slice(0,142)+'…':s;
 if(/матчи турнира не загрузились|в базе нет матчей/i.test(s))return s;
 if(s.length>145)s=s.slice(0,142)+'…';
 return s;
}
function paintError(info){
 const el=document.getElementById('gtsCreateLeagueProgress');
 if(!el||!info)return;
 el.className='gts-create-progress show error';
 const spinner=el.querySelector('.gts-create-spinner');if(spinner)spinner.style.display='none';
 const copy=el.querySelector('.gts-create-progress-text');
 if(copy){
  const text='Ошибка: '+compactMessage(info.message,info.status);
  copy.textContent=text;copy.title=String(info.message||'');
 }
}
function wrapApi(){
 const api=window.GTS?.api;if(typeof api!=='function'||api.__gtsCreateErrorCapture)return false;
 const wrapped=async function(url,opts){
  try{return await api.call(this,url,opts)}catch(e){
   if(isCreateRequest(url)){
    const info={message:e?.message||String(e),status:Number(e?.status)||null,at:Date.now(),url:String(url||'')};
    window.__gtsCreateLeagueLastError=info;
    paintError(info);
   }
   throw e;
  }
 };
 try{Object.assign(wrapped,api)}catch{}
 wrapped.__gtsCreateErrorCapture=true;wrapped.__gtsCreateErrorOriginal=api;
 window.GTS.api=wrapped;return true;
}
function wrapCreate(){
 const fn=window.createLeague;if(typeof fn!=='function'||fn.__gtsExactCreateError)return false;
 if(!fn.__gtsProgress)return false;
 const wrapped=async function(...args){
  window.__gtsCreateLeagueLastError=null;
  const result=await fn.apply(this,args);
  const info=window.__gtsCreateLeagueLastError;
  if(info&&Date.now()-Number(info.at||0)<10*60*1000)paintError(info);
  return result;
 };
 try{Object.assign(wrapped,fn)}catch{}
 wrapped.__gtsExactCreateError=true;wrapped.__gtsExactCreateErrorOriginal=fn;
 window.createLeague=wrapped;return true;
}

const style=document.createElement('style');
style.textContent=`
.gts-sstats-key-state{display:flex;align-items:center;justify-content:center;gap:6px;margin:2px 0 9px!important;font-size:10px!important}
.gts-sstats-key-state .dot{width:7px;height:7px;border-radius:50%;background:#8fa4b9;box-shadow:0 0 0 3px rgba(143,164,185,.10)}
.gts-sstats-key-state.ok{color:#1baa68!important}.gts-sstats-key-state.ok .dot{background:#22c77a;box-shadow:0 0 8px rgba(34,199,122,.55)}
.gts-sstats-key-state.off{color:#e88a3b!important}.gts-sstats-key-state.off .dot{background:#e88a3b;box-shadow:0 0 8px rgba(232,138,59,.35)}
.gts-sstats-key-state.bad{color:#ff5a68!important}.gts-sstats-key-state.bad .dot{background:#ff5a68}
`;
document.head.appendChild(style);

let keyStateCache=null,keyStateAt=0,keyStateBusy=false;
async function loadKeyState(el){
 if(!el||keyStateBusy)return;
 if(keyStateCache!==null&&Date.now()-keyStateAt<30000){paintKeyState(el,keyStateCache);return}
 keyStateBusy=true;
 try{
  const d=await window.GTS.api('/api/leagues/catalog');
  keyStateCache=!!d?.sstats_api_key_configured;keyStateAt=Date.now();paintKeyState(el,keyStateCache);
 }catch(e){
  el.className='gts-sstats-key-state sheet-note bad';
  el.innerHTML='<span class="dot"></span><span>Не удалось проверить подключение SStats API</span>';
 }finally{keyStateBusy=false}
}
function paintKeyState(el,configured){
 if(!el)return;
 el.className=`gts-sstats-key-state sheet-note ${configured?'ok':'off'}`;
 el.innerHTML=`<span class="dot"></span><span>${configured?'SStats API · ключ подключён':'SStats API · работа без ключа'}</span>`;
}
function ensureKeyState(){
 const btn=document.getElementById('createLeagueBtn');if(!btn)return;
 let el=document.getElementById('gtsSstatsKeyState');
 if(!el){
  el=document.createElement('div');el.id='gtsSstatsKeyState';el.className='gts-sstats-key-state sheet-note';
  el.innerHTML='<span class="dot"></span><span>Проверяем SStats API…</span>';
  btn.insertAdjacentElement('beforebegin',el);
 }
 loadKeyState(el);
}
function observeCreateSheet(){
 const root=document.getElementById('sheetContent');if(!root)return false;
 const obs=new MutationObserver(()=>queueMicrotask(ensureKeyState));
 obs.observe(root,{childList:true,subtree:true});
 ensureKeyState();return true;
}

function install(){wrapApi();wrapCreate();ensureKeyState();return !!window.GTS?.api?.__gtsCreateErrorCapture&&!!window.createLeague?.__gtsExactCreateError}
if(!install()){
 const timer=setInterval(()=>{if(install())clearInterval(timer)},50);
 setTimeout(()=>clearInterval(timer),10000);
}
if(!observeCreateSheet()){
 const timer=setInterval(()=>{if(observeCreateSheet())clearInterval(timer)},100);
 setTimeout(()=>clearInterval(timer),10000);
}
document.addEventListener('gts:ready',()=>setTimeout(()=>{install();ensureKeyState()},100));
})();