(()=>{
const tg=window.Telegram?.WebApp;if(tg){tg.ready();tg.expand()}
let browserLoginPromise=null;
function browserLogin(status,state){
 if(browserLoginPromise)return browserLoginPromise;
 browserLoginPromise=new Promise((resolve,reject)=>{
  const style=document.createElement('style');style.dataset.gtsBrowserLoginStyle='1';style.textContent=`.gts-browser-login{position:fixed;inset:0;z-index:1000;display:grid;place-items:center;padding:24px;background:radial-gradient(circle at 50% 0,#12345c 0,#07111f 48%,#040a12 100%);font-family:Inter,system-ui,-apple-system,Segoe UI,sans-serif;color:#fff}.gts-browser-login-card{width:min(420px,100%);text-align:center;padding:28px 22px;border-radius:28px;background:rgba(12,31,51,.94);border:1px solid rgba(95,198,255,.22);box-shadow:0 24px 70px rgba(0,0,0,.38)}.gts-browser-login-icon{width:94px;height:94px;border-radius:25px;margin:0 auto 17px;display:block}.gts-browser-login h1{font-size:25px;margin:0 0 8px}.gts-browser-login p{font-size:13px;line-height:1.5;color:#9db6ce;margin:0 0 22px}.gts-browser-login-btn{width:100%;border:0;border-radius:16px;padding:14px 16px;background:#229ed9;color:#fff;font-size:15px;font-weight:900}.gts-browser-login-btn:disabled{opacity:.55}.gts-browser-login-error{min-height:18px;margin-top:10px;color:#ff9b9b;font-size:11px}`;document.head.appendChild(style);
  const root=document.createElement('div');root.className='gts-browser-login';root.innerHTML=`<div class="gts-browser-login-card"><img class="gts-browser-login-icon" src="/static/pwa-icon.svg?v=2" alt=""><h1>Угадай счёт</h1><p>Войди через Telegram, чтобы увидеть свои лиги, прогнозы и результаты.</p><button class="gts-browser-login-btn">Войти через Telegram</button><div class="gts-browser-login-error"></div></div>`;document.body.appendChild(root);
  const btn=root.querySelector('.gts-browser-login-btn'),err=root.querySelector('.gts-browser-login-error');
  btn.onclick=()=>{const url=status?.fallback_login_url||status?.login_url;if(!url){err.textContent='Вход через Telegram настроен не полностью';return}btn.disabled=true;btn.textContent='Переходим в Telegram…';sessionStorage.setItem('gts_browser_login_started','1');location.assign(url)};
 });
 return browserLoginPromise;
}
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
  if(this.token){try{this.me=await this.api('/api/auth/me');sessionStorage.removeItem('gts_browser_login_started');return this.me}catch(e){if(e.status!==401)throw e;this.token=''}}
  if(!tg?.initData){
   let status={};try{const r=await fetch('/api/auth/web/status',{cache:'no-store'});status=await r.json()}catch{}
   if(status?.configured&&(status?.fallback_login_url||status?.login_url))return browserLogin(status,this);
   throw new Error('Вход через браузер пока не настроен. Открой приложение через Telegram.')
  }
  const r=await fetch('/api/auth/telegram',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({init_data:tg.initData})});let d={};try{d=await r.json()}catch{}
  if(!r.ok)throw new Error(d.detail||'Ошибка входа');this.token=d.access_token;this.me=d.user||await this.api('/api/auth/me');return this.me
 },
 async loadLeagues(){const d=await this.api('/api/leagues/mine');this.leagues=d.response||[];if(!this.leagueId&&this.leagues[0])this.leagueId=this.leagues[0].id;return this.leagues}
};
window.GTS=Object.assign(window.GTS||{},state);
window.gtsApi=(url,opts)=>window.GTS.api(url,opts);
if(!document.querySelector('script[data-gts-pwa]')){const s=document.createElement('script');s.src='/static/pwa.js?v=4';s.dataset.gtsPwa='1';document.head.appendChild(s)}
if(!document.querySelector('script[data-gts-tournament-scope]')){const s=document.createElement('script');s.src='/static/tournament-scope.js?v=1';s.dataset.gtsTournamentScope='1';document.head.appendChild(s)}
if(!document.querySelector('script[data-gts-league-invite]')){const s=document.createElement('script');s.src='/static/league-invite.js?v=1';s.dataset.gtsLeagueInvite='1';document.head.appendChild(s)}
if(!document.querySelector('script[data-gts-league-members]')){const s=document.createElement('script');s.src='/static/league-members.js?v=3';s.dataset.gtsLeagueMembers='1';document.head.appendChild(s)}
})();
