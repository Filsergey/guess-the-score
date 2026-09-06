const CACHE_NAME='guess-the-score-pwa-v1';
const STATIC_ASSETS=[
  '/static/manifest.webmanifest',
  '/static/pwa-icon.svg?v=1',
  '/static/pwa.js?v=1'
];

self.addEventListener('install',event=>{
  event.waitUntil(caches.open(CACHE_NAME).then(cache=>cache.addAll(STATIC_ASSETS)).catch(()=>null));
  self.skipWaiting();
});

self.addEventListener('activate',event=>{
  event.waitUntil((async()=>{
    const names=await caches.keys();
    await Promise.all(names.filter(name=>name.startsWith('guess-the-score-pwa-')&&name!==CACHE_NAME).map(name=>caches.delete(name)));
    await self.clients.claim();
  })());
});

self.addEventListener('fetch',event=>{
  const request=event.request;
  if(request.method!=='GET')return;
  const url=new URL(request.url);
  if(url.origin!==self.location.origin)return;
  if(url.pathname.startsWith('/api/'))return;
  if(!url.pathname.startsWith('/static/'))return;

  event.respondWith((async()=>{
    try{
      const response=await fetch(request);
      if(response&&response.ok){
        const cache=await caches.open(CACHE_NAME);
        cache.put(request,response.clone()).catch(()=>{});
      }
      return response;
    }catch{
      const cached=await caches.match(request);
      if(cached)return cached;
      throw new Error('offline');
    }
  })());
});

self.addEventListener('push',event=>{
  let data={};
  try{data=event.data?event.data.json():{}}catch{data={body:event.data?.text?.()||''}}
  const title=data.title||'Угадай счёт';
  const options={
    body:data.body||'Новое уведомление',
    icon:'/static/pwa-icon.svg?v=1',
    badge:'/static/pwa-icon.svg?v=1',
    data:{url:data.url||'/'},
    tag:data.tag||undefined,
    renotify:Boolean(data.renotify)
  };
  event.waitUntil(self.registration.showNotification(title,options));
});

self.addEventListener('notificationclick',event=>{
  event.notification.close();
  const target=new URL(event.notification?.data?.url||'/',self.location.origin).href;
  event.waitUntil((async()=>{
    const windows=await self.clients.matchAll({type:'window',includeUncontrolled:true});
    for(const client of windows){
      if('focus' in client){
        if('navigate' in client)await client.navigate(target).catch(()=>{});
        return client.focus();
      }
    }
    if(self.clients.openWindow)return self.clients.openWindow(target);
  })());
});
