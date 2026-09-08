(()=>{
const isAdmin=()=>['admin','superadmin'].includes(String(window.GTS?.me?.role||'').toLowerCase());
const root=()=>document.getElementById('menuView');
function ensure(){
  if(!isAdmin())return;
  const r=root();
  if(!r||!r.classList.contains('active'))return;
  const page=r.querySelector('.settings-page');
  if(!page)return;
  // renderUsage() leaves this flag on #menuView. When another view later renders
  // Settings into the same root, the stale flag used to make mountTabs() return.
  r.dataset.gtsOpenaiUsage='';
  if(page.querySelector('[data-gts-admin-tabs]'))return;
  const html='<div class="gts-admin-tabs" data-gts-admin-tabs="1"><button class="gts-admin-tab active" data-gts-admin-settings>Настройки</button><button class="gts-admin-tab" data-gts-admin-usage>OpenAI расходы</button></div>';
  const head=page.querySelector('.page-head');
  if(head)head.insertAdjacentHTML('afterend',html);else page.insertAdjacentHTML('afterbegin',html);
  page.querySelector('[data-gts-admin-usage]')?.addEventListener('click',()=>window.gtsOpenAIUsage?.(30));
}
const obs=new MutationObserver(()=>queueMicrotask(ensure));
function start(){const r=root();if(r)obs.observe(r,{childList:true,subtree:true});ensure()}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',start,{once:true});else start();
document.addEventListener('gts:ready',()=>setTimeout(ensure,0));
document.addEventListener('gts:profile-updated',()=>setTimeout(ensure,0));
document.addEventListener('click',e=>{if(e.target.closest?.('#navMenu'))setTimeout(ensure,0)});
})();
