(()=>{
function isCreateRequest(url){
 const s=String(url||'');
 return s==='/api/leagues/catalog/sync'||s==='/api/leagues'||s.startsWith('/api/leagues/catalog/sync?');
}
function compactMessage(value,status){
 let s=String(value||'Неизвестная ошибка').replace(/\s+/g,' ').trim();
 s=s.replace(/^Не удалось синхронизировать турнир:\s*/i,'').trim();
 if(status===429||/\b429\b|too many requests|слишком много запросов/i.test(s))return 'SStats: слишком много запросов (HTTP 429)';
 if(status===401||status===403||/\b401\b|\b403\b/i.test(s))return `SStats отказал в доступе${status?` (HTTP ${status})`:''}`;
 if(/timeout|timed out|слишком долго/i.test(s))return 'SStats слишком долго отвечает — запрос остановлен по таймауту';
 if(/не вернул матчи|матчи выбранного турнира/i.test(s))return s;
 if(s.length>145)s=s.slice(0,142)+'…';
 return s;
}
function paintError(info){
 const el=document.getElementById('gtsCreateLeagueProgress');
 if(!el||!info)return;
 el.className='gts-create-progress show error';
 const spinner=el.querySelector('.gts-create-spinner');if(spinner)spinner.style.display='none';
 const copy=el.querySelector('.gts-create-progress-text');
 if(copy){const text='Ошибка: '+compactMessage(info.message,info.status);copy.textContent=text;copy.title=String(info.message||'')}
}
function wrapApi(){
 const api=window.GTS?.api;if(typeof api!=='function'||api.__gtsCreateErrorCapture)return false;
 const wrapped=async function(url,opts){
  try{return await api.call(this,url,opts)}catch(e){
   if(isCreateRequest(url)){
    const info={message:e?.message||String(e),status:Number(e?.status)||null,at:Date.now(),url:String(url||'')};
    window.__gtsCreateLeagueLastError=info;paintError(info)
   }
   throw e
  }
 };
 try{Object.assign(wrapped,api)}catch{}
 wrapped.__gtsCreateErrorCapture=true;wrapped.__gtsCreateErrorOriginal=api;window.GTS.api=wrapped;return true
}
function wrapCreate(){
 const fn=window.createLeague;if(typeof fn!=='function'||fn.__gtsExactCreateError||!fn.__gtsProgress)return false;
 const wrapped=async function(...args){
  window.__gtsCreateLeagueLastError=null;
  const result=await fn.apply(this,args);
  const info=window.__gtsCreateLeagueLastError;
  if(info&&Date.now()-Number(info.at||0)<10*60*1000)paintError(info);
  return result
 };
 try{Object.assign(wrapped,fn)}catch{}
 wrapped.__gtsExactCreateError=true;wrapped.__gtsExactCreateErrorOriginal=fn;window.createLeague=wrapped;return true
}
function install(){wrapApi();wrapCreate();return !!window.GTS?.api?.__gtsCreateErrorCapture&&!!window.createLeague?.__gtsExactCreateError}
if(!install()){const timer=setInterval(()=>{if(install())clearInterval(timer)},50);setTimeout(()=>clearInterval(timer),10000)}
document.addEventListener('gts:ready',()=>setTimeout(install,100));
})();