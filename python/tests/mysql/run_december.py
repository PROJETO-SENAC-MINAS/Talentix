"""ATS on MySQL 8: real transactions, migrations, authorization and audit."""
import json,os,uuid,sys
from pathlib import Path
import httpx
import pymysql
if os.getenv('TALENTIX_ISOLATED_TESTS')!='1' or not os.environ['DB_NAME'].startswith('talentix_test'):
    raise SystemExit('Somente o banco descartável de CI.')
API=os.getenv('TEST_API_URL','http://127.0.0.1:8000');nonce=uuid.uuid4().hex[:12];records=[];clients=[]
class Client(httpx.Client):
    def request(self,method,url,**kwargs):
        if method.upper() in ('POST','PUT','PATCH','DELETE') and self.cookies.get('talentix_csrf'):
            kwargs['headers']={**kwargs.get('headers',{}),'X-CSRF-Token':self.cookies.get('talentix_csrf')}
        return super().request(method,url,**kwargs)
def call(c,method,path,status=200,**kwargs):
    r=c.request(method,path,**kwargs);records.append({'method':method,'path':path,'status':r.status_code,'passed':r.status_code==status})
    assert r.status_code==status,(path,r.status_code,r.text)
    return r.json()
def account(role):
    c=Client(base_url=API,timeout=30,trust_env=False);clients.append(c);email=f'{role}-{len(clients)}-{nonce}@december.example.com'
    d={'nome':'Dezembro '+role,'email':email,'senha':'Dezembro123!'}
    if role=='empresa':d.update(razao_social='Empresa ATS',cnpj=str(int(uuid.uuid4().hex[:12],16)).zfill(14)[-14:])
    ids=call(c,'POST','/auth/cadastro/'+role,201,json=d);call(c,'POST','/auth/login',json={'email':email,'senha':d['senha']});return c,ids
try:
    e1,ed1=account('empresa');e2,ed2=account('empresa');c1,cd1=account('candidato');c2,cd2=account('candidato');r1,rd1=account('recrutador')
    eid=ed1['id_empresa'];cid=cd1['id_candidato']
    call(e1,'POST',f'/empresas/{eid}/recrutadores',201,json={'id_usuario_recrutador':rd1['id_usuario'],'cargo':'RH ATS'})
    # Login again after linking updates the effective recruiter role.
    call(r1,'POST','/auth/login',json={'email':f'recrutador-5-{nonce}@december.example.com','senha':'Dezembro123!'})
    v=call(e1,'POST','/vagas',201,json={'id_empresa':eid,'titulo':'Backend ATS '+nonce,'descricao':'Python SQL','modalidade':'Remoto','nivel':'Junior'})['ID_Vagas']
    call(e1,'PATCH',f'/vagas/{v}/publicar')
    a=call(c1,'POST','/candidaturas',201,json={'id_vaga':v})['ID_Candidaturas']
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=2) as workers:
        results=list(workers.map(lambda _: call(e1,'POST',f'/ats/vagas/{v}/inicializar'),range(2)))
    b=call(e1,'GET',f'/ats/vagas/{v}/pipeline');assert len(b['etapas'])==6 and len(b['cards'])==1
    first=b['etapas'][0]['ID_Etapa'];second=b['etapas'][1]['ID_Etapa']
    custom=call(e1,'POST',f'/ats/vagas/{v}/etapas',201,json={'nome':'Case técnico','ordem':3})['ID_Etapa']
    call(e1,'PUT',f'/ats/etapas/{custom}',json={'nome':'Case revisado','ordem':4})
    move={'id_etapa':second,'versao':1,'ordem':0,'responsavel':rd1['id_usuario'],'prazo':'2026-12-15','notas':'Nota privada ATS'}
    call(e1,'PUT',f'/ats/candidaturas/{a}/card',json=move)
    call(e1,'PUT',f'/ats/candidaturas/{a}/card',409,json=move)
    call(e2,'GET',f'/ats/vagas/{v}/pipeline',403);call(c1,'GET',f'/ats/candidaturas/{a}/historico',403)
    mid=call(e1,'POST',f'/ats/etapas/{second}/scorecards',201,json={'nome':'Entrevista estruturada','cego':True,'criterios':[{'nome':'Python','peso':3},{'nome':'SQL','peso':1}]})['ID_Modelo']
    path=f'/ats/candidaturas/{a}/scorecards/{mid}/avaliacoes'
    score=call(e1,'POST',path,201,json={'notas':[4,2],'parecer':'Boa base','recomendacao':'Aprovar'});assert score['Media']==3.5
    assert call(r1,'GET',path)['bloqueado'] is True
    assert call(c1,'GET',f'/candidaturas/{a}')['ID_Status_Candidatura']==2
    call(c1,'GET',path,403);call(e2,'GET',path,403)
    call(r1,'POST',path,201,json={'notas':[2,4],'parecer':'Avaliar evolução','recomendacao':'Avaliar'})
    assert call(r1,'GET',path)['media']==3
    call(r1,'POST',path,409,json={'notas':[5,5],'parecer':'Repetido','recomendacao':'Aprovar'})
    concurrent_model=call(e1,'POST',f'/ats/etapas/{second}/scorecards',201,json={'nome':'Rodada concorrente','cego':True,'criterios':[{'nome':'Python','peso':1}]})['ID_Modelo']
    with ThreadPoolExecutor(max_workers=2) as workers:
        scores=list(workers.map(lambda evaluator:call(evaluator,'POST',f'/ats/candidaturas/{a}/scorecards/{concurrent_model}/avaliacoes',201,json={'notas':[4],'parecer':'Avaliação independente','recomendacao':'Avaliar'}),[e1,r1]))
    call(e1,'PUT',f'/ats/candidaturas/{a}/card',json={**move,'versao':2,'estado':'reprovado','motivo':'Experiência para esta vaga'})
    assert len(call(e1,'GET',f'/ats/candidaturas/{a}/historico'))==7
    pid=call(e1,'POST','/ats/pools',201,json={'nome':'Backend'})['ID_Pool']
    call(e1,'PUT',f'/ats/pools/{pid}',json={'nome':'Full Stack'})
    member=f'/ats/pools/{pid}/candidatos/{cid}'
    call(e1,'PUT',member,403,json={'tags':['Python']})
    call(c1,'GET','/ats/consentimentos');call(c1,'PUT',f'/ats/consentimentos/{eid}',json={'autorizado':True})
    call(e1,'PUT',member,json={'tags':['Python','SQL'],'favorito':True,'notas':'Retomar contato em nova oportunidade'})
    assert call(e1,'GET','/ats/talentos?favorito=true&tag=Python')['total']==1
    assert len(call(e1,'GET',f'/ats/talentos/{cid}/historico')['processos'])==1
    call(e2,'GET',f'/ats/talentos/{cid}/historico',403)
    call(e2,'PUT',member,403,json={'tags':[]})
    call(e1,'PUT',f'/ats/pools/{pid}/candidatos/{cd2["id_candidato"]}',403,json={'tags':[]})
    call(e1,'POST',f'/ats/talentos/{cid}/convites',201,json={'id_vaga':v});call(e1,'POST',f'/ats/talentos/{cid}/convites',409,json={'id_vaga':v})
    assert any(n['Titulo']=='Convite para nova vaga' for n in call(c1,'GET','/notificacoes'))
    call(e1,'DELETE',member);call(e1,'PUT',member,json={'tags':['Python']})
    call(c1,'PUT',f'/ats/consentimentos/{eid}',json={'autorizado':False})
    assert call(e1,'GET','/ats/talentos')['total']==0
    call(e1,'POST',f'/ats/talentos/{cid}/convites',403,json={'id_vaga':v})
    call(e1,'DELETE',f'/ats/pools/{pid}')
    # Request from the same real authenticated browser without CSRF must fail.
    bad=httpx.Client(base_url=API,cookies=e1.cookies,trust_env=False)
    assert bad.post('/ats/pools',json={'nome':'Sem CSRF'}).status_code==403;bad.close()
    # New tables and movement logs are present with MySQL foreign keys/indexes.
    conn=pymysql.connect(host=os.environ['DB_HOST'],port=int(os.environ['DB_PORT']),user=os.environ['DB_USER'],password=os.environ['DB_PASSWORD'],database=os.environ['DB_NAME'])
    with conn.cursor() as cur:
        cur.execute('SELECT COUNT(*) FROM ATS_Eventos WHERE ID_Candidaturas=%s',(a,));assert cur.fetchone()[0]==7
        cur.execute("SELECT COUNT(*) FROM Audit_Logs WHERE Acao LIKE 'ats.%'");assert cur.fetchone()[0]>=10
        cur.execute('SELECT Notas,Tags,Ativo FROM ATS_Membros WHERE ID_Pool=%s AND ID_Candidatos=%s',(pid,cid));row=cur.fetchone();assert row[0] is None and json.loads(row[1])==[] and row[2]==0
    conn.close()
    print(f'ATS MySQL: {len(records)} checks passed.')
finally:
    out=Path(os.environ['TEST_RESULTS_DIR']);out.mkdir(parents=True,exist_ok=True);(out/'december-mysql.json').write_text(json.dumps(records,indent=2))
    for c in clients:c.close()
