"""Retenção conservadora e anonimização solicitada, nunca executadas em GET."""

import secrets
from datetime import datetime, timezone, timedelta
from app.core.config import settings
from app.core.security import hash_senha
from app.core.upload import remover_arquivo
from app.db.database import fetch_one, fetch_all, execute, transaction, after_commit


async def ultimo_owner(uid):
    companies = await fetch_all(
        """SELECT e.ID_Empresas FROM Empresas e WHERE e.Ativo=1 AND
        (e.ID_Usuarios=%s OR EXISTS(SELECT 1 FROM Org_Membros m WHERE m.ID_Empresas=e.ID_Empresas AND m.ID_Usuarios=%s AND m.Papel='owner' AND m.Ativo=1))""",
        (uid, uid),
    )
    for e in companies:
        await fetch_one(
            "SELECT ID_Empresas FROM Empresas WHERE ID_Empresas=%s FOR UPDATE",
            (e["ID_Empresas"],),
        )
        others = await fetch_one(
            "SELECT ID_Usuarios FROM Org_Membros WHERE ID_Empresas=%s AND ID_Usuarios<>%s AND Papel='owner' AND Ativo=1 LIMIT 1 FOR UPDATE",
            (e["ID_Empresas"], uid),
        )
        if not others:
            return True
    return False


async def processar_solicitacoes():
    rows = await fetch_all(
        "SELECT ID_Solicitacao FROM Privacidade_Solicitacoes WHERE Tipo='exclusao' AND Estado='pendente' AND ExecutarApos<=NOW() ORDER BY ExecutarApos LIMIT 30"
    )
    for item in rows:
        async with transaction():
            row = await fetch_one(
                "SELECT * FROM Privacidade_Solicitacoes WHERE ID_Solicitacao=%s FOR UPDATE",
                (item["ID_Solicitacao"],),
            )
            if row["Estado"] != "pendente":
                continue
            uid = row["ID_Usuarios"]
            if await ultimo_owner(uid):
                await execute(
                    "UPDATE Privacidade_Solicitacoes SET Estado='bloqueado' WHERE ID_Solicitacao=%s",
                    (row["ID_Solicitacao"],),
                )
                continue
            c = await fetch_one(
                "SELECT ID_Candidatos FROM Candidatos WHERE ID_Usuarios=%s FOR UPDATE",
                (uid,),
            )
            u = await fetch_one(
                "SELECT FotoUrl FROM Usuarios WHERE ID_Usuarios=%s FOR UPDATE", (uid,)
            )
            await execute(
                """UPDATE Usuarios SET Nome='Conta excluída',Email=%s,Telefone=NULL,FotoUrl=NULL,SenhaHash=%s,
                Ativo=0,TwoFactorAtivo=0,TwoFactorSecretEnc=NULL WHERE ID_Usuarios=%s""",
                (
                    "excluido-" + uid + "@invalid.example",
                    hash_senha(secrets.token_urlsafe(32)),
                    uid,
                ),
            )
            await execute(
                "UPDATE Sessoes SET RevogadaEm=NOW() WHERE ID_Usuarios=%s AND RevogadaEm IS NULL",
                (uid,),
            )
            await execute(
                "UPDATE Org_Membros SET Ativo=0,Versao=Versao+1 WHERE ID_Usuarios=%s",
                (uid,),
            )
            await execute(
                "UPDATE Recrutadores SET Ativo=0 WHERE ID_Usuarios=%s", (uid,)
            )
            await execute(
                "UPDATE Mensagens SET Conteudo='[conteúdo removido a pedido do remetente]' WHERE ID_Remetente=%s",
                (uid,),
            )
            await execute(
                "UPDATE Outbox_Email SET Corpo='',Estado='ignorado' WHERE ID_Usuarios=%s",
                (uid,),
            )
            await execute('DELETE FROM Push_Assinaturas WHERE ID_Usuarios=%s',(uid,))
            await execute("DELETE FROM Notificacoes WHERE ID_Usuarios=%s", (uid,))
            await execute("DELETE FROM Historico_Buscas WHERE ID_Usuarios=%s", (uid,))
            await execute(
                "UPDATE Buscas_Salvas SET Ativa=0 WHERE ID_Usuarios=%s", (uid,)
            )
            await execute(
                "UPDATE Publico_Avaliacoes SET Comentario='[removido]',Estado='rejeitada' WHERE ID_Usuarios=%s",
                (uid,),
            )
            if c:
                cid = c["ID_Candidatos"]
                await execute(
                    """UPDATE Candidatos SET Ativo=0,Resumo=NULL,TituloProfissional=NULL,Cidade=NULL,Estado=NULL,
                    LinkedinUrl=NULL,GithubUrl=NULL,PortfolioUrl=NULL,Preferencias=NULL,HabilidadesComportamentais=NULL WHERE ID_Candidatos=%s""",
                    (cid,),
                )
                for table in (
                    "Experiencias",
                    "Formacoes",
                    "Candidato_Itens",
                    "Candidato_Habilidades",
                    "Candidato_Idiomas",
                ):
                    await execute(f"DELETE FROM {table} WHERE ID_Candidatos=%s", (cid,))
                await execute(
                    "UPDATE ATS_Consentimentos SET Autorizado=0 WHERE ID_Candidatos=%s",
                    (cid,),
                )
                await execute(
                    "UPDATE ATS_Membros SET Ativo=0,Notas=NULL,Tags='[]',Favorito=0 WHERE ID_Candidatos=%s",
                    (cid,),
                )
                await execute(
                    "UPDATE Curriculos SET Ativo=0,Principal=0,DeletadoEm=NOW() WHERE ID_Candidatos=%s",
                    (cid,),
                )
                await execute(
                    """UPDATE Curriculo_Importacoes SET TextoExtraido=NULL,DadosExtraidos=NULL,DadosConfirmados=NULL
                    WHERE ID_Curriculos IN (SELECT ID_Curriculos FROM Curriculos WHERE ID_Candidatos=%s)""",
                    (cid,),
                )
                await execute(
                    "DELETE FROM IA_Explicacoes WHERE ID_Candidatos=%s", (cid,)
                )
            if u and u["FotoUrl"]:
                shared = await fetch_one(
                    "SELECT ID_Usuarios FROM Usuarios WHERE FotoUrl=%s LIMIT 1",
                    (u["FotoUrl"],),
                )
                if not shared:
                    await after_commit(lambda url=u["FotoUrl"]: remover_arquivo(url))
            await execute(
                "UPDATE Privacidade_Solicitacoes SET Estado='concluido',ConcluidaEm=NOW() WHERE ID_Solicitacao=%s",
                (row["ID_Solicitacao"],),
            )


async def retencao():
    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(
        days=settings.DATA_RETENTION_DAYS
    )
    # Documentos ligados a candidaturas permanecem em retenção: não apagar prova do processo.
    rows = await fetch_all(
        """SELECT cr.ID_Curriculos,cr.ID_Candidatos,cr.ArquivoUrl FROM Curriculos cr WHERE cr.Ativo=0 AND cr.DeletadoEm<=%s
        AND cr.ArquivoUrl<>'' AND NOT EXISTS(SELECT 1 FROM Candidaturas c WHERE c.CurriculoUrl=cr.ArquivoUrl) LIMIT 100""",
        (cutoff,),
    )
    for row in rows:
        async with transaction():
            await fetch_one(
                "SELECT ID_Candidatos FROM Candidatos WHERE ID_Candidatos=%s FOR UPDATE",
                (row["ID_Candidatos"],),
            )
            current = await fetch_one(
                "SELECT Ativo,DeletadoEm FROM Curriculos WHERE ID_Curriculos=%s FOR UPDATE",
                (row["ID_Curriculos"],),
            )
            if not current or current["Ativo"]:
                continue
            await execute(
                "UPDATE Curriculos SET ArquivoUrl='',ArquivoHash=NULL WHERE ID_Curriculos=%s",
                (row["ID_Curriculos"],),
            )
            references = await fetch_one(
                "SELECT ID_Curriculos FROM Curriculos WHERE ArquivoUrl=%s LIMIT 1",
                (row["ArquivoUrl"],),
            )
            if not references:
                await after_commit(lambda url=row["ArquivoUrl"]: remover_arquivo(url))
