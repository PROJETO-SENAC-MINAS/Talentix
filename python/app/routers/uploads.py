"""
Upload de foto de perfil (Usuario) e logo (Empresa).
"""
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, status

from app.db.database import fetch_one, execute
from app.core.deps import usuario_atual
from app.core.upload import salvar_arquivo

router = APIRouter(prefix="/uploads", tags=["Uploads"])


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