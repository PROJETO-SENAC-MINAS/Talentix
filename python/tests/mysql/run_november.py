"""Updates 4–6 no MySQL real e worker real. Nunca executar em banco de usuário."""
import json
import os
from pathlib import Path
from io import BytesIO
import subprocess
import sys
import uuid
import traceback
from concurrent.futures import ThreadPoolExecutor
import httpx
import pymysql
from PIL import Image
from pypdf import PdfReader
from reportlab.pdfgen import canvas

if os.getenv('TALENTIX_ISOLATED_TESTS') != '1' or not os.environ['DB_NAME'].startswith('talentix_test') or os.environ['DB_HOST'] not in ('127.0.0.1','localhost'):
    raise SystemExit('Somente MySQL isolado talentix_test é permitido.')
conn=pymysql.connect(host=os.environ['DB_HOST'],port=int(os.environ['DB_PORT']),user=os.environ['DB_USER'],password=os.environ['DB_PASSWORD'],database=os.environ['DB_NAME'],autocommit=True)
OUT=Path(os.environ['TEST_RESULTS_DIR']);OUT.mkdir(parents=True,exist_ok=True)
API=os.getenv('TEST_API_URL','http://127.0.0.1:8000')
nonce=uuid.uuid4().hex[:10]
cases=[];clients=[]

def check(name,ok):
    cases.append({'case':name,'passed':bool(ok)})
    if not ok: raise AssertionError(name)

def query(sql,args=()):
    with conn.cursor() as cur:
        cur.execute(sql,args)
        return cur.fetchall() if cur.description else cur.rowcount

class Client(httpx.Client):
    def request(self,method,url,**kwargs):
        if method.upper() in ('POST','PUT','PATCH','DELETE') and self.cookies.get('talentix_csrf'):
            kwargs['headers']={**(kwargs.get('headers') or {}),'X-CSRF-Token':self.cookies.get('talentix_csrf')}
        return super().request(method,url,**kwargs)

def account(role):
    c=Client(base_url=API,timeout=30,trust_env=False);clients.append(c)
    email=role+'-'+str(len(clients))+'-'+nonce+'@november.example.com'
    d={'nome':'Teste Novembro','email':email,'senha':'Novembro123!'}
    if role=='empresa':d.update(razao_social='Empresa Novembro',cnpj=str(int(uuid.uuid4().hex[:12],16)).zfill(14)[-14:])
    r=c.post('/auth/cadastro/'+role,json=d);check('Cadastro '+email,r.status_code==201)
    data=r.json();r=c.post('/auth/login',json={'email':email,'senha':d['senha']});check('Login '+email,r.status_code==200)
    return c,data

def worker():
    r=subprocess.run([sys.executable,'-m','app.worker_profissional','--once'],cwd=Path(__file__).resolve().parents[2],env=os.environ,capture_output=True,text=True,timeout=120)
    check('Worker profissional conclui sem falhas',r.returncode==0)

failure=None
try:
    c1,d1=account('candidato');c2,d2=account('candidato');e1,de1=account('empresa');e2,de2=account('empresa')
    p=d1['id_candidato'];p2=d2['id_candidato']
    initial=c1.get(f'/candidatos/{p}/profissional').json()['completude']
    fields={'titulo_profissional':'Python '+nonce,'resumo':'Meu perfil oficial','cidade':'Contagem','estado':'MG','pretensao_salarial':3000,
        'modalidades':['remoto'],'tipos_contrato':['CLT'],'habilidades_comportamentais':['Comunicação'],'preferencias':'Tecnologia',
        'github_url':'https://github.com/example','linkedin_url':'https://linkedin.com/in/example','portfolio_url':'https://example.com'}
    check('Persistir campos profissionais MySQL',c1.put(f'/candidatos/{p}',json=fields).status_code==200)
    check('Perfil IDOR bloqueado',c2.put(f'/candidatos/{p}',json=fields).status_code==403)
    check('Recrutamento não lê perfil sem candidatura',e1.get(f'/candidatos/{p}/profissional').status_code==403)
    for tipo in ('curso','projeto'):
        data={'tipo':tipo,'titulo':'Item '+tipo,'url':'https://example.com','data_inicio':'2025-01-01'}
        r=c1.post(f'/candidatos/{p}/itens',json=data);check('Criar '+tipo,r.status_code==201);item=r.json()['ID_Item']
        check('Editar '+tipo,c1.put('/itens-profissionais/'+item,json={**data,'titulo':'Atualizado '+tipo}).status_code==200)
        check('Item IDOR bloqueado',c2.delete('/itens-profissionais/'+item).status_code==403)
    for name,nivel in [('Ciência da computação','Graduação'),('Python profissional','Certificado')]:
        check('Formação/certificado',c1.post(f'/candidatos/{p}/formacoes',json={'instituicao':'Senac','curso':name,'nivel':nivel}).status_code==201)
    check('Experiência profissional',c1.post(f'/candidatos/{p}/experiencias',json={'empresa':'Senac','cargo':'Analista','data_inicio':'2025-01-01','atual':True}).status_code==201)
    skill=c1.post('/habilidades',json={'nome':'Python Novembro '+nonce}).json()['ID_Habilidades']
    check('Habilidade técnica',c1.post(f'/candidatos/{p}/habilidades',json={'id_habilidade':skill,'nivel':3}).status_code==201)
    language=c1.get('/idiomas').json()[0]['ID_Idiomas']
    li=c1.post(f'/candidatos/{p}/idiomas',json={'id_idioma':language,'nivel':'fluente'}).json()['ID_Candidato_Idiomas']
    check('Editar idioma',c1.put(f'/candidatos/{p}/idiomas/{li}',json={'id_idioma':language,'nivel':'avancado'}).status_code==200)
    check('Idioma IDOR bloqueado',c2.put(f'/candidatos/{p}/idiomas/{li}',json={'id_idioma':language}).status_code==403)
    image=BytesIO();Image.new('RGB',(40,40),'green').save(image,'PNG');raw=image.getvalue()
    photo=c1.post('/uploads/foto-perfil',files={'arquivo':('foto.png',raw+b'EXIF-secret','image/png')});check('Foto segura',photo.status_code==200)
    photo_url=photo.json()['url'];check('Foto privada',c2.get(photo_url).status_code==404)
    check('Foto metadados removidos',b'EXIF-secret' not in c1.get(photo_url).content)
    check('Completude real 100%',c1.get(f'/candidatos/{p}/profissional').json()['completude']==100)
    generated=c1.post(f'/candidatos/{p}/curriculo-talentix');check('Gerar PDF Talentix',generated.status_code==201)
    generated_id=generated.json()['ID_Curriculos'];url=generated.json()['ArquivoUrl']
    pdf=c1.get(url).content;check('PDF contém perfil oficial','Meu perfil oficial' in PdfReader(BytesIO(pdf)).pages[0].extract_text())
    check('Exportação é download',c1.get(url).headers['content-disposition'].startswith('attachment;'))
    check('Prévia é inline autenticado',c1.get(url+'?preview=true').headers['content-disposition'].startswith('inline;'))
    stream=BytesIO();doc=canvas.Canvas(stream);y=800
    for line in ['Maria Revisão','Desenvolvedora Python','maria@example.com','(31) 99999-1234','Resumo','Apresentação sugerida',
                 'Formação acadêmica','Técnico em Sistemas | SENAC Minas | 2025 - 2027',
                 'Certificados','Python Avançado | IFMG | 2026','Java Básico | IFRS | 2024',
                 'Projetos','Talentix Importado - Portal de empregos','Desenvolvido durante o curso no SENAC.',
                 'https://github.com/exemplo/talentix','Idiomas','Inglês fluente']:
        doc.drawString(50,y,line);y-=25
    doc.save();resume=stream.getvalue()
    r=c1.post(f'/candidatos/{p}/curriculos',data={'titulo':'Importação para revisar','principal':'true'},files={'arquivo':('cv.pdf',resume,'application/pdf')});check('Upload não espera parser',r.status_code==201 and r.json()['importacao']['ID_Status_Processamento_IA']==1)
    cv=r.json();ident=cv['ID_Curriculos'];check('Versão incremental',cv['Versao']==2)
    check('Nenhum dado aplicado automaticamente',c1.get(f'/candidatos/{p}').json()['Resumo']=='Meu perfil oficial')
    worker()
    imp=c1.get('/curriculos/'+ident+'/importacao').json();check('Extração em subprocesso conclui',imp['ID_Status_Processamento_IA']==3 and 'Maria' in imp['TextoExtraido'])
    check('Contato extraído',imp['DadosExtraidos']['contato']['email']=='maria@example.com')
    check('Importação privada',c2.get('/curriculos/'+ident+'/importacao').status_code==403)
    check('Confirmação manual seletiva',c1.post('/curriculos/'+ident+'/importacao/aplicar',json={'selecionados':{'perfil':['resumo']},'sobrescrever_perfil':True}).status_code==200)
    check('Campo não aprovado intacto',c1.get(f'/candidatos/{p}').json()['TituloProfissional']==fields['titulo_profissional'])
    check('Campo aprovado aplicado',c1.get(f'/candidatos/{p}').json()['Resumo']=='Apresentação sugerida')
    dados=imp['DadosExtraidos']
    check('PDF separa formação, certificados e projetos',len(dados['formacoes'])==1 and len(dados['certificados'])==2 and len(dados['projetos'])==1)
    selection={'versao_revisao':2,'importar_certificados':True,'importar_projetos':True,
               'selecionados':{'formacoes':[0],'certificados':[1],'projetos':[0]}}
    applied=c1.post('/curriculos/'+ident+'/importacao/aplicar',json=selection)
    check('Importação independente em MySQL',applied.status_code==200 and {k:v for k,v in applied.json()['importados'].items() if v}=={'formacoes':1,'certificados':1,'projetos':1})
    official=c1.get(f'/candidatos/{p}/profissional').json()
    check('Certificado no grupo correto',any(f['Curso']=='Java Básico' and f['Nivel']=='Certificado' for f in official['formacoes']))
    check('Certificado desmarcado não importado',not any(f['Curso']=='Python Avançado' for f in official['formacoes']))
    check('Projeto no grupo correto',any(i['Titulo']=='Talentix Importado' and i['Tipo']=='projeto' for i in official['itens']))
    check('Projetos não viram certificados',not any(f['Curso']=='Talentix Importado' for f in official['formacoes']))
    check('Repetição não duplica itens',sum(c1.post('/curriculos/'+ident+'/importacao/aplicar',json=selection).json()['importados'].values())==0)
    check('Importação alheia bloqueada',c2.post('/curriculos/'+ident+'/importacao/aplicar',json=selection).status_code==403)
    check('Original nunca sobrescrito',c1.get(cv['ArquivoUrl']).content==resume and c1.get(url).content==pdf)
    check('Currículo principal trocável',c1.put('/curriculos/'+generated_id,json={'titulo':'Principal Talentix','principal':True}).status_code==200)
    check('Apenas um principal',sum(x['Principal'] for x in c1.get(f'/candidatos/{p}/curriculos').json())==1)
    bad=c1.post(f'/candidatos/{p}/curriculos',data={'titulo':'Documento ilegível'},files={'arquivo':('bad.pdf',b'%PDF-1.4\nfalso','application/pdf')}).json()
    worker();check('PDF inválido falha compreensível',c1.get('/curriculos/'+bad['ID_Curriculos']+'/importacao').json()['ID_Status_Processamento_IA']==4)
    check('Extensão executável recusada',c1.post(f'/candidatos/{p}/curriculos',data={'titulo':'Inválido'},files={'arquivo':('cv.exe',b'MZ','application/pdf')}).status_code==400)
    title='Novembro '+nonce
    payload={'id_empresa':de1['id_empresa'],'titulo':title,'descricao':'Python e SQL','modalidade':'Remoto','nivel':'Júnior','localizacao':'Contagem','tipo_contrato':'CLT','salario_min':3000,'salario_max':5000,'area_profissional':'TI'}
    job=e1.post('/vagas',json=payload).json()['ID_Vagas']
    e1.post('/vagas/'+job+'/habilidades',json={'id_habilidade':skill,'nivel_minimo':2})
    saved=c1.post('/buscas',json={'nome':'Minha busca','filtros':{'cargo':title,'modalidade':'remoto'},'ativa':True}).json()['ID_Busca']
    query('UPDATE Buscas_Salvas SET CriadoEm=%s WHERE ID_Busca=%s',('2020-01-01',saved))
    check('Publicação',e1.patch('/vagas/'+job+'/publicar').status_code==200)
    filt={'cargo':title,'palavra_chave':'SQL','localizacao':'Contagem','modalidade':'remoto','nivel':'Júnior','tipo_contrato':'CLT','area':'TI','salario_min':4500,'habilidades':'Python Novembro '+nonce,'por_pagina':1}
    result=c1.get('/vagas/busca',params=filt).json();check('Filtros combinados MySQL',result['total']==1 and result['resultados'][0]['ID_Vagas']==job)
    check('Compatibilidade de habilidade',result['resultados'][0]['compatibilidade']==100)
    check('Dados empresariais privados ausentes',not {'Cnpj','ID_Usuarios','ID_Usuario_Empresa','Endereco'} & result['resultados'][0].keys())
    check('Paginação',c1.get('/vagas/busca',params={**filt,'pagina':2}).json()['resultados']==[])
    check('Ordenação validada',c1.get('/vagas/busca',params={'ordenar':'DROP TABLE Vagas'}).status_code==422)
    check('Injeção SQL não modifica filtro',c1.get('/vagas/busca',params={'cargo':"' OR 1=1 --"}).json()['total']==0)
    check('Autocomplete limitado',len(c1.get('/vagas/autocomplete',params={'q':title,'limite':1}).json())==1)
    check('Busca salva IDOR',c2.put('/buscas/'+saved,json={'nome':'alheia','filtros':{}}).status_code==404)
    check('Histórico',c1.post('/buscas-historico',json=filt).status_code==201 and len(c1.get('/buscas-historico').json())==1)
    worker();worker();check('Alerta somente uma vez',query('SELECT COUNT(*) FROM Alertas_Busca WHERE ID_Busca=%s',(saved,))[0][0]==1)
    check('Notificação persistida',any(x['Titulo']=='Nova vaga na busca Minha busca' for x in c1.get('/notificacoes').json()))
    check('Candidatura com versão específica',c1.post('/candidaturas',json={'id_vaga':job,'curriculo_url':url}).status_code==201)
    check('Recrutador só lê CV anexado',e1.get(url).status_code==200 and e1.get(cv['ArquivoUrl']).status_code==404 and e2.get(url).status_code==404)
    check('Perfil autorizado após candidatura',e1.get(f'/candidatos/{p}/profissional').status_code==200)
    check('Arquivar documento enviado',c1.delete('/curriculos/'+generated_id).status_code==200)
    history=c1.get(f'/candidatos/{p}/curriculos/historico').json()
    archived=next(x for x in history if x['ID_Curriculos']==generated_id)
    check('Histórico real mantém versão e candidatura',not archived['Ativo'] and archived['CandidaturasEnviadas']==1)
    check('Empresa mantém somente documento anexado arquivado',e1.get(url).status_code==200 and e2.get(url).status_code==404)
    check('Outra conta não consulta histórico',c2.get(f'/candidatos/{p}/curriculos/historico').status_code==403)
    check('Principal substituído ao arquivar',sum(x['Principal'] for x in c1.get(f'/candidatos/{p}/curriculos').json())==1)
    check('Já candidatado',c1.get('/vagas/busca',params={'cargo':title}).json()['resultados'][0]['ja_candidatado'])
    c1.put('/buscas/'+saved,json={'nome':'Minha busca','filtros':{'cargo':title},'ativa':False})
    job2=e1.post('/vagas',json=payload).json()['ID_Vagas'];e1.patch('/vagas/'+job2+'/publicar');worker()
    check('Busca pausada não envia alerta',query('SELECT COUNT(*) FROM Alertas_Busca WHERE ID_Busca=%s',(saved,))[0][0]==1)
    e1.patch('/vagas/'+job+'/encerrar');e1.patch('/vagas/'+job2+'/encerrar')
    check('Encerradas ausentes',c1.get('/vagas/busca',params={'cargo':title}).json()['total']==0)
    check('Excluir busca própria',c1.delete('/buscas/'+saved).status_code==200)
    check('Currículo antigo acessível',c1.get(url).status_code==200)
    item=c1.get(f'/candidatos/{p}/profissional').json()['itens'][0]['ID_Item'];check('Excluir item próprio',c1.delete('/itens-profissionais/'+item).status_code==200)
except Exception as exc:
    traceback.print_exc()
    failure=f'{type(exc).__name__}: {exc}'
finally:
    summary={'cases':len(cases),'passed':sum(x['passed'] for x in cases),'execution_error':failure}
    (OUT/'november-mysql.json').write_text(json.dumps({'summary':summary,'cases':cases},ensure_ascii=False,indent=2))
    print(json.dumps(summary,ensure_ascii=False));conn.close()
    for c in clients:c.close()
sys.exit(1 if failure else 0)
