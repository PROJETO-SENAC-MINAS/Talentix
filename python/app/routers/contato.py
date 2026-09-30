"""Contato persistido e caixa de entrada restrita à administração."""
from app.core.routes import AtomicRouter as APIRouter
from fastapi import Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field
from app.core.deps import exigir_tipo
from app.core.security import novo_uuid
from app.db.database import execute, fetch_all, fetch_one

router = APIRouter(prefix="/contato", tags=["Contato"])


async def garantir_schema_contato() -> None:
    """Garante a tabela de contatos em instalações locais ainda sem a migration 001."""
    await execute(
        """CREATE TABLE IF NOT EXISTS Contatos (
               ID_Contatos CHAR(36) NOT NULL PRIMARY KEY,
               Nome VARCHAR(150) NOT NULL,
               Email VARCHAR(150) NOT NULL,
               Assunto VARCHAR(100) NOT NULL,
               Mensagem TEXT NOT NULL,
               Lido BOOLEAN NOT NULL DEFAULT FALSE,
               CriadoEm DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
           ) ENGINE=InnoDB CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"""
    )


class ContatoCreate(BaseModel):
    nome: str = Field(min_length=3, max_length=150)
    email: EmailStr = Field(max_length=150)
    assunto: str = Field(min_length=1, max_length=100)
    mensagem: str = Field(min_length=10, max_length=5000)


@router.post("", status_code=201)
async def enviar_contato(dados: ContatoCreate):
    id_contato = novo_uuid()
    await execute("""INSERT INTO Contatos (ID_Contatos, Nome, Email, Assunto, Mensagem)
                     VALUES (%s, %s, %s, %s, %s)""",
                  (id_contato, dados.nome, dados.email, dados.assunto, dados.mensagem))
    return {"id_contato": id_contato, "mensagem": "Mensagem recebida pela equipe Talentix."}


@router.get("")
async def listar_contatos(sessao: dict = Depends(exigir_tipo("administrador"))):
    return await fetch_all("SELECT * FROM Contatos ORDER BY CriadoEm DESC")


@router.patch("/{id_contato}/marcar-lido")
async def marcar_contato_lido(id_contato: str, sessao: dict = Depends(exigir_tipo("administrador"))):
    if not await fetch_one("SELECT ID_Contatos FROM Contatos WHERE ID_Contatos=%s", (id_contato,)):
        raise HTTPException(404, "Contato não encontrado.")
    await execute("UPDATE Contatos SET Lido=1 WHERE ID_Contatos=%s", (id_contato,))
    return {"mensagem": "Contato marcado como lido."}
