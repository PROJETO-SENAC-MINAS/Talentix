"""Regressões adicionais com MySQL real, concorrência, rollback e worker.

Somente banco descartável. Execute depois de run_scenarios.py.
"""
import asyncio
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid
import httpx
import pymysql
from pymysql.constants import CLIENT

if os.getenv("TALENTIX_ISOLATED_TESTS") != "1":
    raise SystemExit("TALENTIX_ISOLATED_TESTS=1 é obrigatório.")
assert os.environ["DB_HOST"] in ("127.0.0.1", "localhost")
assert os.environ["DB_NAME"].startswith("talentix_test") or (os.environ["DB_PORT"] == "33307" and os.environ["DB_NAME"] == "talentix")
BASE = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(BASE))
API = os.getenv("TEST_API_URL", "http://127.0.0.1:8000")
OUT = Path(os.getenv("TEST_RESULTS_DIR", "test-results")); OUT.mkdir(parents=True,exist_ok=True)
config = dict(host=os.environ["DB_HOST"],port=int(os.environ["DB_PORT"]),user=os.environ["DB_USER"],password=os.environ["DB_PASSWORD"],database=os.environ["DB_NAME"],autocommit=True)
conn = pymysql.connect(**config)
root = pymysql.connect(host=config["host"],port=config["port"],user=os.getenv("TEST_ROOT_USER","root"),password=os.environ["TEST_ROOT_PASSWORD"],autocommit=True,client_flag=CLIENT.MULTI_STATEMENTS)
results = []
clients = []
PASSWORD="Regressao123!"
nonce=uuid.uuid4().hex[:10]


def check(name, value):
    results.append({"case":name,"passed":bool(value)})
    if not value: raise AssertionError(name)


def scalar(statement,params=(),connection=conn):
    with connection.cursor() as cur:
        cur.execute(statement,params)
        row=cur.fetchone()
        return row[0] if row else None


def execute(statement,params=(),connection=conn):
    with connection.cursor() as cur:
        cur.execute(statement,params)


class TalentixTestClient(httpx.Client):
    """Cliente de integração que reproduz o double-submit CSRF do navegador."""
    def request(self, method, url, **kwargs):
        if method.upper() in {"POST", "PUT", "PATCH", "DELETE"}:
            csrf = self.cookies.get("talentix_csrf")
            if csrf:
                headers = dict(kwargs.get("headers") or {})
                headers.setdefault("X-CSRF-Token", csrf)
                kwargs["headers"] = headers
        return super().request(method, url, **kwargs)


def client():
    c=TalentixTestClient(base_url=API,timeout=30,trust_env=False);clients.append(c);return c


def signup(role,name):
    c=client();email=f'{name.lower().replace(" ","-")}-{nonce}@regressao.example.com';payload={"nome":name,"email":email,"senha":PASSWORD}
    if role=='empresa':payload.update(razao_social=name,cnpj=str(int(uuid.uuid4().hex[:12],16)).zfill(14)[-14:])
    response=c.post('/auth/cadastro/'+role,json=payload);check('cadastro '+name,response.status_code==201)
    data=response.json();check('login '+name,c.post('/auth/login',json={"email":email,"senha":PASSWORD}).status_code==200)
    return c,data,email


def worker():
    completed=subprocess.run([sys.executable,'-m','app.worker_ia','--once'],cwd=BASE,env=os.environ.copy(),capture_output=True,text=True,timeout=90)
    if completed.returncode: print(completed.stderr[-2500:])
    check('worker executa sem erro',completed.returncode==0)


error=None
try:
    company,e,email_company=signup('empresa','Empresa regressao')
    candidate,c,email_candidate=signup('candidato','Candidato regressao')
    recruit,r,email_recruit=signup('recrutador','Recrutador regressao')
    other,e2,_=signup('empresa','Outra empresa regressao')
    admin=client();check('admin autentica',admin.post('/auth/login',json={"email":"admin@audit.example.com","senha":"Auditoria123!"}).status_code==200)
    # 20 leituras paralelas logo após o commit, no isolamento padrão.
    def read_profile(_):
        response=candidate.get('/candidatos/me');return response.status_code==200 and response.json()['ID_Candidatos']==c['id_candidato']
    with ThreadPoolExecutor(max_workers=8) as pool:check('pool enxerga cadastro em 20 leituras paralelas',all(pool.map(read_profile,range(20))))
    async def atomic_pool():
        from app.db.database import init_pool,close_pool,execute,fetch_one,transaction
        await init_pool()
        uid=str(uuid.uuid4())
        try:
            try:
                async with transaction():
                    await execute('INSERT INTO Usuarios(ID_Usuarios,Nome,Email,SenhaHash) VALUES (%s,%s,%s,%s)',(uid,'Rollback',f'rollback-{nonce}@regressao.example.com','test'))
                    raise RuntimeError('Falha simulada depois da primeira escrita')
            except RuntimeError:pass
            check('rollback real remove escrita intermediaria',await fetch_one('SELECT ID_Usuarios FROM Usuarios WHERE ID_Usuarios=%s',(uid,)) is None)
            async with transaction():
                await execute('INSERT INTO Usuarios(ID_Usuarios,Nome,Email,SenhaHash) VALUES (%s,%s,%s,%s)',(uid,'Commit',f'commit-{nonce}@regressao.example.com','test'))
            check('conexao retorna utilizavel depois de rollback',await fetch_one('SELECT ID_Usuarios FROM Usuarios WHERE ID_Usuarios=%s',(uid,)) is not None)
        finally:await close_pool()
    asyncio.run(atomic_pool())
    # Provoca falha no segundo INSERT do cadastro; não deixa usuário órfão.
    execute(f"USE `{config['database']}`",connection=root)
    execute("""CREATE TRIGGER talentix_test_signup_failure BEFORE INSERT ON Empresas FOR EACH ROW
               BEGIN IF NEW.RazaoSocial='Falha rollback HTTP' THEN SIGNAL SQLSTATE '23000' SET MYSQL_ERRNO=1062, MESSAGE_TEXT='Falha injetada pelo teste'; END IF; END""",connection=root)
    rollback_email=f'atomicidade-{nonce}@regressao.example.com'
    payload={'nome':'Atomicidade','email':rollback_email,'senha':PASSWORD,'razao_social':'Falha rollback HTTP','cnpj':'77889900112233'}
    try:
        check('falha no perfil de empresa retorna conflito',client().post('/auth/cadastro/empresa',json=payload).status_code==409)
        check('cadastro HTTP nao deixa usuario orfao',scalar('SELECT COUNT(*) FROM Usuarios WHERE Email=%s',(rollback_email,))==0)
    finally:execute('DROP TRIGGER talentix_test_signup_failure',connection=root)
    payload['razao_social']='Cadastro corrigido'
    check('reenvio corrigido apos rollback funciona',client().post('/auth/cadastro/empresa',json=payload).status_code==201)
    oversized={**payload,'email':f'comprimento-{nonce}@regressao.example.com','razao_social':'x'*501}
    check('razao social longa rejeitada antes da persistencia',client().post('/auth/cadastro/empresa',json=oversized).status_code==422)
    check('validacao nao grava usuario',scalar('SELECT COUNT(*) FROM Usuarios WHERE Email=%s',(oversized['email'],))==0)
    # A conta de recrutador espera vínculo; o cookie antigo ganha o papel correto
    # após a concessão e perde o acesso imediatamente após a revogação.
    check('recrutador novo aguarda vinculo',recruit.get('/auth/me').json()['tipo_usuario']=='usuario')
    linked=company.post(f"/empresas/{e['id_empresa']}/recrutadores",json={'id_usuario_recrutador':r['id_usuario'],'cargo':'RH'})
    check('responsavel concede vinculo',linked.status_code==201);rid=linked.json()['ID_Recrutadores']
    check('papel atualizado sem confiar no cookie antigo',recruit.get('/auth/me').json()['tipo_usuario']=='recrutador')
    check('recrutador encontra somente sua empresa',recruit.get('/empresas/me').json()['ID_Empresas']==e['id_empresa'])
    job_payload={'id_empresa':e['id_empresa'],'titulo':'Python SQL regressao','descricao':'Desenvolvimento Python SQL e testes de software'}
    job_response=company.post('/vagas',json=job_payload);check('empresa cria rascunho',job_response.status_code==201);vid=job_response.json()['ID_Vagas']
    foreign=other.post('/vagas',json={**job_payload,'id_empresa':e2['id_empresa']});check('outra empresa cria rascunho',foreign.status_code==201)
    check('recrutador pode ler proprio rascunho',recruit.get('/vagas/'+vid).status_code==200)
    check('recrutador nao le rascunho de outra empresa',recruit.get('/vagas/'+foreign.json()['ID_Vagas']).status_code==404)
    check('recrutador nao administra financeiro',recruit.get(f"/empresas/{e['id_empresa']}/assinatura").status_code==403)
    check('recrutador pode publicar vaga vinculada',recruit.patch('/vagas/'+vid+'/publicar').status_code==200)
    application=candidate.post('/candidaturas',json={'id_vaga':vid});check('candidatura publicada',application.status_code==201);aid=application.json()['ID_Candidaturas']
    check('primeira etapa criada atomicamente',scalar('SELECT COUNT(*) FROM Etapas_Processo WHERE ID_Candidaturas=%s',(aid,))==1)
    check('recrutador administra propria candidatura',recruit.get('/candidaturas/'+aid).status_code==200)
    check('outra empresa nao administra candidatura',other.get('/candidaturas/'+aid).status_code==403)
    # O índice é calculado de verdade, sem respostas fixas ou callback fictício.
    python_skill=admin.post('/habilidades',json={'nome':'Python regressao'}).json()['ID_Habilidades']
    sql_skill=admin.post('/habilidades',json={'nome':'SQL regressao'}).json()['ID_Habilidades']
    candidate.post(f"/candidatos/{c['id_candidato']}/habilidades",json={'id_habilidade':python_skill,'nivel':3})
    company.post('/vagas/'+vid+'/habilidades',json={'id_habilidade':python_skill,'obrigatoria':True,'nivel_minimo':2})
    company.post('/vagas/'+vid+'/habilidades',json={'id_habilidade':sql_skill,'obrigatoria':True,'nivel_minimo':2})
    course=admin.post('/cursos',json={'titulo':'SQL regressao completo','descricao':'Aprenda SQL regressao','categoria':'SQL regressao'})
    check('curso de lacuna criado',course.status_code==201)
    analysis=candidate.post('/analises-ia',json={'id_candidato':c['id_candidato'],'id_vaga':vid,'id_candidatura':aid});check('analise enfileirada',analysis.status_code==201);analysis_id=analysis.json()['ID_Analises_IA']
    worker();result=candidate.get('/analises-ia/'+analysis_id).json()
    check('worker conclui analise real',result['ID_Status_Processamento_IA']==3 and 0<=result['ScoreCompatibilidade']<=100 and result['ModeloIA']=='talentix-tfidf-habilidades-v1')
    check('worker explica habilidade e lacuna', 'Python regressao' in result['PontosFortes'] and 'SQL regressao' in result['Lacunas'])
    recs=candidate.get(f"/candidatos/{c['id_candidato']}/recomendacoes-curso").json()
    check('worker recomenda curso da lacuna',any(x['ID_Cursos']==course.json()['ID_Cursos'] for x in recs))
    # Recupera execução interrompida e dois workers não duplicam efeitos.
    retry=candidate.post('/analises-ia',json={'id_candidato':c['id_candidato'],'id_vaga':vid}).json()['ID_Analises_IA']
    execute('UPDATE Analises_IA SET ID_Status_Processamento_IA=2, ProcessamentoIniciadoEm=DATE_SUB(NOW(), INTERVAL 11 MINUTE) WHERE ID_Analises_IA=%s',(retry,))
    worker();check('worker recupera job interrompido',candidate.get('/analises-ia/'+retry).json()['ID_Status_Processamento_IA']==3)
    parallel_ids=[candidate.post('/analises-ia',json={'id_candidato':c['id_candidato'],'id_vaga':vid}).json()['ID_Analises_IA'] for _ in range(2)]
    previous_notifications=scalar('SELECT COUNT(*) FROM Notificacoes WHERE ID_Usuarios=%s AND Tipo=%s',(c['id_usuario'],'analise'))
    workers=[subprocess.Popen([sys.executable,'-m','app.worker_ia','--once'],cwd=BASE,env=os.environ.copy(),stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True) for _ in range(2)]
    for process in workers:
        stdout,stderr=process.communicate(timeout=90)
        if process.returncode:print(stderr[-2500:])
        check('worker paralelo encerra sem erro',process.returncode==0)
    check('workers paralelos concluem ambos os registros',all(candidate.get('/analises-ia/'+id).json()['ID_Status_Processamento_IA']==3 for id in parallel_ids))
    check('workers paralelos nao duplicam notificacoes',scalar('SELECT COUNT(*) FROM Notificacoes WHERE ID_Usuarios=%s AND Tipo=%s',(c['id_usuario'],'analise'))==previous_notifications+2)
    # Estado financeiro terminal e callbacks simultâneos são idempotentes.
    sub=admin.post('/assinaturas',json={'id_empresa':e['id_empresa'],'plano':'Teste','valor':'50.00','inicio':'2026-01-01'});check('assinatura criada',sub.status_code==201);sid=sub.json()['ID_Assinaturas']
    check('segunda assinatura ativa bloqueada',admin.post('/assinaturas',json={'id_empresa':e['id_empresa'],'plano':'Outro','valor':'50.00','inicio':'2026-01-01'}).status_code==409)
    payment=company.post('/pagamentos',json={'id_assinatura':sid,'valor':'50.00','transacao_id':'concorrencia-'+nonce});check('pagamento registrado',payment.status_code==201);pid=payment.json()['ID_Pagamentos']
    before=scalar('SELECT COUNT(*) FROM Notificacoes WHERE ID_Usuarios=%s AND Tipo=%s',(e['id_usuario'],'pagamento'))
    def callback(_):
        response=httpx.patch(API+f'/pagamentos/{pid}/processar?aprovado=true',headers={'X-Payment-Webhook-Token':os.environ['PAYMENT_WEBHOOK_TOKEN']},timeout=30)
        return response.status_code,response.json().get('PagoEm')
    with ThreadPoolExecutor(max_workers=6) as pool:answers=list(pool.map(callback,range(6)))
    check('seis callbacks paralelos retornam mesmo pagamento',all(code==200 for code,_ in answers) and len({date for _,date in answers})==1)
    check('callbacks paralelos notificam uma unica vez',scalar('SELECT COUNT(*) FROM Notificacoes WHERE ID_Usuarios=%s AND Tipo=%s',(e['id_usuario'],'pagamento'))==before+1)
    check('callback contrario nao altera estado terminal',httpx.patch(API+f'/pagamentos/{pid}/processar?aprovado=false',headers={'X-Payment-Webhook-Token':os.environ['PAYMENT_WEBHOOK_TOKEN']}).status_code==409)
    company.delete('/recrutadores/'+rid)
    check('remocao de recrutador revoga cookie existente',recruit.get('/candidaturas/'+aid).status_code==401)
    # Recuperação de senha invalida todas as sessões já emitidas.
    from itsdangerous import URLSafeTimedSerializer
    old_hash=scalar('SELECT SenhaHash FROM Usuarios WHERE ID_Usuarios=%s',(c['id_usuario'],))
    token=URLSafeTimedSerializer(os.environ['SECRET_KEY'],salt='talentix-reset-senha').dumps({'id_usuario':c['id_usuario'],'fingerprint':old_hash[-16:]})
    check('redefinicao de senha funciona',client().post('/auth/redefinir-senha',json={'token':token,'nova_senha':'NovaRegressao123!'}).status_code==200)
    check('redefinicao revoga sessao anterior',candidate.get('/auth/me').status_code==401)
    # Migração no esquema anterior, preservação de usuário e repetição segura.
    migration_name='talentix_test_migration_'+nonce
    legacy=(Path(__file__).parent/'fixtures/legacy_schema.sql').read_text().replace('talentix',migration_name)
    execute(legacy,connection=root)
    with root.cursor() as cur:
        while cur.nextset():pass
    from app.core.config import settings
    import migrate
    old_name=settings.DB_NAME;settings.DB_NAME=migration_name
    migration_conn=pymysql.connect(host=config['host'],port=config['port'],user=os.getenv('TEST_ROOT_USER','root'),password=os.environ['TEST_ROOT_PASSWORD'],database=migration_name,autocommit=True,client_flag=CLIENT.MULTI_STATEMENTS)
    try:
        execute("INSERT INTO Usuarios(ID_Usuarios,Nome,Email,SenhaHash) VALUES ('preservado','Preservado','preservado@regressao.example.com','test')",connection=migration_conn)
        execute("INSERT INTO Empresas(ID_Empresas,ID_Usuarios,RazaoSocial,Cnpj) VALUES ('empresa-preservada','preservado','Empresa preservada','00112233445566')",connection=migration_conn)
        execute("INSERT INTO Assinaturas(ID_Assinaturas,ID_Empresas,ID_Status_Assinatura,Plano,Valor,Inicio) VALUES ('ativa-1','empresa-preservada',1,'Teste',50,'2026-01-01'),('ativa-2','empresa-preservada',1,'Teste',50,'2026-01-01')",connection=migration_conn)
        try:
            migrate.migrate(migration_conn)
            check('migracao bloqueia dados conflitantes',False)
        except RuntimeError:
            check('migracao bloqueia dados conflitantes',True)
        check('migracao nao apaga assinaturas conflitantes',scalar('SELECT COUNT(*) FROM Assinaturas',connection=migration_conn)==2)
        check('preflight interrompe antes de DDL',scalar("SELECT COUNT(*) FROM information_schema.TABLES WHERE TABLE_SCHEMA=%s AND TABLE_NAME='Schema_Migrations'",(migration_name,),migration_conn)==0)
        # Simula revisão manual exclusivamente na fixture descartável.
        execute("UPDATE Assinaturas SET ID_Status_Assinatura=3 WHERE ID_Assinaturas='ativa-2'",connection=migration_conn)
        check('migracao de banco existente funciona',migrate.migrate(migration_conn))
        check('migracao preserva usuario existente',scalar('SELECT COUNT(*) FROM Usuarios WHERE ID_Usuarios=%s',('preservado',),migration_conn)==1)
        check('migracao repetida nao altera dados',migrate.migrate(migration_conn) is False)
        check('003 registrada',scalar("SELECT COUNT(*) FROM Schema_Migrations WHERE Versao='003_security_hardening'",connection=migration_conn)==1)
        check('004 cria importacoes de curriculo',scalar("SELECT COUNT(*) FROM information_schema.TABLES WHERE TABLE_SCHEMA=%s AND TABLE_NAME='Curriculo_Importacoes'",(migration_name,),migration_conn)==1)
        import tempfile, shutil
        with tempfile.TemporaryDirectory() as tmp:
            directory=Path(tmp)
            for source in migrate.discover_migrations():shutil.copy(source,directory/source.name)
            future=directory/'900_future_test.sql'
            future.write_text("CREATE TABLE IF NOT EXISTS Future_Test (id INT PRIMARY KEY, value VARCHAR(50)); INSERT INTO Future_Test VALUES (1, 'texto; preservado');")
            check('migration futura descoberta sem editar runner',migrate.migrate(migration_conn,directory))
            check('SQL respeita ponto e virgula em strings',scalar('SELECT value FROM Future_Test WHERE id=1',connection=migration_conn)=='texto; preservado')
            check('migration futura roda uma vez',migrate.migrate(migration_conn,directory) is False)
            future.write_text(future.read_text()+' SELECT 1;')
            try:
                migrate.migrate(migration_conn,directory)
                check('checksum rejeita migration alterada',False)
            except RuntimeError:
                check('checksum rejeita migration alterada',True)
            future.unlink()
            failed=directory/'901_failure_test.sql'
            failed.write_text('CREATE TABLE IF NOT EXISTS Retry_Test(id INT); INVALID SQL;')
            try:
                migrate.migrate(migration_conn,directory)
                check('migration falha propaga erro',False)
            except pymysql.Error:
                check('migration falha propaga erro',True)
            check('migration falha nao registrada',scalar("SELECT COUNT(*) FROM Schema_Migrations WHERE Versao='901_failure_test'",connection=migration_conn)==0)
            failed.write_text('CREATE TABLE IF NOT EXISTS Retry_Test(id INT);')
            check('migration interrompida pode ser retomada',migrate.migrate(migration_conn,directory))

        check('migracao cria unicidade de pagamentos',scalar("SELECT COUNT(*) FROM information_schema.STATISTICS WHERE TABLE_SCHEMA=%s AND INDEX_NAME='UQ_Pagamentos_TransacaoId'",(migration_name,),migration_conn)==1)
    finally:
        settings.DB_NAME=old_name;migration_conn.close()
        execute(f'DROP DATABASE `{migration_name}`',connection=root)
except Exception as exc:
    error=f'{type(exc).__name__}: {exc}'
    print(error)
finally:
    for c in clients:c.close()
    conn.close();root.close()
    summary={'cases':len(results),'passed':sum(r['passed'] for r in results),'failed':sum(not r['passed'] for r in results),'execution_error':error}
    (OUT/'mysql-regressions.json').write_text(json.dumps({'summary':summary,'cases':results},ensure_ascii=False,indent=2))
    print(json.dumps(summary,ensure_ascii=False))
sys.exit(1 if error or summary['failed'] else 0)
