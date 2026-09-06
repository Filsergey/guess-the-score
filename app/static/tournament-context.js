(()=>{
if(window.__gtsTournamentContextInstalled)return;window.__gtsTournamentContextInstalled=true;
const originalFetch=window.fetch.bind(window);
function selectedLeague(){try{return window.getSelectedLeague?.()||null}catch{return null}}
function rewrite(input){if(typeof input!=='string'||!input.startsWith('/api/tournament-predictions/'))return input;const league=selectedLeague();if(!league)return input;try{const u=new URL(input,location.origin);u.searchParams.set('provider',league.tournament_provider||'sstats');if(league.tournament_season)u.searchParams.set('season',String(league.tournament_season));if(league.tournament_id)u.searchParams.set('tournament_id',String(league.tournament_id));else u.searchParams.delete('tournament_id');return u.pathname+'?'+u.searchParams.toString()}catch{return input}}
window.fetch=function(input,init){if(typeof input==='string')input=rewrite(input);return originalFetch(input,init)};
})();