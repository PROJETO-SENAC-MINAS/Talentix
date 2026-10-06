"""ATS HTTP regression: tenant isolation, blind scores and consent."""
import json
import pytest

def setup(c,auth):
    auth(c,'ue1','empresa')
    assert c.post('/ats/vagas/v1/inicializar').status_code==200
    b=c.get('/ats/vagas/v1/pipeline').json()
    return b['etapas'],b['cards'][0]

def template(c,stage):
    r=c.post(f'/ats/etapas/{stage}/scorecards',json={'nome':'Entrevista','cego':True,'criterios':[{'nome':'Python','peso':3,'obrigatorio':True},{'nome':'Comunicação','peso':1,'obrigatorio':False}]})
    assert r.status_code==201,r.text
    return r.json()['ID_Modelo']

def test_pipeline_idempotent_history_and_concurrency(ambiente,autenticar):
    c,db=ambiente;stages,card=setup(c,autenticar)
    assert len(stages)==6
    assert c.post('/ats/vagas/v1/inicializar').status_code==200
    assert db.execute('SELECT COUNT(*) FROM ATS_Eventos').fetchone()[0]==1
    d={'id_etapa':stages[1]['ID_Etapa'],'versao':1,'ordem':0,'responsavel':'ue1','prazo':'2026-12-12','notas':'Interna'}
    r=c.put('/ats/candidaturas/ca1/card',json=d)
    assert r.status_code==200,r.text
    assert r.json()['Versao']==2
    assert c.put('/ats/candidaturas/ca1/card',json=d).status_code==409
    assert len(c.get('/ats/candidaturas/ca1/historico').json())==2
    assert c.put('/ats/etapas/'+stages[1]['ID_Etapa'],json={'nome':'Entrevista','ordem':2,'ativa':False}).status_code==409
    assert len(c.get('/ats/vagas/v1/pipeline?responsavel=ue1&estado=ativo').json()['cards'])==1

@pytest.mark.parametrize('role,user',[('empresa','ue2'),('recrutador','ur2'),('candidato','uc1')])
def test_idor_all_ats_resources(ambiente,autenticar,role,user):
    c,db=ambiente;stages,card=setup(c,autenticar);mid=template(c,stages[0]['ID_Etapa']);pid=c.post('/ats/pools',json={'nome':'Backend'}).json()['ID_Pool']
    autenticar(c,user,role)
    for path in ['/ats/vagas/v1/pipeline','/ats/candidaturas/ca1/historico','/ats/candidaturas/ca1/scorecards',f'/ats/candidaturas/ca1/scorecards/{mid}/avaliacoes']:
        assert c.get(path).status_code==403,path
    for path,data in [(f'/ats/pools/{pid}/candidatos/c2',{'tags':[]}),('/ats/candidaturas/ca1/card',{'id_etapa':stages[0]['ID_Etapa'],'versao':1,'ordem':0}),('/ats/etapas/'+stages[0]['ID_Etapa'],{'nome':'Hijack','ordem':0})]:
        assert c.put(path,json=data).status_code==403,path
    assert c.delete('/ats/pools/'+pid).status_code==403
    assert c.post(f'/ats/candidaturas/ca1/scorecards/{mid}/avaliacoes',json={'notas':[5,5],'parecer':'Hijack','recomendacao':'Aprovar'}).status_code==403
    assert c.post('/ats/talentos/c1/convites',json={'id_vaga':'v1'}).status_code==403

def test_admin_and_recruiter_binding(ambiente,autenticar):
    c,db=ambiente;setup(c,autenticar);autenticar(c,'ua','administrador')
    assert c.get('/ats/contexto').status_code==422
    assert c.get('/ats/contexto?id_empresa=e1').status_code==200
    assert c.get('/ats/vagas/v1/pipeline').status_code==200
    autenticar(c,'ur2','recrutador');assert c.post('/ats/vagas/v2/inicializar').status_code==200
    db.execute("UPDATE Recrutadores SET Ativo=0 WHERE ID_Recrutadores='r2'");db.commit()
    assert c.get('/ats/vagas/v2/pipeline').status_code in {401,403}

def test_blind_scores_history_and_manual_decision(ambiente,autenticar):
    c,db=ambiente;stages,card=setup(c,autenticar);mid=template(c,stages[0]['ID_Etapa'])
    db.execute("UPDATE Recrutadores SET ID_Empresas='e1' WHERE ID_Recrutadores='r2'");db.commit()
    path=f'/ats/candidaturas/ca1/scorecards/{mid}/avaliacoes'
    r=c.post(path,json={'notas':[4,2],'parecer':'Boa base','comentario':'Realizada','recomendacao':'Aprovar'})
    assert r.status_code==201,r.text
    assert r.json()['Media']==3.5
    assert db.execute("SELECT ID_Status_Candidatura FROM Candidaturas WHERE ID_Candidaturas='ca1'").fetchone()[0]==1
    assert c.post(path,json={'notas':[5,5],'parecer':'Duplicada','recomendacao':'Reprovar'}).status_code==409
    autenticar(c,'uc1','candidato');assert c.put('/ats/consentimentos/e1',json={'autorizado':True}).status_code==200
    autenticar(c,'ur2','recrutador');assert c.get(path).json()=={'bloqueado':True,'avaliacoes':[],'media':None}
    h=c.get('/ats/talentos/c1/historico').json();assert h['processos'][0]['scorecards'][0]['bloqueado'] is True
    assert c.post(path,json={'notas':[2,4],'parecer':'Evoluir','recomendacao':'Avaliar'}).status_code==201
    d=c.get(path).json();assert len(d['avaliacoes'])==2 and d['media']==3

@pytest.mark.parametrize('notes',[[None,3],[6,3],[-1,3],[3],[None,None]])
def test_invalid_notes(ambiente,autenticar,notes):
    c,db=ambiente;stages,card=setup(c,autenticar);mid=template(c,stages[0]['ID_Etapa'])
    assert c.post(f'/ats/candidaturas/ca1/scorecards/{mid}/avaliacoes',json={'notas':notes,'parecer':'Teste','recomendacao':'Avaliar'}).status_code==422
    assert db.execute('SELECT COUNT(*) FROM ATS_Avaliacoes').fetchone()[0]==0

def test_crm_consent_isolation_filters_and_revoke(ambiente,autenticar):
    c,db=ambiente;setup(c,autenticar);pid=c.post('/ats/pools',json={'nome':'Full Stack'}).json()['ID_Pool'];path=f'/ats/pools/{pid}/candidatos/c1'
    assert c.put(path,json={'tags':['Python'],'favorito':True,'notas':'Potencial'}).status_code==403
    assert c.get('/ats/talentos').json()['total']==0
    autenticar(c,'uc1','candidato');assert c.put('/ats/consentimentos/e2',json={'autorizado':True}).status_code==403
    assert c.put('/ats/consentimentos/e1',json={'autorizado':True}).status_code==200
    autenticar(c,'ue1','empresa');assert c.put(path,json={'tags':['Python'],'favorito':True,'notas':'Potencial'}).status_code==200
    assert c.put(f'/ats/pools/{pid}/candidatos/c2',json={'tags':[]}).status_code==403
    assert c.get('/ats/talentos?tag=Python&favorito=true').json()['total']==1
    for suffix in ['nome=%27+OR+1%3D1--','skill=Java','formacao=SENAC','experiencia=Python','avaliado=true']:
        assert c.get('/ats/talentos?'+suffix).json()['total']==0,suffix
    h=c.get('/ats/talentos/c1/historico').json();assert len(h['processos'])==1 and h['pools'][0]['Notas']=='Potencial'
    autenticar(c,'ue2','empresa');assert c.get('/ats/talentos/c1/historico').status_code==403
    autenticar(c,'uc1','candidato');assert c.put('/ats/consentimentos/e1',json={'autorizado':False}).status_code==200
    autenticar(c,'ue1','empresa');assert c.get('/ats/talentos').json()['total']==0
    assert c.get('/ats/talentos/c1/historico').status_code==403
    assert tuple(db.execute('SELECT Notas,Tags,Ativo FROM ATS_Membros').fetchone())==(None,'[]',0)
    assert c.get('/ats/candidaturas/ca1/historico').status_code==200

def test_reason_responsible_and_cross_job_stage(ambiente,autenticar):
    c,db=ambiente;stages,card=setup(c,autenticar)
    d={'id_etapa':stages[0]['ID_Etapa'],'versao':1,'ordem':0,'estado':'reprovado'}
    assert c.put('/ats/candidaturas/ca1/card',json=d).status_code==422
    d.update(motivo='Experiência insuficiente',responsavel='ur2');assert c.put('/ats/candidaturas/ca1/card',json=d).status_code==422
    d['responsavel']=None;assert c.put('/ats/candidaturas/ca1/card',json=d).status_code==200
    assert db.execute("SELECT ID_Status_Candidatura FROM Candidaturas WHERE ID_Candidaturas='ca1'").fetchone()[0]==6
    autenticar(c,'ua','administrador');c.post('/ats/vagas/v2/inicializar');other=c.get('/ats/vagas/v2/pipeline').json()['etapas'][0]['ID_Etapa']
    d.update(id_etapa=other,versao=2);assert c.put('/ats/candidaturas/ca1/card',json=d).status_code==422

def test_csrf_and_candidate_private_notes(ambiente,autenticar):
    c,db=ambiente;setup(c,autenticar);c.headers.pop('X-CSRF-Token')
    assert c.post('/ats/vagas/v1/inicializar').status_code==403
    assert c.post('/ats/pools',json={'nome':'Teste'}).status_code==403
    autenticar(c,'uc1','candidato');d=c.get('/candidaturas/ca1').json()
    assert 'Notas' not in d and 'scorecards' not in d
    assert c.get('/ats/pools').status_code==403

def test_candidate_withdrawal_and_legacy_status_audited(ambiente,autenticar):
    c,db=ambiente;stages,card=setup(c,autenticar)
    # Legacy rejection cannot bypass required reason, and rolls back status.
    assert c.patch('/candidaturas/ca1/status?id_status_candidatura=6').status_code==422
    assert db.execute("SELECT ID_Status_Candidatura FROM Candidaturas WHERE ID_Candidaturas='ca1'").fetchone()[0]==1
    autenticar(c,'uc1','candidato')
    assert c.delete('/candidaturas/ca1').status_code==200
    autenticar(c,'ue1','empresa')
    assert c.get('/ats/vagas/v1/pipeline?estado=desistente').json()['cards'][0]['Estado']=='desistente'
    h=c.get('/ats/candidaturas/ca1/historico').json()
    assert [e['Sequencia'] for e in h]==[1,2] and json.loads(h[-1]['Depois'])['Estado']=='desistente'
    assert c.put('/ats/candidaturas/ca1/card',json={'id_etapa':stages[0]['ID_Etapa'],'versao':2,'ordem':0}).status_code==409

def test_ats_private_cache_and_rate_limit(monkeypatch,ambiente,autenticar):
    from starlette.applications import Starlette
    from starlette.responses import JSONResponse
    from starlette.routing import Route
    from fastapi.testclient import TestClient
    from app.core.middleware import RateLimitMiddleware
    from app.core.config import settings
    c,db=ambiente;autenticar(c,'ue1','empresa')
    assert c.get('/ats/contexto').headers['cache-control']=='no-store'
    monkeypatch.setattr(settings,'RATE_LIMIT_REQUESTS',2)
    async def ok(request):return JSONResponse({'ok':True})
    a=Starlette(routes=[Route('/ats/{resource}',ok)]);a.add_middleware(RateLimitMiddleware)
    with TestClient(a) as client:
        assert client.get('/ats/first').status_code==200
        assert client.get('/ats/second').status_code==200
        assert client.get('/ats/third').status_code==429

def test_kanban_position_ordering(ambiente,autenticar):
    c,db=ambiente;stages,card=setup(c,autenticar)
    db.execute("INSERT INTO Candidaturas(ID_Candidaturas,ID_Candidatos,ID_Vagas) VALUES ('ca3','c2','v1')");db.commit()
    assert c.post('/ats/vagas/v1/inicializar').status_code==200
    assert c.put('/ats/candidaturas/ca3/card',json={'id_etapa':stages[0]['ID_Etapa'],'versao':1,'ordem':0}).status_code==200
    cards=c.get('/ats/vagas/v1/pipeline').json()['cards']
    assert [c['ID_Candidaturas'] for c in cards]==['ca3','ca1']
    assert [c['Ordem'] for c in cards]==[0,1]
