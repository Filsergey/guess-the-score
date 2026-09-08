(()=>{
  const STYLE_ID='gts-sheet-close-style-v6';
  const ANCHOR_CLASS='gts-sheet-close-anchor';
  const BUTTON_CLASS='gts-sheet-close-float';
  const SPACE_CLASS='gts-sheet-close-space';

  function ensureStyle(){
    if(document.getElementById(STYLE_ID))return;
    const style=document.createElement('style');
    style.id=STYLE_ID;
    style.textContent=`
      .${ANCHOR_CLASS}{position:sticky;top:8px;height:0;z-index:90;pointer-events:none}
      .${BUTTON_CLASS}{position:absolute;right:2px;top:0;width:40px;height:40px;border-radius:50%;border:1px solid rgba(var(--gts-accent-rgb,36,164,255),.34);background:rgba(6,18,30,.88);color:#fff;display:grid;place-items:center;padding:0;box-shadow:0 8px 24px rgba(0,0,0,.34);backdrop-filter:blur(12px);-webkit-backdrop-filter:blur(12px);font-size:27px;font-weight:400;line-height:1;cursor:pointer;pointer-events:auto;-webkit-tap-highlight-color:transparent}
      .${BUTTON_CLASS}:active{transform:scale(.94)}
      #sheetContent.${SPACE_CLASS}{padding-top:44px!important}
      #sheetContent [data-match-detail-id] .sheet-round{padding-left:48px;padding-right:48px}
      #sheetContent [data-match-detail-id] .match-detail-head{grid-template-columns:minmax(0,1fr) 96px minmax(0,1fr);gap:8px}
      #sheetContent [data-match-detail-id] .match-detail-team{min-width:0;overflow-wrap:anywhere}
      #sheetContent [data-match-detail-id] .match-detail-score{min-width:0}
      .gts-match-detail-date{margin:0 0 5px;font-size:11px;font-weight:750;line-height:1.2;letter-spacing:.02em;color:var(--gts-muted,#8fa4b9);white-space:nowrap;text-align:center}
      @media (max-width:430px){
        #sheetContent.${SPACE_CLASS}{padding-top:42px!important}
        #sheetContent [data-match-detail-id] .match-detail-head{grid-template-columns:minmax(0,1fr) 92px minmax(0,1fr);gap:6px}
        #sheetContent [data-match-detail-id] .match-detail-team{font-size:12px}
        #sheetContent [data-match-detail-id] .match-detail-team img,#sheetContent [data-match-detail-id] .match-detail-team .crest{width:60px;height:60px}
      }
      html[data-gts-tournament-theme='laliga'] .${BUTTON_CLASS},
      html[data-gts-tournament-theme='epl'] .${BUTTON_CLASS},
      html[data-gts-tournament-theme='seriea'] .${BUTTON_CLASS},
      html[data-gts-tournament-theme='bundesliga'] .${BUTTON_CLASS}{background:rgba(255,255,255,.94);color:#111;border-color:#d8d8d8}
    `;
    document.head.appendChild(style);
  }

  function formatMatchDate(value){
    if(!value)return '';
    const date=new Date(value);
    if(Number.isNaN(date.getTime()))return '';
    return date.toLocaleDateString('ru-RU',{day:'2-digit',month:'2-digit',year:'numeric'});
  }

  function decorateMatchDetail(detail){
    if(!detail)return;
    const id=Number(detail.dataset?.matchDetailId);
    if(!Number.isFinite(id))return;
    const base=window.GTS?.match?.(id);
    const value=formatMatchDate(base?.kickoff_at);
    const score=detail.querySelector('.match-detail-score');
    if(!score||!value)return;
    let node=score.querySelector('.gts-match-detail-date');
    if(!node){
      node=document.createElement('div');
      node.className='gts-match-detail-date';
      node.textContent=value;
      score.insertBefore(node,score.firstChild);
      return;
    }
    if(node.textContent!==value)node.textContent=value;
  }

  function findNativeClose(content){
    if(!content)return null;
    const selectors=[
      '[data-md-close]',
      '[data-sheet-close]',
      '[data-close-sheet]',
      'button.close',
      'button[aria-label="Закрыть"]',
      'button[aria-label="Закрыть окно"]'
    ];
    for(const selector of selectors){
      const node=content.querySelector(selector);
      if(node&&!node.classList.contains(BUTTON_CLASS))return node;
    }
    const buttons=[...content.querySelectorAll('button')];
    return buttons.find(node=>{
      if(node.classList.contains(BUTTON_CLASS))return false;
      const text=(node.textContent||'').trim().toLocaleLowerCase('ru-RU');
      return text==='закрыть'||text==='close';
    })||null;
  }

  function closeCurrentSheet(){
    try{
      if(typeof window.gtsSheetBack==='function'&&window.gtsSheetBack())return;
    }catch{}
    try{
      if(typeof window.gtsTrySheetBack==='function'&&window.gtsTrySheetBack())return;
    }catch{}
    const content=document.getElementById('sheetContent');
    const nativeClose=findNativeClose(content);
    if(nativeClose){nativeClose.click();return}
    if(typeof window.closeSheet==='function'){window.closeSheet();return}
    document.dispatchEvent(new CustomEvent('gts:force-close-sheet'));
    if(typeof window.forceCloseSheet==='function'){window.forceCloseSheet();return}
    const modal=document.getElementById('modal');
    modal?.classList.remove('open');
  }

  function hasSheetContent(modal,content){
    if(!modal?.classList.contains('open'))return false;
    if(!content)return false;
    return content.childElementCount>0||Boolean((content.textContent||'').trim());
  }

  function sync(){
    ensureStyle();
    const modal=document.getElementById('modal');
    const sheet=modal?.querySelector('.sheet');
    const content=document.getElementById('sheetContent');
    if(!modal||!sheet||!content)return;

    const detail=content.querySelector('[data-match-detail-id]');
    decorateMatchDetail(detail);

    let anchor=sheet.querySelector(`:scope > .${ANCHOR_CLASS}`);
    const active=hasSheetContent(modal,content);
    content.classList.toggle(SPACE_CLASS,active);

    if(!active){anchor?.remove();return}
    if(anchor)return;

    anchor=document.createElement('div');
    anchor.className=ANCHOR_CLASS;
    const button=document.createElement('button');
    button.type='button';
    button.className=BUTTON_CLASS;
    button.setAttribute('aria-label','Закрыть окно');
    button.innerHTML='&times;';
    button.addEventListener('click',e=>{
      e.preventDefault();
      e.stopPropagation();
      closeCurrentSheet();
    });
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
