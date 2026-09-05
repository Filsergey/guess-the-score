(()=>{
const root=document.getElementById('leaderboard');if(!root)return;
const style=document.createElement('style');style.textContent=`
#leaderboard tbody tr.me-row{background:linear-gradient(90deg,rgba(38,143,255,.13),rgba(38,143,255,.035));box-shadow:inset 3px 0 0 #268fff}
#leaderboard tbody tr.me-row .player-wrap strong{color:#eef7ff}
#leaderboard tbody tr.me-row .player-wrap strong::after{content:'  ВЫ';color:#58aaff;font-size:8px;font-weight:900;letter-spacing:.5px}
#leaderboard .playing-since{display:block;color:#6f91ad;font-size:8px;margin-top:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
`;
document.head.appendChild(style);
const auth=()=>{const t=localStorage.getItem('access_token')||'';return t?{Authorization:`Bearer ${t}`}:{}};
const leagueId=()=>localStorage.getItem('selected_league_id');
let busy=false,last='';
function dateText(v){if(!v)return '';const d=new Date(v);if(Number.isNaN(d.getTime()))return '';return d.toLocaleDateString('ru-RU',{day:'numeric',month:'short',year:'numeric'})}
async function decorate(){
 if(busy)return;const id=leagueId(),rows=[...root.querySelectorAll('tbody tr')];if(!id||!rows.length)return;
 const key=id+':'+rows.length+':'+rows.map(r=>r.textContent).join('|');if(key===last)return;busy=true;
 try{
  const [br,mr]=await Promise.all([fetch(`/api/leagues/${id}/leaderboard`,{headers:auth()}),fetch('/api/auth/me',{headers:auth()})]);if(!br.ok||!mr.ok)return;
  const board=await br.json(),me=await mr.json(),items=board.response||[];if(items.length!==rows.length)return;
  rows.forEach((row,i)=>{
   const x=items[i]||{};row.classList.toggle('me-row',!x.is_oracle&&Number(x.user_id)===Number(me.id));
   if(x.is_oracle||!x.registered_at)return;
   const wrap=row.querySelector('.player-wrap>div');if(!wrap)return;
   let note=wrap.querySelector('.playing-since');if(!note){note=document.createElement('span');note.className='playing-since';wrap.appendChild(note)}
   note.textContent=`В игре с ${dateText(x.registered_at)}`;
  });last=key;
 }finally{busy=false}
}
new MutationObserver(()=>setTimeout(decorate,60)).observe(root,{childList:true,subtree:true});decorate();
})();
