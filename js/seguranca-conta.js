document.addEventListener('DOMContentLoaded', () => {
  if (!window.Talentix) return;
  const {api, esc, toast} = Talentix;
  const nav = document.querySelector('.sidebar__nav');
  const main = document.querySelector('main.content');
  if (!nav || !main || document.querySelector('[data-tab="seguranca"]')) return;

  const btn = document.createElement('button');
  btn.type='button'; btn.className='nav-item'; btn.dataset.tab='seguranca'; btn.textContent='Segurança';
  nav.appendChild(btn);

  const section=document.createElement('section');
  section.className='tab-panel'; section.id='tab-seguranca';
  section.innerHTML=`
    <header class="content__header"><div><h1>Segurança da conta</h1><p class="content__sub">Gerencie senha, 2FA e dispositivos conectados.</p></div></header>
    <div class="card"><h2>Status</h2><div id="securityStatus" aria-live="polite">Carregando…</div></div>
    <div class="card"><h2>Alterar senha</h2><form id="securityPassword"><div class="field"><label for="secCurrentPassword">Senha atual</label><input id="secCurrentPassword" type="password" autocomplete="current-password" required></div><div class="field"><label for="secNewPassword">Nova senha</label><input id="secNewPassword" type="password" autocomplete="new-password" required minlength="8"></div><button class="btn btn-primary" type="submit">Alterar senha</button></form></div>
    <div class="card"><h2>Autenticação em dois fatores</h2><p id="security2faText"></p><button class="btn btn-secondary" id="security2faStart" type="button">Configurar 2FA</button><div id="security2faSetup" hidden><p>Adicione a chave ao seu aplicativo autenticador:</p><code id="security2faSecret" class="account-id"></code><div class="field"><label for="security2faCode">Código de 6 dígitos</label><input id="security2faCode" inputmode="numeric" pattern="[0-9]{6}" maxlength="6"></div><button class="btn btn-primary" id="security2faConfirm" type="button">Confirmar 2FA</button></div></div>
    <div class="card"><div class="content__header"><div><h2>Sessões ativas</h2><p class="content__sub">Encerre acessos que você não reconhece.</p></div><button class="btn btn-secondary" id="securityCloseAll" type="button">Encerrar todas</button></div><div class="list" id="securitySessions"></div></div>`;
  main.appendChild(section);

  let me=null;
  const fmt=v=>v?new Date(v).toLocaleString('pt-BR'):'—';
  async function load(){
    me=await api('/auth/me');
    document.querySelector('#securityStatus').innerHTML='<p><strong>E-mail:</strong> '+esc(me.Email)+' · '+(me.email_confirmado?'confirmado':'pendente')+'</p><p><strong>Último login:</strong> '+esc(fmt(me.UltimoLoginEm))+'</p>';
    document.querySelector('#security2faText').textContent=me.two_factor_ativo?'2FA está ativo nesta conta.':'2FA ainda não está ativo.';
    document.querySelector('#security2faStart').hidden=Boolean(me.two_factor_ativo);
    const sessions=await api('/auth/sessoes');
    document.querySelector('#securitySessions').innerHTML=sessions.length?sessions.map(s=>'<article class="list-item"><div><h3>'+(s.Atual?'Este dispositivo':'Sessão')+'</h3><p>'+esc(s.UserAgent||'Dispositivo não identificado')+'</p><p>Última atividade: '+esc(fmt(s.UltimaAtividadeEm))+'</p></div>'+(s.RevogadaEm?'<span class="badge badge-muted">Encerrada</span>':'<button class="btn btn-secondary" data-session="'+esc(s.ID_Sessoes)+'" type="button">Encerrar</button>')+'</article>').join(''):'<p class="empty-state">Nenhuma sessão registrada.</p>';
  }
  btn.addEventListener('click',()=>load().catch(e=>toast(e.message,true)));
  document.querySelector('#securityPassword').addEventListener('submit',async e=>{e.preventDefault();try{await api('/auth/alterar-senha',{method:'POST',body:JSON.stringify({senha_atual:document.querySelector('#secCurrentPassword').value,nova_senha:document.querySelector('#secNewPassword').value})});location.assign('login.html');}catch(err){toast(err.message,true)}});
  document.querySelector('#security2faStart').addEventListener('click',async()=>{try{const d=await api('/auth/2fa/iniciar',{method:'POST'});document.querySelector('#security2faSecret').textContent=d.secret;document.querySelector('#security2faSetup').hidden=false;document.querySelector('#security2faCode').focus();}catch(e){toast(e.message,true)}});
  document.querySelector('#security2faConfirm').addEventListener('click',async()=>{try{await api('/auth/2fa/confirmar',{method:'POST',body:JSON.stringify({codigo:document.querySelector('#security2faCode').value})});toast('2FA ativado.');await load();document.querySelector('#security2faSetup').hidden=true;}catch(e){toast(e.message,true)}});
  document.querySelector('#securitySessions').addEventListener('click',async e=>{const id=e.target.dataset.session;if(!id)return;try{await api('/auth/sessoes/'+id,{method:'DELETE'});if(me&&id===me.id_sessao)location.assign('login.html');else await load();}catch(err){toast(err.message,true)}});
  document.querySelector('#securityCloseAll').addEventListener('click',async()=>{if(!confirm('Encerrar todas as sessões, inclusive esta?'))return;try{await api('/auth/sessoes/encerrar-todas',{method:'POST'});location.assign('login.html');}catch(e){toast(e.message,true)}});
});