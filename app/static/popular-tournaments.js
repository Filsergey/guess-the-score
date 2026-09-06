(()=>{
const esc=s=>String(s??'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[m]));
const norm=s=>String(s||'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase().replace(/[._–—-]+/g,' ').replace(/[^a-z0-9а-яё ]+/gi,' ').replace(/\s+/g,' ').trim();
const bad=n=>/(women|woman|femin|u19|u20|u21|u23|youth|junior|reserve|qualification|qualifier|qualifying|playoff|play off)/i.test(n);
const CATALOG_CACHE_KEY='gts-create-league-catalog-v1',CATALOG_CACHE_TTL=30*60*1000;

// Только эти турниры доступны при создании пользовательской лиги.
// Порядок здесь = порядок в выпадающем списке.
const SPECS=[
 {label:'Лига чемпионов',aliases:['uefa champions league','champions league'],countries:[]},
 {label:'АПЛ',aliases:['premier league','english premier league'],countries:['england','united kingdom','great britain']},
 {label:'Ла Лига',aliases:['la liga','laliga','primera division'],countries:['spain']},
 {label:'Бундеслига',aliases:['bundesliga'],countries:['germany']},
 {label:'Серия А',aliases:['serie a'],countries:['italy']},
 {label:'Лига 1',aliases:['ligue 1','league 1'],countries:['france']},
 {label:'Эредивизи',aliases:['eredivisie'],countries:['netherlands','holland']},
 {label:'Чемпионат Бразилии (Серия А)',aliases:['brasileirao serie a','brasileirao','campeonato brasileiro serie a','campeonato brasileiro','brasileiro serie a','serie a'],countries:['brazil','brasil']},
 {label:'Примейра-лига',aliases:['primeira liga','liga portugal','liga portugal betclic'],countries:['portugal']},
 {label:'Лига МХ',aliases:['liga mx','primera division'],countries:['mexico']},
 {label:'РПЛ',aliases:['russian premier league','premier liga','premier league','rpl'],countries:['russia','russian federation']},
];

function countryMatches(country,spec){if(!spec.countries.length)return true;const c=norm(country);return spec.countries.some(x=>c===norm(x)||c.includes(norm(x)))}
function aliasScore(name,aliases){let best=-1;for(const raw of aliases){const a=norm(raw);if(name===a)best=Math.max(best,60);else if(name.startsWith(a+' ')||name.endsWith(' '+a))best=Math.max(best,45);else if(name.includes(a))best=Math.max(best,30)}return best}
function candidateScore(item,spec){
 const name=norm(item.name),country=norm(item.country);
 if(!name||bad(name))return -1;
 const a=aliasScore(name,spec.aliases);if(a<0)return -1;
 if(!countryMatches(country,spec))return -1;
 let score=a+50;
 if(item.seasons?.length)score+=Math.min(5,item.seasons.length);
 const currentYear=new Date().getFullYear();
 if((item.seasons||[]).some(s=>Number(s.year||s)===currentYear||Number(s.year||s)===currentYear-1))score+=4;
 return score;
}
function pickAllowed(items){
 const used=new Set(),out=[];
 for(const spec of SPECS){
  let best=null,bestScore=-1;
  for(const item of items){
   if(used.has(Number(item.league_id)))continue;
   const score=candidateScore(item,spec);
   if(score>bestScore){best=item;bestScore=score}
  }
  if(best&&bestScore>=0){used.add(Number(best.league_id));out.push({...best,_displayLabel:spec.label})}
 }
 return out;
}
function option(x){return `<option value="${Number(x.league_id)}">${esc(x._displayLabel)}</option>`}
function cachedCatalog(){try{const x=JSON.parse(sessionStorage.getItem(CATALOG_CACHE_KEY)||'null');if(x&&Array.isArray(x.items)&&Date.now()-Number(x.savedAt||0)<CATALOG_CACHE_TTL)return x.items}catch{}return null}
function saveCatalog(items){try{sessionStorage.setItem(CATALOG_CACHE_KEY,JSON.stringify({savedAt:Date.now(),items}))}catch{}}
async function fetchCatalog(){
 const cached=cachedCatalog();if(cached?.length)return cached;
 const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),8000);
 try{
  const d=await window.GTS.api('/api/leagues/catalog',{signal:controller.signal}),items=d?.response||[];
  if(!Array.isArray(items)||!items.length)throw new Error('SStats не вернул список турниров');
  saveCatalog(items);return items
 }finally{clearTimeout(timer)}
}
function renderError(message){
 window.openSheet?.(`<div class="sheet-title">Создать лигу</div><div class="sheet-note error">${esc(message||'Не удалось загрузить турниры')}</div><button class="save secondary" onclick="openCreateLeague()">Повторить</button><button class="close" onclick="closeSheet()">Закрыть</button>`)
}
async function openCreateLeagueTopOnly(){
 window.openSheet?.('<div class="sheet-title">Создать лигу</div><div class="sheet-note">Загружаем турниры…</div><button class="close" onclick="closeSheet()">Закрыть</button>');
 try{
  const allowed=pickAllowed(await fetchCatalog());
  let opts='<option value="">Выбери чемпионат</option>'+allowed.map(option).join('');
  const missing=SPECS.length-allowed.length;
  const note=missing>0
   ?`Доступны только выбранные турниры. Сейчас SStats нашёл ${allowed.length} из ${SPECS.length}.`
   :'Доступны Лига чемпионов и 10 выбранных топ-чемпионатов. После выбора укажи сезон.';
  window.openSheet?.(`<div class="sheet-title">Создать лигу</div><input id="newLeagueName" class="field" placeholder="Название новой лиги"><select id="newLeagueTournament" class="field" onchange="onCreateTournamentChange()">${opts}</select><select id="newLeagueSeason" class="field" disabled><option value="">Сначала выбери чемпионат</option></select><div class="sheet-note">${esc(note)}</div><button class="save" id="createLeagueBtn" onclick="createLeague()" ${allowed.length?'':'disabled'}>Создать лигу</button><button class="close" onclick="closeSheet()">Закрыть</button>`);
 }catch(e){
  const message=e?.name==='AbortError'?'SStats слишком долго отвечает. Попробуй ещё раз.':(e?.message||'Не удалось загрузить каталог SStats');
  renderError(message)
 }
}
window.clearCreateLeagueCatalogCache=()=>{try{sessionStorage.removeItem(CATALOG_CACHE_KEY)}catch{}};

function installCreateProgress(){
 if(typeof window.createLeague!=='function'||window.createLeague.__gtsProgress)return false;
 const original=window.createLeague;
 const style=document.createElement('style');
 style.textContent=`
 .gts-create-progress{display:none;align-items:center;justify-content:center;gap:8px;min-height:22px;margin:9px 2px 0;color:var(--muted,#8fa4b9);font-size:11px;line-height:1;white-space:nowrap;overflow:hidden}
 .gts-create-progress.show{display:flex}
 .gts-create-progress .gts-create-spinner{width:12px;height:12px;flex:0 0 12px;border:2px solid currentColor;border-right-color:transparent;border-radius:50%;animation:gtsCreateSpin .7s linear infinite}
 .gts-create-progress .gts-create-progress-text{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
 .gts-create-progress.error{color:#ff5a68}.gts-create-progress.done{color:#31c98b}
 @keyframes gtsCreateSpin{to{transform:rotate(360deg)}}`;
 document.head.appendChild(style);
 function line(){
  let el=document.getElementById('gtsCreateLeagueProgress');
  if(el)return el;
  const btn=document.getElementById('createLeagueBtn');if(!btn)return null;
  el=document.createElement('div');el.id='gtsCreateLeagueProgress';el.className='gts-create-progress';el.setAttribute('aria-live','polite');
  el.innerHTML='<span class="gts-create-spinner"></span><span class="gts-create-progress-text"></span>';
  btn.insertAdjacentElement('afterend',el);return el;
 }
 function setLine(text,state='working'){
  const el=line();if(!el)return;el.className=`gts-create-progress show ${state==='error'?'error':state==='done'?'done':''}`;
  const spinner=el.querySelector('.gts-create-spinner');if(spinner)spinner.style.display=state==='working'?'block':'none';
  const copy=el.querySelector('.gts-create-progress-text');if(copy)copy.textContent=text;
 }
 const wrapped=async function(...args){
  const btn=document.getElementById('createLeagueBtn');
  const started=Date.now();let lastButton='';
  setLine('Подготавливаем турнир: матчи, команды и игроки · 0 с');
  const render=()=>{
   const text=String(btn?.textContent||'');const sec=Math.max(0,Math.floor((Date.now()-started)/1000));
   if(/Созда[её]м лигу/i.test(text))setLine(`Данные готовы · создаём лигу · ${sec} с`);
   else setLine(`Подготавливаем турнир: матчи, команды и игроки · ${sec} с`);
   lastButton=text;
  };
  render();
  const observer=btn?new MutationObserver(()=>{if(String(btn.textContent||'')!==lastButton)render()}):null;observer?.observe(btn,{childList:true,subtree:true,characterData:true});
  const timer=setInterval(render,1000);
  try{
   const result=await original.apply(this,args);
   if(!document.getElementById('modal')?.classList.contains('open'))setLine('Лига создана','done');
   else if(String(btn?.textContent||'').trim()==='Создать лигу')setLine('Операция остановлена · проверь сообщение выше','error');
   return result;
  }catch(e){setLine('Ошибка загрузки · попробуй ещё раз','error');throw e}
  finally{clearInterval(timer);observer?.disconnect()}
 };
 wrapped.__gtsProgress=true;wrapped.__original=original;window.createLeague=wrapped;return true;
}

setTimeout(()=>{window.openCreateLeague=openCreateLeagueTopOnly;if(!installCreateProgress()){const t=setInterval(()=>{if(installCreateProgress())clearInterval(t)},50);setTimeout(()=>clearInterval(t),5000)}},0);
})();