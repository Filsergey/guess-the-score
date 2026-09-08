(()=>{
  const STYLE_ID='gts-match-detail-close-style-v3';
  const BUTTON_CLASS='gts-match-detail-close-float';

  function ensureStyle(){
    if(document.getElementById(STYLE_ID))return;
    const style=document.createElement('style');
    style.id=STYLE_ID;
    style.textContent=`
      .gts-match-detail-close-anchor{position:sticky;top:8px;height:0;z-index:80;pointer-events:none}
      .gts-match-detail-close-float{position:absolute;right:2px;top:0;width:40px;height:40px;border-radius:50%;border:1px solid rgba(var(--gts-accent-rgb,36,164,255),.34);background:rgba(6,18,30,.88);color:#fff;display:grid;place-items:center;padding:0;box-shadow:0 8px 24px rgba(0,0,0,.34);backdrop-filter:blur(12px);-webkit-backdrop-filter:blur(12px);font-size:27px;font-weight:400;line-height:1;cursor:pointer;pointer-events:auto;-webkit-tap-highlight-color:transparent}
      .gts-match-detail-close-float:active{transform:scale(.94)}
      #sheetContent [data-match-detail-id]{padding-top:46px}
      #sheetContent [data-match-detail-id] .sheet-round{padding-left:48px;padding-right:48px}
      #sheetContent [data-match-detail-id] .match-detail-head{grid-template-columns:minmax(0,1fr) 96px minmax(0,1fr);gap:8px}
      #sheetContent [data-match-detail-id] .match-detail-team{min-width:0;overflow-wrap:anywhere}
      #sheetContent [data-match-detail-id] .match-detail-score{min-width:0}
      .gts-match-detail-date{margin:0 0 5px;font-size:11px;font-weight:750;line-height:1.2;letter-spacing:.02em;color:var(--gts-muted,#8fa4b9);white-space:nowrap;text-align:center}
      @media (max-width:430px){
        #sheetContent [data-match-detail-id]{padding-top:44px}
        #sheetContent [data-match-detail-id] .match-detail-head{grid-template-columns:minmax(0,1fr) 92px minmax(0,1fr);gap:6px}
        #sheetContent [data-match-detail-id] .match-detail-team{font-size:12px}
        #sheetContent [data-match-detail-id] .match-detail-team img,#sheetContent [data-match-detail-id] .match-detail-team .crest{width:60px;height:60px}
      }
      html[data-gts-tournament-theme='laliga'] .gts-match-detail-close-float,
      html[data-gts-tournament-theme='epl'] .gts-match-detail-close-float,
      html[data-gts-tournament-theme='seriea'] .gts-match-detail-close-float,
      html[data-gts-tournament-theme='bundesliga'] .gts-match-detail-close-float{background:rgba(255,255,255,.94);color:#111;border-color:#d8d8d8}
    `;
    document.head.appendChild(style);
  }

  function formatMatchDate(value){
    if(!value)return '';
    const date=new Date(value);
    if(Number.isNaN(date.getTime()))return '';
    return date.toLocaleDateString('ru-RU',{day:'2-digit',month:'2-digit',year:'numeric'});
  }

  function decorateDetail(detail){
    const id=Number(detail?.dataset?.matchDetailId);
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
    decorateDetail(detail);
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
