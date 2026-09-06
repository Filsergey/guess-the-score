(()=>{
const tg=window.Telegram?.WebApp;if(tg){tg.ready();tg.expand()}
const state={
 me:null,
 leagues:[],
 get token(){return localStorage.getItem('access_token')||''},
 set token(v){if(v)localStorage.setItem('access_token',v);else localStorage.removeItem('access_token')},
 get leagueId(){const v=Number(localStorage.getItem('selected_league_id')||0);return v||null},
 set leagueId(v){if(v)localStorage.setItem('selected_league_id',String(v));else localStorage.removeItem('selected_league_id')},
 matches(){return window.getMatchFeedData?.()||window.matchFeedData||window.allMatchesData||[]},
 match(id){return this.matches().find(x=>Number(x.id)===Number(id))||null},
 authHeaders(extra={}){return {...extra,...(this.token?{Authorization:`Bearer ${this.token}`}:{})}},
 async api(url,opts={}){
  const headers=this.authHeaders(opts.headers||{}),r=await fetch(url,{...opts,headers});let d={};try{d=await r.json()}catch{}
  if(!r.ok){const err=new Error(d.detail||`HTTP ${r.status}`);err.status=r.status;err.payload=d;throw err}return d
 },
 async login(){
  if(this.token){try{this.me=await this.api('/api/auth/me');return this.me}catch(e){if(e.status!==401)throw e;this.token=''}}
  if(!tg?.initData)throw new Error('Открой приложение через кнопку Telegram-бота');
  const r=await fetch('/api/auth/telegram',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({init_data:tg.initData})});let d={};try{d=await r.json()}catch{}
  if(!r.ok)throw new Error(d.detail||'Ошибка входа');this.token=d.access_token;this.me=d.user||await this.api('/api/auth/me');return this.me
 },
 async loadLeagues(){const d=await this.api('/api/leagues/mine');this.leagues=d.response||[];if(!this.leagueId&&this.leagues[0])this.leagueId=this.leagues[0].id;return this.leagues}
};
window.GTS=Object.assign(window.GTS||{},state);
window.gtsApi=(url,opts)=>window.GTS.api(url,opts);
if(!document.querySelector('script[data-gts-pwa]')){const s=document.createElement('script');s.src='/static/pwa.js?v=1';s.dataset.gtsPwa='1';document.head.appendChild(s)}
if(!document.querySelector('script[data-gts-tournament-scope]')){const s=document.createElement('script');s.src='/static/tournament-scope.js?v=1';s.dataset.gtsTournamentScope='1';document.head.appendChild(s)}
if(!document.querySelector('script[data-gts-league-invite]')){const s=document.createElement('script');s.src='/static/league-invite.js?v=1';s.dataset.gtsLeagueInvite='1';document.head.appendChild(s)}
if(!document.querySelector('script[data-gts-league-members]')){const s=document.createElement('script');s.src='/static/league-members.js?v=3';s.dataset.gtsLeagueMembers='1';document.head.appendChild(s)}
})();