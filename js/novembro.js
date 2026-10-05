/* Prévia e versões usam exclusivamente dados salvos e a sessão autenticada. */
document.addEventListener('DOMContentLoaded', () => {
  const {$, esc, safeUrl, api, toast} = Talentix;
  let candidato = null, principalEditado = false;
  const data = value => value ? String(value).slice(0, 10).split('-').reverse().join('/') : 'Não informado';
  const contratos = {estagio:'Estágio',temporario:'Temporário',aprendiz:'Aprendiz',freelancer:'Freelancer',CLT:'CLT',PJ:'PJ'};
  const modalidades = {presencial:'Presencial',hibrido:'Híbrida',remoto:'Remota'};
  const nomes = values => (values || []).filter(Boolean).map(esc).join(' · ');
  const section = (title, contents) => `<section class="card"><h3>${esc(title)}</h3>${contents || '<p class="muted">Não informado.</p>'}</section>`;
  const registro = (title, subtitle, description) => `<article><h4>${esc(title)}</h4><p>${esc(subtitle)}</p>${description ? `<p>${esc(description).replace(/\n/g,'<br>')}</p>` : ''}</article>`;
  document.addEventListener('perfil:pronto', e => {candidato = e.detail;});
  document.querySelectorAll('[data-fechar-novembro]').forEach(button => button.addEventListener('click', () => $('#'+button.dataset.fecharNovembro).close()));

  $('#visualizarPerfil').addEventListener('click', async e => {
    if (!candidato) return;
    e.currentTarget.disabled = true;
    try {
      const d = await api(`/candidatos/${candidato}/profissional`), p = d.perfil;
      const links = [['LinkedIn',p.LinkedinUrl],['GitHub',p.GithubUrl],['Portfólio',p.PortfolioUrl]].filter(([,url])=>url).map(([nome,url])=>`<a href="${esc(safeUrl(url))}" target="_blank" rel="noopener noreferrer">${nome}</a>`).join(' · ');
      $('#previaPerfilSalvo').innerHTML =
        section(p.Nome, `${p.FotoUrl ? `<img src="${esc(safeUrl(p.FotoUrl))}" width="96" height="96" alt="Foto de ${esc(p.Nome)}">` : ''}<p><strong>${esc(p.TituloProfissional || 'Título profissional não informado')}</strong></p><p>${nomes([p.Cidade,p.Estado]) || 'Localização não informada'}</p>${p.Resumo ? `<p>${esc(p.Resumo).replace(/\n/g,'<br>')}</p>` : ''}<p>Completude: ${Number(d.completude)}%</p>${links ? `<p>${links}</p>` : ''}`) +
        section('Preferências profissionais', `<p>${p.Disponivel == null ? 'Disponibilidade não informada' : p.Disponivel ? 'Disponível para oportunidades' : 'Sem disponibilidade no momento'}</p><p>Modalidades: ${nomes(p.Modalidades.map(m=>modalidades[m] || m)) || 'Não informado'}</p><p>Contratos: ${nomes(p.TiposContrato.map(c=>contratos[c] || c)) || 'Não informado'}</p><p>Pretensão salarial: ${p.PretensaoSalarial == null ? 'Não informada' : Number(p.PretensaoSalarial).toLocaleString('pt-BR',{style:'currency',currency:'BRL'})}</p>${p.Preferencias ? `<p>${esc(p.Preferencias)}</p>` : ''}`) +
        section('Experiências profissionais', d.experiencias.map(i=>registro(i.Cargo,`${i.Empresa} · ${data(i.DataInicio)} a ${i.Atual ? 'atualmente' : data(i.DataFim)}`,i.Descricao)).join('')) +
        section('Formação acadêmica', d.formacoes.filter(i=>i.Nivel !== 'Certificado').map(i=>registro(i.Curso,[i.Instituicao,i.Nivel,i.Status].filter(Boolean).join(' · '),`Início: ${data(i.DataInicio)} · Conclusão: ${data(i.DataConclusao)}`)).join('')) +
        section('Certificados', d.formacoes.filter(i=>i.Nivel === 'Certificado').map(i=>registro(i.Curso,i.Instituicao,`Conclusão: ${data(i.DataConclusao)}`)).join('')) +
        ['projeto','curso'].map(tipo=>section(tipo === 'projeto' ? 'Projetos' : 'Cursos',d.itens.filter(i=>i.Tipo===tipo).map(i=>registro(i.Titulo,i.Instituicao || '',i.Descricao)+(i.Url ? `<p><a href="${esc(safeUrl(i.Url))}" target="_blank" rel="noopener noreferrer">Abrir ${tipo}</a></p>` : '')).join(''))).join('') +
        section('Habilidades técnicas', `<p>${nomes(d.habilidades.map(i=>i.Nome)) || 'Não informado'}</p>`) +
        section('Habilidades comportamentais', `<p>${nomes(p.HabilidadesComportamentais) || 'Não informado'}</p>`) +
        section('Idiomas',d.idiomas.map(i=>registro(i.Nome,i.Nivel || 'Nível não informado')).join(''));
      $('#modalPerfilSalvo').showModal();
    } catch(error) {toast(error.message,true);} finally {$('#visualizarPerfil').disabled = false;}
  });

  $('#verHistoricoCurriculos').addEventListener('click', async () => {
    if (!candidato) return;
    try {
      const rows = await api(`/candidatos/${candidato}/curriculos/historico`);
      $('#historicoCurriculos').innerHTML = rows.map(c => `<article class="list-item"><div class="list-item__main"><h3>${esc(c.Titulo)}</h3><p>Versão ${Number(c.Versao)} · ${c.Ativo ? 'Disponível' : 'Arquivada'}${c.Ativo && c.Principal ? ' · Principal' : ''}</p><p>${c.Origem === 'talentix' ? 'PDF do perfil Talentix' : 'Arquivo enviado'} · ${Number(c.CandidaturasEnviadas)} candidatura(s) com esta versão</p>${c.DeletadoEm ? `<p>Arquivada em ${data(c.DeletadoEm)}</p>` : ''}</div><div class="list-item__actions">${String(c.ArquivoUrl).endsWith('.pdf') ? `<a class="btn btn-secondary" href="${esc(safeUrl(c.ArquivoUrl))}?preview=true" target="_blank" rel="noopener">Prévia</a>` : ''}<a class="btn btn-secondary" href="${esc(safeUrl(c.ArquivoUrl))}" target="_blank" rel="noopener">Baixar</a></div></article>`).join('') || '<p class="empty-state">Nenhuma versão de currículo disponível.</p>';
      $('#modalHistoricoCurriculos').showModal();
    } catch(error) {toast(error.message,true);}
  });
  $('#listaCurriculos').addEventListener('click', e => {
    const b = e.target.closest('[data-nome-curriculo]');
    if (!b) return;
    $('#nomeCurriculoId').value = b.dataset.nomeCurriculo;
    $('#nomeCurriculoTexto').value = b.dataset.titulo;
    principalEditado = b.dataset.principal === '1';
    $('#nomeCurriculoErro').hidden = true;
    $('#modalNomeCurriculo').showModal();
  });
  $('#formNomeCurriculo').addEventListener('submit', async e => {
    e.preventDefault(); const b = e.submitter; b.disabled = true;
    try {
      await api(`/curriculos/${encodeURIComponent($('#nomeCurriculoId').value)}`,{method:'PUT',body:JSON.stringify({titulo:$('#nomeCurriculoTexto').value.trim(),principal:principalEditado})});
      $('#modalNomeCurriculo').close(); document.dispatchEvent(new Event('curriculos:atualizar')); toast('Nome atualizado. O documento e as candidaturas foram preservados.');
    } catch(error) {$('#nomeCurriculoErro').textContent=error.message; $('#nomeCurriculoErro').hidden=false;} finally {b.disabled=false;}
  });
});
