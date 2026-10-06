"""ATS empresarial: autorização por empresa, histórico imutável e decisões humanas."""
import json
from datetime import date
from typing import Literal
from fastapi import Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field, model_validator
from app.core.routes import AtomicRouter
from app.core.deps import exigir_tipo
from app.core.access import checar_empresa, empresa_da_sessao
from app.core.security import novo_uuid
from app.core.audit import registrar_auditoria
from app.core.notificar import notificar_usuario
from app.db.database import fetch_one, fetch_all, execute

router = AtomicRouter(prefix='/ats', tags=['ATS'])
rh = exigir_tipo('empresa','recrutador','administrador')
def pack(d): return json.dumps(d, ensure_ascii=False, default=str)
def unpack(d): return json.loads(d) if isinstance(d,str) else d

def fail(code,message): raise HTTPException(code,message)

async def company(s, id_empresa=None):
    if s['tipo_usuario']=='administrador':
        if not id_empresa: fail(422,'Selecione a empresa para o acesso administrativo.')
        return await checar_empresa(id_empresa,s)
    e=await empresa_da_sessao(s)
    if id_empresa and id_empresa!=e['ID_Empresas']: fail(403,'Sem permissão sobre esta empresa.')
    return e

async def job(id,s):
    v=await fetch_one('SELECT * FROM Vagas WHERE ID_Vagas=%s',(id,))
    if not v: fail(404,'Vaga não encontrada.')
    await checar_empresa(v['ID_Empresas'],s)
    return v

async def application(id,s):
    c=await fetch_one('SELECT * FROM Candidaturas WHERE ID_Candidaturas=%s',(id,))
    if not c: fail(404,'Candidatura não encontrada.')
    await job(c['ID_Vagas'],s)
    return c

async def stage(id,s):
    e=await fetch_one('SELECT * FROM ATS_Etapas WHERE ID_Etapa=%s',(id,))
    if not e: fail(404,'Etapa não encontrada.')
    await job(e['ID_Vagas'],s)
    return e

async def pool(id,s):
    p=await fetch_one('SELECT * FROM ATS_Pools WHERE ID_Pool=%s AND Ativo=1',(id,))
    if not p: fail(404,'Pool não encontrado.')
    await checar_empresa(p['ID_Empresas'],s)
    return p

async def event(id,action,before,after,s,request):
    seq=await fetch_one('SELECT COALESCE(MAX(Sequencia),0)+1 AS Proxima FROM ATS_Eventos WHERE ID_Candidaturas=%s',(id,))
    await execute('INSERT INTO ATS_Eventos(ID_Evento,ID_Candidaturas,ID_Usuarios,Acao,Antes,Depois,Sequencia) VALUES (%s,%s,%s,%s,%s,%s,%s)',
        (novo_uuid(),id,s['id_usuario'],action,pack(before),pack(after),seq['Proxima']))
    await registrar_auditoria(request,action,'ATS',s['id_usuario'],id,before,after)

class StageData(BaseModel):
    nome: str=Field(min_length=1,max_length=150,pattern=r'.*\S.*')
    ordem: int=Field(ge=0,le=1000)
    ativa: bool=True

@router.get('/contexto')
async def context(id_empresa: str|None=None,s:dict=Depends(rh)):
    e=await company(s,id_empresa)
    return {'empresa':e,'vagas':await fetch_all('SELECT ID_Vagas,Titulo FROM Vagas WHERE ID_Empresas=%s ORDER BY CriadoEm DESC',(e['ID_Empresas'],)),
        'avaliadores':await fetch_all("""SELECT u.ID_Usuarios,u.Nome FROM Usuarios u WHERE u.Ativo=1 AND
        (u.ID_Usuarios=%s OR EXISTS(SELECT 1 FROM Recrutadores r WHERE r.ID_Usuarios=u.ID_Usuarios AND r.ID_Empresas=%s AND r.Ativo=1))""",(e['ID_Usuarios'],e['ID_Empresas']))}

@router.post('/vagas/{id}/etapas',status_code=201)
async def create_stage(id:str,d:StageData,request:Request,s:dict=Depends(rh)):
    await job(id,s)
    eid=novo_uuid()
    await execute('INSERT INTO ATS_Etapas(ID_Etapa,ID_Vagas,Nome,Ordem,Ativa) VALUES (%s,%s,%s,%s,%s)',(eid,id,d.nome.strip(),d.ordem,d.ativa))
    await registrar_auditoria(request,'ats.etapa.criar','ATS_Etapas',s['id_usuario'],eid,novo=d.model_dump())
    return await fetch_one('SELECT * FROM ATS_Etapas WHERE ID_Etapa=%s',(eid,))

@router.put('/etapas/{id}')
async def edit_stage(id:str,d:StageData,request:Request,s:dict=Depends(rh)):
    old=await stage(id,s)
    # Soft archival preserves references and prevents stranding active candidates.
    if not d.ativa and await fetch_one("SELECT ID_Candidaturas FROM ATS_Cards WHERE ID_Etapa=%s AND Estado='ativo' LIMIT 1",(id,)):
        fail(409,'Movimente os candidatos ativos antes de arquivar a etapa.')
    await execute('UPDATE ATS_Etapas SET Nome=%s,Ordem=%s,Ativa=%s WHERE ID_Etapa=%s',(d.nome.strip(),d.ordem,d.ativa,id))
    await registrar_auditoria(request,'ats.etapa.editar','ATS_Etapas',s['id_usuario'],id,old,d.model_dump())
    return d.model_dump()

@router.post('/vagas/{id}/inicializar')
async def initialize(id:str,request:Request,s:dict=Depends(rh)):
    # Lock the job to serialize first initialization and concurrent moves.
    await job(id,s)
    await fetch_one('SELECT ID_Vagas FROM Vagas WHERE ID_Vagas=%s FOR UPDATE',(id,))
    stages=await fetch_all('SELECT * FROM ATS_Etapas WHERE ID_Vagas=%s AND Ativa=1 ORDER BY Ordem,ID_Etapa',(id,))
    if not stages:
        for i,name in enumerate(['Novos','Triagem','Entrevista RH','Entrevista técnica','Proposta','Contratado']):
            await execute('INSERT INTO ATS_Etapas(ID_Etapa,ID_Vagas,Nome,Ordem) VALUES (%s,%s,%s,%s)',(novo_uuid(),id,name,i))
        stages=await fetch_all('SELECT * FROM ATS_Etapas WHERE ID_Vagas=%s AND Ativa=1 ORDER BY Ordem,ID_Etapa',(id,))
    rows=await fetch_all('SELECT * FROM Candidaturas WHERE ID_Vagas=%s ORDER BY CriadaEm,ID_Candidaturas',(id,))
    for i,c in enumerate(rows):
        if await fetch_one('SELECT ID_Candidaturas FROM ATS_Cards WHERE ID_Candidaturas=%s',(c['ID_Candidaturas'],)): continue
        state={5:'aprovado',6:'reprovado',7:'desistente'}.get(c['ID_Status_Candidatura'],'ativo')
        await execute('INSERT INTO ATS_Cards(ID_Candidaturas,ID_Etapa,Ordem,Estado,EntradaEm) VALUES (%s,%s,%s,%s,%s)',(c['ID_Candidaturas'],stages[0]['ID_Etapa'],i,state,c['CriadaEm']))
        await event(c['ID_Candidaturas'],'ats.entrada',None,{'etapa':stages[0]['ID_Etapa'],'estado':state},s,request)
    return {'mensagem':'Pipeline atualizado; histórico preservado.'}

@router.get('/vagas/{id}/pipeline')
async def board(id:str,responsavel:str|None=None,estado:Literal['ativo','aprovado','reprovado','retirado','desistente']|None=None,s:dict=Depends(rh)):
    await job(id,s)
    stages=await fetch_all('SELECT * FROM ATS_Etapas WHERE ID_Vagas=%s ORDER BY Ordem,ID_Etapa',(id,))
    q="""SELECT a.*,u.Nome AS NomeCandidato,c.ID_Candidatos,c.Ativo AS CandidaturaAtiva,c.ID_Status_Candidatura
    FROM ATS_Cards a JOIN Candidaturas c ON c.ID_Candidaturas=a.ID_Candidaturas
    JOIN Candidatos p ON p.ID_Candidatos=c.ID_Candidatos AND p.Ativo=1
    JOIN Usuarios u ON u.ID_Usuarios=p.ID_Usuarios AND u.Ativo=1 WHERE c.ID_Vagas=%s"""
    args=[id]
    if responsavel: q+=' AND a.ID_Responsavel=%s';args.append(responsavel)
    if estado: q+=' AND a.Estado=%s';args.append(estado)
    cards=await fetch_all(q+' ORDER BY a.Ordem,a.ID_Candidaturas',tuple(args))
    for a in cards:
        if not a['CandidaturaAtiva']: a['Estado']='desistente'
    return {'etapas':stages,'cards':cards}

class Move(BaseModel):
    id_etapa: str=Field(min_length=1,max_length=36)
    versao: int=Field(ge=1)
    ordem: int=Field(ge=0,le=1000000)
    responsavel: str|None=Field(default=None,max_length=36)
    prazo: date|None=None
    estado: Literal['ativo','aprovado','reprovado','retirado','desistente']='ativo'
    notas: str|None=Field(default=None,max_length=10000)
    motivo: str|None=Field(default=None,max_length=2000)
    @model_validator(mode='after')
    def reason(self):
        if self.estado in {'reprovado','retirado'} and not (self.motivo or '').strip(): raise ValueError('Informe o motivo da reprovação ou retirada.')
        return self

@router.put('/candidaturas/{id}/card')
async def move(id:str,d:Move,request:Request,s:dict=Depends(rh)):
    c=await application(id,s)
    v=await job(c['ID_Vagas'],s)
    await fetch_one('SELECT ID_Vagas FROM Vagas WHERE ID_Vagas=%s FOR UPDATE',(c['ID_Vagas'],))
    target=await stage(d.id_etapa,s)
    if target['ID_Vagas']!=c['ID_Vagas'] or not target['Ativa']: fail(422,'Etapa não pertence à vaga ou está arquivada.')
    if not c['Ativo']: fail(409,'Candidato desistente; candidatura arquivada não pode ser reativada pelo RH.')
    if d.responsavel:
        valid=await fetch_one("""SELECT ID_Usuarios FROM Usuarios WHERE ID_Usuarios=%s AND Ativo=1 AND
        (ID_Usuarios=%s OR EXISTS(SELECT 1 FROM Recrutadores r WHERE r.ID_Usuarios=Usuarios.ID_Usuarios AND r.ID_Empresas=%s AND r.Ativo=1))""",(d.responsavel,v['ID_Usuarios'] if 'ID_Usuarios' in v else (await checar_empresa(v['ID_Empresas'],s))['ID_Usuarios'],v['ID_Empresas']))
        if not valid: fail(422,'Responsável deve pertencer à empresa.')
    old=await fetch_one('SELECT * FROM ATS_Cards WHERE ID_Candidaturas=%s FOR UPDATE',(id,))
    if not old: fail(409,'Inicialize o pipeline antes de movimentar.')
    if old['Versao']!=d.versao: fail(409,'O candidato foi atualizado por outra pessoa. Recarregue o pipeline.')
    entered=old['ID_Etapa']!=d.id_etapa
    await execute('UPDATE ATS_Cards SET ID_Etapa=%s,ID_Responsavel=%s,Prazo=%s,Ordem=%s,Estado=%s,Notas=%s,Motivo=%s,Versao=Versao+1'+(',EntradaEm=NOW()' if entered else '')+' WHERE ID_Candidaturas=%s',
        (d.id_etapa,d.responsavel,d.prazo,d.ordem,d.estado,d.notas,d.motivo,id))
    # Position insertion: deterministic ordering without discarding historical entries.
    others=await fetch_all('SELECT ID_Candidaturas FROM ATS_Cards WHERE ID_Etapa=%s AND ID_Candidaturas<>%s ORDER BY Ordem,ID_Candidaturas',(d.id_etapa,id))
    ordered=[o['ID_Candidaturas'] for o in others];ordered.insert(min(d.ordem,len(ordered)),id)
    for i,cid in enumerate(ordered):
        if cid==id: await execute('UPDATE ATS_Cards SET Ordem=%s WHERE ID_Candidaturas=%s',(i,cid))
        else: await execute('UPDATE ATS_Cards SET Ordem=%s,Versao=Versao+1 WHERE ID_Candidaturas=%s',(i,cid))
    status={'ativo':2,'aprovado':5,'reprovado':6,'retirado':7,'desistente':7}[d.estado]
    await execute('UPDATE Candidaturas SET ID_Status_Candidatura=%s WHERE ID_Candidaturas=%s',(status,id))
    new=await fetch_one('SELECT * FROM ATS_Cards WHERE ID_Candidaturas=%s',(id,))
    await event(id,'ats.movimentacao',old,new,s,request)
    return new

@router.get('/candidaturas/{id}/historico')
async def history(id:str,s:dict=Depends(rh)):
    await application(id,s)
    return await fetch_all('SELECT * FROM ATS_Eventos WHERE ID_Candidaturas=%s ORDER BY Sequencia',(id,))

class Criterion(BaseModel):
    nome: str=Field(min_length=1,max_length=150,pattern=r'.*\S.*')
    peso: float=Field(gt=0,le=100,allow_inf_nan=False)
    obrigatorio: bool=True

class Template(BaseModel):
    nome: str=Field(min_length=1,max_length=150)
    cego: bool=True
    criterios: list[Criterion]=Field(min_length=1,max_length=30)
    @model_validator(mode='after')
    def unique(self):
        if len({c.nome.strip().lower() for c in self.criterios})!=len(self.criterios): raise ValueError('Critérios repetidos.')
        return self

@router.post('/etapas/{id}/scorecards',status_code=201)
async def create_template(id:str,d:Template,request:Request,s:dict=Depends(rh)):
    await stage(id,s)
    mid=novo_uuid()
    await execute('INSERT INTO ATS_Modelos(ID_Modelo,ID_Etapa,Nome,Cego,Criterios) VALUES (%s,%s,%s,%s,%s)',(mid,id,d.nome,d.cego,pack([c.model_dump() for c in d.criterios])))
    await registrar_auditoria(request,'ats.scorecard.criar','ATS_Modelos',s['id_usuario'],mid,novo=d.model_dump())
    return {'ID_Modelo':mid,**d.model_dump()}

@router.get('/candidaturas/{id}/scorecards')
async def templates(id:str,s:dict=Depends(rh)):
    c=await application(id,s)
    rows=await fetch_all('SELECT m.*,e.Nome AS NomeEtapa FROM ATS_Modelos m JOIN ATS_Etapas e ON e.ID_Etapa=m.ID_Etapa WHERE e.ID_Vagas=%s ORDER BY m.CriadoEm,m.ID_Modelo',(c['ID_Vagas'],))
    for m in rows: m['Criterios']=unpack(m['Criterios'])
    return rows

async def model_for(id,cid,s):
    c=await application(cid,s)
    m=await fetch_one('SELECT * FROM ATS_Modelos WHERE ID_Modelo=%s',(id,))
    if not m: fail(404,'Scorecard não encontrado.')
    e=await stage(m['ID_Etapa'],s)
    if e['ID_Vagas']!=c['ID_Vagas']: fail(403,'Scorecard pertence a outro processo.')
    return m

class Rating(BaseModel):
    notas: list[float|None]=Field(min_length=1,max_length=30)
    comentario: str|None=Field(default=None,max_length=10000)
    parecer: str=Field(min_length=1,max_length=10000,pattern=r'.*\S.*')
    recomendacao: Literal['Aprovar','Avaliar','Reprovar']

@router.post('/candidaturas/{cid}/scorecards/{mid}/avaliacoes',status_code=201)
async def rate(cid:str,mid:str,d:Rating,request:Request,s:dict=Depends(rh)):
    m=await model_for(mid,cid,s)
    await fetch_one('SELECT ID_Candidaturas FROM ATS_Cards WHERE ID_Candidaturas=%s FOR UPDATE',(cid,))
    criteria=unpack(m['Criterios'])
    if len(d.notas)!=len(criteria): fail(422,'Informe uma nota por critério.')
    import math
    for c,n in zip(criteria,d.notas):
        if (n is None and c['obrigatorio']) or (n is not None and (not math.isfinite(n) or not 0<=n<=5)): fail(422,'Notas devem estar entre 0 e 5; preencha os critérios obrigatórios.')
    if await fetch_one('SELECT ID_Avaliacao FROM ATS_Avaliacoes WHERE ID_Modelo=%s AND ID_Candidaturas=%s AND ID_Usuarios=%s',(mid,cid,s['id_usuario'])): fail(409,'Avaliação já enviada; histórico imutável. Crie outro scorecard para nova rodada.')
    pairs=[(c['peso'],n) for c,n in zip(criteria,d.notas) if n is not None]
    if not pairs: fail(422,'Informe pelo menos uma nota.')
    average=sum(w*n for w,n in pairs)/sum(w for w,n in pairs)
    aid=novo_uuid()
    await execute('INSERT INTO ATS_Avaliacoes(ID_Avaliacao,ID_Modelo,ID_Candidaturas,ID_Usuarios,Notas,Comentario,Parecer,Recomendacao,Media) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)',(aid,mid,cid,s['id_usuario'],pack(d.notas),d.comentario,d.parecer,d.recomendacao,average))
    await event(cid,'ats.avaliacao',None,{'id_avaliacao':aid,'modelo':mid},s,request)
    return {'ID_Avaliacao':aid,'Media':average,'mensagem':'Avaliação enviada. A decisão permanece com o RH.'}

@router.get('/candidaturas/{cid}/scorecards/{mid}/avaliacoes')
async def ratings(cid:str,mid:str,s:dict=Depends(rh)):
    m=await model_for(mid,cid,s)
    own=await fetch_one('SELECT ID_Avaliacao FROM ATS_Avaliacoes WHERE ID_Modelo=%s AND ID_Candidaturas=%s AND ID_Usuarios=%s',(mid,cid,s['id_usuario']))
    if m['Cego'] and not own: return {'bloqueado':True,'avaliacoes':[],'media':None}
    rows=await fetch_all('SELECT a.*,u.Nome AS Avaliador FROM ATS_Avaliacoes a JOIN Usuarios u ON u.ID_Usuarios=a.ID_Usuarios WHERE ID_Modelo=%s AND ID_Candidaturas=%s ORDER BY a.CriadoEm,a.ID_Avaliacao',(mid,cid))
    for r in rows: r['Notas']=unpack(r['Notas'])
    return {'bloqueado':False,'avaliacoes':rows,'media':sum(float(r['Media']) for r in rows)/len(rows) if rows else None}

class Consent(BaseModel):
    autorizado: bool

@router.get('/consentimentos')
async def consents(s:dict=Depends(exigir_tipo('candidato'))):
    c=await fetch_one('SELECT ID_Candidatos FROM Candidatos WHERE ID_Usuarios=%s AND Ativo=1',(s['id_usuario'],))
    return await fetch_all("""SELECT DISTINCT e.ID_Empresas,e.NomeFantasia,COALESCE(co.Autorizado,0) AS Autorizado
    FROM Candidaturas ca JOIN Vagas v ON v.ID_Vagas=ca.ID_Vagas JOIN Empresas e ON e.ID_Empresas=v.ID_Empresas AND e.Ativo=1
    LEFT JOIN ATS_Consentimentos co ON co.ID_Empresas=e.ID_Empresas AND co.ID_Candidatos=ca.ID_Candidatos WHERE ca.ID_Candidatos=%s""",(c['ID_Candidatos'],))

@router.put('/consentimentos/{eid}')
async def consent(eid:str,d:Consent,request:Request,s:dict=Depends(exigir_tipo('candidato'))):
    c=await fetch_one('SELECT ID_Candidatos FROM Candidatos WHERE ID_Usuarios=%s AND Ativo=1',(s['id_usuario'],))
    cid=c['ID_Candidatos']
    if not await fetch_one('SELECT ca.ID_Candidaturas FROM Candidaturas ca JOIN Vagas v ON v.ID_Vagas=ca.ID_Vagas WHERE ca.ID_Candidatos=%s AND v.ID_Empresas=%s LIMIT 1',(cid,eid)): fail(403,'Empresa sem relacionamento com o candidato.')
    await fetch_one('SELECT ID_Candidatos FROM Candidatos WHERE ID_Candidatos=%s FOR UPDATE',(cid,))
    old=await fetch_one('SELECT * FROM ATS_Consentimentos WHERE ID_Candidatos=%s AND ID_Empresas=%s',(cid,eid))
    if old: await execute('UPDATE ATS_Consentimentos SET Autorizado=%s,AtualizadoEm=NOW() WHERE ID_Candidatos=%s AND ID_Empresas=%s',(d.autorizado,cid,eid))
    else: await execute('INSERT INTO ATS_Consentimentos(ID_Candidatos,ID_Empresas,Autorizado) VALUES (%s,%s,%s)',(cid,eid,d.autorizado))
    if not d.autorizado:
        await execute('UPDATE ATS_Membros SET Ativo=0,Notas=NULL,Tags=%s,Favorito=0 WHERE ID_Candidatos=%s AND ID_Pool IN (SELECT ID_Pool FROM ATS_Pools WHERE ID_Empresas=%s)',('[]',cid,eid))
    await registrar_auditoria(request,'ats.consentimento','ATS_Consentimentos',s['id_usuario'],eid,old,d.model_dump())
    return {'autorizado':d.autorizado}

class PoolData(BaseModel):
    nome: str=Field(min_length=1,max_length=150,pattern=r'.*\S.*')

@router.get('/pools')
async def pools(id_empresa:str|None=None,s:dict=Depends(rh)):
    e=await company(s,id_empresa)
    return await fetch_all('SELECT * FROM ATS_Pools WHERE ID_Empresas=%s AND Ativo=1 ORDER BY Nome',(e['ID_Empresas'],))

@router.post('/pools',status_code=201)
async def create_pool(d:PoolData,request:Request,id_empresa:str|None=None,s:dict=Depends(rh)):
    e=await company(s,id_empresa);pid=novo_uuid()
    await execute('INSERT INTO ATS_Pools(ID_Pool,ID_Empresas,Nome) VALUES (%s,%s,%s)',(pid,e['ID_Empresas'],d.nome.strip()))
    await registrar_auditoria(request,'ats.pool.criar','ATS_Pools',s['id_usuario'],pid,novo=d.model_dump())
    return {'ID_Pool':pid,'Nome':d.nome}

@router.put('/pools/{id}')
async def rename_pool(id:str,d:PoolData,request:Request,s:dict=Depends(rh)):
    old=await pool(id,s)
    await execute('UPDATE ATS_Pools SET Nome=%s WHERE ID_Pool=%s',(d.nome.strip(),id))
    await registrar_auditoria(request,'ats.pool.editar','ATS_Pools',s['id_usuario'],id,old,d.model_dump())
    return d.model_dump()

@router.delete('/pools/{id}')
async def archive_pool(id:str,request:Request,s:dict=Depends(rh)):
    old=await pool(id,s)
    await execute('UPDATE ATS_Pools SET Ativo=0 WHERE ID_Pool=%s',(id,))
    await registrar_auditoria(request,'ats.pool.arquivar','ATS_Pools',s['id_usuario'],id,old)
    return {'mensagem':'Pool arquivado.'}

async def eligible(cid,eid):
    # Prior relationship alone does not imply authorization for the Talent CRM.
    c=await fetch_one("""SELECT p.ID_Candidatos FROM Candidatos p JOIN Usuarios u ON u.ID_Usuarios=p.ID_Usuarios AND u.Ativo=1
    JOIN ATS_Consentimentos co ON co.ID_Candidatos=p.ID_Candidatos AND co.ID_Empresas=%s AND co.Autorizado=1
    WHERE p.ID_Candidatos=%s AND p.Ativo=1 AND EXISTS(SELECT 1 FROM Candidaturas ca JOIN Vagas v ON v.ID_Vagas=ca.ID_Vagas WHERE ca.ID_Candidatos=p.ID_Candidatos AND v.ID_Empresas=%s)""",(eid,cid,eid))
    if not c: fail(403,'Candidato sem vínculo e autorização para o banco desta empresa.')

class Member(BaseModel):
    tags: list[str]=Field(default_factory=list,max_length=20)
    favorito: bool=False
    notas: str|None=Field(default=None,max_length=10000)
    @model_validator(mode='after')
    def tags_limit(self):
        if any(not t.strip() or len(t)>60 for t in self.tags): raise ValueError('Tags devem ter entre 1 e 60 caracteres.')
        self.tags=list(dict.fromkeys(t.strip() for t in self.tags))
        return self

@router.put('/pools/{pid}/candidatos/{cid}')
async def member(pid:str,cid:str,d:Member,request:Request,s:dict=Depends(rh)):
    p=await pool(pid,s)
    await fetch_one('SELECT ID_Candidatos FROM Candidatos WHERE ID_Candidatos=%s FOR UPDATE',(cid,))
    await eligible(cid,p['ID_Empresas'])
    old=await fetch_one('SELECT * FROM ATS_Membros WHERE ID_Pool=%s AND ID_Candidatos=%s',(pid,cid))
    if old: await execute('UPDATE ATS_Membros SET Tags=%s,Favorito=%s,Notas=%s,Ativo=1 WHERE ID_Pool=%s AND ID_Candidatos=%s',(pack(d.tags),d.favorito,d.notas,pid,cid))
    else: await execute('INSERT INTO ATS_Membros(ID_Pool,ID_Candidatos,Tags,Favorito,Notas) VALUES (%s,%s,%s,%s,%s)',(pid,cid,pack(d.tags),d.favorito,d.notas))
    await registrar_auditoria(request,'ats.pool.membro','ATS_Membros',s['id_usuario'],cid,old,d.model_dump())
    return d.model_dump()

@router.delete('/pools/{pid}/candidatos/{cid}')
async def remove_member(pid:str,cid:str,request:Request,s:dict=Depends(rh)):
    await pool(pid,s)
    await execute('UPDATE ATS_Membros SET Ativo=0 WHERE ID_Pool=%s AND ID_Candidatos=%s',(pid,cid))
    await registrar_auditoria(request,'ats.pool.remover','ATS_Membros',s['id_usuario'],cid,novo={'pool':pid})
    return {'mensagem':'Candidato removido do pool.'}

@router.get('/talentos')
async def talents(id_empresa:str|None=None,nome:str=Query('',max_length=150),skill:str=Query('',max_length=100),formacao:str=Query('',max_length=150),experiencia:str=Query('',max_length=150),tag:str=Query('',max_length=60),id_pool:str|None=None,favorito:bool=False,avaliado:bool=False,pagina:int=Query(1,ge=1),s:dict=Depends(rh)):
    e=await company(s,id_empresa);eid=e['ID_Empresas']
    if id_pool:
        p=await pool(id_pool,s)
        if p['ID_Empresas']!=eid: fail(403,'Pool de outra empresa.')
    q=""" FROM Candidatos c JOIN Usuarios u ON u.ID_Usuarios=c.ID_Usuarios AND u.Ativo=1
    JOIN ATS_Consentimentos co ON co.ID_Candidatos=c.ID_Candidatos AND co.ID_Empresas=%s AND co.Autorizado=1
    WHERE c.Ativo=1 AND EXISTS(SELECT 1 FROM Candidaturas ca JOIN Vagas v ON v.ID_Vagas=ca.ID_Vagas WHERE ca.ID_Candidatos=c.ID_Candidatos AND v.ID_Empresas=%s)"""
    args=[eid,eid]
    if nome: q+=' AND u.Nome LIKE %s';args.append('%'+nome+'%')
    if skill:
        q+=' AND EXISTS(SELECT 1 FROM Candidato_Habilidades ch JOIN Habilidades h ON h.ID_Habilidades=ch.ID_Habilidades WHERE ch.ID_Candidatos=c.ID_Candidatos AND h.Nome LIKE %s)';args.append('%'+skill+'%')
    if formacao:
        q+=" AND (EXISTS(SELECT 1 FROM Formacoes f WHERE f.ID_Candidatos=c.ID_Candidatos AND (f.Curso LIKE %s OR f.Instituicao LIKE %s)) OR EXISTS(SELECT 1 FROM Candidato_Itens i WHERE i.ID_Candidatos=c.ID_Candidatos AND i.Tipo='curso' AND i.Titulo LIKE %s))";args.extend(['%'+formacao+'%']*3)
    if experiencia:
        q+=' AND EXISTS(SELECT 1 FROM Experiencias x WHERE x.ID_Candidatos=c.ID_Candidatos AND (x.Cargo LIKE %s OR x.Descricao LIKE %s))';args.extend(['%'+experiencia+'%']*2)
    if id_pool or favorito or tag:
        q+=' AND EXISTS(SELECT 1 FROM ATS_Membros m JOIN ATS_Pools p ON p.ID_Pool=m.ID_Pool WHERE m.ID_Candidatos=c.ID_Candidatos AND m.Ativo=1 AND p.Ativo=1 AND p.ID_Empresas=%s';args.append(eid)
        if id_pool: q+=' AND m.ID_Pool=%s';args.append(id_pool)
        if favorito: q+=' AND m.Favorito=1'
        if tag: q+=' AND m.Tags LIKE %s';args.append('%'+json.dumps(tag,ensure_ascii=False)+'%')
        q+=')'
    if avaliado:
        q+=' AND EXISTS(SELECT 1 FROM ATS_Avaliacoes a JOIN Candidaturas ca ON ca.ID_Candidaturas=a.ID_Candidaturas JOIN Vagas v ON v.ID_Vagas=ca.ID_Vagas WHERE ca.ID_Candidatos=c.ID_Candidatos AND v.ID_Empresas=%s)';args.append(eid)
    count=await fetch_one('SELECT COUNT(*) AS Total'+q,tuple(args))
    rows=await fetch_all('SELECT c.ID_Candidatos,c.TituloProfissional,c.Cidade,c.Estado,u.Nome'+q+' ORDER BY u.Nome,c.ID_Candidatos LIMIT 20 OFFSET %s',tuple(args+[(pagina-1)*20]))
    return {'total':count['Total'],'pagina':pagina,'itens':rows}

@router.get('/talentos/{cid}/historico')
async def talent_history(cid:str,id_empresa:str|None=None,s:dict=Depends(rh)):
    e=await company(s,id_empresa)
    await eligible(cid,e['ID_Empresas'])
    rows=await fetch_all('SELECT c.ID_Candidaturas,c.ID_Vagas,c.ID_Status_Candidatura,c.CriadaEm,v.Titulo,a.Estado,a.Motivo FROM Candidaturas c JOIN Vagas v ON v.ID_Vagas=c.ID_Vagas LEFT JOIN ATS_Cards a ON a.ID_Candidaturas=c.ID_Candidaturas WHERE c.ID_Candidatos=%s AND v.ID_Empresas=%s ORDER BY c.CriadaEm DESC',(cid,e['ID_Empresas']))
    for c in rows:
        c['scorecards']=[]
        for m in await templates(c['ID_Candidaturas'],s):
            result=await ratings(c['ID_Candidaturas'],m['ID_Modelo'],s)
            c['scorecards'].append({'modelo':m,**result})
    members=await fetch_all('SELECT m.*,p.Nome FROM ATS_Membros m JOIN ATS_Pools p ON p.ID_Pool=m.ID_Pool WHERE m.ID_Candidatos=%s AND p.ID_Empresas=%s AND p.Ativo=1 AND m.Ativo=1',(cid,e['ID_Empresas']))
    for m in members: m['Tags']=unpack(m['Tags'])
    return {'processos':rows,'pools':members}

class Invite(BaseModel):
    id_vaga: str=Field(min_length=1,max_length=36)

@router.post('/talentos/{cid}/convites',status_code=201)
async def invite(cid:str,d:Invite,request:Request,s:dict=Depends(rh)):
    v=await job(d.id_vaga,s)
    await eligible(cid,v['ID_Empresas'])
    if not v['Ativo'] or v['ID_Status_Vaga']!=2: fail(409,'Convites exigem uma vaga publicada.')
    if await fetch_one('SELECT ID_Convite FROM ATS_Convites WHERE ID_Candidatos=%s AND ID_Vagas=%s',(cid,d.id_vaga)): fail(409,'Convite já enviado para esta vaga.')
    iid=novo_uuid()
    await execute('INSERT INTO ATS_Convites(ID_Convite,ID_Candidatos,ID_Vagas,ID_Usuarios) VALUES (%s,%s,%s,%s)',(iid,cid,d.id_vaga,s['id_usuario']))
    c=await fetch_one('SELECT ID_Usuarios FROM Candidatos WHERE ID_Candidatos=%s',(cid,))
    await notificar_usuario(id_usuario=c['ID_Usuarios'],titulo='Convite para nova vaga',mensagem=f"Você foi convidado para a vaga {v['Titulo']}. Acesse Vagas e busque pelo título para decidir se deseja se candidatar.",tipo='candidatura')
    await registrar_auditoria(request,'ats.convite','ATS_Convites',s['id_usuario'],iid,novo=d.model_dump())
    return {'ID_Convite':iid,'mensagem':'Convite enviado; candidatura depende da escolha do candidato.'}


async def sync_legacy(id,status,s,request):
    """Legacy cancellation/status still records the ATS transition, never deletes it."""
    old=await fetch_one('SELECT * FROM ATS_Cards WHERE ID_Candidaturas=%s FOR UPDATE',(id,))
    if not old: return
    state={5:'aprovado',6:'reprovado',7:'desistente'}.get(status,'ativo')
    if status==6 and not (old.get('Motivo') or '').strip():
        fail(422,'Use o Pipeline ATS para reprovar e informar o motivo.')
    await execute('UPDATE ATS_Cards SET Estado=%s,Versao=Versao+1 WHERE ID_Candidaturas=%s',(state,id))
    new=await fetch_one('SELECT * FROM ATS_Cards WHERE ID_Candidaturas=%s',(id,))
    await event(id,'ats.status',old,new,s,request)
