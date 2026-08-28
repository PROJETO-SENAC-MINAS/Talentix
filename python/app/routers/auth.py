"""
Autenticação: cadastro de Candidato/Empresa, login, logout, sessão atual.
Login unificado: consulta Usuarios pelo e-mail, verifica a senha com bcrypt,
descobre o tipo (candidato/empresa/administrador) e cria o cookie de sessão.
"""
from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, EmailStr, Field

from app.db.database import fetch_one, execute
from app.core.security import hash_senha, verificar_senha, novo_uuid
from app.core.session import criar_cookie_sessao, destruir_cookie_sessao
from app.core.deps import usuario_atual
from app.core.email_service import email_boas_vindas

router = APIRouter(prefix="/auth", tags=["Autenticação"])


# ---------- Schemas ----------

class CadastroCandidato(BaseModel):
    nome: str
    email: EmailStr
    senha: str = Field(min_length=6)
    telefone: str | None = None


class CadastroEmpresa(BaseModel):
    nome: str
    email: EmailStr
    senha: str = Field(min_length=6)
    telefone: str | None = None
    razao_social: str
    cnpj: str = Field(min_length=14, max_length=18)
    nome_fantasia: str | None = None


class LoginRequest(BaseModel):
    email: EmailStr
    senha: str


# ---------- Helpers internos ----------

async def _descobrir_tipo_usuario(id_usuario: str) -> str:
    if await fetch_one("SELECT ID_Candidatos FROM Candidatos WHERE ID_Usuarios=%s AND Ativo=1", (id_usuario,)):
        return "candidato"
    if await fetch_one("SELECT ID_Empresas FROM Empresas WHERE ID_Usuarios=%s AND Ativo=1", (id_usuario,)):
        return "empresa"
    if await fetch_one("SELECT ID_Administradores FROM Administradores WHERE ID_Usuarios=%s AND Ativo=1", (id_usuario,)):
        return "administrador"
    return "usuario"


# ---------- Endpoints ----------

@router.post("/cadastro/candidato", status_code=status.HTTP_201_CREATED)
async def cadastrar_candidato(dados: CadastroCandidato):
    existente = await fetch_one("SELECT ID_Usuarios FROM Usuarios WHERE Email=%s", (dados.email,))
    if existente:
        raise HTTPException(status.HTTP_409_CONFLICT, "Já existe um usuário com esse e-mail.")

    id_usuario = novo_uuid()
    await execute(
        """INSERT INTO Usuarios (ID_Usuarios, Nome, Email, SenhaHash, Telefone)
           VALUES (%s, %s, %s, %s, %s)""",
        (id_usuario, dados.nome, dados.email, hash_senha(dados.senha), dados.telefone),
    )

    id_candidato = novo_uuid()
    await execute(
        "INSERT INTO Candidatos (ID_Candidatos, ID_Usuarios) VALUES (%s, %s)",
        (id_candidato, id_usuario),
    )

    email_boas_vindas(dados.email, dados.nome)

    return {"id_usuario": id_usuario, "id_candidato": id_candidato, "tipo_usuario": "candidato"}


@router.post("/cadastro/empresa", status_code=status.HTTP_201_CREATED)
async def cadastrar_empresa(dados: CadastroEmpresa):
    existente = await fetch_one("SELECT ID_Usuarios FROM Usuarios WHERE Email=%s", (dados.email,))
    if existente:
        raise HTTPException(status.HTTP_409_CONFLICT, "Já existe um usuário com esse e-mail.")

    cnpj_existente = await fetch_one("SELECT ID_Empresas FROM Empresas WHERE Cnpj=%s", (dados.cnpj,))
    if cnpj_existente:
        raise HTTPException(status.HTTP_409_CONFLICT, "Já existe uma empresa com esse CNPJ.")

    id_usuario = novo_uuid()
    await execute(
        """INSERT INTO Usuarios (ID_Usuarios, Nome, Email, SenhaHash, Telefone)
           VALUES (%s, %s, %s, %s, %s)""",
        (id_usuario, dados.nome, dados.email, hash_senha(dados.senha), dados.telefone),
    )

    id_empresa = novo_uuid()
    await execute(
        """INSERT INTO Empresas (ID_Empresas, ID_Usuarios, RazaoSocial, NomeFantasia, Cnpj)
           VALUES (%s, %s, %s, %s, %s)""",
        (id_empresa, id_usuario, dados.razao_social, dados.nome_fantasia, dados.cnpj),
    )

    email_boas_vindas(dados.email, dados.nome)

    return {"id_usuario": id_usuario, "id_empresa": id_empresa, "tipo_usuario": "empresa"}


@router.post("/login")
async def login(dados: LoginRequest, response: Response):
    usuario = await fetch_one(
        "SELECT ID_Usuarios, SenhaHash, Ativo FROM Usuarios WHERE Email=%s",
        (dados.email,),
    )
    if not usuario or not usuario["Ativo"]:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "E-mail ou senha inválidos.")

    if not verificar_senha(dados.senha, usuario["SenhaHash"]):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "E-mail ou senha inválidos.")

    tipo_usuario = await _descobrir_tipo_usuario(usuario["ID_Usuarios"])
    criar_cookie_sessao(response, usuario["ID_Usuarios"], tipo_usuario)

    return {"id_usuario": usuario["ID_Usuarios"], "tipo_usuario": tipo_usuario}


@router.post("/logout")
async def logout(response: Response):
    destruir_cookie_sessao(response)
    return {"mensagem": "Logout realizado com sucesso."}


@router.get("/me")
async def me(sessao: dict = Depends(usuario_atual)):
    usuario = await fetch_one(
        "SELECT ID_Usuarios, Nome, Email, Telefone, FotoUrl, Ativo, CriadoEm FROM Usuarios WHERE ID_Usuarios=%s",
        (sessao["id_usuario"],),
    )
    if not usuario:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Usuário não encontrado.")
    return {**usuario, "tipo_usuario": sessao["tipo_usuario"]}