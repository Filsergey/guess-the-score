(()=>{
const box=document.getElementById('sheetContent');
if(!box)return;
const style=document.createElement('style');
style.textContent=`
.gts-detail-group{margin:10px 0;border:1px solid rgba(var(--gts-accent-rgb,36,164,255),.20);border-radius:14px;overflow:hidden;background:color-mix(in srgb,var(--gts-panel,#10263b) 94%,transparent)}
.gts-detail-group-head{width:100%;border:0!important;background:transparent!important;color:var(--gts-text,#fff)!important;display:flex;align-items:center;justify-content:space-between;gap:10px;padding:12px 13px!important;font-size:12px!important;font-weight:900!important;text-align:left;box-shadow:none!important}
.gts-detail-group-head .gts-detail-chevron{font-size:15px;line-height:1;color:var(--gts-accent-2,#72cbff);transition:transform .18s ease}
.gts-detail-group.open .gts-detail-chevron{transform:rotate(180deg)}
.gts-detail-group-body{display:none;padding:0 12px 12px}
.gts-detail-group.open .gts-detail-group-body{display:block}
.gts-detail-group .match-detail-block{margin:0!important}
.gts-detail-group .match-detail-title{display:none!important}
.gts-detail-group .match-detail-meta{margin:0!important}
html[data-gts-tournament-theme='laliga'] .gts-detail-group,html[data-gts-tournament-theme='epl'] .gts-detail-group,html[data-gts-tournament-theme='seriea'] .gts-detail-group,html[data-gts-tournament-theme='bundesliga'] .gts-detail-group{background:#fff!important;border-color:#dedede!important}
html[data-gts-tournament-theme='laliga'] .gts-detail-group-head,html[data-gts-tournament-theme='epl'] .gts-detail-group-head,html[data-gts-tournament-theme='seriea'] .gts-detail-group-head,html[data-gts-tournament-theme='bundesliga'] .gts-detail-group-head{color:#111!important}
`;
document.head.appendChild(style);
function makeGroup(title,node,open=false){
 if(!node||node.closest('.gts-detail-group'))return;
 const group=document.createElement('section');group.className='gts-detail-group'+(open?' open':'');
 const head=document.createElement('button');head.type='button';head.className='gts-detail-group-head';head.innerHTML=`<span>${title}</span><span class="gts-detail-chevron">⌄</span>`;
 const body=document.createElement('div');body.className='gts-detail-group-body';
 node.parentNode.insertBefore(group,node);group.append(head,body);body.appendChild(node);
 head.onclick=e=>{e.preventDefault();group.classList.toggle('open')};
}
function decorate(){
 const root=box.querySelector('[data-match-detail-id]');if(!root)return;
 const meta=root.querySelector(':scope > .match-detail-meta');if(meta&&!meta.closest('.gts-detail-group'))makeGroup('Информация о матче',meta,false);
 [...root.querySelectorAll(':scope > .match-detail-block')].forEach(block=>{
  const title=(block.querySelector('.match-detail-title')?.textContent||'Подробности').trim();
  makeGroup(title,block,false);
 });
}
new MutationObserver(()=>queueMicrotask(decorate)).observe(box,{childList:true,subtree:true});
document.addEventListener('gts:matches-updated',()=>setTimeout(decorate,50));
setTimeout(decorate,300);
})();