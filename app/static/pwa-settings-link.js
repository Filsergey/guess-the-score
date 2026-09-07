(()=>{
const style=document.createElement('style');style.textContent=`
.settings-pwa-card{padding:16px;margin-bottom:12px}.settings-pwa-row{display:flex;align-items:center;gap:12px}.settings-pwa-icon{width:44px;height:44px;flex:0 0 44px;border-radius:13px;display:grid;place-items:center;background:color-mix(in srgb,var(--gts-panel,#10263b) 78%,var(--gts-accent,#268fff) 22%);border:1px solid color-mix(in srgb,var(--gts-accent,#268fff) 45%,transparent);font-size:22px}.settings-pwa-copy{min-width:0;flex:1}.settings-pwa-copy strong{display:block;font-size:13px;font-weight:900}.settings-pwa-copy span{display:block;margin-top:4px;color:var(--gts-muted,#879db3);font-size:10px;line-height:1.4}.settings-pwa-btn{width:100%;margin-top:12px;border:1px solid color-mix(in srgb,var(--gts-accent,#268fff) 70%,transparent);border-radius:13px;padding:12px 13px;background:color-mix(in srgb,var(--gts-panel,#10263b) 82%,var(--gts-accent,#268fff) 18%);color:var(--gts-text,#fff);font-size:11px;font-weight:900}.settings-pwa-btn:disabled{opacity:.62}.settings-pwa-hint{margin-top:8px;text-align:center;color:var(--gts-muted,#879db3);font-size:8px;line-height:1.4}
`;document.head.appendChild(style);
const standalone=()=>window.matchMedia?.('(display-mode: standalone)')?.matches||window.navigator.standalone===true;
const inTelegram=()=>Boolean(window.Telegram?.WebApp?.initData);
const isIOS=()=>/iPhone|iPad|iPod/i.test(navigator.userAgent)||(/Macintosh/i.test(navigator.userAgent)&&navigator.maxTouchPoints>1);
function safariHelp(){
 if(window.gtsPwaInstallHelp)return window.gtsPwaInstallHelp();
 const html=`<div class="sheet-title">Установить «Угадай счёт»</div><div class="sheet-note" style="text-align:left;line-height:1.7">1. Открой приложение в <b>Safari</b>.<br>2. Нажми кнопку <b>«Поделиться»</b> внизу экрана.<br>3. Выбери <b>«На экран Домой»</b>.<br>4. Нажми <b>«Добавить»</b>.</div><button class="save secondary" onclick="closeSheet()">Понятно</button>`;
 if(window.openSheet)window.openSheet(html);else alert('Safari → Поделиться → На экран Домой → Добавить');
}
function openSafari(){
 const url=new URL(location.origin+'/');url.searchParams.set('pwa_install','1');
 if(inTelegram()&&window.Telegram?.WebApp?.openLink){window.Telegram.WebApp.openLink(url.toString(),{try_instant_view:false});return}
 if(isIOS()){safariHelp();return}
 window.open(url.toString(),'_blank','noopener');
}
function cardHtml(){
 const installed=standalone();
 const title=installed?'Приложение установлено':'Установить на iPhone';
 const text=installed?'«Угадай счёт» уже запущено как отдельное веб-приложение.':'Добавь «Угадай счёт» на экран «Домой» через Safari — оно будет открываться как обычное приложение.';
 const label=installed?'Установлено ✓':inTelegram()?'Открыть в Safari':isIOS()?'Как установить через Safari':'Открыть веб-приложение';
 return `<div class="card settings-pwa-card" id="settingsPwaCard"><div class="settings-section-title">Приложение</div><div class="settings-pwa-row"><div class="settings-pwa-icon">📲</div><div class="settings-pwa-copy"><strong>${title}</strong><span>${text}</span></div></div><button id="settingsPwaInstall" class="settings-pwa-btn" type="button" ${installed?'disabled':''}>${label}</button>${!installed?'<div class="settings-pwa-hint">Safari → Поделиться → На экран «Домой» → Добавить</div>':''}</div>`;
}
function mount(){
 const page=document.querySelector('#menuView .settings-page');if(!page)return;
 const old=document.getElementById('settingsPwaCard');if(old){const btn=old.querySelector('#settingsPwaInstall');if(btn&&!btn.disabled)btn.onclick=openSafari;return}
 const cards=[...page.querySelectorAll(':scope > .settings-card')];if(!cards.length)return;
 const notifications=cards.find(c=>c.textContent.includes('Уведомления'))||cards[cards.length-1];
 notifications.insertAdjacentHTML('beforebegin',cardHtml());
 document.getElementById('settingsPwaInstall')?.addEventListener('click',openSafari);
}
const root=document.getElementById('menuView');if(root)new MutationObserver(()=>{if(root.classList.contains('active'))mount()}).observe(root,{childList:true,subtree:true});
document.addEventListener('gts:ready',()=>setTimeout(mount,120));document.addEventListener('click',e=>{if(e.target.closest('#navMenu'))setTimeout(mount,120)});document.addEventListener('gts:pwa-installed',()=>setTimeout(mount,50));setTimeout(mount,700);
window.gtsOpenPwaInstall=openSafari;
})();
