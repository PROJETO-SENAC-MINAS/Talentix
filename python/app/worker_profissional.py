"""Fila durável de currículos e alertas: python -m app.worker_profissional [--once]."""
import argparse
import asyncio
import json
import logging
from app.db.database import init_pool, close_pool, transaction, fetch_one, fetch_all, execute
from app.core.notificar import notificar_usuario
from app.core.email_service import email_alerta_busca
from app.routers.curriculo import _processar_importacao
from app.routers.busca import FiltrosBusca, predicado

logger = logging.getLogger(__name__)


async def processar_curriculo():
    async with transaction():
        row = await fetch_one("""SELECT ci.*, c.ArquivoUrl FROM Curriculo_Importacoes ci
            JOIN Curriculos c ON c.ID_Curriculos=ci.ID_Curriculos AND c.Ativo=1
            JOIN Candidatos p ON p.ID_Candidatos=c.ID_Candidatos AND p.Ativo=1
            JOIN Usuarios u ON u.ID_Usuarios=p.ID_Usuarios AND u.Ativo=1
            WHERE ci.ID_Status_Processamento_IA=1 OR (ci.ID_Status_Processamento_IA=2
              AND ci.ProcessamentoIniciadoEm < DATE_SUB(NOW(), INTERVAL 10 MINUTE))
            ORDER BY ci.CriadoEm LIMIT 1 FOR UPDATE SKIP LOCKED""")
        if not row:
            return False
        await execute("UPDATE Curriculo_Importacoes SET ID_Status_Processamento_IA=2,ProcessamentoIniciadoEm=NOW(),ErroProcessamento=NULL WHERE ID_Curriculos=%s", (row["ID_Curriculos"],))
        row.update(await fetch_one("SELECT ProcessamentoIniciadoEm FROM Curriculo_Importacoes WHERE ID_Curriculos=%s", (row["ID_Curriculos"],)))
    await _processar_importacao(row)
    return True


async def processar_alertas(after=""):
    rows = await fetch_all("""SELECT b.* FROM Buscas_Salvas b JOIN Usuarios u ON u.ID_Usuarios=b.ID_Usuarios AND u.Ativo=1
        JOIN Candidatos c ON c.ID_Usuarios=u.ID_Usuarios AND c.Ativo=1
        WHERE b.Ativa=1 AND b.ID_Busca>%s ORDER BY b.ID_Busca LIMIT 50""", (after,))
    for saved in rows:
        f = FiltrosBusca.model_validate(json.loads(saved["Filtros"]) if isinstance(saved["Filtros"], (bytes, str)) else saved["Filtros"])
        where, args = predicado(f)
        jobs = await fetch_all("""SELECT v.ID_Vagas,v.Titulo FROM Vagas v JOIN Empresas e ON e.ID_Empresas=v.ID_Empresas
            WHERE """ + where + """ AND v.PublicadaEm>%s AND NOT EXISTS (SELECT 1 FROM Alertas_Busca a
            WHERE a.ID_Busca=%s AND a.ID_Vagas=v.ID_Vagas) ORDER BY v.PublicadaEm LIMIT 10""",
            tuple(args + [saved["CriadoEm"], saved["ID_Busca"]]))
        for job in jobs:
            async with transaction():
                current = await fetch_one("SELECT * FROM Buscas_Salvas WHERE ID_Busca=%s FOR UPDATE", (saved["ID_Busca"],))
                if not current or not current["Ativa"] or current["Filtros"] != saved["Filtros"]:
                    break
                live = await fetch_one("""SELECT v.ID_Vagas FROM Vagas v JOIN Empresas e ON e.ID_Empresas=v.ID_Empresas
                    WHERE v.ID_Vagas=%s AND v.Ativo=1 AND v.ID_Status_Vaga=2 AND e.Ativo=1 FOR UPDATE""", (job["ID_Vagas"],))
                sent = await fetch_one("SELECT ID_Vagas FROM Alertas_Busca WHERE ID_Busca=%s AND ID_Vagas=%s", (saved["ID_Busca"], job["ID_Vagas"]))
                if live and not sent:
                    await execute("INSERT INTO Alertas_Busca(ID_Busca,ID_Vagas) VALUES (%s,%s)", (saved["ID_Busca"], job["ID_Vagas"]))
                    verified = await fetch_one("SELECT EmailConfirmadoEm FROM Usuarios WHERE ID_Usuarios=%s AND Ativo=1", (saved["ID_Usuarios"],))
                    email_fn = (lambda email, nome=saved["Nome"], titulo=job["Titulo"]: email_alerta_busca(email, nome, titulo)) if verified and verified["EmailConfirmadoEm"] else None
                    await notificar_usuario(saved["ID_Usuarios"], "Nova vaga na busca " + saved["Nome"], job["Titulo"], "vaga", enviar_email_fn=email_fn)
    return rows[-1]["ID_Busca"] if len(rows) == 50 else ""


async def main(once=False):
    await init_pool()
    cursor = ""
    try:
        while True:
            try:
                processed = await processar_curriculo()
                cursor = await processar_alertas(cursor)
            except Exception:
                logger.exception("Falha no worker profissional; a fila será retomada.")
                if once:
                    raise
                processed = False
            if once and not processed and not cursor:
                break
            if not processed:
                await asyncio.sleep(5)
    finally:
        await close_pool()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true")
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main(parser.parse_args().once))
