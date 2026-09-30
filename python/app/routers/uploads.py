"""
Upload de foto de perfil (Usuario) e logo (Empresa).
"""
from app.core.routes import AtomicRouter as APIRouter

from fastapi import Depends, UploadFile, File, HTTPException, status
from fastapi.responses import FileResponse
from pathlib import Path
import re

from app.db.database import fetch_one, execute
from app.core.deps import usuario_atual
from app.core.access import empresa_da_sessao
from app.core.upload import salvar_arquivo
from app.core.config import settings

router = APIRouter(prefix="/uploads", tags=["Uploads"])


@router.get("/curriculos/{nome_arquivo}")
async def baixar_curriculo(nome_arquivo: str, sessao: dict = Depends(usuario_atual)):
    if not re.fullmatch(r"[a-f0-9]{64}\.(pdf|doc|docx)", nome_arquivo):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Currículo não encontrado.")

    url = f"/uploads/curriculos/{nome_arquivo}"
    if sessao["tipo_usuario"] == "administrador":
        curriculo = await fetch_one(
            "SELECT ID_Curriculos FROM Curriculos WHERE ArquivoUrl=%s AND Ativo=1 LIMIT 1", (url,)
        )
    elif sessao["tipo_usuario"] == "candidato":
        curriculo = await fetch_one(
            """SELECT cr.ID_Curriculos FROM Curriculos cr
               JOIN Candidatos c ON c.ID_Candidatos=cr.ID_Candidatos AND c.Ativo=1
               WHERE cr.ArquivoUrl=%s AND cr.Ativo=1 AND c.ID_Usuarios=%s LIMIT 1""",
            (url, sessao["id_usuario"]),
        )
    elif sessao["tipo_usuario"] in {"empresa", "recrutador"}:
        empresa = await empresa_da_sessao(sessao)
        # Acesso somente ao arquivo que o candidato anexou à candidatura desta empresa.
        curriculo = await fetch_one(
            """SELECT cr.ID_Curriculos FROM Curriculos cr
               JOIN Candidaturas ca ON ca.ID_Candidatos=cr.ID_Candidatos
                 AND ca.CurriculoUrl=cr.ArquivoUrl AND ca.Ativo=1
               JOIN Vagas v ON v.ID_Vagas=ca.ID_Vagas
               JOIN Empresas e ON e.ID_Empresas=v.ID_Empresas AND e.Ativo=1
               WHERE cr.ArquivoUrl=%s AND cr.Ativo=1 AND e.ID_Empresas=%s LIMIT 1""",
            (url, empresa["ID_Empresas"]),
        )
    else:
        curriculo = None

    # Mesmo 404 para inexistência e falta de acesso: não revelar arquivos de terceiros.
    caminho = Path(settings.UPLOAD_DIR) / "curriculos" / nome_arquivo
    if not curriculo or not caminho.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Currículo não encontrado.")
    return FileResponse(
        caminho,
        filename=nome_arquivo,
        headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"},
    )


@router.post("/foto-perfil")
async def enviar_foto_perfil(arquivo: UploadFile = File(...), sessao: dict = Depends(usuario_atual)):
    info = await salvar_arquivo(arquivo, "fotos")
    await execute(
        """UPDATE Usuarios SET FotoUrl=%s, FotoTamanhoBytes=%s, FotoTipoMime=%s, FotoHash=%s
           WHERE ID_Usuarios=%s""",
        (info["url"], info["tamanho_bytes"], info["tipo_mime"], info["hash"], sessao["id_usuario"]),
    )
    return info


@router.post("/logo-empresa/{id_empresa}")
async def enviar_logo_empresa(
    id_empresa: str, arquivo: UploadFile = File(...), sessao: dict = Depends(usuario_atual)
):
    empresa = await fetch_one("SELECT * FROM Empresas WHERE ID_Empresas=%s", (id_empresa,))
    if not empresa:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Empresa não encontrada.")
    if empresa["ID_Usuarios"] != sessao["id_usuario"] and sessao["tipo_usuario"] != "administrador":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Sem permissão sobre esta empresa.")

    info = await salvar_arquivo(arquivo, "logos")
    await execute(
        """UPDATE Empresas SET LogoUrl=%s, LogoTamanhoBytes=%s, LogoTipoMime=%s, LogoHash=%s
           WHERE ID_Empresas=%s""",
        (info["url"], info["tamanho_bytes"], info["tipo_mime"], info["hash"], id_empresa),
    )
    return info
