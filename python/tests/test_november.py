"""Atualizações 4–6: persistência, completude, consentimento e isolamento HTTP."""
import asyncio
import json
from io import BytesIO
from pathlib import Path
from PIL import Image
from pypdf import PdfReader
import pytest
from app.core.config import settings
from app.core.resume_parser import analisar_curriculo
from app.routers.curriculo import _processar_importacao


def png():
    out = BytesIO(); Image.new("RGB", (16, 16), "blue").save(out, "PNG")
    return out.getvalue()


def test_perfil_campos_completude_e_idor(ambiente, autenticar):
    c, conn = ambiente; autenticar(c,"uc1","candidato")
    before = c.get('/candidatos/c1/profissional').json()
    assert before['completude'] == 2
    data = {"titulo_profissional":"Python", "resumo":"Apresentação", "cidade":"Contagem","estado":"mg",
            "modalidades":["remoto"],"tipos_contrato":["CLT"],"preferencias":"Tecnologia",
            "habilidades_comportamentais":["Comunicação"], "github_url":"https://github.com/example", "pretensao_salarial":3000}
    assert c.put('/candidatos/c1',json=data).status_code == 200
    after = c.get('/candidatos/c1/profissional').json()
    assert after['completude'] == 52
    assert after['perfil']['Modalidades'] == ['remoto'] and after['perfil']['Estado'] == 'MG'
    assert all(x['campo']!='GitHub' for x in after['faltantes'])
    assert json.loads(conn.execute("SELECT TiposContrato FROM Candidatos WHERE ID_Candidatos='c1'").fetchone()[0]) == ['CLT']
    for bad in ({"github_url":"javascript:alert(1)"},{"modalidades":["qualquer"]},{"estado":"XX"},{"pretensao_salarial":-1},{"resumo":"x"*5001}):
        assert c.put('/candidatos/c1',json=bad).status_code == 422
    assert c.put('/candidatos/c2',json=data).status_code == 403
    assert c.get('/candidatos/c2/profissional').status_code == 403
    autenticar(c,"ue1","empresa"); assert c.get('/candidatos/c1/profissional').status_code == 200
    assert c.get('/candidatos/c2/profissional').status_code == 403


@pytest.mark.parametrize('tipo',['projeto','curso'])
def test_itens_edicao_e_permissoes(ambiente, autenticar, tipo):
    c,_=ambiente;autenticar(c,'uc1','candidato')
    payload={"tipo":tipo,"titulo":"Primeiro","url":"https://example.com"}
    r=c.post('/candidatos/c1/itens',json=payload);assert r.status_code==201
    ident=r.json()['ID_Item']
    assert c.put('/itens-profissionais/'+ident,json={**payload,'titulo':'Atualizado'}).status_code==200
    assert c.get('/candidatos/c1/profissional').json()['itens'][0]['Titulo']=='Atualizado'
    assert c.post('/candidatos/c1/itens',json={**payload,'url':'file:///etc/passwd'}).status_code==422
    assert c.post('/candidatos/c1/itens',json={**payload,'data_inicio':'2026-10-01','data_fim':'2025-01-01'}).status_code==422
    autenticar(c,'uc2','candidato')
    assert c.put('/itens-profissionais/'+ident,json=payload).status_code==403
    assert c.delete('/itens-profissionais/'+ident).status_code==403
    autenticar(c,'uc1','candidato');assert c.delete('/itens-profissionais/'+ident).status_code==200


def test_foto_decodificada_privada_e_limites(ambiente,autenticar):
    c,_=ambiente;autenticar(c,'uc1','candidato')
    raw=png()+b'<script>payload</script>'
    r=c.post('/uploads/foto-perfil',files={'arquivo':('foto.png',raw,'image/png')});assert r.status_code==200
    url=r.json()['url'];result=c.get(url);assert result.status_code==200 and b'<script>' not in result.content
    assert 'no-store' in result.headers['cache-control']
    autenticar(c,'uc2','candidato');assert c.get(url).status_code==404
    autenticar(c,'ue1','empresa');assert c.get(url).status_code==200
    autenticar(c,'ue2','empresa');assert c.get(url).status_code==404
    c.cookies.clear();assert c.get(url).status_code==401
    autenticar(c,'uc1','candidato')
    assert c.post('/uploads/foto-perfil',files={'arquivo':('foto.png',b'\x89PNG\r\n\x1a\nfalso','image/png')}).status_code==400
    assert c.post('/uploads/foto-perfil',files={'arquivo':('foto.svg',b'<svg/>','image/svg+xml')}).status_code==400
    assert c.post('/uploads/foto-perfil',files={'arquivo':('foto.png',b'x'*(5*1024*1024+1),'image/png')}).status_code==413


def test_upload_fila_versoes_principal_geracao(ambiente,autenticar):
    c,conn=ambiente;autenticar(c,'uc1','candidato')
    c.put('/candidatos/c1',json={'titulo_profissional':'Analista','resumo':'Texto oficial'})
    generated=c.post('/candidatos/c1/curriculo-talentix');assert generated.status_code==201
    cv=generated.json();assert cv['Versao']==2 and cv['Origem']=='talentix'
    raw=c.get(cv['ArquivoUrl']).content;assert 'Texto oficial' in PdfReader(BytesIO(raw)).pages[0].extract_text()
    uploaded=c.post('/candidatos/c1/curriculos',data={'titulo':'Segunda versão'},files={'arquivo':('cv.pdf',raw,'application/pdf')})
    assert uploaded.status_code==201 and uploaded.json()['importacao']['ID_Status_Processamento_IA']==1
    assert c.get('/candidatos/c1').json()['Resumo']=='Texto oficial'
    assert c.get(cv['ArquivoUrl']+'?preview=true').headers['content-disposition'].startswith('inline;')
    assert c.put('/curriculos/'+cv['ID_Curriculos'],json={'titulo':'Principal','principal':True}).status_code==200
    assert sum(r['Principal'] for r in c.get('/candidatos/c1/curriculos').json())==1
    assert c.post('/curriculos/'+cv['ID_Curriculos']+'/importacao/aplicar',json={}).status_code==409
    autenticar(c,'uc2','candidato')
    assert c.put('/curriculos/'+cv['ID_Curriculos'],json={'titulo':'IDOR'}).status_code==403
    assert c.get(cv['ArquivoUrl']).status_code==404
    assert c.post('/candidatos/c1/curriculo-talentix').status_code==403


def test_historico_arquivado_preserva_candidatura_e_escolhe_principal(ambiente, autenticar):
    c, conn = ambiente
    autenticar(c, 'uc1', 'candidato')
    cv = c.post('/candidatos/c1/curriculo-talentix').json()
    assert c.put('/curriculos/cr1', json={'titulo':' Versão enviada ', 'principal':True}).status_code == 200
    assert c.put('/curriculos/cr1', json={'titulo':'   '}).status_code == 422
    original = conn.execute("SELECT CurriculoUrl FROM Candidaturas WHERE ID_Candidaturas='ca1'").fetchone()[0]
    assert c.delete('/curriculos/cr1').status_code == 200
    active = c.get('/candidatos/c1/curriculos').json()
    assert [r['ID_Curriculos'] for r in active if r['Principal']] == [cv['ID_Curriculos']]
    history = c.get('/candidatos/c1/curriculos/historico').json()
    old = next(r for r in history if r['ID_Curriculos'] == 'cr1')
    assert old['Titulo'] == 'Versão enviada' and not old['Ativo'] and not old['Principal']
    assert old['CandidaturasEnviadas'] == 1
    assert conn.execute("SELECT CurriculoUrl FROM Candidaturas WHERE ID_Candidaturas='ca1'").fetchone()[0] == original
    assert c.get(original).status_code == 200
    assert c.post('/candidaturas',json={'id_vaga':'v2','curriculo_url':original}).status_code == 403
    autenticar(c,'ue1','empresa')
    assert c.get(original).status_code == 200
    assert c.get('/candidatos/c1/curriculos/historico').status_code == 403
    autenticar(c,'ue2','empresa')
    assert c.get(original).status_code == 404
    autenticar(c,'uc2','candidato')
    assert c.get('/candidatos/c1/curriculos/historico').status_code == 403
    assert c.get(original).status_code == 404


def test_primeira_versao_automaticamente_principal(ambiente, autenticar):
    c, conn = ambiente
    autenticar(c,'uc1','candidato')
    conn.execute("UPDATE Curriculos SET Principal=0 WHERE ID_Candidatos='c1'")
    conn.commit()
    r = c.post('/candidatos/c1/curriculo-talentix')
    assert r.status_code == 201 and r.json()['Principal']


def test_confirmacao_seletiva_e_dados_separados(ambiente,autenticar):
    c,conn=ambiente;autenticar(c,'uc1','candidato')
    dados={'perfil':{'titulo_profissional':'Título aprovado','resumo':'Não aprovado'},'experiencias':[],'formacoes':[],'habilidades':[],'idiomas':[]}
    conn.execute("INSERT INTO Curriculo_Importacoes(ID_Curriculo_Importacoes,ID_Curriculos,ID_Status_Processamento_IA,DadosExtraidos,TextoExtraido) VALUES ('imp','cr1',3,?,?)",(json.dumps(dados),'original'));conn.commit()
    assert c.get('/candidatos/c1').json()['TituloProfissional'] is None
    assert c.post('/curriculos/cr1/importacao/aplicar',json={'selecionados':{'perfil':['titulo_profissional']}}).status_code==200
    p=c.get('/candidatos/c1').json();assert p['TituloProfissional']=='Título aprovado' and p['Resumo'] is None
    imp=c.get('/curriculos/cr1/importacao').json()
    assert imp['DadosExtraidos']=={**dados, 'versao':3, 'certificados':[], 'projetos':[]} and imp['TextoExtraido']=='original' and imp['DadosConfirmados']
    assert json.loads(conn.execute("SELECT DadosExtraidos FROM Curriculo_Importacoes WHERE ID_Curriculos='cr1'").fetchone()[0]) == dados
    autenticar(c,'uc2','candidato');assert c.post('/curriculos/cr1/importacao/aplicar',json={}).status_code==403


@pytest.mark.parametrize('indices', [[0, 1], [1]])
def test_importacao_grupos_e_itens_confirmados_juntos(ambiente, autenticar, indices):
    c, conn = ambiente
    autenticar(c, 'uc1', 'candidato')
    dados = {
        'perfil': {'titulo_profissional': 'Título aprovado', 'resumo': 'Não aprovado'},
        'experiencias': [
            {'empresa': 'Empresa A', 'cargo': 'Assistente', 'data_inicio': '2025-01-01'},
            {'empresa': 'Empresa B', 'cargo': 'Analista', 'data_inicio': '2026-01-01'},
        ],
        'formacoes': [
            {'instituicao': 'Escola A', 'curso': 'Sistemas', 'data_inicio': '2027-01-01', 'data_conclusao': '2025-01-01'},
            {'instituicao': 'Escola B', 'curso': 'Testes'},
        ],
        'habilidades': [{'nome': 'Python'}, {'nome': 'SQL'}],
        'idiomas': [{'idioma': 'Inglês', 'nivel': 'fluente'}, {'idioma': 'Espanhol', 'nivel': 'basico'}],
    }
    conn.execute("INSERT INTO Curriculo_Importacoes(ID_Curriculo_Importacoes,ID_Curriculos,ID_Status_Processamento_IA,DadosExtraidos) VALUES ('imp','cr1',3,?)", (json.dumps(dados),))
    conn.commit()
    selecionados = {secao: indices for secao in ('experiencias', 'formacoes', 'habilidades', 'idiomas')}
    selecionados['perfil'] = ['titulo_profissional']
    payload = {**{'importar_' + secao: True for secao in selecionados}, 'selecionados': selecionados}
    resposta = c.post('/curriculos/cr1/importacao/aplicar', json=payload)
    assert resposta.status_code == 200, resposta.text
    assert resposta.json()['importados'] == {'perfil': 1, **{secao: len(indices) for secao in selecionados if secao != 'perfil'}}
    perfil = c.get('/candidatos/c1').json()
    assert perfil['TituloProfissional'] == 'Título aprovado' and perfil['Resumo'] is None
    experiencias = c.get('/candidatos/c1/experiencias').json()
    assert {e['Empresa'] for e in experiencias} == {dados['experiencias'][i]['empresa'] for i in indices}
    formacoes = c.get('/candidatos/c1/formacoes').json()
    assert {f['Curso'] for f in formacoes} == {dados['formacoes'][i]['curso'] for i in indices}
    if 0 in indices:
        primeira = next(f for f in formacoes if f['Curso'] == 'Sistemas')
        assert primeira['DataInicio'] == '2025-01-01' and primeira['DataConclusao'] == '2027-01-01'
    habilidades = c.get('/candidatos/c1/habilidades').json()
    assert {h['NomeHabilidade'] for h in habilidades} == {dados['habilidades'][i]['nome'] for i in indices}
    idiomas = c.get('/candidatos/c1/idiomas').json()
    assert {i['NomeIdioma'] for i in idiomas} == {dados['idiomas'][i]['idioma'] for i in indices}
    # Repetir a confirmação não duplica as coleções, nem altera a extração original.
    repetida = c.post('/curriculos/cr1/importacao/aplicar', json=payload)
    assert repetida.status_code == 200
    assert repetida.json()['importados'] == dict.fromkeys(selecionados, 0)
    assert c.get('/curriculos/cr1/importacao').json()['DadosExtraidos'] == {**dados, 'versao':3, 'certificados':[], 'projetos':[]}
    assert json.loads(conn.execute("SELECT DadosExtraidos FROM Curriculo_Importacoes WHERE ID_Curriculos='cr1'").fetchone()[0]) == dados
    assert conn.execute("SELECT COUNT(*) FROM Experiencias WHERE ID_Candidatos='c2'").fetchone()[0] == 0


@pytest.mark.parametrize('legado', [False, True])
def test_importa_certificados_e_projetos_em_destinos_independentes(ambiente, autenticar, legado):
    from app.core.resume_parser import analisar_curriculo
    c, conn = ambiente
    autenticar(c, 'uc1', 'candidato')
    texto = '''Maria Silva
Desenvolvedora Web
Formação acadêmica
Técnico em Sistemas | SENAC Minas | 2025 - 2027
Certificados
Python Avançado | IFMG | 2026
Java Básico | IFRS | 2024
Projetos
Talentix — Plataforma de empregos
Desenvolvida durante o curso no SENAC.
https://github.com/exemplo/talentix
Biblioteca — Gestão de empréstimos
'''
    dados = analisar_curriculo(texto)
    if legado:
        # A extração antiga incluía projetos no último grupo reconhecido.
        dados.update(versao=1, formacoes=dados['formacoes'] + dados.pop('certificados') + [
            {'instituicao':'SENAC', 'curso':'Projeto indevidamente classificado', 'nivel':'Certificado'}])
        dados.pop('projetos')
    conn.execute("INSERT INTO Curriculo_Importacoes(ID_Curriculo_Importacoes,ID_Curriculos,ID_Status_Processamento_IA,DadosExtraidos,TextoExtraido) VALUES ('imp','cr1',3,?,?)", (json.dumps(dados), texto))
    conn.commit()
    previa = c.get('/curriculos/cr1/importacao').json()['DadosExtraidos']
    assert len(previa['formacoes']) == 1 and len(previa['certificados']) == 2 and len(previa['projetos']) == 2
    assert c.post('/curriculos/cr1/analisar').json()['DadosExtraidos'] == previa
    assert not c.get('/candidatos/c1/formacoes').json()
    assert not c.get('/candidatos/c1/profissional').json()['itens']
    # Confirmar só o certificado de índice 1 não importa formação nem projeto.
    payload = {'versao_revisao':2, 'importar_certificados':True, 'selecionados':{'certificados':[1]}}
    resposta = c.post('/curriculos/cr1/importacao/aplicar', json=payload)
    assert resposta.status_code == 200, resposta.text
    assert resposta.json()['importados']['certificados'] == 1
    assert sum(resposta.json()['importados'].values()) == 1
    formacoes = c.get('/candidatos/c1/formacoes').json()
    assert [(f['Curso'], f['Nivel']) for f in formacoes] == [('Java Básico', 'Certificado')]
    assert not c.get('/candidatos/c1/profissional').json()['itens']
    payload = {'versao_revisao':2, 'importar_certificados':True, 'importar_projetos':True,
               'selecionados':{'formacoes':[0], 'certificados':[0,1], 'projetos':[0]}}
    resposta = c.post('/curriculos/cr1/importacao/aplicar', json=payload)
    assert resposta.status_code == 200, resposta.text
    assert {k:v for k,v in resposta.json()['importados'].items() if v} == {'formacoes':1, 'certificados':1, 'projetos':1}
    profissional = c.get('/candidatos/c1/profissional').json()
    assert len([f for f in profissional['formacoes'] if f['Nivel'] == 'Certificado']) == 2
    assert len([f for f in profissional['formacoes'] if f['Nivel'] != 'Certificado']) == 1
    assert [(i['Tipo'], i['Titulo']) for i in profissional['itens']] == [('projeto', 'Talentix')]
    assert profissional['itens'][0]['Url'] == 'https://github.com/exemplo/talentix'
    assert not any(f['campo'] in ('Projeto','Certificado','Formação acadêmica') for f in profissional['faltantes'])
    assert sum(c.post('/curriculos/cr1/importacao/aplicar', json=payload).json()['importados'].values()) == 0
    assert json.loads(conn.execute("SELECT DadosExtraidos FROM Curriculo_Importacoes WHERE ID_Curriculos='cr1'").fetchone()[0]) == dados
    audit = json.loads(conn.execute("SELECT DadosConfirmados FROM Curriculo_Importacoes WHERE ID_Curriculos='cr1'").fetchone()[0])
    assert audit['selecionados']['projetos'] == [previa['projetos'][0]]
    autenticar(c, 'uc2', 'candidato')
    assert c.post('/curriculos/cr1/importacao/aplicar', json=payload).status_code == 403
    assert not c.get('/candidatos/c2/profissional').json()['itens']


def test_importacao_projeto_invalido_nao_persiste_parcialmente(ambiente, autenticar):
    c, conn = ambiente
    autenticar(c, 'uc1', 'candidato')
    dados = {'versao':2, 'certificados':[{'curso':'Python','instituicao':'IFMG'}],
             'projetos':[{'titulo':'Link inválido','url':'javascript:alert(1)'}]}
    conn.execute("INSERT INTO Curriculo_Importacoes(ID_Curriculo_Importacoes,ID_Curriculos,ID_Status_Processamento_IA,DadosExtraidos) VALUES ('imp','cr1',3,?)", (json.dumps(dados),))
    conn.commit()
    payload = {'versao_revisao':2, 'importar_certificados':True, 'importar_projetos':True,
               'selecionados':{'certificados':[0], 'projetos':[0]}}
    resposta = c.post('/curriculos/cr1/importacao/aplicar', json=payload)
    assert resposta.status_code == 422 and 'Link inválido' in resposta.json()['detail']
    assert not c.get('/candidatos/c1/formacoes').json()
    assert not c.get('/candidatos/c1/profissional').json()['itens']
    payload['selecionados']['projetos'] = []
    assert c.post('/curriculos/cr1/importacao/aplicar', json=payload).json()['importados']['certificados'] == 1


@pytest.mark.parametrize('versao_antiga', [None, 1, 2, 3])
def test_revisao_com_todas_categorias_marcadas(ambiente, autenticar, versao_antiga):
    c, conn = ambiente
    autenticar(c, 'uc1', 'candidato')
    texto = (Path(__file__).parent / 'fixtures/resume_review_sections.txt').read_text()
    dados = analisar_curriculo(texto)
    if versao_antiga != 3:
        dados['versao'] = versao_antiga
        dados['formacoes'] += dados.pop('certificados')
        dados['formacoes'].extend({'curso':p['titulo'],'instituicao':p['descricao'],'nivel':'Certificado'} for p in dados.pop('projetos'))
        dados['formacoes'][0].update(data_inicio='2027-01-01', data_conclusao='2025-01-01')
    conn.execute("INSERT INTO Curriculo_Importacoes(ID_Curriculo_Importacoes,ID_Curriculos,ID_Status_Processamento_IA,DadosExtraidos,TextoExtraido) VALUES ('imp','cr1',3,?,?)", (json.dumps(dados), texto))
    conn.commit()
    previa = c.get('/curriculos/cr1/importacao').json()['DadosExtraidos']
    assert previa['versao'] == 3
    assert [len(previa[s]) for s in ('formacoes','certificados','projetos')] == [2,2,4]
    secoes = ('perfil','experiencias','formacoes','certificados','projetos','habilidades','idiomas')
    payload = {'versao_revisao':2, **{'importar_'+s:True for s in secoes}, 'selecionados':{
        s:([k for k,v in previa[s].items() if v is not None] if s == 'perfil' else list(range(len(previa[s])))) for s in secoes}}
    resposta = c.post('/curriculos/cr1/importacao/aplicar', json=payload)
    assert resposta.status_code == 200, resposta.text
    assert all(resposta.json()['importados'][s] > 0 for s in secoes)
    oficial = c.get('/candidatos/c1/profissional').json()
    assert len(oficial['formacoes']) == 4 and len(oficial['itens']) == 4
    assert sum(f['Nivel']=='Certificado' for f in oficial['formacoes']) == 2
    assert all(f['Curso'] not in ('Talentix','LUMORA','AcademiaFit','ChurrasPlan') for f in oficial['formacoes'])
    assert sum(c.post('/curriculos/cr1/importacao/aplicar',json=payload).json()['importados'].values()) == 0
    assert json.loads(conn.execute("SELECT DadosExtraidos FROM Curriculo_Importacoes WHERE ID_Curriculos='cr1'").fetchone()[0]) == dados


@pytest.mark.parametrize('selecao,codigo,mensagem', [
    ({'grupo_desconhecido':[0]},422,'categoria desconhecida'),
    ({'formacoes':list(range(51))},422,'até 50 itens'),
    ({'formacoes':['0']},422,'referência inválida'),
    ({'formacoes':[-1]},422,'referência inválida'),
    ({'formacoes':[50]},409,'itens desta revisão mudaram'),
])
def test_erro_de_selecao_identifica_a_causa_sem_alterar_perfil(ambiente, autenticar, selecao, codigo, mensagem):
    c, conn = ambiente
    autenticar(c, 'uc1', 'candidato')
    dados = {'versao':3, 'formacoes':[{'curso':'Sistemas','instituicao':'SENAC'}]}
    conn.execute("INSERT INTO Curriculo_Importacoes(ID_Curriculo_Importacoes,ID_Curriculos,ID_Status_Processamento_IA,DadosExtraidos) VALUES ('imp','cr1',3,?)", (json.dumps(dados),))
    conn.commit()
    resposta = c.post('/curriculos/cr1/importacao/aplicar', json={'versao_revisao':2,'selecionados':selecao})
    assert resposta.status_code == codigo and mensagem in resposta.text
    assert not c.get('/candidatos/c1/formacoes').json()


def test_erro_parser_compreensivel(ambiente):
    _,conn=ambiente
    conn.execute("INSERT INTO Curriculo_Importacoes(ID_Curriculo_Importacoes,ID_Curriculos,ID_Status_Processamento_IA,ProcessamentoIniciadoEm) VALUES ('imp','cr1',2,'2026-10-01')");conn.commit()
    result=asyncio.run(_processar_importacao({'ID_Curriculos':'cr1','ArquivoUrl':'/uploads/curriculos/'+'a'*64+'.pdf','ProcessamentoIniciadoEm':'2026-10-01'}))
    assert result['ID_Status_Processamento_IA']==4
    assert 'Não foi possível ler' in result['ErroProcessamento'] and settings.UPLOAD_DIR not in result['ErroProcessamento']


def test_parser_contato():
    d=analisar_curriculo('Maria Silva\nAnalista Python\nmaria@example.com\n(31) 99999-1234\nIdiomas\nInglês fluente')
    assert d['contato']=={'nome':'Maria Silva','email':'maria@example.com','telefone':'(31) 99999-1234'}


def test_busca_combinada_paginacao_injection_e_privacidade(ambiente,autenticar):
    c,conn=ambiente
    conn.execute("UPDATE Vagas SET Descricao='Python SQL',Localizacao='Contagem',Modalidade='Remoto',Nivel='Júnior',TipoContrato='CLT',SalarioMin=2500,SalarioMax=3500,AreaProfissional='TI' WHERE ID_Vagas='v1'")
    conn.execute("INSERT INTO Vaga_Habilidades(ID_Vaga_Habilidades,ID_Vagas,ID_Habilidades,NivelMinimo) VALUES ('vh1','v1','h',1)");conn.commit()
    r=c.get('/vagas/busca',params={'cargo':'Vaga','palavra_chave':'Python','localizacao':'Contagem','modalidade':'remoto','nivel':'Júnior','tipo_contrato':'CLT','salario_min':3000,'empresa':'Empresa 1','area':'TI','habilidades':'Python','por_pagina':1})
    assert r.status_code==200 and r.json()['total']==1
    assert r.json()['resultados'][0]['habilidades'][0]['Nome']=='Python'
    assert 'ID_Usuarios' not in r.json()['resultados'][0]
    assert c.get('/vagas/busca',params={'cargo':"' OR 1=1 --"}).json()['total']==0
    assert c.get('/vagas/busca',params={'por_pagina':1,'pagina':2}).json()['pagina']==2
    assert c.get('/vagas/busca',params={'ordenar':'SalarioMin;DROP TABLE Usuarios'}).status_code==422
    assert c.get('/vagas/busca',params={'salario_min':4000,'salario_max':1000}).status_code==422
    assert c.get('/vagas/busca',params={'por_pagina':51}).status_code==422
    assert c.get('/vagas/autocomplete',params={'q':'Va','limite':1}).json()==[{'Titulo':'Vaga 1'}]
    conn.execute("UPDATE Vagas SET SalarioConfidencial=1 WHERE ID_Vagas='v1'");conn.commit()
    assert c.get('/vagas/busca',params={'cargo':'Vaga 1'}).json()['resultados'][0]['SalarioMax'] is None
    assert c.get('/vagas/busca',params={'salario_min':1}).json()['total']==0
    conn.execute("UPDATE Vagas SET ID_Status_Vaga=4 WHERE ID_Vagas='v1'");conn.commit()
    assert c.get('/vagas/busca').json()['total']==1
    assert c.get('/vagas/autocomplete',params={'q':'Vaga 1'}).json()==[]


def test_buscas_historico_vinculados_sessao(ambiente,autenticar):
    c,_=ambiente;autenticar(c,'uc1','candidato')
    payload={'nome':'Python remoto','filtros':{'cargo':'Python','modalidade':'remoto'},'ativa':True}
    r=c.post('/buscas',json=payload);assert r.status_code==201;ident=r.json()['ID_Busca']
    assert c.get('/buscas').json()[0]['Filtros']['cargo']=='Python'
    assert c.post('/buscas-historico',json=payload['filtros']).status_code==201
    assert len(c.get('/buscas-historico').json())==1
    assert c.put('/buscas/'+ident,json={**payload,'ativa':False}).status_code==200
    autenticar(c,'uc2','candidato');assert c.get('/buscas').json()==[] and c.get('/buscas-historico').json()==[]
    assert c.put('/buscas/'+ident,json=payload).status_code==404
    c.delete('/buscas/'+ident)
    autenticar(c,'uc1','candidato');assert len(c.get('/buscas').json())==1
    assert c.delete('/buscas/'+ident).status_code==200
    autenticar(c,'ue1','empresa');assert c.post('/buscas',json=payload).status_code==403


def test_alertas_ativos_sem_repeticao(ambiente,autenticar):
    from app.worker_profissional import processar_alertas
    c,conn=ambiente;autenticar(c,'uc1','candidato')
    saved=c.post('/buscas',json={'nome':'Vaga','filtros':{'cargo':'Vaga'},'ativa':True}).json()['ID_Busca']
    conn.execute("UPDATE Vagas SET PublicadaEm='2099-01-01'");conn.commit()
    asyncio.run(processar_alertas());conn.commit()
    assert conn.execute('SELECT COUNT(*) FROM Alertas_Busca').fetchone()[0]==2
    asyncio.run(processar_alertas());conn.commit()
    assert conn.execute('SELECT COUNT(*) FROM Alertas_Busca').fetchone()[0]==2
    c.put('/buscas/'+saved,json={'nome':'Vaga','filtros':{'cargo':'Vaga'},'ativa':False})
    conn.execute("DELETE FROM Alertas_Busca");conn.commit()
    asyncio.run(processar_alertas());conn.commit()
    assert conn.execute('SELECT COUNT(*) FROM Alertas_Busca').fetchone()[0]==0
