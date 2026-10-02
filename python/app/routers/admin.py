"""Operações administrativas de usuários, empresas e auditoria da plataforma."""
from app.core.routes import AtomicRouter as APIRouter
from fastapi import Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, EmailStr, Field

from app.core.audit import registrar_auditoria
from app.core.deps import exigir_tipo
from app.db.database import execute, fetch_all, fetch_one

router = APIRouter(prefix="/admin", tags=["Administração"])


class UsuarioAdminUpdate(BaseModel):
    nome: str | None = Field(default=None, min_length=1, max_length=150)
    email: EmailStr | None = None
    telefone: str | None = Field(default=None, max_length=20)


class StatusAtivoUpdate(BaseModel):
    ativo: bool


class EmpresaAdminUpdate(BaseModel):
    razao_social: str | None = Field(default=None, min_length=1, max_length=200)
    nome_fantasia: str | None = Field(default=None, max_length=200)
    cnpj: str | None = Field(default=None, min_length=14, max_length=18)
    descricao: str | None = Field(default=None, max_length=5000)
    setor: str | None = Field(default=None, max_length=100)
    porte: str | None = Field(default=None, max_length=50)
    site_url: str | None = Field(default=None, max_length=300)
    endereco: str | None = Field(default=None, max_length=300)
    verificada: bool | None = None


def _perfis_usuario(row: dict) -> str:
    perfis = []
    if row.pop("ID_Administradores", None):
        perfis.append("Administrador")
    if row.pop("ID_Empresas", None):
        perfis.append("Empresa")
    if row.pop("ID_Recrutadores", None):
        perfis.append("Recrutador")
    if row.pop("ID_Candidatos", None):
        perfis.append("Candidato")
    return ", ".join(perfis) or "Usuário"


@router.get("/usuarios")
async def listar_usuarios_admin(
    incluir_inativos: bool = True,
    sessao: dict = Depends(exigir_tipo("administrador")),
):
    filtro = "" if incluir_inativos else "WHERE u.Ativo=1"
    registros = await fetch_all(
        f"""SELECT u.ID_Usuarios, u.Nome, u.Email, u.Telefone, u.Ativo, u.CriadoEm, u.AtualizadoEm,
                   c.ID_Candidatos, e.ID_Empresas, a.ID_Administradores, r.ID_Recrutadores
            FROM Usuarios u
            LEFT JOIN Candidatos c ON c.ID_Usuarios=u.ID_Usuarios
            LEFT JOIN Empresas e ON e.ID_Usuarios=u.ID_Usuarios
            LEFT JOIN Administradores a ON a.ID_Usuarios=u.ID_Usuarios
            LEFT JOIN Recrutadores r ON r.ID_Usuarios=u.ID_Usuarios
            {filtro}
            ORDER BY u.CriadoEm DESC"""
    )
    for registro in registros:
        registro["Perfis"] = _perfis_usuario(registro)
        registro["EhUsuarioAtual"] = registro["ID_Usuarios"] == sessao["id_usuario"]
    return registros


@router.put("/usuarios/{id_usuario}")
async def editar_usuario_admin(
    id_usuario: str,
    dados: UsuarioAdminUpdate,
    request: Request,
    sessao: dict = Depends(exigir_tipo("administrador")),
):
    usuario = await fetch_one(
        "SELECT ID_Usuarios, Nome, Email, Telefone, Ativo FROM Usuarios WHERE ID_Usuarios=%s", (id_usuario,)
    )
    if not usuario:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Usuário não encontrado.")

    campos = dados.model_dump(exclude_unset=True)
    if not campos:
        return await fetch_one(
            "SELECT ID_Usuarios, Nome, Email, Telefone, Ativo, CriadoEm, AtualizadoEm FROM Usuarios WHERE ID_Usuarios=%s",
            (id_usuario,),
        )

    mapa = {"nome": "Nome", "email": "Email", "telefone": "Telefone"}
    set_clauses = [f"{mapa[campo]}=%s" for campo in campos]
    valores = list(campos.values()) + [id_usuario]
    await execute(
        f"UPDATE Usuarios SET {', '.join(set_clauses)} WHERE ID_Usuarios=%s",
        tuple(valores),
    )
    atualizado = await fetch_one(
        "SELECT ID_Usuarios, Nome, Email, Telefone, Ativo, CriadoEm, AtualizadoEm FROM Usuarios WHERE ID_Usuarios=%s",
        (id_usuario,),
    )
    await registrar_auditoria(request, "ADMIN_USUARIO_EDITADO", "Usuarios", sessao["id_usuario"], id_usuario, usuario, atualizado)
    return atualizado
    # retorno abaixo mantido inalcançável por compatibilidade de diff
    return await fetch_one(
        "SELECT ID_Usuarios, Nome, Email, Telefone, Ativo, CriadoEm, AtualizadoEm FROM Usuarios WHERE ID_Usuarios=%s",
        (id_usuario,),
    )


@router.patch("/usuarios/{id_usuario}/status")
async def alterar_status_usuario_admin(
    id_usuario: str,
    dados: StatusAtivoUpdate,
    request: Request,
    sessao: dict = Depends(exigir_tipo("administrador")),
):
    if id_usuario == sessao["id_usuario"] and not dados.ativo:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Você não pode desativar sua própria conta administrativa.")
    if not await fetch_one("SELECT ID_Usuarios FROM Usuarios WHERE ID_Usuarios=%s", (id_usuario,)):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Usuário não encontrado.")

    ativo = 1 if dados.ativo else 0
    await execute(
        "UPDATE Usuarios SET Ativo=%s, DeletadoEm=IF(%s=1,NULL,NOW()) WHERE ID_Usuarios=%s",
        (ativo, ativo, id_usuario),
    )
    for tabela in ("Candidatos", "Empresas", "Administradores", "Recrutadores"):
        await execute(
            f"UPDATE {tabela} SET Ativo=%s, DeletadoEm=IF(%s=1,NULL,NOW()) WHERE ID_Usuarios=%s",
            (ativo, ativo, id_usuario),
        )
    await registrar_auditoria(request, "ADMIN_USUARIO_STATUS", "Usuarios", sessao["id_usuario"], id_usuario, novo={"ativo": dados.ativo})
    return {"mensagem": "Usuário ativado." if dados.ativo else "Usuário desativado."}


@router.delete("/usuarios/{id_usuario}")
async def excluir_usuario_admin(
    id_usuario: str,
    request: Request,
    confirmar: bool = Query(False),
    sessao: dict = Depends(exigir_tipo("administrador")),
):
    if not confirmar:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Confirmação obrigatória para exclusão permanente.")
    if id_usuario == sessao["id_usuario"]:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Você não pode excluir sua própria conta administrativa.")
    if not await fetch_one("SELECT ID_Usuarios FROM Usuarios WHERE ID_Usuarios=%s", (id_usuario,)):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Usuário não encontrado.")
    await registrar_auditoria(request, "ADMIN_USUARIO_EXCLUIDO", "Usuarios", sessao["id_usuario"], id_usuario)
    await execute("DELETE FROM Usuarios WHERE ID_Usuarios=%s", (id_usuario,))
    return {"mensagem": "Usuário excluído permanentemente."}


@router.get("/empresas")
async def listar_empresas_admin(
    incluir_inativas: bool = True,
    sessao: dict = Depends(exigir_tipo("administrador")),
):
    filtro = "" if incluir_inativas else "AND e.Ativo=1"
    return await fetch_all(
        f"""SELECT e.ID_Empresas, e.ID_Usuarios, e.RazaoSocial, e.NomeFantasia, e.Cnpj,
                   e.Descricao, e.Setor, e.Porte, e.SiteUrl, e.Endereco, e.Verificada,
                   e.Ativo, e.CriadoEm, e.AtualizadoEm,
                   u.Nome AS NomeResponsavel, u.Email AS EmailResponsavel, u.Telefone AS TelefoneResponsavel,
                   (SELECT COUNT(*) FROM Recrutadores r
                    WHERE r.ID_Empresas=e.ID_Empresas AND r.Ativo=1) AS FuncionariosCadastrados,
                   (SELECT COUNT(*) FROM Vagas v
                    WHERE v.ID_Empresas=e.ID_Empresas AND v.Ativo=1) AS VagasAtivas
            FROM Empresas e
            JOIN Usuarios u ON u.ID_Usuarios=e.ID_Usuarios
            WHERE 1=1 {filtro}
            ORDER BY e.CriadoEm DESC"""
    )


@router.put("/empresas/{id_empresa}")
async def editar_empresa_admin(
    id_empresa: str,
    dados: EmpresaAdminUpdate,
    request: Request,
    sessao: dict = Depends(exigir_tipo("administrador")),
):
    empresa = await fetch_one("SELECT * FROM Empresas WHERE ID_Empresas=%s", (id_empresa,))
    if not empresa:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Empresa não encontrada.")
    campos = dados.model_dump(exclude_unset=True)
    if not campos:
        return await fetch_one("SELECT * FROM Empresas WHERE ID_Empresas=%s", (id_empresa,))

    mapa = {
        "razao_social": "RazaoSocial", "nome_fantasia": "NomeFantasia", "cnpj": "Cnpj",
        "descricao": "Descricao", "setor": "Setor", "porte": "Porte", "site_url": "SiteUrl",
        "endereco": "Endereco", "verificada": "Verificada",
    }
    set_clauses = [f"{mapa[campo]}=%s" for campo in campos]
    valores = list(campos.values()) + [id_empresa]
    await execute(
        f"UPDATE Empresas SET {', '.join(set_clauses)} WHERE ID_Empresas=%s",
        tuple(valores),
    )
    atualizada = await fetch_one("SELECT * FROM Empresas WHERE ID_Empresas=%s", (id_empresa,))
    await registrar_auditoria(request, "ADMIN_EMPRESA_EDITADA", "Empresas", sessao["id_usuario"], id_empresa, empresa, atualizada)
    return atualizada


@router.patch("/empresas/{id_empresa}/status")
async def alterar_status_empresa_admin(
    id_empresa: str,
    dados: StatusAtivoUpdate,
    request: Request,
    sessao: dict = Depends(exigir_tipo("administrador")),
):
    if not await fetch_one("SELECT ID_Empresas FROM Empresas WHERE ID_Empresas=%s", (id_empresa,)):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Empresa não encontrada.")
    ativo = 1 if dados.ativo else 0
    await execute(
        "UPDATE Empresas SET Ativo=%s, DeletadoEm=IF(%s=1,NULL,NOW()) WHERE ID_Empresas=%s",
        (ativo, ativo, id_empresa),
    )
    await registrar_auditoria(request, "ADMIN_EMPRESA_STATUS", "Empresas", sessao["id_usuario"], id_empresa, novo={"ativo": dados.ativo})
    return {"mensagem": "Empresa ativada." if dados.ativo else "Empresa desativada."}


@router.delete("/empresas/{id_empresa}")
async def excluir_empresa_admin(
    id_empresa: str,
    request: Request,
    confirmar: bool = Query(False),
    sessao: dict = Depends(exigir_tipo("administrador")),
):
    if not confirmar:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Confirmação obrigatória para exclusão permanente.")
    if not await fetch_one("SELECT ID_Empresas FROM Empresas WHERE ID_Empresas=%s", (id_empresa,)):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Empresa não encontrada.")
    await registrar_auditoria(request, "ADMIN_EMPRESA_EXCLUIDA", "Empresas", sessao["id_usuario"], id_empresa)
    await execute("DELETE FROM Empresas WHERE ID_Empresas=%s", (id_empresa,))
    return {"mensagem": "Empresa excluída permanentemente."}


@router.get("/auditoria")
async def listar_auditoria_admin(
    limite: int = Query(200, ge=1, le=500),
    sessao: dict = Depends(exigir_tipo("administrador")),
):
    return await fetch_all(
        """SELECT a.ID_Audit_Logs, a.ID_Usuarios, a.Acao, a.Recurso, a.RecursoId,
                  a.RequestId, a.UserAgent, a.ValorAnterior, a.ValorNovo, a.CriadoEm,
                  u.Nome AS UsuarioNome, u.Email AS UsuarioEmail
           FROM Audit_Logs a
           LEFT JOIN Usuarios u ON u.ID_Usuarios=a.ID_Usuarios
           ORDER BY a.CriadoEm DESC LIMIT %s""",
        (limite,),
    )


@router.get("/denuncias")
async def listar_denuncias_admin(sessao: dict = Depends(exigir_tipo("administrador"))):
    return await fetch_all(
        """SELECT d.ID_Denuncias, d.ID_Denunciante, d.ID_Usuario_Alvo, d.ID_Vagas,
                  d.ID_Status_Denuncia, d.Motivo, d.Descricao, d.CriadaEm, d.ResolvidaEm,
                  s.Codigo AS StatusCodigo, s.Descricao AS StatusDescricao,
                  denunciante.Nome AS DenuncianteNome, denunciante.Email AS DenuncianteEmail,
                  alvo.Nome AS AlvoNome, alvo.Email AS AlvoEmail,
                  v.Titulo AS VagaTitulo,
                  admin_usuario.Nome AS AdministradorNome
           FROM Denuncias d
           JOIN Status_Denuncia s ON s.ID_Status_Denuncia=d.ID_Status_Denuncia
           JOIN Usuarios denunciante ON denunciante.ID_Usuarios=d.ID_Denunciante
           LEFT JOIN Usuarios alvo ON alvo.ID_Usuarios=d.ID_Usuario_Alvo
           LEFT JOIN Vagas v ON v.ID_Vagas=d.ID_Vagas
           LEFT JOIN Administradores a ON a.ID_Administradores=d.ID_Administradores
           LEFT JOIN Usuarios admin_usuario ON admin_usuario.ID_Usuarios=a.ID_Usuarios
           ORDER BY d.CriadaEm DESC"""
    )


@router.get("/notificacoes")
async def listar_notificacoes_admin(
    limite: int = Query(200, ge=1, le=500),
    sessao: dict = Depends(exigir_tipo("administrador")),
):
    return await fetch_all(
        """SELECT n.ID_Notificacoes, n.ID_Usuarios, n.Titulo, n.Mensagem, n.Tipo, n.Lida, n.CriadaEm,
                  u.Nome AS UsuarioNome, u.Email AS UsuarioEmail
           FROM Notificacoes n
           JOIN Usuarios u ON u.ID_Usuarios=n.ID_Usuarios
           ORDER BY n.CriadaEm DESC LIMIT %s""",
        (limite,),
    )


@router.get("/mensagens")
async def listar_mensagens_admin(
    limite: int = Query(200, ge=1, le=500),
    sessao: dict = Depends(exigir_tipo("administrador")),
):
    return await fetch_all(
        """SELECT m.ID_Mensagens, m.ID_Remetente, m.ID_Destinatario, m.ID_Candidaturas,
                  m.Conteudo, m.Lida, m.EnviadaEm,
                  remetente.Nome AS RemetenteNome, remetente.Email AS RemetenteEmail,
                  destinatario.Nome AS DestinatarioNome, destinatario.Email AS DestinatarioEmail
           FROM Mensagens m
           JOIN Usuarios remetente ON remetente.ID_Usuarios=m.ID_Remetente
           JOIN Usuarios destinatario ON destinatario.ID_Usuarios=m.ID_Destinatario
           ORDER BY m.EnviadaEm DESC LIMIT %s""",
        (limite,),
    )
