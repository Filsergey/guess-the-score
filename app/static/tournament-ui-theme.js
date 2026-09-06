(()=>{
const PALETTES={
  2:{name:'ucl',accent:'#20a7ff',accent2:'#5fc6ff',rgb:'32,167,255',bg1:'#07182e',bg2:'#0b2548',panel:'#102b4d',text:'#f5f9ff',muted:'#a9c8e8'},
  39:{name:'epl',accent:'#8d4dff',accent2:'#c79cff',rgb:'141,77,255',bg1:'#140d24',bg2:'#2a1749',panel:'#2a1c43',text:'#fbf8ff',muted:'#d4c3ef'},
  140:{name:'laliga',accent:'#ff4655',accent2:'#ff8a94',rgb:'255,70,85',bg1:'#210d15',bg2:'#451b28',panel:'#3a1a24',text:'#fff7f8',muted:'#e9bec4'},
  135:{name:'seriea',accent:'#3da5ff',accent2:'#91d2ff',rgb:'61,165,255',bg1:'#081b2f',bg2:'#143a63',panel:'#133452',text:'#f7fbff',muted:'#bad7ee'},
  78:{name:'bundesliga',accent:'#ff3d49',accent2:'#ff8d95',rgb:'255,61,73',bg1:'#1e0d12',bg2:'#41161d',panel:'#351820',text:'#fff8f8',muted:'#e6c1c5'}
};
const DEFAULT={name:'default',accent:'#24a4ff',accent2:'#72cbff',rgb:'36,164,255',bg1:'#071522',bg2:'#102a43',panel:'#10263b',text:'#f5f9ff',muted:'#a9c3da'};
function tournamentForLeague(league){const tournaments=window.getTournaments?.()||[];if(!league)return null;return tournaments.find(t=>Number(t.id)===Number(league.tournament_id)&&Number(t.season)===Number(league.tournament_season))||tournaments.find(t=>Number(t.id)===Number(league.tournament_id))||null}
function palette(){const t=tournamentForLeague(window.getSelectedLeague?.());return PALETTES[Number(t?.provider_id)]||DEFAULT}
function apply(){const p=palette(),r=document.documentElement,b=document.body;r.dataset.gtsTournamentTheme=p.name;r.style.setProperty('--gts-accent',p.accent);r.style.setProperty('--gts-accent-2',p.accent2);r.style.setProperty('--gts-accent-rgb',p.rgb);r.style.setProperty('--gts-bg-1',p.bg1);r.style.setProperty('--gts-bg-2',p.bg2);r.style.setProperty('--gts-panel',p.panel);r.style.setProperty('--gts-text',p.text);r.style.setProperty('--gts-muted',p.muted);if(!String(b.style.backgroundImage||'').includes('url("data:')){b.style.background=`radial-gradient(circle at 50% -10%,rgba(${p.rgb},.16),transparent 34%),linear-gradient(180deg,${p.bg2} 0%,${p.bg1} 44%,#07111d 100%)`;b.style.backgroundAttachment='fixed'}setTimeout(()=>window.applyTournamentBranding?.(),30)}
const s=document.createElement('style');s.textContent=`
:root{--gts-accent:#24a4ff;--gts-accent-2:#72cbff;--gts-accent-rgb:36,164,255;--gts-bg-1:#071522;--gts-bg-2:#102a43;--gts-panel:#10263b;--gts-text:#f5f9ff;--gts-muted:#a9c3da}
body{transition:background .28s ease}
.top{background:linear-gradient(145deg,color-mix(in srgb,var(--gts-panel) 92%,#000 8%),color-mix(in srgb,var(--gts-bg-1) 94%,#000 6%))!important;border-color:var(--gts-accent)!important;border-left-color:var(--gts-accent)!important;border-right-color:var(--gts-accent)!important;box-shadow:0 0 0 1px rgba(var(--gts-accent-rgb),.12),0 0 18px rgba(var(--gts-accent-rgb),.38),inset 0 1px 0 rgba(255,255,255,.06)!important}
.nav{background:linear-gradient(180deg,color-mix(in srgb,var(--gts-bg-1) 90%,#000 10%),color-mix(in srgb,var(--gts-bg-1) 96%,#000 4%))!important;border-top-color:rgba(var(--gts-accent-rgb),.18)!important}
.nav button,.nav a{color:var(--gts-muted)!important}.nav .active,.nav [aria-current='page']{color:var(--gts-accent-2)!important;text-shadow:0 0 10px rgba(var(--gts-accent-rgb),.35)}
.section-head h2,.leagues-page-head h1,.league-section-label{color:var(--gts-text)!important}.link{color:var(--gts-accent-2)!important}
.tournament,.match,.league-card,.sheet,.modal,.menu-card,.panel{border-color:rgba(var(--gts-accent-rgb),.24)!important}
.tournament{background-color:color-mix(in srgb,var(--gts-bg-2) 78%,#000 22%)!important}
button:not(.league-delete):not(.close),.pill,.league-edit,.theme-file-label{border-color:rgba(var(--gts-accent-rgb),.40)!important}
.league-bottom-actions button:first-child,.primary,.btn-primary{background:linear-gradient(135deg,color-mix(in srgb,var(--gts-panel) 82%,var(--gts-accent) 18%),color-mix(in srgb,var(--gts-bg-1) 88%,var(--gts-accent) 12%))!important;color:var(--gts-text)!important}
.league-bottom-actions button,.secondary,.btn-secondary{background:color-mix(in srgb,var(--gts-panel) 86%,#000 14%)!important;color:var(--gts-text)!important}
input:focus,select:focus,textarea:focus{border-color:var(--gts-accent)!important;box-shadow:0 0 0 2px rgba(var(--gts-accent-rgb),.14)!important}
.selector-copy small,.profile-rank small{color:var(--gts-accent-2)!important}
.top .profile .avatar{border-color:var(--gts-accent)!important;box-shadow:0 0 10px rgba(var(--gts-accent-rgb),.35)!important}
::-webkit-scrollbar-thumb{background:rgba(var(--gts-accent-rgb),.28)!important}
`;
document.head.appendChild(s);
document.addEventListener('gts:ready',()=>setTimeout(apply,150));document.addEventListener('gts:league-change',()=>setTimeout(apply,80));setTimeout(apply,1000);window.applyTournamentUiTheme=apply;
})();