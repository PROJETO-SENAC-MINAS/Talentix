document.addEventListener('DOMContentLoaded', () => {
  const {api,esc,toast} = Talentix;
  const area=document.createElement('div');area.className='card';area.id='atsConsentimentos';
  area.innerHTML='<h2 class="section-subtitle">Banco de talentos das empresas</h2><p>Escolha quais empresas podem guardar seu perfil em pools e convidar você para novas vagas. A autorização é opcional e pode ser revogada. Suas candidaturas atuais continuam disponíveis.</p><div id="atsConsentLista"></div>';
  document.querySelector('#tab-perfil').append(area);
  async function load() {
    try { const data=await api('/ats/consentimentos');
      document.querySelector('#atsConsentLista').innerHTML=data.map(e=>`<div class="list-item"><p>${esc(e.NomeFantasia || 'Empresa')}</p><button type="button" class="btn btn-secondary" data-consent="${esc(e.ID_Empresas)}" data-authorize="${e.Autorizado ? 'false':'true'}">${e.Autorizado ? 'Revogar autorização':'Autorizar banco de talentos'}</button></div>`).join('') || '<p>As empresas para as quais você se candidatar aparecerão aqui.</p>';
    } catch(e) { document.querySelector('#atsConsentLista').textContent=e.message; }
  }
  area.addEventListener('click',async e=>{const b=e.target.closest('[data-consent]');if(!b)return;b.disabled=true;
    try {await api('/ats/consentimentos/'+encodeURIComponent(b.dataset.consent),{method:'PUT',body:JSON.stringify({autorizado:b.dataset.authorize==='true'})});await load();toast('Autorização atualizada.');}catch(e){toast(e.message,true);b.disabled=false;}
  });load();
});
