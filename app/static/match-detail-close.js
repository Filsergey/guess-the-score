(()=>{
  const STYLE_ID='gts-match-detail-close-style-v1';
  const BUTTON_CLASS='gts-match-detail-close-float';

  function ensureStyle(){
    if(document.getElementById(STYLE_ID))return;
    const style=document.createElement('style');
    style.id=STYLE_ID;
    style.textContent=`
      .gts-match-detail-close-anchor{position:sticky;top:8px;height:0;z-index:80;pointer-events:none}
      .gts-match-detail-close-float{position:absolute;right:0;top:0;width:40px;height:40px;border-radius:50%;border:1px solid rgba(var(--gts-accent-rgb,36,164,255),.34);background:rgba(6,18,30,.88);color:#fff;display:grid;place-items:center;padding:0;box-shadow:0 8px 24px rgba(0,0,0,.34);backdrop-filter:blur(12px);-webkit-backdrop-filter:blur(12px);font-size:27px;font-weight:400;line-height:1;cursor:pointer;pointer-events:auto;-webkit-tap-highlight-color:transparent}
      .gts-match-detail-close-float:active{transform:scale(.94)}
      html[data-gts-tournament-theme='laliga'] .gts-match-detail-close-float,
      html[data-gts-tournament-theme='epl'] .gts-match-detail-close-float,
      html[data-gts-tournament-theme='seriea'] .gts-match-detail-close-float,
      html[data-gts-tournament-theme='bundesliga'] .gts-match-detail-close-float{background:rgba(255,255,255,.94);color:#111;border-color:#d8d8d8}
    `;
    document.head.appendChild(style);
  }

  function closeDetail(){
    const close=document.querySelector('#sheetContent [data-match-detail-id] [data-md-close]');
    if(close){close.click();return}
    document.dispatchEvent(new CustomEvent('gts:force-close-sheet'));
    if(typeof window.forceCloseSheet==='function'){window.forceCloseSheet();return}
    const modal=document.getElementById('modal');
    modal?.classList.remove('open');
  }

  function sync(){
    ensureStyle();
    const modal=document.getElementById('modal');
    const sheet=modal?.querySelector('.sheet');
    const content=document.getElementById('sheetContent');
    if(!modal||!sheet||!content)return;
    const detail=content.querySelector('[data-match-detail-id]');
    let anchor=sheet.querySelector(':scope > .gts-match-detail-close-anchor');
    if(!detail){anchor?.remove();return}
    if(anchor)return;
    anchor=document.createElement('div');
    anchor.className='gts-match-detail-close-anchor';
    const button=document.createElement('button');
    button.type='button';
    button.className=BUTTON_CLASS;
    button.setAttribute('aria-label','Закрыть окно матча');
    button.innerHTML='&times;';
    button.addEventListener('click',e=>{e.preventDefault();e.stopPropagation();closeDetail()});
    anchor.appendChild(button);
    sheet.insertBefore(anchor,content);
  }

  function init(){
    sync();
    const modal=document.getElementById('modal');
    if(!modal)return;
    new MutationObserver(sync).observe(modal,{subtree:true,childList:true,attributes:true,attributeFilter:['class']});
  }

  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init,{once:true});
  else init();
})();
