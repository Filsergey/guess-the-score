(()=>{
const style=document.createElement('style');
style.textContent=`
#leaderboard tr.oracle-row{background:linear-gradient(90deg,rgba(72,108,255,.13),rgba(117,78,255,.08));box-shadow:inset 3px 0 0 #6c8cff}
#leaderboard tr.oracle-row td{border-bottom-color:#26395d}
#leaderboard tr.oracle-row .player-wrap strong{color:#dce5ff}
#leaderboard tr.oracle-row .player-wrap strong::before{content:'✦ ';color:#8ea4ff}
#leaderboard tr.oracle-row .avatar{display:none}
#leaderboard tr.oracle-row .player-wrap>div::after{content:'ИИ-соперник';display:block;color:#8ea4ff;font-size:9px;margin-top:2px}
#leaderboard tr.oracle-row .pts{color:#9eb0ff}
`;
document.head.appendChild(style);
function decorate(){
  document.querySelectorAll('#leaderboard tbody tr').forEach(row=>{
    const txt=(row.textContent||'').trim();
    row.classList.toggle('oracle-row',/Оракул/i.test(txt));
  });
}
const root=document.getElementById('leaderboard');
if(root){new MutationObserver(decorate).observe(root,{childList:true,subtree:true});decorate()}
})();
