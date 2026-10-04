/* Perfil em uma tela; usa somente a sessão e dados oficiais retornados pela API. */
document.addEventListener('DOMContentLoaded', () => {
  const {$, esc, api, toast} = Talentix;
  let candidato, itens = [], idiomas = [], atualizarTimer;
  const moved = [$('#formExperiencia')?.closest('.card'), ...document.querySelectorAll('#tab-formacao > .card')].filter(Boolean);
  const anchors = moved.map(card => {const marker = document.createComment('posição do cartão profissional'); card.before(marker); return marker;});
  function layout(tab) {
    moved.forEach((card, i) => tab === 'perfil' ? $('#tab-perfil').append(card) : anchors[i].after(card));
  }
  layout('perfil');
  document.querySelectorAll('.nav-item').forEach(b => b.addEventListener('click', () => layout(b.dataset.tab)));
  // Os mesmos formulários também continuam acessíveis pelas abas antigas.
  const limites = {pTituloProfissional:150,pResumo:5000,pCidade:100,pLinkedin:300,pGithub:300,pPortfolio:300,expEmpresa:150,expCargo:150,expDescricao:5000,fInstituicao:200,fCurso:200,hNome:100,cvTitulo:150};
  for (const [id, n] of Object.entries(limites)) if ($('#'+id)) $('#'+id).maxLength = n;
  ['pLinkedin','pGithub','pPortfolio'].forEach(id => $('#'+id).pattern = 'https?://.*');

  async function atualizar() {
    if (!candidato) return;
    const d = await api(`/candidatos/${candidato}/profissional`);
    $('#completudeTexto').textContent = `Completude do perfil: ${d.completude}%`;
    $('#completudeBarra').value = d.completude;
    $('#perfilFaltantes').innerHTML = d.faltantes.map(f => `<li>Adicionar ${esc(f.campo)}: +${f.peso}%</li>`).join('');
    $('#fotoProfissional').hidden = !d.perfil.FotoUrl;
    if (d.perfil.FotoUrl) $('#fotoProfissional').src = API_BASE_URL + d.perfil.FotoUrl;
    itens = d.itens; idiomas = d.idiomas;
    $('#listaItensProfissionais').innerHTML = itens.map(i => `<article class="list-item"><div class="list-item__main"><h3>${esc(i.Titulo)}</h3><p>${esc(i.Tipo)} · ${esc(i.Instituicao)}</p><p>${esc(i.Descricao)}</p>${i.Url ? `<a href="${esc(Talentix.safeUrl(i.Url))}" target="_blank" rel="noopener noreferrer">Abrir ${esc(i.Tipo)}</a>` : ''}</div><div class="list-item__actions"><button type="button" class="btn btn-secondary" data-editar-item="${esc(i.ID_Item)}">Editar ${esc(i.Tipo)}</button><button type="button" class="btn-danger-ghost" data-remover-item="${esc(i.ID_Item)}">Remover ${esc(i.Tipo)}</button></div></article>`).join('') || '<p>Nenhum curso ou projeto cadastrado.</p>';
    $('#listaIdiomasProfissionais').innerHTML = idiomas.map(i => `<div class="list-item"><p>${esc(i.Nome)} · ${esc(i.Nivel)}</p><button type="button" class="btn btn-secondary" data-editar-idioma="${esc(i.ID_Candidato_Idiomas)}">Editar ${esc(i.Nome)}</button><button type="button" class="btn-danger-ghost" data-remover-idioma="${esc(i.ID_Candidato_Idiomas)}">Remover ${esc(i.Nome)}</button></div>`).join('') || '<p>Nenhum idioma cadastrado.</p>';
  }
  const refresh = () => {clearTimeout(atualizarTimer); atualizarTimer = setTimeout(() => atualizar().catch(e => toast(e.message, true)), 100);};
  document.addEventListener('perfil:alterado', refresh);
  document.addEventListener('perfil:pronto', async e => {
    candidato = e.detail;
    try {
      const catalogo = await api('/idiomas');
      $('#idiomaCatalogo').innerHTML = '<option value="">Selecione um idioma</option>' + catalogo.map(i => `<option value="${esc(i.ID_Idiomas)}">${esc(i.Nome)}</option>`).join('');
      await atualizar();
    } catch(error) {toast(error.message, true);}
  });
  $('#formFoto').addEventListener('submit', async e => {
    e.preventDefault();
    const file = $('#fotoArquivo').files[0];
    if (!file || file.size > 5*1024*1024 || !['image/jpeg','image/png','image/webp'].includes(file.type)) {toast('Use JPG, PNG ou WebP de até 5 MB.', true); return;}
    const form = new FormData(); form.append('arquivo',file);
    try {await api('/uploads/foto-perfil',{method:'POST',body:form}); await atualizar(); toast('Foto atualizada.');} catch(error) {toast(error.message,true);}
  });
  $('#formItemProfissional').addEventListener('submit', async e => {
    e.preventDefault();
    if ($('#itemInicio').value && $('#itemFim').value && $('#itemInicio').value > $('#itemFim').value) {toast('Revise as datas do item.',true); return;}
    const id = $('#itemId').value;
    const payload = {tipo:$('#itemTipo').value,titulo:$('#itemTitulo').value.trim(),instituicao:$('#itemInstituicao').value.trim() || null,descricao:$('#itemDescricao').value.trim() || null,url:$('#itemUrl').value.trim() || null,data_inicio:$('#itemInicio').value || null,data_fim:$('#itemFim').value || null};
    try {await api(id ? `/itens-profissionais/${id}` : `/candidatos/${candidato}/itens`,{method:id ? 'PUT':'POST',body:JSON.stringify(payload)}); $('#formItemProfissional').reset(); $('#itemId').value = ''; await atualizar(); toast('Item salvo.');} catch(error) {toast(error.message,true);}
  });
  $('#cancelarItem').addEventListener('click', () => {$('#formItemProfissional').reset(); $('#itemId').value='';});
  $('#listaItensProfissionais').addEventListener('click', async e => {
    const id = e.target.dataset.editarItem || e.target.dataset.removerItem; if (!id) return;
    try {
      if (e.target.dataset.removerItem) {await api(`/itens-profissionais/${id}`,{method:'DELETE'}); await atualizar();}
      else {
        const i = itens.find(v => v.ID_Item === id); $('#itemId').value = id;
        for (const [idCampo,key] of Object.entries({itemTipo:'Tipo',itemTitulo:'Titulo',itemInstituicao:'Instituicao',itemDescricao:'Descricao',itemUrl:'Url',itemInicio:'DataInicio',itemFim:'DataFim'})) $('#'+idCampo).value = i[key] || '';
        $('#itemTitulo').focus();
      }
    } catch(error) {toast(error.message,true);}
  });
  let idiomaEditado;
  $('#formIdioma').addEventListener('submit', async e => {
    e.preventDefault();
    try {await api(`/candidatos/${candidato}/idiomas${idiomaEditado ? '/'+idiomaEditado : ''}`,{method:idiomaEditado ? 'PUT':'POST',body:JSON.stringify({id_idioma:$('#idiomaCatalogo').value,nivel:$('#idiomaNivel').value})}); idiomaEditado=null; await atualizar(); toast('Idioma salvo.');} catch(error) {toast(error.message,true);}
  });
  $('#listaIdiomasProfissionais').addEventListener('click', async e => {
    try {
      if (e.target.dataset.removerIdioma) {await api(`/candidatos/${candidato}/idiomas/${e.target.dataset.removerIdioma}`,{method:'DELETE'}); await atualizar();}
      if (e.target.dataset.editarIdioma) {idiomaEditado=e.target.dataset.editarIdioma; const i=idiomas.find(i => i.ID_Candidato_Idiomas===idiomaEditado); $('#idiomaCatalogo').value=i.ID_Idiomas; $('#idiomaNivel').value=i.Nivel || 'basico'; $('#idiomaCatalogo').focus();}
    } catch(error) {toast(error.message,true);}
  });
  $('#gerarCurriculoTalentix').addEventListener('click', async e => {
    e.target.disabled = true;
    try {await api(`/candidatos/${candidato}/curriculo-talentix`,{method:'POST'}); document.dispatchEvent(new Event('curriculos:atualizar')); toast('PDF Talentix gerado. Abra a prévia ou baixe a nova versão.');} catch(error) {toast(error.message,true);} finally {e.target.disabled=false;}
  });
});
