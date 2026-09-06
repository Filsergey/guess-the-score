(()=>{
const esc=s=>String(s??'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot',"'":'&#039;'}[m]));
const norm=s=>String(s||'').toLowerCase().replace(/[._-]+/g,' ').replace(/\s+/g,' ').trim();
const bad=n=>/(women|woman|femin|u19|u20|u21|u23|youth|junior|reserve|qualification|qualifier|qualifying)/i.test(n);
const SPECS=[
 {label:'Лига чемпионов',aliases:['uefa champions league','champions league'],countries:['europe','international']},
 {label:'Premier League',aliases:['premier league','english premier league'],countries:['england','united kingdom','great britain']},
 {label:'La Liga',aliases:['la liga','laliga','primera division'],countries:['spain']},
 {label:'Serie A',aliases:['serie a'],countries:['italy']},
 {label:'Bundesliga',aliases:['bundesliga'],countries:['germany']},
];
function candidateScore(item,spec){const name=norm(item.name),country=norm(item.country);if(bad(name))return -1;const alias=spec.aliases.find(a=>name===a)||spec.aliases.find(a=>name.includes(a));if(!alias)return -1;let score=10;if(name===alias)score+=20;if(spec.countries.some(c=>country.includes(c)))score+=30;if(item.seasons?.length)score+=2;return score}
function pickPopular(items){const used=new Set(),out=[];for(const spec of SPECS){let best=null,bestScore=-1;for(const item of items){if(used.has(Number(item.league_id)))continue;const score=candidateScore(item,spec);if(score>bestScore){best=item;bestScore=score}}if(best&&bestScore>=0){used.add(Number(best.league_id));out.push({...best,_popularLabel:spec.label})}}return {popular:out,used}}
function option(x,label){const text=label||(x.country?`${x.country} · ${x.name}`:x.name);return `<option value="${Number(x.league_id)}">${esc(text)}</option>`}
async function openCreateLeaguePopular(){
 window.openSheet?.('<div class="sheet-title">Создать лигу</div><div class="sheet-note">Загружаем турниры SStats…</div><button class="close" onclick="closeSheet()">Закрыть</button>');
 try{
  const d=await window.GTS.api('/api/leagues/catalog'),items=d.response||[],{popular,used}=pickPopular(items);
  const rest=items.filter(x=>!used.has(Number(x.league_id))).sort((a,b)=>`${a.country||''} ${a.name||''}`.localeCompare(`${b.country||''} ${b.name||''}`,'ru'));
  let opts='<option value="">Выбери турнир</option>';
  if(popular.length)opts+=`<optgroup label="⭐ Популярные">${popular.map(x=>option(x,x._popularLabel)).join('')}</optgroup>`;
  opts+=`<optgroup label="Все турниры">${rest.map(x=>option(x)).join('')}</optgroup>`;
  window.openSheet?.(`<div class="sheet-title">Создать лигу</div><input id="newLeagueName" class="field" placeholder="Название новой лиги"><select id="newLeagueTournament" class="field" onchange="onCreateTournamentChange()">${opts}</select><select id="newLeagueSeason" class="field" disabled><option value="">Сначала выбери турнир</option></select><div class="sheet-note">Сначала показаны 5 самых известных турниров. После выбора турнира выбери сезон.</div><button class="save" id="createLeagueBtn" onclick="createLeague()">Создать лигу</button><button class="close" onclick="closeSheet()">Закрыть</button>`);
 }catch(e){window.toast?.(e.message||'Не удалось загрузить каталог SStats')}
}
window.openCreateLeague=openCreateLeaguePopular;
})();