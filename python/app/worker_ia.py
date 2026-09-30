"""Worker local: python -m app.worker_ia [--once]. Sem serviços externos."""
import argparse
import asyncio
import logging
from app.core.config import settings
from app.core.matching import calculate_match, normalize
from app.core.notificar import notificar_usuario
from app.core.security import novo_uuid
from app.db.database import init_pool, close_pool, fetch_one, fetch_all, execute, transaction
from app.routers.ia import processar_analise_ia, processar_recomendacao_vaga, AnaliseIAResultado, RecomendacaoVagaResultado

logger = logging.getLogger(__name__)
JOBS = (("Analises_IA", "ID_Analises_IA"), ("Recomendacoes_Vaga", "ID_Recomendacoes_Vaga"))


async def claim_job():
    for table, key in JOBS:
        async with transaction():
            created = "CriadoEm" if table == "Analises_IA" else "CriadaEm"
            row = await fetch_one(f"""SELECT * FROM {table}
                WHERE ID_Status_Processamento_IA=1 OR (ID_Status_Processamento_IA=2
                  AND ProcessamentoIniciadoEm < DATE_SUB(NOW(), INTERVAL 10 MINUTE))
                ORDER BY {created} LIMIT 1 FOR UPDATE SKIP LOCKED""")
            if row:
                await execute(f"UPDATE {table} SET ID_Status_Processamento_IA=2, ProcessamentoIniciadoEm=NOW(), ErroProcessamento=NULL WHERE {key}=%s", (row[key],))
                claimed = await fetch_one(f"SELECT * FROM {table} WHERE {key}=%s", (row[key],))
                return table, key, claimed
    return None


async def match_context(candidate_id, job_id):
    profile = await fetch_one("""SELECT c.* FROM Candidatos c JOIN Usuarios u ON u.ID_Usuarios=c.ID_Usuarios
                               WHERE c.ID_Candidatos=%s AND c.Ativo=1 AND u.Ativo=1""", (candidate_id,))
    job = await fetch_one("""SELECT v.* FROM Vagas v JOIN Empresas e ON e.ID_Empresas=v.ID_Empresas
                           WHERE v.ID_Vagas=%s AND v.Ativo=1 AND e.Ativo=1""", (job_id,))
    if not profile or not job:
        raise ValueError("Perfil ou vaga indisponível.")
    skills = await fetch_all("""SELECT h.Nome, ch.Nivel FROM Candidato_Habilidades ch
                              JOIN Habilidades h ON h.ID_Habilidades=ch.ID_Habilidades AND h.Ativo=1
                              WHERE ch.ID_Candidatos=%s""", (candidate_id,))
    required = await fetch_all("""SELECT h.Nome, vh.Peso, vh.Obrigatoria, vh.NivelMinimo FROM Vaga_Habilidades vh
                                JOIN Habilidades h ON h.ID_Habilidades=vh.ID_Habilidades AND h.Ativo=1
                                WHERE vh.ID_Vagas=%s""", (job_id,))
    experiences = await fetch_all("SELECT Cargo, Descricao FROM Experiencias WHERE ID_Candidatos=%s", (candidate_id,))
    education = await fetch_all("SELECT Curso FROM Formacoes WHERE ID_Candidatos=%s", (candidate_id,))
    text = " ".join(str(value or "") for value in [profile.get("TituloProfissional"), profile.get("Resumo"),
                    *(h["Nome"] for h in skills), *(e.get("Cargo") for e in experiences),
                    *(e.get("Descricao") for e in experiences), *(f["Curso"] for f in education)])
    result = await asyncio.to_thread(calculate_match, text, f"{job['Titulo']} {job['Descricao']}", skills, required)
    return profile, job, result


async def recommend_courses(profile, missing):
    if not missing:
        return
    courses = await fetch_all("SELECT * FROM Cursos WHERE Ativo=1")
    for course in courses:
        text = normalize(" ".join(str(course.get(k) or "") for k in ("Titulo", "Descricao", "Categoria")))
        related = [s for s in missing if normalize(s) in text]
        if not related:
            continue
        inserted = await execute("""INSERT IGNORE INTO Recomendacoes_Curso
            (ID_Recomendacoes_Curso, ID_Candidatos, ID_Cursos, ID_Status_Processamento_IA, Motivo, Prioridade)
            VALUES (%s,%s,%s,3,%s,1)""", (novo_uuid(), profile["ID_Candidatos"], course["ID_Cursos"],
                                         "Desenvolver habilidades da vaga: " + ", ".join(related)))
        if inserted:
            await notificar_usuario(profile["ID_Usuarios"], "Curso recomendado", f"Conheça o curso {course['Titulo']}.", "curso")


async def process_next():
    claimed = await claim_job()
    if not claimed:
        return False
    table, key, row = claimed
    try:
        profile, job, result = await match_context(row["ID_Candidatos"], row["ID_Vagas"])
        async with transaction():
            current = await fetch_one(f"SELECT * FROM {table} WHERE {key}=%s FOR UPDATE", (row[key],))
            if current["ID_Status_Processamento_IA"] != 2 or current["ProcessamentoIniciadoEm"] != row["ProcessamentoIniciadoEm"]:
                return True  # outro worker/callback já assumiu ou finalizou
            if table == "Analises_IA":
                await processar_analise_ia(row[key], AnaliseIAResultado(**{k:v for k,v in result.items() if k != "missing_skills"}))
                await recommend_courses(profile, result["missing_skills"])
                await notificar_usuario(profile["ID_Usuarios"], "Compatibilidade analisada", f"Sua análise para {job['Titulo']} está disponível.", "analise")
                # Recomenda a vaga analisada quando publicada, sem sobrescrever histórico.
                if job["ID_Status_Vaga"] == 2:
                    await execute("""INSERT IGNORE INTO Recomendacoes_Vaga
                        (ID_Recomendacoes_Vaga, ID_Candidatos, ID_Vagas, ID_Status_Processamento_IA, Score, Motivo)
                        VALUES (%s,%s,%s,3,%s,%s)""", (novo_uuid(), profile["ID_Candidatos"], job["ID_Vagas"], result["score_compatibilidade"], result["justificativa"]))
            else:
                await processar_recomendacao_vaga(row[key], RecomendacaoVagaResultado(score=result["score_compatibilidade"], motivo=result["justificativa"]))
        logger.info("Análise concluída: %s", row[key])
    except Exception:
        logger.exception("Falha ao processar a análise %s", row[key])
        await execute(f"""UPDATE {table} SET ID_Status_Processamento_IA=4, ErroProcessamento=%s
                         WHERE {key}=%s AND ID_Status_Processamento_IA=2 AND ProcessamentoIniciadoEm=%s""",
                      ("Falha ao processar. Confira se perfil e vaga continuam disponíveis.", row[key], row["ProcessamentoIniciadoEm"]))
    return True


async def main(once):
    if not settings.IA_WORKER_TOKEN:
        raise SystemExit("Configure IA_WORKER_TOKEN antes de iniciar o worker.")
    await init_pool()
    try:
        while True:
            processed = await process_next()
            if once and not processed:
                break
            if not processed:
                await asyncio.sleep(2)
    finally:
        await close_pool()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true", help="Processa a fila existente e termina.")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main(args.once))
