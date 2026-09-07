(()=>{
const AVATAR='/static/oracle-avatar.webp?v=2';
const style=document.createElement('style');
style.textContent=`
#leaderboard tr.oracle-row{background:linear-gradient(90deg,rgba(72,108,255,.13),rgba(117,78,255,.08));box-shadow:inset 3px 0 0 #6c8cff}
#leaderboard tr.oracle-row td{border-bottom-color:#26395d}
#leaderboard tr.oracle-row .player-wrap strong{color:#dce5ff}
#leaderboard tr.oracle-row .avatar{display:block!important;width:36px;height:36px;object-fit:cover;border-radius:50%;border:1px solid rgba(142,164,255,.55);background:#10263b}
#leaderboard tr.oracle-row .player-wrap>div::after{content:'ИИ-соперник';display:block;color:#8ea4ff;font-size:9px;margin-top:2px}
#leaderboard tr.oracle-row .pts{color:#9eb0ff}
`;
document.head.appendChild(style);
function setAvatar(row){
  const wrap=row.querySelector('.player-wrap');if(!wrap)return;
  let avatar=wrap.querySelector('.avatar');
  if(avatar?.tagName==='IMG'){if(avatar.src.endsWith(AVATAR))return;avatar.src=AVATAR;avatar.alt='Оракул';return}
  const img=document.createElement('img');img.className='avatar';img.src=AVATAR;img.alt='Оракул';
  if(avatar)avatar.replaceWith(img);else wrap.prepend(img);
}
function decorate(){
  document.querySelectorAll('#leaderboard tbody tr').forEach(row=>{
    const txt=(row.textContent||'').trim(),isOracle=/Оракул/i.test(txt);
    row.classList.toggle('oracle-row',isOracle);
    if(isOracle)setAvatar(row);
  });
}
const root=document.getElementById('leaderboard');
if(root){new MutationObserver(decorate).observe(root,{childList:true,subtree:true});decorate()}
})();
