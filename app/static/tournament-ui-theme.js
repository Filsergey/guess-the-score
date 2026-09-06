(()=>{
const PALETTES={
  2:{name:'ucl',accent:'#20a7ff',accent2:'#5fc6ff',rgb:'32,167,255',bg1:'#07182e',bg2:'#0b2548',panel:'#102b4d',text:'#f5f9ff',muted:'#a9c8e8'},
  39:{name:'epl',accent:'#8d4dff',accent2:'#c79cff',rgb:'141,77,255',bg1:'#140d24',bg2:'#2a1749',panel:'#2a1c43',text:'#fbf8ff',muted:'#d4c3ef'},
  140:{name:'laliga',accent:'#ff4655',accent2:'#ff4655',rgb:'255,70,85',bg1:'#ffffff',bg2:'#f4f4f2',panel:'#ffffff',text:'#111111',muted:'#626262'},
  135:{name:'seriea',accent:'#3da5ff',accent2:'#91d2ff',rgb:'61,165,255',bg1:'#081b2f',bg2:'#143a63',panel:'#133452',text:'#f7fbff',muted:'#bad7ee'},
  78:{name:'bundesliga',accent:'#ff3d49',accent2:'#ff8d95',rgb:'255,61,73',bg1:'#1e0d12',bg2:'#41161d',panel:'#351820',text:'#fff8f8',muted:'#e6c1c5'}
};
const DEFAULT={name:'default',accent:'#24a4ff',accent2:'#72cbff',rgb:'36,164,255',bg1:'#071522',bg2:'#102a43',panel:'#10263b',text:'#f5f9ff',muted:'#a9c3da'};
function tournamentForLeague(league){const tournaments=window.getTournaments?.()||[];if(!league)return null;return tournaments.find(t=>Number(t.id)===Number(league.tournament_id)&&Number(t.season)===Number(league.tournament_season))||tournaments.find(t=>Number(t.id)===Number(league.tournament_id))||null}
function palette(){const t=tournamentForLeague(window.getSelectedLeague?.());return PALETTES[Number(t?.provider_id)]||DEFAULT}
function apply(){const p=palette(),r=document.documentElement,b=document.body;r.dataset.gtsTournamentTheme=p.name;r.style.setProperty('--gts-accent',p.accent);r.style.setProperty('--gts-accent-2',p.accent2);r.style.setProperty('--gts-accent-rgb',p.rgb);r.style.setProperty('--gts-bg-1',p.bg1);r.style.setProperty('--gts-bg-2',p.bg2);r.style.setProperty('--gts-panel',p.panel);r.style.setProperty('--gts-text',p.text);r.style.setProperty('--gts-muted',p.muted);if(!String(b.style.backgroundImage||'').includes('url("data:')){b.style.background=p.name==='laliga'?'#f4f4f2':`linear-gradient(180deg,${p.bg2} 0%,${p.bg1} 48%,#07111d 100%)`;b.style.backgroundAttachment='fixed'}setTimeout(()=>window.applyTournamentBranding?.(),30)}
const s=document.createElement('style');s.textContent=`
:root{--gts-accent:#24a4ff;--gts-accent-2:#72cbff;--gts-accent-rgb:36,164,255;--gts-bg-1:#071522;--gts-bg-2:#102a43;--gts-panel:#10263b;--gts-text:#f5f9ff;--gts-muted:#a9c3da}
body{transition:background .28s ease}
.top{background:linear-gradient(145deg,color-mix(in srgb,var(--gts-panel) 92%,#000 8%),color-mix(in srgb,var(--gts-bg-1) 94%,#000 6%))!important;border-color:rgba(var(--gts-accent-rgb),.72)!important;box-shadow:none!important}
.nav{background:linear-gradient(180deg,color-mix(in srgb,var(--gts-bg-1) 90%,#000 10%),color-mix(in srgb,var(--gts-bg-1) 96%,#000 4%))!important;border-top-color:rgba(var(--gts-accent-rgb),.18)!important;box-shadow:none!important}
.nav button,.nav a{color:var(--gts-muted)!important}.nav .active,.nav [aria-current='page']{color:var(--gts-accent-2)!important;text-shadow:none!important}
.section-head h2,.leagues-page-head h1,.league-section-label{color:var(--gts-text)!important}.link{color:var(--gts-accent-2)!important}
.tournament,.match,.league-card,.sheet,.modal,.menu-card,.panel{border-color:rgba(var(--gts-accent-rgb),.24)!important}
.tournament{background-color:color-mix(in srgb,var(--gts-bg-2) 78%,#000 22%)!important}
button:not(.league-delete):not(.close),.pill,.league-edit,.theme-file-label{border-color:rgba(var(--gts-accent-rgb),.40)!important}
.league-bottom-actions button:first-child,.primary,.btn-primary{background:linear-gradient(135deg,color-mix(in srgb,var(--gts-panel) 82%,var(--gts-accent) 18%),color-mix(in srgb,var(--gts-bg-1) 88%,var(--gts-accent) 12%))!important;color:var(--gts-text)!important}
.league-bottom-actions button,.secondary,.btn-secondary{background:color-mix(in srgb,var(--gts-panel) 86%,#000 14%)!important;color:var(--gts-text)!important}
input:focus,select:focus,textarea:focus{border-color:var(--gts-accent)!important;box-shadow:none!important}.selector-copy small,.profile-rank small{color:var(--gts-accent-2)!important}.top .profile .avatar{border-color:var(--gts-accent)!important;box-shadow:none!important}::-webkit-scrollbar-thumb{background:rgba(var(--gts-accent-rgb),.28)!important}
html[data-gts-tournament-theme='ucl'] .top{border-color:#20a7ff!important;box-shadow:0 0 0 1px rgba(32,167,255,.13),0 0 18px rgba(32,167,255,.40),inset 0 1px 0 rgba(255,255,255,.06)!important}
html[data-gts-tournament-theme='ucl'] .nav .active,html[data-gts-tournament-theme='ucl'] .nav [aria-current='page']{text-shadow:0 0 10px rgba(32,167,255,.38)!important}
html[data-gts-tournament-theme='ucl'] .top .profile .avatar{box-shadow:0 0 10px rgba(32,167,255,.38)!important}
html[data-gts-tournament-theme='ucl'] input:focus,html[data-gts-tournament-theme='ucl'] select:focus,html[data-gts-tournament-theme='ucl'] textarea:focus{box-shadow:0 0 0 2px rgba(32,167,255,.14)!important}
html:not([data-gts-tournament-theme='ucl']) .league-card.selected{box-shadow:none!important}

html[data-gts-tournament-theme='laliga'] body{background:#f4f4f2!important;color:#111!important}
html[data-gts-tournament-theme='laliga'] .top{background:#fff!important;border-color:#ff4655!important;box-shadow:none!important}
html[data-gts-tournament-theme='laliga'] .select,html[data-gts-tournament-theme='laliga'] .selector-copy strong,html[data-gts-tournament-theme='laliga'] .selector-chevron,html[data-gts-tournament-theme='laliga'] .top .profile-rank strong{color:#111!important}
html[data-gts-tournament-theme='laliga'] .selector-copy small,html[data-gts-tournament-theme='laliga'] .top .profile-rank small{color:#ff4655!important}
html[data-gts-tournament-theme='laliga'] .top .profile{border-left-color:#e4e4e4!important}
html[data-gts-tournament-theme='laliga'] .nav{background:#fff!important;border-top:1px solid #dedede!important;box-shadow:none!important}
html[data-gts-tournament-theme='laliga'] .nav button,html[data-gts-tournament-theme='laliga'] .nav a{color:#666!important}
html[data-gts-tournament-theme='laliga'] .nav .active,html[data-gts-tournament-theme='laliga'] .nav [aria-current='page']{color:#ff4655!important;text-shadow:none!important}
html[data-gts-tournament-theme='laliga'] h1,html[data-gts-tournament-theme='laliga'] h2,html[data-gts-tournament-theme='laliga'] h3,html[data-gts-tournament-theme='laliga'] .section-head h2,html[data-gts-tournament-theme='laliga'] .leagues-page-head h1,html[data-gts-tournament-theme='laliga'] .league-section-label,html[data-gts-tournament-theme='laliga'] .tournament-title{color:#111!important;text-shadow:none!important}
html[data-gts-tournament-theme='laliga'] .muted,html[data-gts-tournament-theme='laliga'] .match .muted{color:#666!important}
html[data-gts-tournament-theme='laliga'] .tournament,html[data-gts-tournament-theme='laliga'] .match,html[data-gts-tournament-theme='laliga'] .sheet,html[data-gts-tournament-theme='laliga'] .modal,html[data-gts-tournament-theme='laliga'] .menu-card,html[data-gts-tournament-theme='laliga'] .panel{background:#fff!important;color:#111!important;border-color:#dedede!important;box-shadow:none!important}
html[data-gts-tournament-theme='laliga'] .tournament{background-image:linear-gradient(135deg,#fff 0%,#f8f8f6 72%,#fff1f2 100%)!important}
html[data-gts-tournament-theme='laliga'] .tournament .muted{color:#555!important}
html[data-gts-tournament-theme='laliga'] .link{color:#ff4655!important}
html[data-gts-tournament-theme='laliga'] .pill,html[data-gts-tournament-theme='laliga'] .primary,html[data-gts-tournament-theme='laliga'] .btn-primary{background:#ff4655!important;color:#fff!important;border-color:#ff4655!important}
html[data-gts-tournament-theme='laliga'] .secondary,html[data-gts-tournament-theme='laliga'] .btn-secondary,html[data-gts-tournament-theme='laliga'] .league-bottom-actions button{background:#fff!important;color:#111!important;border-color:#cfcfcf!important}
html[data-gts-tournament-theme='laliga'] input,html[data-gts-tournament-theme='laliga'] select,html[data-gts-tournament-theme='laliga'] textarea{background:#fff!important;color:#111!important;border-color:#d7d7d7!important}
html[data-gts-tournament-theme='laliga'] .match{background:#fff!important}
html[data-gts-tournament-theme='laliga'] .match *:not(.pill):not(button){text-shadow:none}
html[data-gts-tournament-theme='laliga'] #view-home,html[data-gts-tournament-theme='laliga'] #view-matches,html[data-gts-tournament-theme='laliga'] #view-leagues,html[data-gts-tournament-theme='laliga'] #view-table,html[data-gts-tournament-theme='laliga'] #view-menu{color:#111!important}
html[data-gts-tournament-theme='laliga'] #leaguesView .league-card{background:#fff!important;border-color:#d8d8d8!important;color:#111!important;box-shadow:none!important}
html[data-gts-tournament-theme='laliga'] #leaguesView .league-card.selected{background:#fff!important;border:2px solid #ff4655!important;box-shadow:none!important}
html[data-gts-tournament-theme='laliga'] #leaguesView .league-card .league-name{color:#111!important}
html[data-gts-tournament-theme='laliga'] #leaguesView .league-card .gts-tournament-line{color:#666!important}
html[data-gts-tournament-theme='laliga'] #leaguesView .league-card .gts-members-line{color:#111!important}
html[data-gts-tournament-theme='laliga'] #leaguesView .league-card .league-role{background:#fff!important;color:#ff4655!important;border-color:#ff4655!important}
html[data-gts-tournament-theme='laliga'] #leaguesView .league-card .league-edit{background:#fff!important;color:#111!important;border-color:#cfcfcf!important}
html[data-gts-tournament-theme='laliga'] #leaguesView .league-card .league-delete{background:#fff!important;border-color:#ff4655!important;color:#ff4655!important}
html[data-gts-tournament-theme='laliga'] #leaguesView .league-emblem{background:#fff!important}
`;
document.head.appendChild(s);document.addEventListener('gts:ready',()=>setTimeout(apply,150));document.addEventListener('gts:league-change',()=>setTimeout(apply,80));setTimeout(apply,1000);window.applyTournamentUiTheme=apply;
})();