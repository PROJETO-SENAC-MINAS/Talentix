/* Somente arquivos públicos do app. Nenhum dado, currículo, sessão ou resposta de API é armazenado. */
const CACHE='talentix-shell-20261014-v1';
const SHELL=['/html/offline.html','/icons/talentix.svg','/icons/talentix-maskable.svg'];
self.addEventListener('install',event=>{event.waitUntil(caches.open(CACHE).then(cache=>cache.addAll(SHELL)));});
self.addEventListener('activate',event=>{event.waitUntil(caches.keys().then(keys=>Promise.all(keys.filter(k=>k.startsWith('talentix-shell-')&&k!==CACHE).map(k=>caches.delete(k)))).then(()=>self.clients.claim()));});
self.addEventListener('fetch',event=>{
  const request=event.request,url=new URL(request.url);
  if(request.method!=='GET'||url.origin!==self.location.origin)return;
  if(request.mode==='navigate'){
    event.respondWith(fetch(request).catch(()=>caches.match('/html/offline.html')));return;
  }
  if(!/^\/(css|js|icons)\/[a-zA-Z0-9._/-]+$/.test(url.pathname))return;
  event.respondWith(fetch(request).then(response=>{
    if(response.ok&&response.type==='basic'){
      const copy=response.clone();event.waitUntil(caches.open(CACHE).then(async cache=>{await cache.put(request,copy);const keys=await cache.keys();for(const key of keys.slice(0,Math.max(0,keys.length-60)))if(!SHELL.includes(new URL(key.url).pathname))await cache.delete(key);}));
    }return response;
  }).catch(()=>caches.match(request)));
});
// A integração push exige configuração do servidor e consentimento separado.
self.addEventListener('push',event=>{event.waitUntil(self.registration.showNotification('Talentix',{body:'Uma atualização está disponível. Abra a plataforma para consultar.',icon:'/icons/talentix.svg',data:{url:'/html/central.html'}}));});
self.addEventListener('notificationclick',event=>{event.notification.close();event.waitUntil(self.clients.openWindow('/html/central.html'));});
