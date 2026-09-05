(()=>{
/* Compatibility bridge while the legacy inline frontend is being split into modules. */
const state={
 get token(){return localStorage.getItem('access_token')||''},
 get leagueId(){const v=Number(localStorage.getItem('selected_league_id')||0);return v||null},
 matches(){return window.getMatchFeedData?.()||window.matchFeedData||window.allMatchesData||[]},
 match(id){return this.matches().find(x=>Number(x.id)===Number(id))||null},
 authHeaders(extra={}){return {...extra,...(this.token?{Authorization:`Bearer ${this.token}`}:{})}}
};
window.GTS=Object.assign(window.GTS||{},state);
})();