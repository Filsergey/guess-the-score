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
setTimeout(()=>{window.openCreateLeague=openCreateLeagueTopOnly},0);
})();