(()=>{
const style=document.createElement('style');
style.textContent=`
/* Header stays visible on every tab, but remains below modal sheets. */
body .app>.top{position:sticky!important;top:0!important;z-index:12!important}
body .app>.top .profile{padding-left:7px!important;padding-right:7px!important}
body .app>.top .profile-avatar-wrap{min-height:50px!important;padding:5px 7px!important;border-radius:14px!important;background:rgba(255,255,255,.055)!important;border:1px solid rgba(255,255,255,.10)!important;box-shadow:inset 0 1px 0 rgba(255,255,255,.05)!important}
body .app>.top .profile .avatar{width:38px!important;height:38px!important;flex-basis:38px!important}
body .app>.top .profile-rank{align-items:flex-start!important;gap:2px!important}
body .app>.top .profile-rank strong{font-size:9.5px!important;font-weight:900!important;line-height:1.05!important}
body .app>.top .profile-rank small{font-size:8px!important;font-weight:750!important;line-height:1.05!important}
html[data-gts-tournament-theme='laliga'] body .app>.top .profile-avatar-wrap,
html[data-gts-tournament-theme='epl'] body .app>.top .profile-avatar-wrap,
html[data-gts-tournament-theme='seriea'] body .app>.top .profile-avatar-wrap,
html[data-gts-tournament-theme='bundesliga'] body .app>.top .profile-avatar-wrap{background:rgba(255,255,255,.72)!important;border-color:rgba(0,0,0,.10)!important;box-shadow:none!important}
html[data-gts-tournament-theme='laliga'] body .app>.top .profile-rank strong{color:#111!important}
html[data-gts-tournament-theme='laliga'] body .app>.top .profile-rank small{color:#ff4655!important}
html[data-gts-tournament-theme='epl'] body .app>.top .profile-avatar-wrap,
html[data-gts-tournament-theme='seriea'] body .app>.top .profile-avatar-wrap{background:rgba(255,255,255,.10)!important;border-color:rgba(255,255,255,.18)!important}
html[data-gts-tournament-theme='epl'] body .app>.top .profile-rank strong,
html[data-gts-tournament-theme='seriea'] body .app>.top .profile-rank strong{color:#fff!important}
html[data-gts-tournament-theme='bundesliga'] body .app>.top .profile-rank strong{color:#111!important}

/* Domestic league match cards: no grey action strip. */
html[data-gts-tournament-theme='laliga'] body .app .match .actions,
html[data-gts-tournament-theme='epl'] body .app .match .actions,
html[data-gts-tournament-theme='seriea'] body .app .match .actions,
html[data-gts-tournament-theme='bundesliga'] body .app .match .actions{background:#fff!important;border-top:1px solid #dedede!important}
html[data-gts-tournament-theme='laliga'] body .app .match .action,
html[data-gts-tournament-theme='epl'] body .app .match .action,
html[data-gts-tournament-theme='seriea'] body .app .match .action,
html[data-gts-tournament-theme='bundesliga'] body .app .match .action{background:#fff!important;border-color:#dedede!important;box-shadow:none!important;font-weight:800!important}
html[data-gts-tournament-theme='laliga'] body .app .match .action.participants{color:#a965ff!important}
html[data-gts-tournament-theme='laliga'] body .app .match .action.ai{color:#ff4655!important}
html[data-gts-tournament-theme='epl'] body .app .match .action.participants{color:#37003c!important}
html[data-gts-tournament-theme='epl'] body .app .match .action.ai{color:#00a86b!important}
html[data-gts-tournament-theme='seriea'] body .app .match .action.participants{color:#0068ff!important}
html[data-gts-tournament-theme='seriea'] body .app .match .action.ai{color:#0068ff!important}
html[data-gts-tournament-theme='bundesliga'] body .app .match .action.participants{color:#111!important}
html[data-gts-tournament-theme='bundesliga'] body .app .match .action.ai{color:#d20515!important}
html[data-gts-tournament-theme='laliga'] body .app .match .action+.action{border-left-color:#dedede!important}

@media(max-width:430px){body .app>.top .profile-avatar-wrap{min-height:46px!important;padding:4px 6px!important;border-radius:12px!important}body .app>.top .profile .avatar{width:34px!important;height:34px!important;flex-basis:34px!important}}
`;
document.head.appendChild(style);
function cleanParticipantButtons(root=document){
  root.querySelectorAll?.('.match .action').forEach(btn=>{
    const text=(btn.textContent||'').trim();
    if(/Участники/i.test(text)){
      btn.classList.add('participants');
      btn.textContent=text.replace(/^👥\s*/,'');
    }
  });
}
cleanParticipantButtons();
new MutationObserver(records=>{for(const r of records)for(const n of r.addedNodes)if(n.nodeType===1)cleanParticipantButtons(n)}).observe(document.body,{childList:true,subtree:true});
document.addEventListener('gts:matches-updated',()=>cleanParticipantButtons());
document.addEventListener('gts:league-change',()=>setTimeout(cleanParticipantButtons,60));
})();