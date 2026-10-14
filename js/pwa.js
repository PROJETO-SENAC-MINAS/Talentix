(() => {
  'use strict';
  if(!('serviceWorker' in navigator)||!window.isSecureContext){
    for(const id of ['ativarPush','desativarPush']){const b=document.getElementById(id);if(b)b.disabled=true;}
    const state=document.getElementById('pushEstado');
    if(state)state.textContent='Notificações push precisam de HTTPS ou localhost e de um navegador compatível.';
    return;
  }
  navigator.serviceWorker.register('../service-worker.js',{scope:'/'}).catch(()=>{});
  let prompt;
  const button=document.getElementById('instalarApp');
  window.addEventListener('beforeinstallprompt',event=>{event.preventDefault();prompt=event;if(button)button.hidden=false;});
  button?.addEventListener('click',async()=>{if(!prompt)return;await prompt.prompt();await prompt.userChoice;prompt=null;button.hidden=true;});
  window.addEventListener('appinstalled',()=>{if(button)button.hidden=true;});
  document.getElementById('ativarPush')?.addEventListener('click',async()=>{
    const status=document.getElementById('pushEstado');
    try{
      if(!('PushManager'in window)||!('Notification'in window))throw Error('Este navegador não oferece notificações push.');
      const config=await Talentix.api('/push/configuracao');
      if(!config.disponivel)throw Error('Notificações do navegador ainda não estão disponíveis neste ambiente.');
      const permission=await Notification.requestPermission();
      if(permission!=='granted')throw Error('Você pode continuar usando as notificações dentro do Talentix.');
      const registration=await navigator.serviceWorker.ready;
      const old=await registration.pushManager.getSubscription();
      if(old)await old.unsubscribe();
      const value=config.chave_publica.replace(/-/g,'+').replace(/_/g,'/');
      const key=Uint8Array.from(atob(value+'='.repeat((4-value.length%4)%4)),c=>c.charCodeAt(0));
      const sub=await registration.pushManager.subscribe({userVisibleOnly:true,applicationServerKey:key});
      try{await Talentix.api('/push/assinaturas',{method:'POST',body:JSON.stringify(sub.toJSON())});}
      catch(e){await sub.unsubscribe();throw e;}
      status.textContent='Notificações ativadas neste navegador.';
    }catch(error){status.textContent=error.message;}
  });
  document.getElementById('desativarPush')?.addEventListener('click',async()=>{
    const status=document.getElementById('pushEstado');
    try{
      await Talentix.api('/push/assinaturas',{method:'DELETE'});
      const registration=await navigator.serviceWorker.ready;const sub=await registration.pushManager.getSubscription();if(sub)await sub.unsubscribe();
      status.textContent='Notificações push desativadas.';
    }catch(e){status.textContent=e.message;}
  });
})();
